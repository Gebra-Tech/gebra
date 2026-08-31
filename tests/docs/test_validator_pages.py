"""The per-validator explainer pages, held to the surfaces they explain.

A validator page's job is to let a reader interpret one property's findings, which means it
carries two lists that are really contracts: the condition IDs the property may emit (the
PROPERTY-CATALOG-SPEC §0.4 registry) and the fields of the records those findings arrive in
(the §0.3 envelope models). Both are frozen, and both move only by specification addendum —
so a page that named four of five conditions, or explained a witness key the model no longer
has, would be wrong in exactly the way prose goes wrong: quietly, and only for the reader.

These tests are that reconciliation. They read the page's own condition table and its prose
and check them against the registry and the models, so a registry addendum or a witness-shape
change fails the build rather than dating the page. Pages are listed in
:data:`VALIDATOR_PAGES` as they land — the four remaining explainers join it with their own
cards, and a page that is still a placeholder is out of scope here (the placeholder rules are
:mod:`tests.docs.test_docs_site`'s).

The module reads Markdown and inspects model classes. It imports no workflow, runs no node,
opens no connection (WA-07).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from gebra.verify import (
    ConditionId,
    Failure,
    PropertySlug,
    Witness,
    conditions_for,
)
from gebra.verify.witnesses import WellFormednessWitness

DOCS = Path(__file__).resolve().parents[2] / "docs"

#: The landed explainer pages, by the property each one is about. A card that writes the next
#: page adds its row here; nothing else about these tests changes.
VALIDATOR_PAGES: dict[PropertySlug, str] = {
    "graph-well-formed": "validators/p01-graph-well-formed.md",
}

#: The witness model each landed page explains — the concrete member of the §0.3 witness union
#: whose keys the page's transcript prints and whose meaning its prose gives.
WITNESS_MODELS: dict[PropertySlug, type[Witness]] = {
    "graph-well-formed": WellFormednessWitness,
}

#: The header of the condition table every explainer carries.
CONDITION_TABLE_HEADER = "| Condition | What it requires | Condition ID | Anchor |"

#: What a condition ID looks like: kebab-case, at least two segments. The column also names IR
#: members in backticks (`entry`, `finish`, `from`, `path_map`), and this is what tells the two
#: apart without a hand-maintained exclusion list — every registered id carries a hyphen, and no
#: IR member name does. A hyphenated token that is *not* a condition id fails the reconciliation
#: below rather than being skipped, which is the direction to fail in.
CONDITION_ID_SHAPE = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)+$")

BACKTICKED = re.compile(r"`([^`]+)`")


def _page(slug: PropertySlug) -> str:
    return (DOCS / VALIDATOR_PAGES[slug]).read_text(encoding="utf-8")


def _condition_column(text: str) -> list[str]:
    """The `Condition ID` cells of the page's condition table, in table order."""
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if line.strip() != CONDITION_TABLE_HEADER:
            continue
        cells = []
        for candidate in lines[index + 2 :]:  # +2 skips the alignment row
            if not candidate.startswith("|"):
                break
            cells.append([cell.strip() for cell in candidate.strip("|").split("|")][2])
        return cells
    raise AssertionError(f"no condition table with header {CONDITION_TABLE_HEADER!r}")


def _named_conditions(text: str) -> set[ConditionId]:
    """Every condition ID the page's condition table names, whatever prose surrounds it."""
    named: set[ConditionId] = set()
    for cell in _condition_column(text):
        named |= {token for token in BACKTICKED.findall(cell) if CONDITION_ID_SHAPE.match(token)}
    return named


@pytest.mark.parametrize("slug", sorted(VALIDATOR_PAGES))
def test_the_condition_table_names_exactly_the_registered_conditions(slug: PropertySlug) -> None:
    """Both directions: no condition left undocumented, and none invented for the page.

    The §0.4 registry is closed — introducing, renaming or promoting an id is a specification
    addendum — so a page whose table drifted from it would be describing a vocabulary the
    validator does not have.
    """
    assert _named_conditions(_page(slug)) == {entry.id for entry in conditions_for(slug)}


@pytest.mark.parametrize("slug", sorted(VALIDATOR_PAGES))
def test_every_condition_the_page_documents_is_one_this_release_may_emit(
    slug: PropertySlug,
) -> None:
    """WA-12 for the diagnostic vocabulary: a held-but-not-ratified name documents nothing.

    §0.4's PROPOSED tier registers a name without licensing its emission, and a page that
    presented one as a finding a reader might meet would be describing unbuilt behaviour.
    """
    held_back = [entry.id for entry in conditions_for(slug) if not entry.emittable]

    assert held_back == [], f"{VALIDATOR_PAGES[slug]} documents non-emittable {held_back}"


@pytest.mark.parametrize("slug", sorted(VALIDATOR_PAGES))
def test_every_field_of_the_pass_witness_is_explained(slug: PropertySlug) -> None:
    """The card's own acceptance, mechanized: every key of the pinned witness is on the page.

    Naming the field in backticks is the test's proxy for explaining it — weak on its own,
    load-bearing against the failure it is here to catch, which is a witness gaining or losing
    a key while the page keeps describing the old shape.
    """
    page = _page(slug)
    missing = [name for name in WITNESS_MODELS[slug].model_fields if f"`{name}`" not in page]

    assert missing == [], f"{VALIDATOR_PAGES[slug]} explains no {missing}"


@pytest.mark.parametrize("slug", sorted(VALIDATOR_PAGES))
def test_every_field_of_the_failure_record_is_named(slug: PropertySlug) -> None:
    """The same for the negative side, including the optional members.

    The optional ones matter most: `remediation`, `advisories`, `subsumed_by` and `notes` are
    dropped from a serialized record that does not set them, so a reader who met them for the
    first time in a report would have no page to read them off.
    """
    page = _page(slug)
    missing = [name for name in Failure.model_fields if f"`{name}`" not in page]

    assert missing == [], f"{VALIDATOR_PAGES[slug]} names no {missing}"


def test_every_landed_page_names_the_property_it_is_about() -> None:
    """A cheap guard on the mapping itself: a row pointing at the wrong page fails here."""
    for slug, page in VALIDATOR_PAGES.items():
        assert (DOCS / page).is_file(), f"{page} does not exist"
        assert f"`{slug}`" in _page(slug)
