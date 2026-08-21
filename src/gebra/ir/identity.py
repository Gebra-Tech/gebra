"""Node identity — the IR-SPEC §5 grammar as utilities.

A ``node_id`` is a non-empty ``/``-joined path of segments, one per nesting level from the
graph root (IR-SPEC §5.1). Two segment productions share that path and are disjoint:

* a **user segment** — a source-level name, NFC-normalized and then percent-escaped so that
  the only ``%`` sequences it contains are ``%2F`` (a literal ``/``) and ``%25`` (a literal
  ``%``);
* a **synthetic segment** — ``"%" kind "[" selector "]"``, the naming for unnamed LCEL
  fragments, with ``kind`` drawn from the closed seven-token vocabulary IR-SPEC §5.2 fixes
  for 1.0 and ``selector`` escaped by the same rules.

Two entry points cover construction. :func:`node_id_from_names` takes *source names* and
escapes each one; :func:`join_node_id` takes *already-formed segments*, which is what you
want as soon as a synthetic token is involved::

    node_id_from_names(["research", "web search"])            -> "research/web search"
    join_node_id([escape_segment("chain"), synthetic_segment("seq", 0)])  -> "chain/%seq[0]"

Both refuse the reserved segments ``__start__`` and ``__end__`` at every nesting level, and
so does every parsing entry point: :func:`parse_node_id`, :func:`validate_node_id`, and the
:data:`NodeIdStr` annotation that :class:`gebra.ir.models.Node` puts on ``id``.

Inspection goes through :func:`parse_node_id`, whose :class:`NodeId` carries the segments in
order; :func:`openinference_attributes` derives the three OpenInference fields of §5.4 from
it.

**What this module is not.** It decides the *shape* of an identity, never the *existence* of
what it names: whether an id resolves to a node in ``nodes[]`` is P-01's question. §2.3 states
the grammar as a MUST on ``nodes[].id`` and nowhere else, so the strings that merely *refer*
to a node — ``entry``, ``finish``, ``from``, ``to``, ``path_map`` values,
``runtime.interrupts``, ``compensation.hook`` — are left unconstrained by the models and
resolved by the reporting stage.

Nothing here executes anything: it is string and Unicode work over already-serialized text
(WA-07).
"""

from __future__ import annotations

import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum
from typing import Annotated, Final, TypeAlias

from pydantic import AfterValidator

__all__ = [
    "OPENINFERENCE_ID",
    "OPENINFERENCE_NAME",
    "OPENINFERENCE_PARENT_ID",
    "RESERVED_SEGMENTS",
    "SEGMENT_SEPARATOR",
    "SYNTHETIC_KINDS",
    "NodeId",
    "NodeIdError",
    "NodeIdErrorReason",
    "NodeIdStr",
    "Segment",
    "SegmentKind",
    "escape_segment",
    "is_valid_node_id",
    "join_node_id",
    "node_id_from_names",
    "openinference_attributes",
    "parse_node_id",
    "split_node_id",
    "synthetic_segment",
    "unescape_segment",
    "validate_node_id",
]

#: The path delimiter (IR-SPEC §5.1). Splitting on it is context-free: a literal ``/`` in a
#: source name is always escaped, so ``node_id.split("/")`` needs no parser state.
SEGMENT_SEPARATOR: Final = "/"

#: The escape marker, and the two — and only two — escapes the grammar defines (§5.1).
ESCAPE_MARKER: Final = "%"
ESCAPED_SEPARATOR: Final = "%2F"
ESCAPED_MARKER: Final = "%25"
_ESCAPES: Final = {ESCAPED_SEPARATOR: SEGMENT_SEPARATOR, ESCAPED_MARKER: ESCAPE_MARKER}
_ESCAPE_WIDTH: Final = 3

#: The closed ``kind`` vocabulary for synthetic LCEL segments, fixed for ir_version 1.0
#: (IR-SPEC §5.2, ratified — walkthrough #1, 2026-07-18; DEC-09). Adding a token is a
#: minor-version change per IR-SPEC §8, so this set is not extensible at runtime.
SYNTHETIC_KINDS: Final[frozenset[str]] = frozenset(
    {"seq", "map", "branch", "lambda", "retry", "fallback", "bind"}
)

