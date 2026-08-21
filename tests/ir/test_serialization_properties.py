"""Property tests for the lossless round trip — SOW §2 criterion 6.

The goldens in ``test_serialization`` pin representative documents; these pin the claim
itself over generated ones. The adversarial surface is text: YAML re-interprets unquoted
scalars (``yes``, ``null``, ``1.0``), folds long lines, has three quoting styles and its
own line-break characters, and a loader that gets any of that wrong loses content silently.
Numbers are the second surface — YAML 1.1's float resolver refuses ``1e-05``, so a dumper
that emits it writes a string back.

Everything here is pure data (WA-07): strategies build models, and the round trip is a
function from a model to text and back.
"""

from __future__ import annotations

from typing import Any

from hypothesis import given
from hypothesis import strategies as st

from gebra.ir import (
    Annotations,
    DeterministicSpec,
    Interrupts,
    Node,
    NormalEdge,
    RecursionLimit,
    RetryPolicy,
    Runtime,
    StateField,
    Variant,
    WorkflowIR,
    dump_json,
    dump_yaml,
    load_json,
    load_yaml,
    node_id_from_names,
)
from gebra.ir.identity import RESERVED_SEGMENTS

#: Strings of Unicode scalar values — ``st.text()`` never produces surrogates.
TEXT = st.text(max_size=12)

#: The spellings a YAML round trip gets wrong when it forgets to quote, folds a long line,
#: or lets a YAML 1.1 line-break character through unescaped.
YAML_TRAPS = st.sampled_from(
    [
        "",
        " ",
        "  leading and trailing  ",
        "a  double  space",
        "yes",
        "no",
        "on",
        "off",
        "null",
        "~",
        "true",
        "1.0",
        "0x1f",
        "1e-05",
        "-",
        "- item",
        "key: value",
        "#comment",
        "*alias",
        "&anchor",
        "%directive",
        "@reserved",
        "`backtick",
        "!tag",
        "|literal",
        ">folded",
        "line\nbreak",
        "trailing\n",
        "tab\tseparated",
        "\x85next-line",
        " line-separator",
        " paragraph-separator",
        "﻿byte-order-mark",
        "\x00null-byte",
        "quote'single\"double",
        "café",
        "日本語",
        "a" * 200,
        "words " * 40,
    ]
)

#: Any string a document may carry in a free-text position.
STRINGS = TEXT | YAML_TRAPS

#: Finite doubles — the only numbers JSON has a form for.
FINITE_FLOATS = st.floats(allow_nan=False, allow_infinity=False)

#: Integers, including the ones outside the I-JSON exact range: the surface carries them
#: unchanged, and it is canonicalization that refuses them (PD-004).
INTEGERS = st.integers(min_value=-(2**70), max_value=2**70)

#: Source names a §5 segment can be built from.
NAMES = st.text(min_size=1, max_size=6).filter(lambda name: name not in RESERVED_SEGMENTS)


@st.composite
def node_ids(draw: st.DrawFn) -> str:
    """A §5-legal node id built from generated source names, escaping and NFC included."""
    names = draw(st.lists(NAMES, min_size=1, max_size=3))
    try:
        return node_id_from_names(names)
    except ValueError:  # a name that normalizes to an inadmissible segment
        return "fallback"


def foreign_json(max_leaves: int = 12) -> st.SearchStrategy[Any]:
    """The ``args_schema`` interior: a foreign JSON Schema object, carried verbatim."""
    leaves = st.none() | st.booleans() | INTEGERS | FINITE_FLOATS | STRINGS
    return st.recursive(
        leaves,
        lambda children: (
            st.lists(children, max_size=3) | st.dictionaries(STRINGS, children, max_size=3)
        ),
        max_leaves=max_leaves,
    )


@st.composite
def node_annotations(draw: st.DrawFn) -> Annotations:
    """A node contract with every slot reachable."""
    return Annotations(
        pure=draw(st.none() | st.booleans()),
        effect=draw(st.none() | st.lists(STRINGS, max_size=3).map(tuple)),
        idempotent=draw(st.none() | st.booleans()),
        deterministic=draw(
            st.none()
            | st.booleans()
            | st.builds(
                DeterministicSpec,
                seed=INTEGERS,
                temperature=st.none() | FINITE_FLOATS,
            )
        ),
        input=draw(st.none() | st.lists(STRINGS, max_size=3).map(tuple)),
        output=draw(st.none() | st.lists(STRINGS, max_size=3).map(tuple)),
        source=draw(st.none() | STRINGS),
        map=draw(st.none() | STRINGS),
        args_schema=draw(st.none() | st.dictionaries(STRINGS, foreign_json(), max_size=3)),
        retry_policy=draw(
            st.none()
            | st.builds(
                RetryPolicy,
                max_attempts=INTEGERS,
                retry_on=st.lists(STRINGS, max_size=3).map(tuple),
            )
        ),
        variant=draw(st.none() | st.builds(Variant, key=STRINGS, measure=STRINGS)),
        prompt_digest=draw(st.none() | STRINGS),
        config_digest=draw(st.none() | STRINGS),
    )


