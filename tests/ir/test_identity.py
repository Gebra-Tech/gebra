"""The IR-SPEC §5 node-identity grammar, checked against the spec's own worked examples.

Three review bases are encoded here as executable tables:

* :data:`SPEC_PATH_EXAMPLES`, :data:`SPEC_ESCAPE_EXAMPLES` and
  :data:`SPEC_SYNTHETIC_EXAMPLES` — every literal identity example the §5 text writes down,
  each carrying the sentence it was transcribed from.
* :data:`SPEC_OPENINFERENCE_ROWS` — the §5.4 mapping table (decision D-024), row by row.
* :data:`SPEC_SYNTHETIC_KINDS` / :data:`SPEC_RESERVED_SEGMENTS` — the two closed
  vocabularies §5.1/§5.2 fix for 1.0, asserted equal to the module's own constants in both
  directions, so neither a dropped nor an invented token passes.

The reserved-name tests sweep every nesting level of every depth up to four, through both
the utilities and the models.

Nothing here executes a workflow, a node, or a network call (WA-07): the tests are string
and Unicode work over literal payloads.
"""

from __future__ import annotations

import unicodedata
from typing import Any

import pytest
from pydantic import ValidationError

from gebra.ir import (
    OPENINFERENCE_ID,
    OPENINFERENCE_NAME,
    OPENINFERENCE_PARENT_ID,
    RESERVED_SEGMENTS,
    SEGMENT_SEPARATOR,
    SYNTHETIC_KINDS,
    ConditionalEdge,
    Node,
    NodeIdError,
    NodeIdErrorReason,
    NormalEdge,
    SegmentKind,
    WorkflowIR,
    escape_segment,
    is_valid_node_id,
    join_node_id,
    node_id_from_names,
    openinference_attributes,
    parse_node_id,
    split_node_id,
    synthetic_segment,
    unescape_segment,
    validate_node_id,
)

#: IR-SPEC §5.2: "This spec **fixes the closed `kind` vocabulary for 1.0**: `seq`, `map`,
#: `branch`, `lambda`, `retry`, `fallback`, `bind`", in the spec's order.
SPEC_SYNTHETIC_KINDS = ("seq", "map", "branch", "lambda", "retry", "fallback", "bind")

#: IR-SPEC §5.1: "**Reserved segments**: `__start__`, `__end__`".
SPEC_RESERVED_SEGMENTS = ("__start__", "__end__")

#: (citation, source names one per nesting level, the node id the spec writes).
SPEC_PATH_EXAMPLES: tuple[tuple[str, tuple[str, ...], str], ...] = (
    (
        "§5.1 subgraph path form — 'research/tools/web_search'",
        ("research", "tools", "web_search"),
        "research/tools/web_search",
    ),
)

#: (citation, source name, the escaped segment the spec writes).
SPEC_ESCAPE_EXAMPLES: tuple[tuple[str, str, str], ...] = (
    ('§5.1 escape := "%2F" — a literal "/" in the source name', "/", "%2F"),
    ('§5.1 escape := "%25" — a literal "%" in the source name', "%", "%25"),
    (
        (
            '§5.2 disjointness — "a user\'s literal % always escapes to %25", applied to '
            "the section's own %seq[0] token"
        ),
        "%seq[0]",
        "%25seq[0]",
    ),
)

#: (citation, kind, selector, the synthetic segment the spec writes).
SPEC_SYNTHETIC_EXAMPLES: tuple[tuple[str, str, str | int, str], ...] = (
    (
        "§5.2 — 'e.g. %seq[0]', with the zero-based structural index as selector",
        "seq",
        0,
        "%seq[0]",
    ),
    (
        "§5.2 — 'e.g. %map[docs]', with the source-level key as selector",
        "map",
        "docs",
        "%map[docs]",
    ),
)

