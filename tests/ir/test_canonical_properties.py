"""Property tests for the RFC 8785 emitter and the digest's order-insensitivity.

The §6 contract is byte-exact reproducibility, so the emitter's two hand-written parts —
ES number formatting and the UTF-16 member sort — get adversarial inputs rather than only
the table-driven pins in ``test_canonical``. Everything here is pure data (WA-07).
"""

from __future__ import annotations

import json
import math
import re
from typing import Any

from hypothesis import given
from hypothesis import strategies as st

from gebra.ir.canonical import _emit, _format_double, _utf16_sort_key, graph_version
from gebra.ir.models import WorkflowIR

#: Strings of Unicode scalar values — what the walk admits into a canonical tree.
#: ``st.text()`` never produces surrogates, so its output is exactly this set.
SCALAR_TEXT = st.text()

#: Finite doubles — step 5 has excluded NaN and the infinities before emission.
FINITE_FLOATS = st.floats(allow_nan=False, allow_infinity=False)

#: Integers within the I-JSON exact range (IR-SPEC §6.3; PD-004).
EXACT_INTEGERS = st.integers(min_value=-(2**53 - 1), max_value=2**53 - 1)

#: The four ECMAScript ``Number::toString`` output shapes for a finite double: zero,
#: integer, positional decimal, and exponential (sign always on the exponent, no leading
#: zeros anywhere, no trailing fraction zeros — shortest-digits output has none).
ES_NUMBER_GRAMMAR = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]*[1-9])?(?:e[+-][1-9][0-9]*)?$")


def json_trees(max_leaves: int = 20) -> st.SearchStrategy[Any]:
    """Recursive JSON values built only from what a canonical tree may hold."""
    leaves = st.none() | st.booleans() | EXACT_INTEGERS | FINITE_FLOATS | SCALAR_TEXT
    return st.recursive(
        leaves,
        lambda children: (
            st.lists(children, max_size=4) | st.dictionaries(SCALAR_TEXT, children, max_size=4)
        ),
        max_leaves=max_leaves,
    )


@given(value=FINITE_FLOATS)
def test_formatted_doubles_round_trip_exactly(value: float) -> None:
    """RFC 8785 §3.2.2.3 rests on shortest-round-trip digits: parsing the rendering back
    recovers the identical double (±0.0 both render ``"0"``, which parses to +0.0)."""
    rendered = _format_double(value)
    if value == 0.0:
        assert rendered == "0"
    else:
        assert float(rendered) == value


@given(value=FINITE_FLOATS)
def test_formatted_doubles_match_the_es_output_grammar(value: float) -> None:
    """Never ``1e16``-style bare exponents, no ``.0`` tails, no padded ``e-07``."""
    assert ES_NUMBER_GRAMMAR.match(_format_double(value))


@given(value=EXACT_INTEGERS)
def test_integers_emit_as_plain_decimal(value: int) -> None:
    assert _emit(value) == str(value).encode("ascii")


def _code_units(value: str) -> list[int]:
    """An independent UTF-16 code-unit expansion, from the surrogate formulas of the
    Unicode standard — deliberately not ``encode("utf-16-be")``, which the implementation
    uses, so the two derivations check each other."""
    units: list[int] = []
    for character in value:
        point = ord(character)
        if point <= 0xFFFF:
            units.append(point)
        else:
            shifted = point - 0x10000
            units.append(0xD800 + (shifted >> 10))
            units.append(0xDC00 + (shifted & 0x3FF))
    return units


@given(left=SCALAR_TEXT, right=SCALAR_TEXT)
def test_the_sort_key_orders_exactly_as_utf16_code_units(left: str, right: str) -> None:
    """RFC 8785 §3.2.3: pure value comparison of 16-bit code units."""
    by_key = sorted([left, right], key=_utf16_sort_key)
    by_units = sorted([left, right], key=_code_units)
    assert by_key == by_units


def _equivalent(left: object, right: object) -> bool:
    """Value equivalence under JSON's single number type.

    ES prints an integral double positionally up to 10²¹ (``2.890028398088411e+16`` emits
    as ``"28900283980884110"``), which ``json.loads`` parses as an ``int`` — a value whose
    *exact* integer can sit between doubles, so ``int == float`` is the wrong comparison.
    Both sides map through ``float``: sound over this domain, because tree integers stay
    within ±(2⁵³−1) (float-exact) and the emitted digits round-trip by construction.
    """
    if isinstance(left, bool) or isinstance(right, bool):
        return left is right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return float(left) == float(right)
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(_equivalent(a, b) for a, b in zip(left, right))
    if isinstance(left, dict) and isinstance(right, dict):
        return left.keys() == right.keys() and all(
            _equivalent(member, right[name]) for name, member in left.items()
        )
    return left == right


@given(tree=json_trees())
def test_emitted_bytes_are_json_that_parses_back_equivalent(tree: object) -> None:
    """The emitter serializes JSON, not a private dialect: ``json.loads`` recovers an
    equivalent value (see :func:`_equivalent` for the one number-type wrinkle)."""
    blob = _emit(tree)
    assert _equivalent(json.loads(blob.decode("utf-8")), tree)


@given(tree=st.dictionaries(SCALAR_TEXT, st.none() | st.booleans(), max_size=6))
def test_member_emission_order_is_the_sorted_key_order(tree: dict[str, Any]) -> None:
    parsed: dict[str, Any] = json.loads(_emit(tree).decode("utf-8"))
    assert list(parsed) == sorted(tree, key=_utf16_sort_key)


@given(data=st.data())
def test_the_digest_ignores_every_authored_ordering(data: st.DataObject) -> None:
    """§6.2/§6.4: authored order of ``nodes[]``, ``edges[]``, and the set-valued arrays is
    normalized away, so any permutation of the authored document digests identically."""
    nodes = [
        {"id": "a", "annotations": {"effect": ["x", "y"], "input": ["k1", "k2"]}},
        {"id": "b"},
        {"id": "c"},
    ]
    edges = [
        {"from": "a", "to": "b"},
        {"from": "b", "to": "c"},
        {"from": "c", "kind": "conditional", "path_map": {"p": "a", "q": "b"}},
    ]
    reference = {
        "ir_version": "1.0",
        "entry": ["a", "b"],
        "finish": "c",
        "state": {"k1": "str", "k2": "str"},
        "nodes": nodes,
        "edges": edges,
    }
    shuffled = dict(reference)
    shuffled["nodes"] = data.draw(st.permutations(nodes))
    shuffled["edges"] = data.draw(st.permutations(edges))
    shuffled["entry"] = data.draw(st.permutations(["a", "b"]))

    def load(payload: dict[str, Any]) -> WorkflowIR:
        return WorkflowIR.model_validate_json(json.dumps(payload))

    assert graph_version(load(shuffled)) == graph_version(load(reference))


@given(value=FINITE_FLOATS)
def test_a_float_emits_identically_alone_and_inside_a_tree(value: float) -> None:
    """No context-dependence: the number rendering is one function of the value."""
    assert _emit({"x": value}) == b'{"x":' + _format_double(value).encode("ascii") + b"}"
    assert not math.isnan(value)
