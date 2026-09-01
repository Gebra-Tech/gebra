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
:data:`VALIDATOR_PAGES` as they land — each remaining explainer joins it with its own card, and
a page that is still a placeholder is out of scope here (the placeholder rules are
:mod:`tests.docs.test_docs_site`'s).

The module reads Markdown and inspects model classes. It imports no workflow, runs no node,
opens no connection (WA-07).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import get_args

import pytest

from gebra.verify import (
    ConditionId,
    DataflowLocation,
    Failure,
    GuardEdgeLabels,
    P01EdgeLocation,
    P02CycleLocation,
    P02SccLocation,
    P04Failure,
    P06NodeLocation,
    PropertySlug,
    ReportModel,
    Witness,
    conditions_for,
)
from gebra.verify.witnesses import (
    CounterGuardSource,
    CycleCensus,
    DataflowCoverage,
    DataflowWitness,
    EffectSafetyWitness,
    GuardEdgeRef,
    P06EffectRecord,
    RecursionLimitDecl,
    RecursionLimitSource,
    Region,
    TerminationWitness,
    VariantDecl,
    VariantSource,
    WellFormednessWitness,
    WitnessInventoryEntry,
    WitnessNote,
    WitnessNoteKind,
)

DOCS = Path(__file__).resolve().parents[2] / "docs"

#: The landed explainer pages, by the property each one is about. A card that writes the next
#: page adds its row here; nothing else about these tests changes.
VALIDATOR_PAGES: dict[PropertySlug, str] = {
    "graph-well-formed": "validators/p01-graph-well-formed.md",
    "termination-witness": "validators/p02-termination-witness.md",
    "dataflow-completeness": "validators/p04-dataflow-completeness.md",
    "effect-safety": "validators/p06-effect-safety.md",
}

#: The witness model each landed page explains — the concrete member of the §0.3 witness union
#: whose keys the page's transcript prints and whose meaning its prose gives.
WITNESS_MODELS: dict[PropertySlug, type[Witness]] = {
    "graph-well-formed": WellFormednessWitness,
    "termination-witness": TerminationWitness,
    "dataflow-completeness": DataflowWitness,
    "effect-safety": EffectSafetyWitness,
}

#: The failure model each landed page explains. Usually the base :class:`Failure`, but a property
#: whose findings carry extra members emits a **subtype** — P-04's ``P04Failure`` adds the two
#: DEC-11 diagnostics — and it is exactly those extras a reader has nowhere else to look up. The
#: base's own members are inherited into ``model_fields``, so one row covers both.
FAILURE_MODELS: dict[PropertySlug, type[Failure]] = {
    "graph-well-formed": Failure,
    "termination-witness": Failure,
    "dataflow-completeness": P04Failure,
    "effect-safety": Failure,
}

#: The evidence models *beyond* the pass witness that a page has to explain: the property's own
#: location subtypes, and the structured payloads its witness nests. Same failure mode as the
#: witness row and the same guard — a reader meets these keys in a record and has nowhere but
#: the page to look them up, so one gained or lost without the page moving is a silent defect.
EVIDENCE_MODELS: dict[PropertySlug, tuple[type[ReportModel], ...]] = {
    "graph-well-formed": (P01EdgeLocation,),
    "termination-witness": (
        WitnessInventoryEntry,
        CounterGuardSource,
        RecursionLimitSource,
        RecursionLimitDecl,
        VariantSource,
        VariantDecl,
        GuardEdgeRef,
        WitnessNote,
        CycleCensus,
        P02SccLocation,
        P02CycleLocation,
        GuardEdgeLabels,
    ),
    "dataflow-completeness": (DataflowCoverage, DataflowLocation),
    "effect-safety": (P06EffectRecord, P06NodeLocation),
}

#: Closed string vocabularies a page must name in full: report content pinned as a ``Literal``,
#: which moves only by specification addendum. P-01's property has none; P-02's is §2.3's note
#: vocabulary, whose five kinds a reader meets on a witness or a failure record; P-06's are the
#: two enumerations of its witness record — §6.3's ``Region`` and the protection arm — where a
#: page listing three regions and two arms would be a page with a hole. The property's other
#: pinned strings (``keyless``, ``send``) are single-member evidence markers rather than sets to
#: enumerate, and the page's transcripts pin them byte-for-byte through the DOC-01 harness.
PROTECTION_FORMS: tuple[str, ...] = get_args(P06EffectRecord.model_fields["protection"].annotation)

CLOSED_VOCABULARIES: dict[PropertySlug, tuple[str, ...]] = {
    "graph-well-formed": (),
    "termination-witness": get_args(WitnessNoteKind),
    "dataflow-completeness": (),
    "effect-safety": (*get_args(Region), *PROTECTION_FORMS),
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

    Read off the page's condition **table**, not the registry, so the guard stands on its own
    rather than only in conjunction with the reconciliation above: a name the registry holds
    back, and a name it does not hold at all, both fail here. The table is deliberately the
    whole scope — a page may *name* a RESERVED id in prose, as P-06's does when it says where
    the diagnostic for a non-binding idempotency key will live, and saying so is the opposite
    of presenting it as a finding a reader might meet.
    """
    emittable = {entry.id for entry in conditions_for(slug) if entry.emittable}
    held_back = sorted(_named_conditions(_page(slug)) - emittable)

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
    first time in a report would have no page to read them off. A property emitting a failure
    *subtype* is held to the subtype's own members too — P-04's two diagnostics reach a reader
    the same way and are documented nowhere else.
    """
    page = _page(slug)
    missing = [name for name in FAILURE_MODELS[slug].model_fields if f"`{name}`" not in page]

    assert missing == [], f"{VALIDATOR_PAGES[slug]} names no {missing}"


@pytest.mark.parametrize("slug", sorted(VALIDATOR_PAGES))
def test_every_field_of_the_evidence_models_is_named(slug: PropertySlug) -> None:
    """The witness check, extended to the models the witness and the failure nest.

    A location subtype's extra fields are the whole reason it is a subtype — P-02's
    ``representative_cycle`` and ``blanket_only``, P-01's ``undefined_target`` — and an
    inventory entry or a note is where a witness keeps its evidence. All of them reach a
    reader as record keys.
    """
    page = _page(slug)
    missing = sorted(
        f"{model.__name__}.{name}"
        for model in EVIDENCE_MODELS[slug]
        for name in model.model_fields
        if f"`{name}`" not in page
    )

    assert missing == [], f"{VALIDATOR_PAGES[slug]} names no {missing}"


@pytest.mark.parametrize("slug", sorted(VALIDATOR_PAGES))
def test_every_member_of_a_closed_vocabulary_is_named(slug: PropertySlug) -> None:
    """A page that lists a frozen vocabulary lists all of it, or it is a page with a hole.

    The note kinds are the case in hand: a reader meets one string in a report, and a table
    missing its row sends them to the source. Growing the vocabulary is a specification
    addendum, so this fails on exactly the change that should reach the page.
    """
    page = _page(slug)
    missing = [member for member in CLOSED_VOCABULARIES[slug] if f"`{member}`" not in page]

    assert missing == [], f"{VALIDATOR_PAGES[slug]} names no {missing}"


def test_every_landed_page_names_the_property_it_is_about() -> None:
    """A cheap guard on the mapping itself: a row pointing at the wrong page fails here."""
    for slug, page in VALIDATOR_PAGES.items():
        assert (DOCS / page).is_file(), f"{page} does not exist"
        assert f"`{slug}`" in _page(slug)