#: The §5.4 mapping table (decision D-024), as
#: (node id, graph.node.id, graph.node.parent_id, graph.node.name, what the row exercises).
SPEC_OPENINFERENCE_ROWS: tuple[tuple[str, str, str, str, str], ...] = (
    (
        "research/tools/web_search",
        "research/tools/web_search",
        "research/tools",
        "web_search",
        "the §5.1 nested-path example",
    ),
    (
        "planner",
        "planner",
        "",
        "planner",
        '§5.4: parent_id is "" for top-level nodes',
    ),
    (
        "outer/a%2Fb",
        "outer/a%2Fb",
        "outer",
        "a/b",
        "§5.4: the id stays escaped verbatim while the name is the unescaped display form",
    ),
    (
        "chain/%map[docs]",
        "chain/%map[docs]",
        "chain",
        "%map[docs]",
        "a synthetic final segment: the %kind[…] frame is structure, not escaped content",
    ),
)


# ── The §5 worked examples ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("citation", "names", "node_id"),
    SPEC_PATH_EXAMPLES,
    ids=[example[2] for example in SPEC_PATH_EXAMPLES],
)
def test_the_path_examples_reproduce(citation: str, names: tuple[str, ...], node_id: str) -> None:
    """One segment per nesting level from the graph root, joined by ``/`` (§5.1)."""
    assert node_id_from_names(names) == node_id, citation
    assert split_node_id(node_id) == names
    assert tuple(segment.name for segment in parse_node_id(node_id).segments) == names
    assert all(segment.kind is SegmentKind.USER for segment in parse_node_id(node_id).segments), (
        citation
    )


@pytest.mark.parametrize(
    ("citation", "name", "segment"),
    SPEC_ESCAPE_EXAMPLES,
    ids=[example[2] for example in SPEC_ESCAPE_EXAMPLES],
)
def test_the_escape_examples_reproduce(citation: str, name: str, segment: str) -> None:
    """Percent-escaping is exactly ``/`` → ``%2F`` and ``%`` → ``%25`` (§5.1)."""
    assert escape_segment(name) == segment, citation
    assert unescape_segment(segment) == name, citation
    assert is_valid_node_id(segment)


@pytest.mark.parametrize(
    ("citation", "kind", "selector", "segment"),
    SPEC_SYNTHETIC_EXAMPLES,
    ids=[example[3] for example in SPEC_SYNTHETIC_EXAMPLES],
)
def test_the_synthetic_token_examples_reproduce(
    citation: str, kind: str, selector: str | int, segment: str
) -> None:
    """Unnamed LCEL fragments get ``"%" kind "[" selector "]"`` (§5.2)."""
    assert synthetic_segment(kind, selector) == segment, citation
    parsed = parse_node_id(segment).segments[0]
    assert parsed.kind is SegmentKind.SYNTHETIC
    assert parsed.synthetic_kind == kind
    assert parsed.selector == str(selector)


def test_the_two_segment_productions_are_disjoint() -> None:
    """§5.1: "no string parses as both" — the escaped ``%25`` can never open a kind token."""
    assert parse_node_id("%seq[0]").segments[0].kind is SegmentKind.SYNTHETIC
    assert parse_node_id("%25seq[0]").segments[0].kind is SegmentKind.USER
    assert parse_node_id("%25seq[0]").segments[0].name == "%seq[0]"
    assert not any(kind.startswith(("2F", "25")) for kind in SYNTHETIC_KINDS)


def test_splitting_is_context_free() -> None:
    """§5.1: "Split-safe: `node_id.split("/")` is always correct with no context"."""
    node_id = node_id_from_names(("outer", "a/b", "100%"))
    assert node_id == "outer/a%2Fb/100%25"
    assert split_node_id(node_id) == tuple(node_id.split(SEGMENT_SEPARATOR))


def test_comparison_is_case_sensitive() -> None:
    """§5.1: comparison is "exact byte equality of the escaped form, case-sensitive"."""
    assert not is_valid_node_id("%2f")  # the lowercase spelling is not an escape
    assert not is_valid_node_id("%SEQ[0]")  # nor is an upcased kind token in the vocabulary
    assert is_valid_node_id("Node")
    assert is_valid_node_id("node")
    assert escape_segment("Node") != escape_segment("node")