#: Segments reserved for the per-level entry/exit pseudo-nodes that mirror LangGraph's
#: START/END (IR-SPEC §5.1; INTROSPECTION-SPEC §3). They are never emitted as ``nodes[]``
#: entries at *any* nesting level, which is what keeps the §4.2 (m5) sentinel ban a
#: per-level property rather than a root-only one.
RESERVED_SEGMENTS: Final[frozenset[str]] = frozenset({"__start__", "__end__"})

#: The three OpenInference attribute names of the IR-SPEC §5.4 mapping (decision D-024).
OPENINFERENCE_ID: Final = "graph.node.id"
OPENINFERENCE_PARENT_ID: Final = "graph.node.parent_id"
OPENINFERENCE_NAME: Final = "graph.node.name"


class NodeIdErrorReason(str, Enum):
    """Why a node id or segment was refused — a stable code to branch on.

    These are *not* property-condition IDs: they never reach a verification envelope, and
    the PROPERTY-CATALOG-SPEC §0.4 registry neither contains nor needs them. A malformed
    node id is an IR-validity error, which the catalog places before any property runs.
    """

    EMPTY_NODE_ID = "empty-node-id"
    EMPTY_SEGMENT = "empty-segment"
    RESERVED_SEGMENT = "reserved-segment"
    UNESCAPED_SEPARATOR = "unescaped-separator"
    INVALID_ESCAPE = "invalid-escape"
    UNKNOWN_SYNTHETIC_KIND = "unknown-synthetic-kind"
    EMPTY_SELECTOR = "empty-selector"
    NOT_NFC = "not-nfc"
    NOT_A_SCALAR_VALUE = "not-a-scalar-value"


class NodeIdError(ValueError):
    """A node id, segment, or selector that the IR-SPEC §5 grammar does not admit.

    Subclassing :class:`ValueError` is load-bearing rather than decorative: pydantic turns a
    ``ValueError`` raised inside a validator into a :class:`~pydantic.ValidationError`, which
    is what lets :data:`NodeIdStr` report a bad ``nodes[].id`` the same way every other model
    error is reported.

    Attributes:
        reason: The :class:`NodeIdErrorReason` code — match on this, not on the message.
        value: The whole string that was being parsed (the node id, when there was one).
        segment: The offending segment, when the failure is attributable to one.
        segment_index: That segment's zero-based nesting level, when known.
    """

    def __init__(
        self,
        message: str,
        *,
        reason: NodeIdErrorReason,
        value: str,
        segment: str | None = None,
        segment_index: int | None = None,
    ) -> None:
        super().__init__(message)
        self.reason = reason
        self.value = value
        self.segment = segment
        self.segment_index = segment_index


class SegmentKind(Enum):
    """Which of the two disjoint §5.1 productions a segment was parsed under."""

    USER = "user"
    """A source-level name in escaped form."""
    SYNTHETIC = "synthetic"
    """An LCEL synthetic token, ``"%" kind "[" selector "]"`` (§5.2)."""


@dataclass(frozen=True, slots=True)
class Segment:
    """One nesting level of a node id, parsed.

    Attributes:
        text: The segment exactly as it appears in the node id — the escaped form, which is
            the form §5.1 compares by byte equality.
        kind: Which production admitted it.
        name: The unescaped display form — what §5.4 puts in ``graph.node.name`` when this
            is the final segment. For a synthetic segment the ``%kind[…]`` frame is
            structure rather than escaped content, so only the selector is decoded.
        synthetic_kind: The ``kind`` token, for a synthetic segment; ``None`` otherwise.
        selector: The unescaped selector, for a synthetic segment; ``None`` otherwise.
    """

    text: str
    kind: SegmentKind
    name: str
    synthetic_kind: str | None = None
    selector: str | None = None


