"""The V.S.F.E label: its grammar, its order, and what a bump does — the pinned cases.

``test_models_properties`` holds the same three claims over generated versions; this module
pins the individual decisions those properties quantify over, and the refusals a property
test cannot state (there is no strategy for "every string that is not a label").

Everything here is pure data (WA-07).
"""

from __future__ import annotations

import pytest

from gebra.versioning import (
    COMPONENT_COUNT,
    MAX_LABEL_LENGTH,
    Component,
    Version,
    VersionFormatError,
    VersionFormatErrorReason,
)

# ── The grammar ──────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("label", "counts"),
    [
        ("1.0.0.0", (1, 0, 0, 0)),
        ("0.0.0.0", (0, 0, 0, 0)),
        ("1.4.2.0", (1, 4, 2, 0)),
        ("1.10.9.100", (1, 10, 9, 100)),
        ("2.0.0.7", (2, 0, 0, 7)),
        ("12345678.0.0.0", (12345678, 0, 0, 0)),
    ],
)
def test_a_label_parses_to_its_counts(label: str, counts: tuple[int, int, int, int]) -> None:
    version = Version.parse(label)

    assert version.counts == counts
    assert str(version) == label


@pytest.mark.parametrize(
    ("label", "reason"),
    [
        # Wrong component count — the scheme's name fixes it at four.
        ("1.0.0", VersionFormatErrorReason.MALFORMED),
        ("1.0.0.0.0", VersionFormatErrorReason.MALFORMED),
        ("1", VersionFormatErrorReason.MALFORMED),
        ("", VersionFormatErrorReason.MALFORMED),
        # Decorations a version-shaped string picks up in the wild.
        ("v1.0.0.0", VersionFormatErrorReason.MALFORMED),
        ("1.0.0.0 ", VersionFormatErrorReason.MALFORMED),
        (" 1.0.0.0", VersionFormatErrorReason.MALFORMED),
        ("1.0.0.0\n", VersionFormatErrorReason.MALFORMED),
        ("1.0.0.0.yaml", VersionFormatErrorReason.MALFORMED),
        ("+1.0.0.0", VersionFormatErrorReason.MALFORMED),
        ("-1.0.0.0", VersionFormatErrorReason.MALFORMED),
        ("1.0.0.-1", VersionFormatErrorReason.MALFORMED),
        ("1.0.0.1e3", VersionFormatErrorReason.MALFORMED),
        ("1..0.0", VersionFormatErrorReason.MALFORMED),
        ("1.0.0.", VersionFormatErrorReason.MALFORMED),
        (".1.0.0", VersionFormatErrorReason.MALFORMED),
        # `int()` would take these; a file name and a total order cannot.
        ("١.٠.٠.٠", VersionFormatErrorReason.MALFORMED),
        ("1_0.0.0.0", VersionFormatErrorReason.MALFORMED),
        # A second spelling of a version that already has one.
        ("01.0.0.0", VersionFormatErrorReason.LEADING_ZERO),
        ("1.00.0.0", VersionFormatErrorReason.LEADING_ZERO),
        ("1.0.0.007", VersionFormatErrorReason.LEADING_ZERO),
        # Longer than a snapshot's file name may be (PD-012 / SD-01's floor).
        ("1." * 3 + "9" * MAX_LABEL_LENGTH, VersionFormatErrorReason.TOO_LONG),
    ],
)
def test_a_string_that_is_not_a_label_is_refused_with_its_reason(
    label: str, reason: VersionFormatErrorReason
) -> None:
    with pytest.raises(VersionFormatError) as caught:
        Version.parse(label)

    assert caught.value.reason is reason
    assert caught.value.value == label


def test_the_leading_zero_message_names_the_spelling_that_would_have_worked() -> None:
    """The one refusal a caller is likeliest to hit by hand, so it says what to write."""
    with pytest.raises(VersionFormatError, match=r"'1\.1\.0\.0'"):
        Version.parse("1.01.0.0")


def test_a_negative_component_is_refused_at_construction() -> None:
    """Unreachable through :meth:`Version.parse` — a label carries no sign — so this is the
    constructor's own floor: a version counts changes, and counts do not go down."""
    with pytest.raises(VersionFormatError) as caught:
        Version(1, -1, 0, 0)

    assert caught.value.reason is VersionFormatErrorReason.NEGATIVE


@pytest.mark.parametrize("count", [1.0, "1", True, None])
def test_a_component_that_is_not_a_whole_number_is_refused_at_construction(count: object) -> None:
    """A count that is not an integer renders to something no label grammar admits, which
    would break the one claim the constructor's floor exists to keep: every version is a
    label the store can use as a file name. ``True`` is in the list because ``bool`` is an
    ``int`` subclass and ``str(True)`` is ``'True'``."""
    with pytest.raises(VersionFormatError) as caught:
        Version(1, count, 0, 0)  # type: ignore[arg-type]

    assert caught.value.reason is VersionFormatErrorReason.MALFORMED


def test_a_version_too_long_to_be_a_file_name_is_refused_at_construction() -> None:
    with pytest.raises(VersionFormatError) as caught:
        Version(10**MAX_LABEL_LENGTH, 0, 0, 0)

    assert caught.value.reason is VersionFormatErrorReason.TOO_LONG