# ── The closed vocabularies ───────────────────────────────────────────────────────────────


def test_the_synthetic_kind_vocabulary_is_exactly_the_seven_ratified_tokens() -> None:
    """§5.2 fixes the vocabulary for 1.0; additions are a minor-version change (§8)."""
    assert SYNTHETIC_KINDS == frozenset(SPEC_SYNTHETIC_KINDS)
    assert len(SPEC_SYNTHETIC_KINDS) == 7
    for kind in SPEC_SYNTHETIC_KINDS:
        assert synthetic_segment(kind, 0) == f"%{kind}[0]"


@pytest.mark.parametrize("kind", ["parallel", "assign", "seq2", "SEQ", ""])
def test_a_kind_outside_the_vocabulary_is_refused(kind: str) -> None:
    """A synthetic-shaped segment whose kind is unlisted is not a segment at all."""
    with pytest.raises(NodeIdError) as excinfo:
        synthetic_segment(kind, 0)
    assert excinfo.value.reason is NodeIdErrorReason.UNKNOWN_SYNTHETIC_KIND
    assert not is_valid_node_id(f"%{kind}[0]")


def test_the_reserved_segments_are_exactly_the_two_ratified_names() -> None:
    """§5.1 reserves the two names that mirror LangGraph's START/END."""
    assert RESERVED_SEGMENTS == frozenset(SPEC_RESERVED_SEGMENTS)


# ── Reserved names, at every nesting level ────────────────────────────────────────────────


def _paths_with_a_reserved_segment(reserved: str, depth: int) -> list[tuple[tuple[str, ...], int]]:
    """Every depth-``depth`` path carrying ``reserved`` at exactly one nesting level."""
    paths = []
    for position in range(depth):
        names = [f"level{index}" for index in range(depth)]
        names[position] = reserved
        paths.append((tuple(names), position))
    return paths


RESERVED_CASES = [
    (reserved, names, position)
    for reserved in SPEC_RESERVED_SEGMENTS
    for depth in range(1, 5)
    for names, position in _paths_with_a_reserved_segment(reserved, depth)
]
RESERVED_CASE_IDS = [SEGMENT_SEPARATOR.join(case[1]) for case in RESERVED_CASES]


@pytest.mark.parametrize(("reserved", "names", "position"), RESERVED_CASES, ids=RESERVED_CASE_IDS)
def test_a_reserved_segment_is_refused_at_every_nesting_level(
    reserved: str, names: tuple[str, ...], position: int
) -> None:
    """§5.1: reserved and never emitted as a node "at *any* nesting level"."""
    node_id = SEGMENT_SEPARATOR.join(names)

    with pytest.raises(NodeIdError) as excinfo:
        validate_node_id(node_id)
    error = excinfo.value
    assert error.reason is NodeIdErrorReason.RESERVED_SEGMENT
    assert error.segment == reserved
    assert error.segment_index == position
    assert not is_valid_node_id(node_id)

    # Both construction paths refuse it too, so a reserved name cannot be minted.
    with pytest.raises(NodeIdError):
        node_id_from_names(names)
    with pytest.raises(NodeIdError):
        join_node_id([escape_segment(name) for name in names])


@pytest.mark.parametrize(("reserved", "names", "position"), RESERVED_CASES, ids=RESERVED_CASE_IDS)
def test_the_models_refuse_a_reserved_segment_at_every_nesting_level(
    reserved: str, names: tuple[str, ...], position: int
) -> None:
    """The §2.3 MUST is enforced where the spec writes it: on ``nodes[].id``."""
    node_id = SEGMENT_SEPARATOR.join(names)

    with pytest.raises(ValidationError) as node_error:
        Node.model_validate({"id": node_id})
    assert node_error.value.errors()[0]["loc"] == ("id",)
    assert reserved in str(node_error.value)

    payload: dict[str, Any] = {
        "ir_version": "1.0",
        "entry": node_id,
        "finish": node_id,
        "nodes": ({"id": node_id},),
        "edges": (),
    }
    with pytest.raises(ValidationError) as ir_error:
        WorkflowIR.model_validate(payload)
    assert ir_error.value.errors()[0]["loc"] == ("nodes", 0, "id")