@dataclass(frozen=True, slots=True)
class NodeId:
    """A parsed node id: the ordered path of §5.1 segments, root level first.

    Attributes:
        text: The id as written — the escaped form, byte-compared and never re-derived.
        segments: One :class:`Segment` per nesting level; always at least one.
    """

    text: str
    segments: tuple[Segment, ...]

    @property
    def parent_id(self) -> str:
        """All segments but the last, ``/``-joined; ``""`` for a top-level node (§5.4)."""
        return SEGMENT_SEPARATOR.join(segment.text for segment in self.segments[:-1])

    @property
    def name(self) -> str:
        """The unescaped display form of the final segment (§5.4)."""
        return self.segments[-1].name


def escape_segment(name: str) -> str:
    """Escape a source name into a segment: NFC-normalize, then percent-encode (§5.1).

    The order is normative and the escapes are the only two the grammar defines: ``%``
    becomes ``%25`` first, so that the ``%`` introduced by ``/`` → ``%2F`` is never escaped
    a second time.

    This is a pure transform and deliberately does not reject the reserved names: the same
    escaping rules apply to a synthetic *selector* (§5.2), where ``__start__`` is an ordinary
    source key. The reserved-segment rule is enforced wherever a segment becomes part of an
    id — :func:`join_node_id`, :func:`node_id_from_names`, and every parsing entry point.

    Raises:
        NodeIdError: if ``name`` is empty. A segment and a selector are both ``1*(…)`` in
            the grammar: non-empty after unescaping.
    """
    if not name:
        raise NodeIdError(
            "a source name is non-empty (IR-SPEC §5.1: a segment is non-empty after unescaping)",
            reason=NodeIdErrorReason.EMPTY_SEGMENT,
            value=name,
        )
    normalized = unicodedata.normalize("NFC", name)
    return normalized.replace(ESCAPE_MARKER, ESCAPED_MARKER).replace(
        SEGMENT_SEPARATOR, ESCAPED_SEPARATOR
    )


def unescape_segment(segment: str) -> str:
    """Decode a user segment back to its source name — the inverse of :func:`escape_segment`.

    Strict everywhere the grammar is: a ``/`` may not appear unescaped, and a ``%`` must
    begin exactly ``%2F`` or ``%25``. Comparison is case-sensitive (§5.1), so ``%2f`` is
    neither an escape nor an unescaped character and is refused.

    Synthetic segments are not user segments and do not decode here; read
    :attr:`Segment.name` (or :attr:`Segment.selector`) from :func:`parse_node_id` instead.

    Raises:
        NodeIdError: if ``segment`` is not a well-formed user segment.
    """
    return _decode(segment, value=segment, segment=segment, segment_index=None)


def synthetic_segment(kind: str, selector: str | int) -> str:
    """Build the synthetic segment ``"%" kind "[" selector "]"`` for an LCEL fragment (§5.2).

    ``selector`` is the source-level key when the fragment has one (a ``RunnableParallel``
    dict key, say) and the zero-based structural index otherwise; an ``int`` is rendered in
    decimal. Selectors are escaped by the §5.1 rules, so a key containing ``/`` or ``%``
    stays inside its brackets.

    A selector of any other type is a :class:`TypeError` rather than something this function
    stringifies. The narrowness is deliberate: source-level keys reach here through
    ``Any``-typed introspection reads, and calling ``str()`` on one would run code belonging
    to the object under extraction (WA-07).

    Raises:
        NodeIdError: if ``kind`` is outside the closed 1.0 vocabulary
            (:data:`SYNTHETIC_KINDS`), or if ``selector`` is an empty string.
        TypeError: if ``selector`` is neither a string nor an integer.
    """
    if kind not in SYNTHETIC_KINDS:
        raise NodeIdError(
            f"{kind!r} is not one of the ir_version 1.0 synthetic kinds "
            f"{sorted(SYNTHETIC_KINDS)} (IR-SPEC §5.2: the vocabulary is closed; adding a "
            "token is a minor-version change per §8)",
            reason=NodeIdErrorReason.UNKNOWN_SYNTHETIC_KIND,
            value=kind,
        )
    # Widened on purpose: the annotation binds typed call sites, but a source-level key
    # reaches an extractor through `Any`, so the narrowing has to happen at runtime too.
    # `str.__str__` / `int.__repr__` are called unbound so that a subclass override cannot
    # run either.
    candidate: object = selector
    if isinstance(candidate, str):
        text = str.__str__(candidate)
    elif isinstance(candidate, int) and not isinstance(candidate, bool):
        text = int.__repr__(candidate)
    else:
        raise TypeError(
            "a selector is a source-level key or a structural index (IR-SPEC §5.2), not "
            f"{type(candidate).__name__}"
        )
    return f"{ESCAPE_MARKER}{kind}[{escape_segment(text)}]"