@st.composite
def workflow_irs(draw: st.DrawFn) -> WorkflowIR:
    """A generated ``WorkflowIR`` — shape-valid, not necessarily well-formed as a graph."""
    ids = draw(st.lists(node_ids(), min_size=1, max_size=3))
    nodes = tuple(
        Node(id=node_id, annotations=draw(st.none() | node_annotations())) for node_id in ids
    )
    edges = tuple(
        NormalEdge(kind="normal", **{"from": node_id}, to=draw(st.sampled_from([*ids, "END"])))
        for node_id in ids
    )
    state_values = st.none() | st.dictionaries(
        STRINGS,
        STRINGS | st.builds(StateField, type=STRINGS, optional=st.none() | st.booleans()),
        max_size=3,
    )
    runtime = st.none() | st.builds(
        Runtime,
        recursion_limit=st.none()
        | st.builds(RecursionLimit, value=INTEGERS, justification=STRINGS),
        interrupts=st.none()
        | st.builds(
            Interrupts,
            before=st.none() | st.lists(st.sampled_from(ids), max_size=2).map(tuple),
            after=st.none() | st.lists(st.sampled_from(ids), max_size=2).map(tuple),
        ),
    )
    return WorkflowIR(
        ir_version="1.0",
        entry=draw(st.sampled_from(ids) | st.just(tuple(ids))),
        finish=draw(st.sampled_from(ids) | st.just(tuple(ids))),
        state=draw(state_values),
        nodes=nodes,
        edges=edges,
        runtime=draw(runtime),
    )


@given(ir=workflow_irs())
def test_a_workflow_round_trips_through_yaml(ir: WorkflowIR) -> None:
    """SOW §2 criterion 6 over generated documents — YAML, by model equality."""
    assert load_yaml(WorkflowIR, dump_yaml(ir)) == ir


@given(ir=workflow_irs())
def test_a_workflow_round_trips_through_json(ir: WorkflowIR) -> None:
    """SOW §2 criterion 6 over generated documents — JSON, by model equality."""
    assert load_json(WorkflowIR, dump_json(ir)) == ir


@given(ir=workflow_irs())
def test_the_two_formats_carry_the_same_model(ir: WorkflowIR) -> None:
    """A document written as YAML and the same document written as JSON load equal."""
    assert load_yaml(WorkflowIR, dump_yaml(ir)) == load_json(WorkflowIR, dump_json(ir))


@given(ir=workflow_irs())
def test_the_dumps_are_fixed_points(ir: WorkflowIR) -> None:
    """Writing a reloaded document reproduces the same text — no drift under repeated
    round trips, which is what makes a surface file diffable."""
    for dump, load in ((dump_yaml, load_yaml), (dump_json, load_json)):
        text = dump(ir)
        assert dump(load(WorkflowIR, text)) == text


@given(value=STRINGS)
def test_arbitrary_text_survives_in_a_free_text_position(value: str) -> None:
    """The adversarial half: whatever YAML would do to this string unquoted, the round trip
    returns it unchanged."""
    limit = RecursionLimit(value=1, justification=value)
    assert load_yaml(RecursionLimit, dump_yaml(limit)) == limit
    assert load_json(RecursionLimit, dump_json(limit)) == limit


@given(key=STRINGS, name=STRINGS)
def test_arbitrary_text_survives_as_a_mapping_key(key: str, name: str) -> None:
    """State keys and foreign member names are text too."""
    annotation = Annotations(args_schema={key: name})
    assert load_yaml(Annotations, dump_yaml(annotation)) == annotation
    assert load_json(Annotations, dump_json(annotation)) == annotation


@given(seed=INTEGERS, temperature=FINITE_FLOATS)
def test_numbers_survive_both_formats(seed: int, temperature: float) -> None:
    """Integers of any width and every finite double, including the ones YAML 1.1's float
    resolver would refuse to read back if they were emitted as ``repr`` gives them."""
    spec = DeterministicSpec(seed=seed, temperature=temperature)
    assert load_yaml(DeterministicSpec, dump_yaml(spec)) == spec
    assert load_json(DeterministicSpec, dump_json(spec)) == spec


@given(schema=foreign_json(max_leaves=25))
def test_foreign_content_survives_verbatim(schema: Any) -> None:
    """``args_schema`` is carried, not interpreted: nulls, array order, empty containers,
    nesting and number widths all come back as authored."""
    annotation = Annotations(args_schema={"schema": schema})
    for dump, load in ((dump_yaml, load_yaml), (dump_json, load_json)):
        reloaded = load(Annotations, dump(annotation))
        assert reloaded == annotation
        assert reloaded.args_schema == {"schema": schema}