def test_a_reserved_name_is_not_reachable_by_escaping_it() -> None:
    """``__start__`` carries no ``/`` or ``%``, so escaping cannot smuggle it past the check."""
    assert escape_segment("__start__") == "__start__"
    assert not is_valid_node_id("__start__")
    assert not is_valid_node_id("outer/__start__")


def test_the_reserved_rule_does_not_reach_into_a_synthetic_selector() -> None:
    """A selector is a source-level key, not a segment, so §5.1's reservation is silent on it."""
    segment = synthetic_segment("map", "__start__")
    assert segment == "%map[__start__]"
    parsed = parse_node_id(segment).segments[0]
    assert parsed.selector == "__start__"
    assert Node.model_validate({"id": segment}).id == segment


# ── The OpenInference derivations (§5.4) ──────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("node_id", "attribute_id", "parent_id", "name", "exercises"),
    SPEC_OPENINFERENCE_ROWS,
    ids=[row[0] for row in SPEC_OPENINFERENCE_ROWS],
)
def test_the_openinference_derivations_reproduce_the_5_4_table(
    node_id: str, attribute_id: str, parent_id: str, name: str, exercises: str
) -> None:
    """§5.4: id verbatim, parent_id = all segments but the last, name = unescaped final."""
    assert openinference_attributes(node_id) == {
        OPENINFERENCE_ID: attribute_id,
        OPENINFERENCE_PARENT_ID: parent_id,
        OPENINFERENCE_NAME: name,
    }, exercises
    parsed = parse_node_id(node_id)
    assert parsed.text == attribute_id
    assert parsed.parent_id == parent_id
    assert parsed.name == name


def test_the_openinference_attribute_names_are_the_d_024_spelling() -> None:
    """The §5.4 table's left column, transcribed."""
    assert (OPENINFERENCE_ID, OPENINFERENCE_PARENT_ID, OPENINFERENCE_NAME) == (
        "graph.node.id",
        "graph.node.parent_id",
        "graph.node.name",
    )


def test_openinference_attributes_refuse_an_invalid_id() -> None:
    """Deriving telemetry fields from a malformed id would launder it into a trace."""
    with pytest.raises(NodeIdError):
        openinference_attributes("outer/__end__")


# ── The error taxonomy ────────────────────────────────────────────────────────────────────


INVALID_NODE_IDS: tuple[tuple[str, NodeIdErrorReason, str], ...] = (
    ("", NodeIdErrorReason.EMPTY_NODE_ID, "§5.1: a node id has at least one segment"),
    ("/a", NodeIdErrorReason.EMPTY_SEGMENT, "a leading separator"),
    ("a/", NodeIdErrorReason.EMPTY_SEGMENT, "a trailing separator"),
    ("a//b", NodeIdErrorReason.EMPTY_SEGMENT, "a doubled separator"),
    ("__start__", NodeIdErrorReason.RESERVED_SEGMENT, "§5.1 reserved"),
    ("__end__", NodeIdErrorReason.RESERVED_SEGMENT, "§5.1 reserved"),
    ("%", NodeIdErrorReason.INVALID_ESCAPE, "a bare escape marker"),
    ("a%", NodeIdErrorReason.INVALID_ESCAPE, "a truncated escape"),
    ("a%zz", NodeIdErrorReason.INVALID_ESCAPE, "an escape outside the two the grammar defines"),
    ("%2f", NodeIdErrorReason.INVALID_ESCAPE, "§5.1: comparison is case-sensitive"),
    ("%25%2", NodeIdErrorReason.INVALID_ESCAPE, "a truncated escape after a valid one"),
    ("%foo[0]", NodeIdErrorReason.UNKNOWN_SYNTHETIC_KIND, "§5.2: the kind vocabulary is closed"),
    ("%seq[]", NodeIdErrorReason.EMPTY_SELECTOR, "§5.2: a selector is non-empty"),
    (
        "\ud800",
        NodeIdErrorReason.NOT_A_SCALAR_VALUE,
        "§5.1: `unescaped` is any Unicode *scalar value*, which a lone surrogate is not",
    ),
    (
        "outer/%map[\udfff]",
        NodeIdErrorReason.NOT_A_SCALAR_VALUE,
        "§5.2: selectors are escaped per §5.1, so the same exclusion reaches them",
    ),
    # Written as escapes on purpose: NFC and NFD "cafe" are indistinguishable in a
    # source file, and this table needs the decomposed spelling to stay decomposed.
    ("cafe\u0301", NodeIdErrorReason.NOT_NFC, "§5.1: segments are NFC-normalized before escaping"),
    ("%map[cafe\u0301]", NodeIdErrorReason.NOT_NFC, "§5.2: selectors are escaped per §5.1"),
)