def parse_node_id(node_id: str) -> NodeId:
    """Parse a node id into its segments, refusing anything §5.1 does not admit.

    Raises:
        NodeIdError: on an empty id, an empty segment (a leading, trailing, or doubled
            ``/``), a reserved segment at any nesting level, a malformed escape, a
            non-NFC source name, or a synthetic token outside the closed vocabulary.
    """
    if not node_id:
        raise NodeIdError(
            "a node id is non-empty (IR-SPEC §5.1: at least one segment)",
            reason=NodeIdErrorReason.EMPTY_NODE_ID,
            value=node_id,
        )
    segments = tuple(
        _parse_segment(text, value=node_id, segment_index=index)
        for index, text in enumerate(node_id.split(SEGMENT_SEPARATOR))
    )
    return NodeId(text=node_id, segments=segments)


def validate_node_id(node_id: str) -> str:
    """Return ``node_id`` if it satisfies the §5 grammar; raise :class:`NodeIdError` if not.

    Shaped to double as a pydantic ``AfterValidator`` — see :data:`NodeIdStr`.
    """
    parse_node_id(node_id)
    return node_id


def is_valid_node_id(node_id: str) -> bool:
    """Whether ``node_id`` satisfies the §5 grammar. Use :func:`validate_node_id` for why."""
    try:
        parse_node_id(node_id)
    except NodeIdError:
        return False
    return True


def split_node_id(node_id: str) -> tuple[str, ...]:
    """Split a node id into its segments in escaped form, validating as it goes.

    Equal to ``tuple(node_id.split("/"))`` on every id the grammar admits — that equality is
    the §5.1 split-safety claim, and this function is the checked way to rely on it.

    Raises:
        NodeIdError: if ``node_id`` is not admitted by the grammar.
    """
    return tuple(segment.text for segment in parse_node_id(node_id).segments)


def join_node_id(segments: Iterable[str]) -> str:
    """Join already-escaped segments into a node id, validating each one.

    Each item must already be a segment: an escaped user name (:func:`escape_segment`) or a
    synthetic token (:func:`synthetic_segment`). Passing a raw source name containing ``/``
    is an error rather than a silent extra nesting level.

    Raises:
        NodeIdError: if no segments are given, or if any of them is not a valid segment —
            including the reserved ``__start__`` / ``__end__`` at any position.
    """
    parts = tuple(segments)
    if not parts:
        raise NodeIdError(
            "a node id is non-empty (IR-SPEC §5.1: at least one segment)",
            reason=NodeIdErrorReason.EMPTY_NODE_ID,
            value="",
        )
    node_id = SEGMENT_SEPARATOR.join(parts)
    for index, text in enumerate(parts):
        _parse_segment(text, value=node_id, segment_index=index)
    return node_id


def node_id_from_names(names: Iterable[str]) -> str:
    """Build a node id from source names, one per nesting level from the graph root (§5.1).

    Each name is escaped by :func:`escape_segment`, so pass names as the source spells them.
    A path that mixes named levels with synthetic LCEL tokens is built with
    :func:`join_node_id` instead, over :func:`escape_segment` and :func:`synthetic_segment`.

    Raises:
        NodeIdError: if ``names`` is empty, if any name is empty, or if any name escapes to
            a reserved segment.
    """
    return join_node_id(escape_segment(name) for name in names)


