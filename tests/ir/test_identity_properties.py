"""Round-trip properties of the IR-SPEC §5 escaping and path grammar.

Where :mod:`tests.ir.test_identity` pins the spec's worked examples, this module states the
laws they are instances of, over generated input:

* escaping then unescaping returns the NFC source name, and unescaping then escaping returns
  the segment byte-for-byte — the two directions of §5.1's percent-encoding;
* joining then splitting returns the segments, and splitting agrees with a bare
  ``str.split("/")`` — §5.1's split-safety claim;
* :func:`~gebra.ir.identity.parse_node_id` is total on ``str``: it either returns a parse of
  exactly its input or raises :class:`~gebra.ir.identity.NodeIdError`, never anything else.

Nothing here executes a workflow, a node, or a network call (WA-07): hypothesis generates
text, and the functions under test are pure string and Unicode work.
"""

from __future__ import annotations

import unicodedata

from hypothesis import assume, given
from hypothesis import strategies as st

from gebra.ir import (
    RESERVED_SEGMENTS,
    SEGMENT_SEPARATOR,
    SYNTHETIC_KINDS,
    NodeIdError,
    SegmentKind,
    escape_segment,
    is_valid_node_id,
    join_node_id,
    node_id_from_names,
    openinference_attributes,
    parse_node_id,
    split_node_id,
    synthetic_segment,
    unescape_segment,
)

#: A source-level name as a user would spell it, before any escaping (§5.1 "user-segment ...
#: non-empty after unescaping"). ``st.text`` excludes surrogates, which are not encodable.
SOURCE_NAMES = st.text(min_size=1)

#: A name that survives becoming a segment on its own: not a reserved one (§5.1).
UNRESERVED_SOURCE_NAMES = SOURCE_NAMES.filter(
    lambda name: unicodedata.normalize("NFC", name) not in RESERVED_SEGMENTS
)

#: An escaped user segment, built directly from the §5.1 productions rather than by escaping
#: — an independent generator, so the two round-trip directions are not the same test twice.
#: Nothing it produces can wear a synthetic shape: a leading ``%`` is always ``%2F``/``%25``,
#: and no kind token starts with ``2F`` or ``25``.
ESCAPED_USER_SEGMENTS = (
    st.lists(
        st.one_of(
            st.characters(codec="utf-8", exclude_characters=SEGMENT_SEPARATOR + "%"),
            st.just("%2F"),
            st.just("%25"),
        ),
        min_size=1,
    )
    .map("".join)
    .filter(lambda segment: segment not in RESERVED_SEGMENTS)
)

#: A user segment that is not merely well-shaped but *valid*: re-normalized, because a
#: generated character can be one NFC rewrites (a CJK compatibility ideograph, say, or a
#: decomposed accent), and never one of the reserved names.
VALID_USER_SEGMENTS = ESCAPED_USER_SEGMENTS.map(
    lambda segment: escape_segment(unescape_segment(segment))
).filter(lambda segment: segment not in RESERVED_SEGMENTS)

#: A segment of either production, ready to be joined into a node id.
SEGMENTS = st.one_of(
    VALID_USER_SEGMENTS,
    st.builds(
        synthetic_segment,
        st.sampled_from(sorted(SYNTHETIC_KINDS)),
        st.one_of(SOURCE_NAMES, st.integers(min_value=0)),
    ),
)


@given(SOURCE_NAMES)
def test_escaping_then_unescaping_returns_the_nfc_source_name(name: str) -> None:
    """§5.1: segments are NFC-normalized *before* escaping, so NFC is what survives."""
    assert unescape_segment(escape_segment(name)) == unicodedata.normalize("NFC", name)


@given(ESCAPED_USER_SEGMENTS)
def test_unescaping_then_escaping_returns_the_segment(segment: str) -> None:
    """The other direction: escaping is injective on NFC names, so no segment is rewritten."""
    decoded = unescape_segment(segment)
    assume(unicodedata.is_normalized("NFC", decoded))
    assert escape_segment(decoded) == segment


@given(SOURCE_NAMES)
def test_escaping_folds_in_normalization(name: str) -> None:
    """Escaping an already-normalized name and a decomposed one give the same segment."""
    assert escape_segment(unicodedata.normalize("NFC", name)) == escape_segment(name)


@given(UNRESERVED_SOURCE_NAMES)
def test_an_escaped_name_is_always_a_valid_segment(name: str) -> None:
    """Whatever the source name, the escaped form is admitted by the grammar."""
    segment = escape_segment(name)
    assert SEGMENT_SEPARATOR not in segment
    assert is_valid_node_id(segment)
    assert parse_node_id(segment).segments[0].kind is SegmentKind.USER


@given(st.lists(SEGMENTS, min_size=1, max_size=5))
def test_joining_then_splitting_returns_the_segments(segments: list[str]) -> None:
    """A node id is exactly its segments, at any depth (§5.1)."""
    node_id = join_node_id(segments)
    assert split_node_id(node_id) == tuple(segments)
    assert len(parse_node_id(node_id).segments) == len(segments)


@given(st.lists(SEGMENTS, min_size=1, max_size=5))
def test_splitting_agrees_with_a_bare_string_split(segments: list[str]) -> None:
    """§5.1: "Split-safe: `node_id.split("/")` is always correct with no context"."""
    node_id = join_node_id(segments)
    assert split_node_id(node_id) == tuple(node_id.split(SEGMENT_SEPARATOR))


@given(st.lists(UNRESERVED_SOURCE_NAMES, min_size=1, max_size=5))
def test_source_names_survive_a_whole_path_round_trip(names: list[str]) -> None:
    """Build an id from names at every nesting level, read the same names back out."""
    node_id = node_id_from_names(names)
    parsed = parse_node_id(node_id)
    assert [segment.name for segment in parsed.segments] == [
        unicodedata.normalize("NFC", name) for name in names
    ]


@given(st.sampled_from(sorted(SYNTHETIC_KINDS)), st.one_of(SOURCE_NAMES, st.integers(min_value=0)))
def test_synthetic_segments_round_trip_their_kind_and_selector(
    kind: str, selector: str | int
) -> None:
    """§5.2: the selector is escaped by the §5.1 rules, so any source key survives."""
    segment = synthetic_segment(kind, selector)
    parsed = parse_node_id(segment).segments[0]
    assert parsed.kind is SegmentKind.SYNTHETIC
    assert parsed.synthetic_kind == kind
    assert parsed.selector == unicodedata.normalize("NFC", str(selector))


@given(st.lists(SEGMENTS, min_size=1, max_size=5))
def test_the_openinference_derivations_recompose_the_id(segments: list[str]) -> None:
    """§5.4: parent_id and the final segment partition the id, with no bytes invented."""
    node_id = join_node_id(segments)
    attributes = openinference_attributes(node_id)
    parent = attributes["graph.node.parent_id"]
    assert node_id == (f"{parent}{SEGMENT_SEPARATOR}" if parent else "") + segments[-1]
    assert attributes["graph.node.id"] == node_id


@given(st.text())
def test_parsing_either_returns_the_input_or_raises_node_id_error(text: str) -> None:
    """No input reaches an unexpected exception: refusal is always the typed one."""
    try:
        parsed = parse_node_id(text)
    except NodeIdError as error:
        assert error.value == text
        assert not is_valid_node_id(text)
        return
    assert parsed.text == text
    assert SEGMENT_SEPARATOR.join(segment.text for segment in parsed.segments) == text