def test_the_scheme_carries_four_components() -> None:
    assert COMPONENT_COUNT == len(Component) == len(Version.initial().counts) == 4


def test_the_first_version_is_1_0_0_0() -> None:
    """No earlier IR exists to compare a first snapshot against, so nothing bumps: the
    starting label is a choice, and this is it (PD-012 and SD-01 use it throughout)."""
    assert str(Version.initial()) == "1.0.0.0"


# ── The order ────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("earlier", "later"),
    [
        ("1.0.0.0", "1.0.0.1"),
        ("1.0.0.9", "1.0.1.0"),
        ("1.0.9.9", "1.1.0.0"),
        ("1.9.9.9", "2.0.0.0"),
        # The case a string comparison of the labels gets backwards.
        ("1.9.0.0", "1.10.0.0"),
        ("1.0.0.9", "1.0.0.10"),
        ("1.2.0.0", "1.11.0.0"),
        # Components to the left dominate, whatever sits to their right.
        ("1.0.99.99", "1.1.0.0"),
        ("1.4.2.0", "2.0.0.0"),
    ],
)
def test_versions_order_by_numeric_component(earlier: str, later: str) -> None:
    assert Version.parse(earlier) < Version.parse(later)
    assert Version.parse(later) > Version.parse(earlier)
    assert Version.parse(earlier) != Version.parse(later)


def test_the_order_is_numeric_where_a_string_sort_would_disagree() -> None:
    """Stated on its own because it is the whole reason the labels are parsed before they
    are compared: sorting them as text puts ``1.10.0.0`` before ``1.9.0.0``."""
    labels = ["1.9.0.0", "1.10.0.0", "1.2.0.0"]

    assert [str(v) for v in sorted(Version.parse(label) for label in labels)] == [
        "1.2.0.0",
        "1.9.0.0",
        "1.10.0.0",
    ]
    assert sorted(labels) == ["1.10.0.0", "1.2.0.0", "1.9.0.0"]


def test_two_parses_of_one_label_are_the_same_value() -> None:
    """Frozen and compared by value, so a version is usable as a dict key and as a set
    member — which is what a store indexing snapshots by version needs of it."""
    assert Version.parse("1.4.2.0") == Version.parse("1.4.2.0")
    assert len({Version.parse("1.4.2.0"), Version(1, 4, 2, 0)}) == 1


def test_a_version_does_not_compare_to_a_label() -> None:
    """The comparison is defined between versions. Comparing one to the string it renders
    to is a caller's bug, and a ``TypeError`` is where it is cheapest to notice."""
    with pytest.raises(TypeError):
        _ = Version.parse("1.0.0.0") < "1.0.0.1"  # type: ignore[operator]


# ── The bump ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("components", "expected"),
    [
        ((), "1.4.2.7"),
        ((Component.S,), "1.5.2.7"),
        ((Component.F,), "1.4.3.7"),
        ((Component.E,), "1.4.2.8"),
        ((Component.V,), "2.4.2.7"),
        ((Component.S, Component.F), "1.5.3.7"),
        ((Component.S, Component.E), "1.5.2.8"),
        ((Component.F, Component.E), "1.4.3.8"),
        ((Component.S, Component.F, Component.E), "1.5.3.8"),
    ],
)
def test_a_bump_increments_what_it_names_and_resets_nothing(
    components: tuple[Component, ...], expected: str
) -> None:
    """D-11 In-Scope 2 bumps "S (topology), F (node/contract), **and/or** E (state
    schema)" — three independent counters, not a semver precedence chain. ``1.4.2.7``
    bumped on S stays at ``2`` contract changes and ``7`` schema changes."""
    assert str(Version.parse("1.4.2.7").bump(*components)) == expected


def test_a_bump_is_order_independent_and_repeat_safe() -> None:
    version = Version.parse("1.4.2.7")

    assert version.bump(Component.S, Component.E) == version.bump(Component.E, Component.S)
    assert version.bump(Component.S).bump(Component.E) == version.bump(Component.S, Component.E)
    assert version.bump(Component.S, Component.S) == version.bump(Component.S)


def test_an_empty_bump_is_the_same_version() -> None:
    """What an unchanged workflow gets. Whether it is re-snapshot at all is SD-03's."""
    version = Version.parse("1.4.2.7")

    assert version.bump() == version


def test_a_bump_that_could_not_be_a_file_name_is_refused() -> None:
    at_the_edge = Version.parse("9" * (MAX_LABEL_LENGTH - 6) + ".0.0.0")

    with pytest.raises(VersionFormatError) as caught:
        at_the_edge.bump(Component.V)

    assert caught.value.reason is VersionFormatErrorReason.TOO_LONG


def test_only_s_f_and_e_are_derived_from_a_workflow_change() -> None:
    """The frozen package defines S, F and E and says nothing about what V counts, so the
    engine assigns it to nothing and carries it through (SOW §1; brief D-11 In-Scope 2)."""
    assert Component.derived() == (Component.S, Component.F, Component.E)
    assert Component.V not in Component.derived()