def openinference_attributes(node_id: str) -> dict[str, str]:
    """Derive the three OpenInference node attributes of IR-SPEC §5.4 (decision D-024).

    ``graph.node.id`` is the id verbatim in escaped form, ``graph.node.parent_id`` is all
    segments but the last (``""`` for a top-level node), and ``graph.node.name`` is the
    unescaped display form of the final segment. The attributes are per-definition, not
    per-invocation: repeated executions of one node share them.

    Raises:
        NodeIdError: if ``node_id`` is not admitted by the grammar.
    """
    parsed = parse_node_id(node_id)
    return {
        OPENINFERENCE_ID: parsed.text,
        OPENINFERENCE_PARENT_ID: parsed.parent_id,
        OPENINFERENCE_NAME: parsed.name,
    }


#: A ``str`` that must satisfy the §5 grammar — the annotation ``nodes[].id`` carries, where
#: IR-SPEC §2.3 writes "``id`` MUST satisfy the §5 grammar".
#:
#: An ``AfterValidator`` rather than a pattern constraint, on purpose: the check runs in
#: Python, so ``model_json_schema()`` still emits a bare ``{"type": "string"}`` and the
#: model/schema lockstep sees no divergence from the vendored fixture schema.
NodeIdStr: TypeAlias = Annotated[str, AfterValidator(validate_node_id)]


def _decode(
    text: str,
    *,
    value: str,
    segment: str | None,
    segment_index: int | None,
) -> str:
    """Decode one escaped run left to right, refusing anything §5.1 does not admit."""
    try:
        text.encode("utf-8")
    except UnicodeEncodeError:
        raise NodeIdError(
            f"{_where(value, segment, segment_index)} contains a lone surrogate (IR-SPEC "
            "§5.1: `unescaped` is any Unicode *scalar value* except '/' and '%', and a "
            "surrogate code point is not one)",
            reason=NodeIdErrorReason.NOT_A_SCALAR_VALUE,
            value=value,
            segment=segment,
            segment_index=segment_index,
        ) from None
    decoded: list[str] = []
    position = 0
    while position < len(text):
        character = text[position]
        if character == SEGMENT_SEPARATOR:
            raise NodeIdError(
                f"{_where(value, segment, segment_index)} contains an unescaped "
                f"{SEGMENT_SEPARATOR!r} (IR-SPEC §5.1: a literal {SEGMENT_SEPARATOR!r} in a "
                f"source name escapes to {ESCAPED_SEPARATOR!r})",
                reason=NodeIdErrorReason.UNESCAPED_SEPARATOR,
                value=value,
                segment=segment,
                segment_index=segment_index,
            )
        if character != ESCAPE_MARKER:
            decoded.append(character)
            position += 1
            continue
        escape = text[position : position + _ESCAPE_WIDTH]
        if escape not in _ESCAPES:
            raise NodeIdError(
                f"{_where(value, segment, segment_index)} contains the malformed escape "
                f"{escape!r} (IR-SPEC §5.1: a {ESCAPE_MARKER!r} begins exactly "
                f"{ESCAPED_SEPARATOR!r} or {ESCAPED_MARKER!r}, case-sensitively)",
                reason=NodeIdErrorReason.INVALID_ESCAPE,
                value=value,
                segment=segment,
                segment_index=segment_index,
            )
        decoded.append(_ESCAPES[escape])
        position += _ESCAPE_WIDTH
    return "".join(decoded)


def _split_synthetic(text: str) -> tuple[str, str] | None:
    """Split a segment with the *shape* ``%<token>[<selector>]``; ``None`` if it has none.

    Shape only — the token is not checked against the closed vocabulary here, because an
    escaped user name can wear this shape (``%25seq[0]``, the source name ``%seq[0]``) and
    must still parse as the user segment it is.
    """
    if not (text.startswith(ESCAPE_MARKER) and text.endswith("]")):
        return None
    opening = text.find("[")
    if opening < 2:  # no "[", or an empty kind token between "%" and "["
        return None
    return text[1:opening], text[opening + 1 : -1]


