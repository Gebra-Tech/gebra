"""D-12-PROMOTION.md pinned to the promotion it records (card CLI-08).

A promotion record's whole weight is that it is true about a file tree, and prose cannot
hold itself to one. So this module reads the record and cross-checks it:

* the F3 trigger it cites is two freeze records that exist and that name this card back;
* every repository path it cites exists;
* the artifact table's four document rows are files on disk, and the three it calls
  **final** actually carry a final stamp naming CLI-08 — a stamp claimed here and absent
  there is the failure mode the record is most exposed to;
* **every** open item in both stamped specs' Appendix B is dispositioned in §5, in both
  directions: an item the specs carry and the record forgets is an obligation dropped
  ("closes or re-routes every open item", CLI-SPEC §7), and an item the record invents is a
  disposition of nothing;
* the scoping sentences that keep this a governance claim rather than a verification one
  stay on the page.

Nothing here imports langgraph, executes anything, or opens a socket (WA-07): the module
reads markdown files and compares strings.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Final

import pytest
import yaml

#: ``tests/docs/`` → the repository root.
REPO_ROOT: Final = Path(__file__).resolve().parents[2]

#: The development-process repository, when it is checked out beside this one. The record
#: cites the vendored brief and the plan's advisory sequencing, which live there.
COMPANION: Final = REPO_ROOT.parent / "gebra-dev-doc"

#: Path prefixes that resolve against :data:`COMPANION` rather than this repository.
COMPANION_TREES: Final = ("docs/briefs/", "docs/plan/")

RECORD_PATH: Final = REPO_ROOT / "docs" / "governance" / "D-12-PROMOTION.md"
IR_FREEZE_PATH: Final = REPO_ROOT / "docs" / "governance" / "IR-MODELS-FREEZE.md"
VAL_FREEZE_PATH: Final = REPO_ROOT / "docs" / "governance" / "VALIDATOR-API-FREEZE.md"

SPECS_DIR: Final = REPO_ROOT / "docs" / "specs"

#: The three repo-authored contract specifications the promotion stamps final.
STAMPED_SPECS: Final = (
    "CLI-SPEC.md",
    "REPORT-FORMAT-SPEC.md",
    "DIAGRAM-STYLE-GUIDE.md",
)

#: The two whose Appendix B the record must disposition item by item.
SPECS_WITH_OPEN_ITEMS: Final = ("CLI-SPEC.md", "REPORT-FORMAT-SPEC.md")

#: The four decision records brief D-12's open questions were ruled by.
OPEN_QUESTION_RULINGS: Final = {
    "OQ-12-01": "PD-015",
    "OQ-12-02": "PD-034",
    "OQ-12-03": "PD-031",
    "OQ-12-04": "PD-033",
}

_OPEN_ITEM = re.compile(r"\bOI-(\d+)\b")


@pytest.fixture(scope="module")
def record_text() -> str:
    return RECORD_PATH.read_text(encoding="utf-8")


def _appendix_b(spec_name: str) -> str:
    """The Appendix B body of ``spec_name``, up to the next same-level heading."""
    lines = (SPECS_DIR / spec_name).read_text(encoding="utf-8").splitlines()
    start = next(
        (index for index, line in enumerate(lines) if line.startswith("## Appendix B")),
        None,
    )
    assert start is not None, f"{spec_name} carries no Appendix B"
    for offset, line in enumerate(lines[start + 1 :], start=start + 1):
        if line.startswith("## "):
            return "\n".join(lines[start + 1 : offset])
    return "\n".join(lines[start + 1 :])


def _open_item_ids(section: str) -> set[str]:
    """The ids of the rows in an open-item table — read off the head of each first cell.

    The specs spell the first cell as the bare id; this record spells it as the id plus a
    one-line restatement of the item, so the match is anchored rather than exact.
    """
    ids: set[str] = set()
    for line in section.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        first = stripped.strip("|").split("|")[0].strip().lstrip("~")
        match = _OPEN_ITEM.match(first)
        if match is not None:
            ids.add(match.group(0))
    return ids


def _flat(text: str) -> str:
    """``text`` with runs of whitespace collapsed — for prose assertions that wrap."""
    return " ".join(text.split())


def _section(text: str, heading: str) -> str:
    """The body under ``heading``, up to the next heading of the same or a higher level."""
    level = len(heading) - len(heading.lstrip("#"))
    lines = text.splitlines()
    try:
        start = lines.index(heading)
    except ValueError:  # pragma: no cover - the failure message below is the useful one
        pytest.fail(f"{RECORD_PATH.name} carries no heading {heading!r}")
    for offset, line in enumerate(lines[start + 1 :], start=start + 1):
        stripped = line.rstrip()
        if stripped.startswith("#") and len(stripped) - len(stripped.lstrip("#")) <= level:
            return "\n".join(lines[start + 1 : offset])
    return "\n".join(lines[start + 1 :])


# ── the record exists and says what it is ───────────────────────────────────────────────


def test_the_record_exists_and_states_the_promotion(record_text: str) -> None:
    assert RECORD_PATH.is_file()
    assert "PROMOTED" in record_text
    assert "CLI-08" in record_text


def test_the_record_is_repository_internal_not_a_published_page(record_text: str) -> None:
    """`docs/governance/` is excluded from the site by name; an edit that published the
    tree would put a governance record among the user documentation."""
    del record_text
    config: dict[str, Any] = yaml.safe_load((REPO_ROOT / "mkdocs.yml").read_text(encoding="utf-8"))
    excluded = {line.strip() for line in config["exclude_docs"].splitlines() if line.strip()}
    assert "governance/" in excluded
    assert RECORD_PATH.parent.name == "governance"


def test_the_f3_trigger_names_two_freeze_records_that_exist(record_text: str) -> None:
    """The card's prereqs are IR-06 and VAL-12; the record must cite both, not one."""
    assert "F3" in record_text
    for path in (IR_FREEZE_PATH, VAL_FREEZE_PATH):
        assert path.is_file(), f"the record cites {path.name}, which does not exist"
        assert path.name in record_text
    for card in ("IR-06", "VAL-12", "CLI-02"):
        assert card in record_text, f"the record does not cite prereq {card}"


