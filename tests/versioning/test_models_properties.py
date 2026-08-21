"""Property tests for parse, compare and bump — the card's first acceptance criterion.

The pinned cases in ``test_models`` are examples of these claims; here the claims
themselves are quantified over generated versions. Four are worth naming:

* **Rendering and parsing are inverse in both directions**, which is what makes a label a
  name for exactly one version — the reason leading zeros are refused rather than tolerated.
* **The order is a total order** and agrees with numeric component-wise comparison.
* **Any non-empty bump moves the version strictly forward**, so a store's chronological
  order and its version order are the same order.
* **Every version renders to a label the ``.gebra/`` store accepts as a file name** —
  SD-01's path-safety floor is a superset of this grammar, checked against the store's own
  validator rather than against a restatement of it.

Everything here is pure data (WA-07).
"""

from __future__ import annotations

import itertools

from hypothesis import assume, given
from hypothesis import strategies as st
from pydantic import TypeAdapter

from gebra.store import MAX_VERSION_LENGTH
from gebra.store.models import VersionLabel
from gebra.versioning import (
    MAX_LABEL_LENGTH,
    Component,
    Version,
    VersionFormatError,
    VersionFormatErrorReason,
)

#: A component count. Bounded well below the length ceiling so that generated versions are
#: renderable; the ceiling itself is pinned by example in ``test_models``.
COUNTS = st.integers(min_value=0, max_value=10**6)

#: A generated version.
VERSIONS = st.builds(Version, v=COUNTS, s=COUNTS, f=COUNTS, e=COUNTS)

#: A version drawn from a small grid. The order axioms need *neighbours* — versions that
#: tie, and versions one increment apart — which two independent draws from the wide range
#: essentially never produce.
_SMALL = st.integers(min_value=0, max_value=3)
SMALL_VERSIONS = st.builds(Version, v=_SMALL, s=_SMALL, f=_SMALL, e=_SMALL)

#: A subset of the components, including the empty one.
COMPONENT_SETS = st.lists(st.sampled_from(list(Component)), max_size=4).map(frozenset)

#: The store's own validator for a snapshot's file base name (PD-012 / SD-01).
_LABELS = TypeAdapter(VersionLabel)

#: The reasons a *parse* can end in. ``NEGATIVE`` is not among them — a label carries no
#: sign, so only the constructor can be handed a count below zero.
_PARSE_REASONS = frozenset(
    {
        VersionFormatErrorReason.MALFORMED,
        VersionFormatErrorReason.LEADING_ZERO,
        VersionFormatErrorReason.TOO_LONG,
    }
)


# ── Parse ────────────────────────────────────────────────────────────────────────────────


@given(version=VERSIONS)
def test_a_version_round_trips_through_its_label(version: Version) -> None:
    assert Version.parse(str(version)) == version


@given(version=VERSIONS)
def test_a_label_round_trips_through_its_version(version: Version) -> None:
    """The other direction: no version has a second spelling, so the label a store writes
    is the label it reads back."""
    label = str(version)

    assert str(Version.parse(label)) == label


@given(left=VERSIONS, right=VERSIONS)
def test_distinct_versions_render_to_distinct_labels(left: Version, right: Version) -> None:
    """Injectivity, which is what a store relies on when it uses the label as a file name:
    two versions cannot collide on one file."""
    assume(left != right)

    assert str(left) != str(right)


@given(version=VERSIONS)
def test_every_version_is_a_label_the_store_accepts(version: Version) -> None:
    """The grammar sits inside SD-01's path-safety floor rather than beside it — checked
    against the store's validator, so the two cannot drift apart silently."""
    assert _LABELS.validate_python(str(version)) == str(version)


def test_the_length_ceiling_is_the_store_s_own() -> None:
    assert MAX_LABEL_LENGTH == MAX_VERSION_LENGTH


@given(text=st.text(max_size=20))
def test_parsing_never_fails_in_any_other_way(text: str) -> None:
    """Whatever arrives, the answer is a version or a :class:`VersionFormatError` carrying a
    reason — never an ``IndexError`` from a split or a ``ValueError`` from an ``int()``."""
    try:
        version = Version.parse(text)
    except VersionFormatError as error:
        assert error.reason in _PARSE_REASONS  # never NEGATIVE: no label carries a sign
        assert error.value == text
    else:
        assert str(version) == text


# ── Compare ──────────────────────────────────────────────────────────────────────────────


@given(version=VERSIONS)
def test_the_order_is_reflexive(version: Version) -> None:
    """Against an equal-but-distinct value, so an identity shortcut could not carry it."""
    same = Version(*version.counts)

    assert version <= same
    assert not version < same


@given(left=SMALL_VERSIONS, right=SMALL_VERSIONS)
def test_the_order_is_total_and_antisymmetric(left: Version, right: Version) -> None:
    """Exactly one of the three relations holds between any two versions."""
    assert (left < right) + (right < left) + (left == right) == 1


@given(triple=st.lists(SMALL_VERSIONS, min_size=3, max_size=3))
def test_the_order_is_transitive(triple: list[Version]) -> None:
    """Every ordering of the three is tried, so the premise is reached without filtering."""
    for left, middle, right in itertools.permutations(triple):
        if left <= middle <= right:
            assert left <= right


@given(left=SMALL_VERSIONS, right=SMALL_VERSIONS)
def test_the_order_is_component_wise_numeric(left: Version, right: Version) -> None:
    """V dominates S dominates F dominates E, each compared as a number."""
    assert (left < right) == (left.counts < right.counts)


@given(left=SMALL_VERSIONS, right=SMALL_VERSIONS)
def test_equality_is_equality_of_counts(left: Version, right: Version) -> None:
    assert (left == right) == (left.counts == right.counts)


# ── Bump ─────────────────────────────────────────────────────────────────────────────────


@given(version=VERSIONS, components=COMPONENT_SETS)
def test_a_bump_moves_the_version_forward_and_never_back(
    version: Version, components: frozenset[Component]
) -> None:
    """The property a store's history rests on: the version order and the order snapshots
    were taken in are the same order, whichever components a change touched."""
    bumped = version.bump(*components)

    if components:
        assert bumped > version
    else:
        assert bumped == version


@given(version=VERSIONS, components=COMPONENT_SETS)
def test_a_bump_increments_what_it_names_and_leaves_the_rest_alone(
    version: Version, components: frozenset[Component]
) -> None:
    """No resets — the counters are independent (D-11 In-Scope 2's "and/or")."""
    bumped = version.bump(*components)

    for component, before, after in zip(Component, version.counts, bumped.counts, strict=True):
        assert after == before + (1 if component in components else 0)


@given(version=VERSIONS, components=COMPONENT_SETS)
def test_a_bump_does_not_depend_on_the_order_the_components_arrive_in(
    version: Version, components: frozenset[Component]
) -> None:
    expected = version.bump(*components)

    for ordering in itertools.permutations(components):
        assert version.bump(*ordering) == expected


@given(version=VERSIONS, components=COMPONENT_SETS)
def test_bumping_one_at_a_time_is_bumping_them_together(
    version: Version, components: frozenset[Component]
) -> None:
    stepwise = version
    for component in components:
        stepwise = stepwise.bump(component)

    assert stepwise == version.bump(*components)