def _parse_segment(text: str, *, value: str, segment_index: int | None) -> Segment:
    """Parse one segment under whichever of the two disjoint §5.1 productions admits it."""
    if not text:
        raise NodeIdError(
            f"{_where(value, text, segment_index)} is empty (IR-SPEC §5.1: a segment is "
            "non-empty after unescaping, so a node id carries no leading, trailing, or "
            f"doubled {SEGMENT_SEPARATOR!r})",
            reason=NodeIdErrorReason.EMPTY_SEGMENT,
            value=value,
            segment=text,
            segment_index=segment_index,
        )
    if text in RESERVED_SEGMENTS:
        raise NodeIdError(
            f"{_where(value, text, segment_index)} is the reserved segment {text!r} "
            "(IR-SPEC §5.1: __start__ and __end__ are reserved and never emitted as nodes "
            "at any nesting level)",
            reason=NodeIdErrorReason.RESERVED_SEGMENT,
            value=value,
            segment=text,
            segment_index=segment_index,
        )

    shape = _split_synthetic(text)
    if shape is not None and shape[0] in SYNTHETIC_KINDS:
        kind, raw_selector = shape
        if not raw_selector:
            raise NodeIdError(
                f"{_where(value, text, segment_index)} has an empty selector (IR-SPEC §5.2: "
                "a selector is a source-level key or a structural index, never empty)",
                reason=NodeIdErrorReason.EMPTY_SELECTOR,
                value=value,
                segment=text,
                segment_index=segment_index,
            )
        selector = _decode(raw_selector, value=value, segment=text, segment_index=segment_index)
        _require_nfc(
            selector,
            synthetic_kind=kind,
            value=value,
            segment=text,
            segment_index=segment_index,
        )
        return Segment(
            text=text,
            kind=SegmentKind.SYNTHETIC,
            name=f"{ESCAPE_MARKER}{kind}[{selector}]",
            synthetic_kind=kind,
            selector=selector,
        )

    try:
        name = _decode(text, value=value, segment=text, segment_index=segment_index)
    except NodeIdError:
        # Only call it a bad kind token when the token itself is clean; otherwise the
        # decoder's own diagnosis (a malformed escape inside `%se%25q[0]`) is the useful one.
        if shape is None or ESCAPE_MARKER in shape[0]:
            raise
        raise NodeIdError(
            f"{_where(value, text, segment_index)} is neither a user segment nor a synthetic "
            f"token: {shape[0]!r} is not one of the ir_version 1.0 kinds "
            f"{sorted(SYNTHETIC_KINDS)} (IR-SPEC §5.2: the vocabulary is closed)",
            reason=NodeIdErrorReason.UNKNOWN_SYNTHETIC_KIND,
            value=value,
            segment=text,
            segment_index=segment_index,
        ) from None
    _require_nfc(name, value=value, segment=text, segment_index=segment_index)
    return Segment(text=text, kind=SegmentKind.USER, name=name)


def _require_nfc(
    name: str,
    *,
    value: str,
    segment: str,
    segment_index: int | None,
    synthetic_kind: str | None = None,
) -> None:
    """Refuse a source name that was escaped without being NFC-normalized first (§5.1).

    ``name`` is the decoded source name, or the decoded selector when the segment is a
    synthetic token. Checking the decoded form rather than the escaped text is deliberate: an
    escape ends in ``F`` or ``5``, and inserting one can leave a following combining mark next
    to a base character it composes with (``F`` + U+0307 → U+1E1E), which would make an NFC
    test on the escaped form reject a correctly built segment.
    """
    if unicodedata.is_normalized("NFC", name):
        return
    corrected = escape_segment(name)
    if synthetic_kind is not None:
        corrected = f"{ESCAPE_MARKER}{synthetic_kind}[{corrected}]"
    raise NodeIdError(
        f"{_where(value, segment, segment_index)} is not NFC-normalized (IR-SPEC §5.1: "
        "segments are NFC-normalized before escaping, so that byte equality is a sound "
        f"comparison); the NFC form of this segment is {corrected!a}",
        reason=NodeIdErrorReason.NOT_NFC,
        value=value,
        segment=segment,
        segment_index=segment_index,
    )


def _where(value: str, segment: str | None, segment_index: int | None) -> str:
    """Name the failure site, mentioning the whole id only when it adds something."""
    if segment_index is None:
        return f"the segment {segment!r}"
    if segment == value:
        return f"segment {segment_index}, {segment!r},"
    return f"segment {segment_index} of {value!r}, {segment!r},"