def test_the_freeze_records_still_point_back_at_this_card(record_text: str) -> None:
    """Both freezes deferred the format stamp to CLI-08 by name; that link is two-way."""
    del record_text
    for path in (IR_FREEZE_PATH, VAL_FREEZE_PATH):
        text = path.read_text(encoding="utf-8")
        assert "CLI-08" in text, f"{path.name} no longer names the card its trigger arms"


def test_every_cited_repository_path_exists(record_text: str) -> None:
    """A pointer to a moved or deleted file would hollow the record silently."""
    cited = {
        match.group(1)
        for match in re.finditer(r"`((?:tests|src|docs|tools)/[A-Za-z0-9_./-]+)`", record_text)
    }
    assert cited, "the record cites no repository paths at all"
    checked = 0
    for path in sorted(cited):
        if path.startswith(COMPANION_TREES):
            # The vendored brief and the plan live in the development-process repository;
            # check them where they are, and only when it is checked out beside this one.
            if COMPANION.is_dir():
                assert (COMPANION / path).exists(), f"the record cites {path}, which is absent"
                checked += 1
            continue
        assert (REPO_ROOT / path).exists(), f"the record cites {path}, which does not exist"
        checked += 1
    assert checked, "no cited path was checked at all"


# ── §3: the artifact table is true about the tree ───────────────────────────────────────


def test_the_stamped_specs_exist_and_carry_the_stamp(record_text: str) -> None:
    """A record that calls a document final while the document does not is the live risk."""
    for name in STAMPED_SPECS:
        path = SPECS_DIR / name
        assert path.is_file(), f"the record's artifact table names {name}, which is absent"
        assert name in record_text, f"the artifact table omits {name}"
        spec_text = path.read_text(encoding="utf-8")
        head = "\n".join(spec_text.splitlines()[:40])
        assert "FINAL" in head, f"{name} carries no final stamp in its status block"
        assert "CLI-08" in head, f"{name}'s stamp does not name the card that made it"
        assert "D-12-PROMOTION.md" in spec_text, f"{name} does not point back at the record"


def test_the_extension_outline_exists_and_is_named_phase_1(record_text: str) -> None:
    outline = SPECS_DIR / "EXTENSION-SPEC.md"
    assert outline.is_file()
    assert "EXTENSION-SPEC.md" in record_text
    row = next(
        line for line in record_text.splitlines() if line.startswith("| `EXTENSION-SPEC.md`")
    )
    assert "outline" in row.lower() and "Phase-1" in row


def test_the_report_format_version_the_record_stamps_is_the_one_the_spec_fixes(
    record_text: str,
) -> None:
    """`1.1` is stamped in two documents; they may not drift apart."""
    assert "`1.1`" in record_text
    spec_text = (SPECS_DIR / "REPORT-FORMAT-SPEC.md").read_text(encoding="utf-8")
    head = "\n".join(spec_text.splitlines()[:40])
    assert "`report_format` is `1.1`, final" in head


# ── §4: the four open questions ─────────────────────────────────────────────────────────