@pytest.mark.parametrize(
    ("node_id", "reason", "why"),
    INVALID_NODE_IDS,
    ids=[ascii(case[0]) for case in INVALID_NODE_IDS],
)
def test_an_invalid_node_id_is_refused_with_its_reason(
    node_id: str, reason: NodeIdErrorReason, why: str
) -> None:
    """Every refusal carries a code to branch on rather than a message to match."""
    with pytest.raises(NodeIdError) as excinfo:
        parse_node_id(node_id)
    assert excinfo.value.reason is reason, why
    assert excinfo.value.value == node_id
    assert not is_valid_node_id(node_id)
    with pytest.raises(ValidationError):
        Node.model_validate({"id": node_id})


def test_node_id_error_is_a_value_error() -> None:
    """Load-bearing: it is what lets pydantic report a bad id as a ``ValidationError``."""
    assert issubclass(NodeIdError, ValueError)


def test_a_non_string_id_is_rejected_before_the_grammar_runs() -> None:
    """Strict mode (A6 PC-3) settles the type before the §5 grammar sees the value.

    Pinned because that ordering is what keeps id validation from ever touching a payload
    object's own code (WA-07): the grammar only receives an exact ``str``. A relaxed
    ``ConfigDict`` would silently remove that ordering.
    """
    with pytest.raises(ValidationError) as excinfo:
        Node.model_validate({"id": 3})
    assert [error["type"] for error in excinfo.value.errors()] == ["string_type"]

    class _Subclass(str):
        pass

    assert type(Node.model_validate({"id": _Subclass("planner")}).id) is str


def test_a_selector_of_a_foreign_type_is_a_type_error_not_a_stringification() -> None:
    """Source keys reach ``synthetic_segment`` through ``Any``-typed reads (WA-07)."""
    with pytest.raises(TypeError):
        synthetic_segment("map", {"not": "a key"})  # type: ignore[arg-type]


#: The P-01 rows of the PROPERTY-CATALOG-SPEC §0.4 condition-ID registry — the vocabulary a
#: validator may emit, transcribed here only to keep it disjoint from the one below.
P01_CONDITION_IDS = (
    "node-unreachable-from-start",
    "dead-end-node-not-wired-to-end",
    "path-map-target-undefined",
    "orphan-node",
    "edge-target-undefined",
)


def test_the_reason_codes_are_not_condition_ids() -> None:
    """They are IR-validity codes; the PROPERTY-CATALOG-SPEC §0.4 registry owns condition IDs.

    Pinned as a test because the two vocabularies look alike and only one of them is
    emittable in a verification envelope. A malformed node id never becomes a finding: the
    registry has no row for it, and the catalog's exit code 2 covers IR validation failing
    before any property runs.
    """
    reasons = {reason.value for reason in NodeIdErrorReason}
    assert reasons.isdisjoint(P01_CONDITION_IDS)


def test_an_empty_source_name_is_refused_by_both_constructors() -> None:
    """§5.1: a segment is ``1*(…)`` — non-empty after unescaping."""
    with pytest.raises(NodeIdError) as escape_error:
        escape_segment("")
    assert escape_error.value.reason is NodeIdErrorReason.EMPTY_SEGMENT
    with pytest.raises(NodeIdError) as join_error:
        join_node_id([])
    assert join_error.value.reason is NodeIdErrorReason.EMPTY_NODE_ID


