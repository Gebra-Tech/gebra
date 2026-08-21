"""The SARIF rule copy against REPORT-FORMAT-SPEC A.3 (card CLI-03).

A.3 fixes the ``shortDescription`` of every emittable condition in a table and hands the other
two strings to CLI-03. So the test that matters is a lockstep one: the module's short
descriptions are parsed out of the spec and compared, and the copy CLI-03 wrote is held to the
budget and to the §4.6 rules. A drift between the two then fails here rather than shipping as
a log whose rule text disagrees with the document that specified it.

Nothing here executes a workflow node, calls a model or opens a socket (WA-07): it reads one
markdown file and one table of strings.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

import pytest

from gebra.report.rules import MAX_RULE_TEXT, RULE_COPY, SARIF_RULE_ENTRIES, rule_copy
from gebra.verify.conditions import CONDITION_REGISTRY

SPEC_PATH: Final = Path(__file__).resolve().parents[2] / "docs" / "specs" / "REPORT-FORMAT-SPEC.md"

_ROW = re.compile(r"^\|\s*`(?P<id>[a-z0-9-]+)`\s*\|(?P<rest>.*)\|\s*$")


def _spec_short_descriptions() -> dict[str, str]:
    """The A.3 table's ``shortDescription.text`` column, by condition ID."""
    section = SPEC_PATH.read_text(encoding="utf-8").split("### A.3 The `rules[]` catalog")[1]
    section = section.split("\n### ")[0]
    descriptions: dict[str, str] = {}
    for line in section.splitlines():
        match = _ROW.match(line.strip())
        if match is None:
            continue
        cells = [cell.strip() for cell in match.group("rest").split("|")]
        descriptions[match.group("id")] = cells[-1]
    return descriptions


def test_the_spec_table_was_found() -> None:
    assert len(_spec_short_descriptions()) == len(SARIF_RULE_ENTRIES) == 13


@pytest.mark.parametrize("entry", SARIF_RULE_ENTRIES, ids=lambda entry: entry.id)
def test_short_descriptions_match_the_spec_table(entry: object) -> None:
    """A.3's own cell, byte-for-byte — never re-invented here."""
    condition = entry.id  # type: ignore[attr-defined]
    assert rule_copy(condition).short_description == _spec_short_descriptions()[condition]


def test_the_catalog_covers_exactly_the_emittable_registry() -> None:
    assert set(RULE_COPY) == {entry.id for entry in SARIF_RULE_ENTRIES}
    held = {entry.id for entry in CONDITION_REGISTRY.values() if not entry.emittable}
    assert not set(RULE_COPY) & held


@pytest.mark.parametrize("entry", SARIF_RULE_ENTRIES, ids=lambda entry: entry.id)
def test_every_string_is_within_the_copy_budget(entry: object) -> None:
    """Appendix C's ≤1024 characters per string, which GitHub also requires."""
    copy = rule_copy(entry.id)  # type: ignore[attr-defined]
    for text in (copy.short_description, copy.full_description, copy.help_text):
        assert 0 < len(text) <= MAX_RULE_TEXT


@pytest.mark.parametrize("entry", SARIF_RULE_ENTRIES, ids=lambda entry: entry.id)
def test_the_full_description_names_its_owning_property(entry: object) -> None:
    """A.3: "the owning property section's statement of the condition"."""
    copy = rule_copy(entry.id)  # type: ignore[attr-defined]
    assert entry.property_id in copy.full_description  # type: ignore[attr-defined]
    assert entry.property_slug in copy.full_description  # type: ignore[attr-defined]


@pytest.mark.parametrize("entry", SARIF_RULE_ENTRIES, ids=lambda entry: entry.id)
def test_the_help_text_points_at_the_catalog_section(entry: object) -> None:
    """A.3: "plus a pointer to the catalog section"."""
    assert "PROPERTY-CATALOG-SPEC" in rule_copy(entry.id).help_text  # type: ignore[attr-defined]


def test_p02_copy_stays_within_witness_presence_wording() -> None:
    """§4.6 rule 2 on the two P-02 conditions, where the temptation is greatest."""
    for condition in ("cycle-without-termination-witness", "counter-guard-without-exit-edge"):
        copy = rule_copy(condition)
        text = (f"{copy.short_description} {copy.full_description} {copy.help_text}").lower()
        assert "declar" in text, "P-02 copy names what the definition declares"
        for claim in ("halts", "will terminate", "always terminates", "safe to run"):
            assert claim not in text


def test_the_copy_speaks_about_the_definition_not_a_running_agent() -> None:
    """§4.6 rule 3: the subject is the workflow definition; nothing observes a run."""
    for entry in SARIF_RULE_ENTRIES:
        copy = rule_copy(entry.id)
        text = f"{copy.full_description} {copy.help_text}".lower()
        for phrase in ("at runtime", "when the agent runs", "during execution"):
            assert phrase not in text