def test_every_open_question_is_ruled_and_names_its_decision_record(record_text: str) -> None:
    section = _section(record_text, "## 4. The four open questions, all ruled")
    for question, ruling in OPEN_QUESTION_RULINGS.items():
        row = next(
            (line for line in section.splitlines() if f"**{question}**" in line),
            None,
        )
        assert row is not None, f"§4 states no ruling for {question}"
        assert ruling in row, f"{question}'s row does not name {ruling}"


def test_the_trace_naming_collision_is_recorded_as_never_shipped(record_text: str) -> None:
    """OQ-12-04's own words were 'before the collision can ship'; §4 must hold that."""
    section = _flat(_section(record_text, "## 4. The four open questions, all ruled"))
    assert "the verb is `history`, not `trace`" in section.lower()
    assert "the collision never shipped" in section


# ── §5: every open item, in both directions ─────────────────────────────────────────────


@pytest.mark.parametrize("spec_name", SPECS_WITH_OPEN_ITEMS)
def test_every_open_item_of_a_stamped_spec_is_dispositioned(
    record_text: str, spec_name: str
) -> None:
    """CLI-SPEC §7 owes this card a disposition for *every* item, not a selection."""
    heading = f"### {spec_name.removesuffix('.md')} Appendix B"
    section = _section(record_text, heading)
    recorded = _open_item_ids(section)
    carried = _open_item_ids(_appendix_b(spec_name))
    assert carried, f"{spec_name}'s Appendix B has no rows to disposition"
    assert carried <= recorded, (
        f"{spec_name} carries {sorted(carried - recorded)} that §5 does not disposition"
    )
    assert recorded <= carried, (
        f"§5 dispositions {sorted(recorded - carried)}, which {spec_name} does not carry"
    )


@pytest.mark.parametrize("spec_name", SPECS_WITH_OPEN_ITEMS)
def test_every_disposition_says_closed_or_re_routed(record_text: str, spec_name: str) -> None:
    """§5 defines exactly two dispositions; a row that is neither decided nothing."""
    heading = f"### {spec_name.removesuffix('.md')} Appendix B"
    for line in _section(record_text, heading).splitlines():
        stripped = line.strip()
        if not stripped.startswith("| OI-"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        disposition = cells[1].lower()
        assert "closed" in disposition or "re-routed" in disposition, (
            f"{spec_name} {cells[0]}: the disposition is neither closed nor re-routed"
        )


@pytest.mark.parametrize("spec_name", SPECS_WITH_OPEN_ITEMS)
def test_the_specs_own_rows_record_the_promotion_that_moved_them(spec_name: str) -> None:
    """The disposition lands in the item's own row too, so the two cannot drift apart."""
    appendix = _appendix_b(spec_name)
    assert appendix.count("CLI-08") >= 3, (
        f"{spec_name}'s Appendix B records almost no promotion disposition in its own rows"
    )


# ── §6 and §7: what final means, and what the record refuses to claim ───────────────────


def test_final_is_defined_rather_than_asserted(record_text: str) -> None:
    """An undefined 'final' would either overclaim or mean nothing."""
    section = _flat(_section(record_text, '## 6. What "final" means, and what it does not'))
    assert "No Phase-0 card amends these three documents' contracts any further" in section
    assert "Records are not amendments" in section
    assert "§1.6's bump table" in section


def test_the_value_rule_bump_rows_exist_where_the_record_says_they_do(
    record_text: str,
) -> None:
    """OI-7 commissioned a §1.6 row; the record claims it landed, so it must be there."""
    del record_text
    spec_text = (SPECS_DIR / "REPORT-FORMAT-SPEC.md").read_text(encoding="utf-8")
    versioning = _section(spec_text, "### 1.6 `report_format` versioning")
    rows = [line for line in versioning.splitlines() if "**value rule**" in line]
    assert len(rows) == 2, "§1.6 does not carry both value-rule rows"
    widens = next(row for row in rows if "widens" in row)
    narrows = next(row for row in rows if "narrows" in row)
    assert "MINOR" in widens
    assert "none" in narrows
    assert "subject.source" in narrows, "the worked example left the narrowing row"


def test_the_scoping_sentences_stay_on_the_page(record_text: str) -> None:
    """The sentences that keep promotion a governance event, not a verification one."""
    section = _flat(_section(record_text, "## 7. What this record does not claim"))
    assert "No verification claim of any kind" in section
    assert "witness-presence wording only" in section
    assert "It does not sign a gate" in section
    assert "does not ship, schedule or design a VS Code extension" in section


def test_the_brief_is_recorded_as_untouched(record_text: str) -> None:
    """WA-03/WA-11: the vendored brief is not edited, and the record must say so."""
    section = _flat(_section(record_text, "## 2. What promotion is taken to mean here"))
    assert "The brief is not edited, and this record does not edit it" in section
    assert "WA-11" in section and "WA-03" in section