def test_join_refuses_an_unescaped_separator_rather_than_re_nesting() -> None:
    """Passing a raw source name to the segment-level constructor is an error, not a level."""
    with pytest.raises(NodeIdError) as excinfo:
        join_node_id(["outer", "a/b"])
    assert excinfo.value.reason is NodeIdErrorReason.UNESCAPED_SEPARATOR
    assert node_id_from_names(["outer", "a/b"]) == "outer/a%2Fb"


def test_unescape_refuses_a_synthetic_segment() -> None:
    """It is the user-segment decoder; a synthetic token's ``%`` is structure, not an escape."""
    with pytest.raises(NodeIdError) as excinfo:
        unescape_segment("%seq[0]")
    assert excinfo.value.reason is NodeIdErrorReason.INVALID_ESCAPE
    assert parse_node_id("%seq[0]").name == "%seq[0]"


def test_escape_segment_normalizes_but_does_not_police_reservation() -> None:
    """It escapes selectors too (§5.2), where ``__start__`` is an ordinary source key."""
    assert escape_segment("cafe\u0301") == "caf\u00e9"  # NFD in, NFC out (§5.1)
    assert unicodedata.is_normalized("NFC", escape_segment("cafe\u0301"))
    assert escape_segment("__end__") == "__end__"  # refused only once it becomes a segment


# ── Where the grammar hooks into the models ───────────────────────────────────────────────


VALID_NODE_IDS = (
    "planner",
    "research/tools/web_search",
    "outer/a%2Fb",
    "100%25",
    "chain/%seq[0]/%map[docs]",
    "%2F",
    "END",  # a node may legitimately be named END; only the reserved segments are refused
)


@pytest.mark.parametrize("node_id", VALID_NODE_IDS)
def test_the_models_accept_every_id_the_grammar_admits(node_id: str) -> None:
    assert Node.model_validate({"id": node_id}).id == node_id


def test_the_id_constraint_adds_nothing_to_the_json_schema() -> None:
    """An ``AfterValidator``, not a pattern: the model/schema lockstep sees no divergence."""
    assert Node.model_json_schema()["properties"]["id"] == {"title": "Id", "type": "string"}
    node_schema = WorkflowIR.model_json_schema()["$defs"]["Node"]["properties"]["id"]
    assert node_schema == {"title": "Id", "type": "string"}


def test_reference_role_strings_stay_unconstrained() -> None:
    """§2.3 states the MUST on ``nodes[].id`` alone, and whether a reference resolves is the
    reporting stage's question — so only the definition site carries the grammar.

    Pinned deliberately: narrowing these later is a decision, not a detail.
    """
    edge = NormalEdge.model_validate({"kind": "normal", "from": "a", "to": "END"})
    assert edge.to == "END"
    router = ConditionalEdge.model_validate(
        {"kind": "conditional", "from": "a", "path_map": {"done": "END"}}
    )
    assert router.path_map == {"done": "END"}
    # A reference the grammar would refuse as an identity still loads, for P-01 to report.
    assert NormalEdge.model_validate({"kind": "normal", "from": "a", "to": "b//c"}).to == "b//c"


def test_a_workflow_ir_with_nested_and_synthetic_ids_loads() -> None:
    """The shapes the extractor will emit: a subgraph path and a stitched LCEL fragment."""
    ir = WorkflowIR.model_validate(
        {
            "ir_version": "1.0",
            "entry": "research/tools/web_search",
            "finish": "chain/%seq[0]",
            "nodes": ({"id": "research/tools/web_search"}, {"id": "chain/%seq[0]"}),
            "edges": ({"from": "research/tools/web_search", "to": "chain/%seq[0]"},),
        }
    )
    assert tuple(node.id for node in ir.nodes) == ("research/tools/web_search", "chain/%seq[0]")
