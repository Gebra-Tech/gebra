"""No marker text states a document's standing, a schedule or a phase (DEC-42; PD-073 §10).

DEC-42 ruled two strings untrue in the same way. The copy beside a ``deferred-to-phase-1``
marker had a second clause, "its catalog section is not yet ratified", and the eight deferred
rows' contract pointers ended in a note calling the catalog section a stub and another document
authoritative. Each states the standing of a document, and each turns untrue of a property the
day its section is ratified while the release that printed it, and every report kept from it,
goes on printing it. DEC-42 kept the first clause alone — *has no validator in this release*, a
fact of the build that produced the marker — and removed the note.

No charter item fixes what every marker's copy may say: the product owner did not adopt one at
the ruling (PD-073 §10 item 3, in the development-process repository), and this module holds
the discipline in a test instead, over the marker text the registry composes and the text the
golden harness defers with:

- for each of the thirteen catalog rows, the ``detail`` of :func:`gebra.verify.not_implemented`
  — the ``deferred-to-phase-1`` marker of a deferred row, the ``not-yet-implemented`` marker a
  shipped row answers with when its validator is not wired in;
- for each obligation of the vendored corpus whose property is deferred, the ``detail`` of
  :func:`gebra.testing.harness.run_obligation` — the set is derived from the corpus and the
  registry when the test runs, and no count is pinned;
- every reason in :data:`gebra.verify.MARKER_REASONS`.

None may contain, case-sensitively, any word of :data:`BARRED`.

Nothing here executes a workflow node, calls a model or opens a network connection (WA-07). It
loads the vendored fixtures, plans their obligations and runs only the deferred ones:
``run_obligation`` returns a deferred obligation's outcome before any validator is looked up,
so no validator runs. ``run_corpus``, which runs the wedge validators, is not used.
"""

from __future__ import annotations

from typing import Final

import pytest

from gebra.testing import load_corpus
from gebra.testing.fixtures import PropertyFixture
from gebra.testing.harness import Outcome, plan_fixture, run_obligation
from gebra.verify import (
    MARKER_REASONS,
    PROPERTY_SLUGS,
    PropertySlug,
    not_implemented,
    property_entry,
)
from tests.conftest import FIXTURES_DIR

#: Words that state a document's standing ("ratified", "drafted", "stub", "authoritative"), a
#: schedule ("scheduled") or a phase ("Phase"). Matched case-sensitively, so the lower-case
#: ``phase`` inside a status token such as ``deferred-to-phase-1`` is not one of them — the
#: token is the wire's, and no marker text quotes it.
BARRED: Final = ("ratified", "drafted", "stub", "authoritative", "scheduled", "Phase")


def barred_words(text: str) -> list[str]:
    """Every word of :data:`BARRED` that ``text`` contains, in :data:`BARRED`'s order."""
    return [word for word in BARRED if word in text]


def _deferred_outcomes(fixtures: tuple[PropertyFixture, ...]) -> list[Outcome]:
    """The harness's outcome for every deferred obligation of ``fixtures``.

    Read off the corpus and the registry when called: an obligation is deferred when its
    property's registry row is ``deferred-to-phase-1`` (``Obligation.deferred``), so a property
    that lands leaves this set with no edit here.
    """
    return [
        run_obligation(fixture, obligation)
        for fixture in fixtures
        for obligation in plan_fixture(fixture)
        if obligation.deferred
    ]


@pytest.mark.parametrize("slug", PROPERTY_SLUGS)
def test_no_marker_detail_states_a_standing_a_schedule_or_a_phase(slug: PropertySlug) -> None:
    """The ``detail`` the registry composes for each row, deferred or shipped."""
    assert barred_words(not_implemented(slug).detail) == []


def test_no_harness_deferral_states_a_standing_a_schedule_or_a_phase() -> None:
    """The ``detail`` of every deferred obligation's outcome, over the whole vendored corpus.

    Never vacuous by accident: every deferred property a vendored fixture declares must have
    produced at least one outcome here. The set is empty only when the corpus exercises no
    deferred property — the day the last one lands.
    """
    fixtures = load_corpus(FIXTURES_DIR)
    assert fixtures, "the vendored corpus loaded no fixture"
    outcomes = _deferred_outcomes(fixtures)
    declared = {
        slug for fixture in fixtures for slug in fixture.properties if property_entry(slug).deferred
    }
    assert {outcome.obligation.property_slug for outcome in outcomes} == declared
    for outcome in outcomes:
        assert outcome.status == "deferred-to-phase-1", outcome.obligation.id
        assert barred_words(outcome.detail) == [], outcome.obligation.id


def test_no_marker_reason_states_a_standing_a_schedule_or_a_phase() -> None:
    """Every reason a surface states beside a marker's status, one per wire status."""
    assert MARKER_REASONS
    for status, reason in MARKER_REASONS.items():
        assert barred_words(reason) == [], status


def test_the_discipline_sees_the_retired_copy() -> None:
    """Arms the three tests above on the strings DEC-35 and DEC-42 retired.

    The marker detail as built before DEC-42, the token's reading DEC-42 §3.3 replaced, and the
    Phase-0 copy DEC-35 retired each trip it; the copy DEC-42 rules does not.
    """
    assert barred_words(
        "P-03 signature-soundness has no validator in this release; its catalog section is not "
        "yet ratified. The catalog contract is PROPERTY-CATALOG-SPEC §P-03 (stub; "
        "Verification-Properties §2 authoritative). No verdict was reached — this is not a pass."
    ) == ["ratified", "stub", "authoritative"]
    assert barred_words("scheduled for Phase 1, not landed in this release") == [
        "scheduled",
        "Phase",
    ]
    assert barred_words("is outside the Phase-0 wedge (SOW §8)") == ["Phase"]
    assert barred_words("a section drafted but not adopted") == ["drafted"]
    assert barred_words("has no validator in this release") == []
