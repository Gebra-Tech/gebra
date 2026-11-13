"""The graph-level declaration — ANNOTATION-API-SPEC §1a (ratified — DEC-36, 2026-10-28).

``gebra.recursion_limit(graph, value, justification=…)`` declares ``runtime.recursion_limit``,
P-02's witness form (b), on the graph's builder. Four claims, one section each: the **carrier**
is the builder every compiled copy shares; the **call-time rules** refuse at the call, error-grade;
the slot is settable **at most once per carrier**; and the **shared validator** — the one the
sidecar's ``[runtime]`` table and the extraction-time read of a hand-set attribute also run —
reads what it is handed through unbound built-in accessors only. The extraction side is
``tests/extraction/test_runtime.py``; the WA-07 claim for the call itself is the guarded child at
the bottom, in an interpreter where the substrate cannot be imported at all.
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

import gebra
from gebra.annotations import (
    RUNTIME_ATTRIBUTE,
    ContractErrorReason,
    GebraContractError,
    RecursionLimitViolation,
    recursion_limit,
)
from gebra.annotations.runtime import (
    RECURSION_LIMIT_SLOT,
    check_recursion_limit,
    check_runtime_attribute,
    describe_declared,
    own_namespace,
    type_label,
)
from gebra.ir.models import RecursionLimit
from gebra.naming import type_identity
from tests.sample_workflows import sentinel_graph as sg
from tests.sample_workflows import sentinel_runtime as sr

REPO_ROOT = str(Path(__file__).resolve().parents[2])

V = RecursionLimitViolation


@pytest.fixture(autouse=True)
def _clear_ledgers() -> Any:
    sg.TRIPPED.clear()
    sr.HOOKS.clear()
    sr.CARRIER_READS.clear()
    yield
    assert sg.TRIPPED == [], sg.TRIPPED


def _held(obj: object) -> object:
    namespace = own_namespace(obj)
    assert namespace is not None
    return namespace.get(RUNTIME_ATTRIBUTE)


# ── The carrier: the builder every compiled copy shares ──────────────────────────────────


def test_the_top_level_name_is_the_annotation_surfaces_own() -> None:
    """§1a: "the eleventh lazily resolved top-level name" — resolved out of the annotations."""
    assert gebra.recursion_limit is recursion_limit
    assert "recursion_limit" in gebra.__all__
    assert len(gebra.__all__) == 11


def test_the_call_returns_the_object_it_was_given() -> None:
    builder = sr.build_review_loop()

    assert recursion_limit(builder, 38, justification="three laps") is builder


def test_on_a_builder_the_builder_carries_the_declaration_in_the_ruled_shape() -> None:
    builder = recursion_limit(sr.build_review_loop(), 38, justification="three laps")

    assert _held(builder) == {"recursion_limit": {"value": 38, "justification": "three laps"}}


def test_on_a_compiled_graph_the_declaration_lands_on_its_builder() -> None:
    """§1a: "when the object exposes a ``.builder`` backreference … the attribute lands on that
    builder" — the compiled object is not a carrier, because ``with_config`` drops it."""
    compiled = sr.build_review_loop().compile()

    assert recursion_limit(compiled, 38, justification="three laps") is compiled
    assert RUNTIME_ATTRIBUTE in own_namespace(compiled.builder)  # type: ignore[operator]
    assert RUNTIME_ATTRIBUTE not in own_namespace(compiled)  # type: ignore[operator]


def test_every_with_config_copy_shares_the_one_declaration() -> None:
    """§6: the builder "survives compilation and binding intact" — so a copy made before or after
    the call carries the declaration through its own ``.builder``."""
    compiled = sr.build_review_loop().compile()
    before = compiled.with_config(recursion_limit=5)
    recursion_limit(compiled, 38, justification="three laps")
    after = compiled.with_config(recursion_limit=7)

    assert before.builder is compiled.builder is after.builder
    assert _held(after.builder) is _held(compiled.builder)


def test_an_object_with_no_builder_carries_the_declaration_itself() -> None:
    """§1a: "only an object with no builder carries the attribute itself"."""
    pregel = sr.build_review_pregel()

    recursion_limit(pregel, 38, justification="three laps")

    assert _held(pregel) == {"recursion_limit": {"value": 38, "justification": "three laps"}}


def test_a_builderless_copy_made_after_the_call_carries_nothing() -> None:
    """The measured gap the EX-D3 critique named: ``with_config`` rebuilds the object through its
    constructor and drops the attribute (A1 addendum A1-D36) — bind first, then declare."""
    copy = sr.declare_pregel().with_config(recursion_limit=38)

    assert RUNTIME_ATTRIBUTE not in own_namespace(copy)  # type: ignore[operator]


def test_the_stored_members_are_exact_types_even_for_subclassed_arguments() -> None:
    """The call stores the slot's own values: an ``int`` subclass and a ``str`` subclass become an
    exact ``int`` and an exact ``str``, read through ``int.__index__``/``str.__str__``."""
    builder = recursion_limit(
        sr.build_review_loop(), sr.RecordingInt(38), justification=sr.RecordingText("three laps")
    )
    stored = _held(builder)["recursion_limit"]  # type: ignore[index]

    assert type(stored["value"]) is int and stored["value"] == 38
    assert type(stored["justification"]) is str
    assert sr.HOOKS == []


# ── Call-time rules: error-grade, at the call ────────────────────────────────────────────


@pytest.mark.parametrize(
    ("value", "justification", "violation"),
    [
        (True, "a reason", V.VALUE_NOT_AN_INTEGER),
        (False, "a reason", V.VALUE_NOT_AN_INTEGER),
        (38.0, "a reason", V.VALUE_NOT_AN_INTEGER),
        ("38", "a reason", V.VALUE_NOT_AN_INTEGER),
        (None, "a reason", V.VALUE_NOT_AN_INTEGER),
        (0, "a reason", V.VALUE_BELOW_ONE),
        (-1, "a reason", V.VALUE_BELOW_ONE),
        (2**53, "a reason", V.VALUE_OUT_OF_RANGE),
        (38, "", V.JUSTIFICATION_BLANK),
        (38, "   \t\n", V.JUSTIFICATION_BLANK),
        (38, None, V.JUSTIFICATION_NOT_A_STRING),
        (38, 7, V.JUSTIFICATION_NOT_A_STRING),
        (38, "lone \ud800 surrogate", V.JUSTIFICATION_UNENCODABLE),
    ],
)
def test_each_call_time_rule_raises_at_the_call(
    value: object, justification: object, violation: RecursionLimitViolation
) -> None:
    """§1a: ``value`` is an ``int`` that is not a ``bool``, ≥ 1, within ±(2⁵³−1); ``justification``
    has a non-whitespace character. The refusal names the slot and the clause, and nothing lands."""
    builder = sr.build_review_loop()

    with pytest.raises(GebraContractError) as caught:
        recursion_limit(builder, value, justification=justification)  # type: ignore[arg-type]

    assert caught.value.reason is ContractErrorReason.SLOT_VALUE_INVALID
    assert caught.value.slot == RECURSION_LIMIT_SLOT
    assert check_recursion_limit({"value": value, "justification": justification}).violations == (
        violation,
    )
    assert RUNTIME_ATTRIBUTE not in own_namespace(builder)  # type: ignore[operator]


def test_the_boundary_values_are_accepted() -> None:
    """``1`` is the substrate's floor and ``2**53 − 1`` the largest exact integer — both in."""
    assert recursion_limit(sr.build_review_loop(), 1, justification="x") is not None
    assert recursion_limit(sr.build_review_loop(), 2**53 - 1, justification="x") is not None


def test_a_refusal_never_renders_the_rejected_value() -> None:
    """A rejected value is named by its type, never through its own ``__repr__``/``__str__``."""
    with pytest.raises(GebraContractError, match="value is a builtins:float"):
        recursion_limit(sr.build_review_loop(), 38.5, justification="x")  # type: ignore[arg-type]


@pytest.mark.parametrize("value", [10**5000, -(10**5000)], ids=["huge", "huge-negative"])
def test_a_number_past_the_integer_string_limit_is_refused_not_crashed_on(value: int) -> None:
    """A value the interpreter will not render (4300 digits) is named, never rendered, so the
    call refuses with its own error rather than letting a ``ValueError`` escape."""
    with pytest.raises(GebraContractError, match="outside the I-JSON exact range") as caught:
        recursion_limit(sr.build_review_loop(), value, justification="x")

    assert caught.value.reason is ContractErrorReason.SLOT_VALUE_INVALID


def test_the_justification_is_a_required_keyword() -> None:
    """Both members are declared together: the call has no form that omits the justification."""
    with pytest.raises(TypeError):
        recursion_limit(sr.build_review_loop(), 38)  # type: ignore[call-arg]


# ── At most once per carrier ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize("second", ["builder", "compiled", "copy"])
def test_a_second_declaration_on_one_carrier_is_an_error_identical_value_included(
    second: str,
) -> None:
    """§1a: "a second call on the builder or on any copy of it, identical value included, is an
    error (the §1 duplicate rule)"."""
    builder = sr.build_review_loop()
    compiled = builder.compile()
    recursion_limit(builder, 38, justification="three laps")
    target = {
        "builder": builder,
        "compiled": compiled,
        "copy": compiled.with_config(recursion_limit=38),
    }[second]

    with pytest.raises(GebraContractError) as caught:
        recursion_limit(target, 38, justification="three laps")

    assert caught.value.reason is ContractErrorReason.DUPLICATE_SLOT
    assert caught.value.slot == RECURSION_LIMIT_SLOT


def test_a_foreign_value_in_the_attribute_is_never_overwritten() -> None:
    """gebra owns ``__gebra_runtime__`` and will not overwrite something it did not attach."""
    builder = sr.build_review_loop()
    builder.__gebra_runtime__ = "somebody else's"  # type: ignore[attr-defined]

    with pytest.raises(GebraContractError, match="gebra did not attach") as caught:
        recursion_limit(builder, 38, justification="three laps")

    assert caught.value.reason is ContractErrorReason.SLOT_VALUE_INVALID
    assert builder.__gebra_runtime__ == "somebody else's"  # type: ignore[attr-defined]


def test_a_hand_set_declaration_the_call_would_refuse_is_not_reported_as_a_duplicate() -> None:
    """Only a declaration the call could have attached is a duplicate; one that extraction would
    ignore (a blank justification set by hand) is something gebra did not attach."""
    builder = sr.build_review_loop()
    builder.__gebra_runtime__ = {  # type: ignore[attr-defined]
        "recursion_limit": {"value": 38, "justification": " "}
    }

    with pytest.raises(GebraContractError, match="gebra did not attach") as caught:
        recursion_limit(builder, 38, justification="three laps")

    assert caught.value.reason is ContractErrorReason.SLOT_VALUE_INVALID


# ── A carrier that will not hold the attribute ───────────────────────────────────────────


class _Slotted:
    __slots__ = ("builder",)

    def __init__(self) -> None:
        self.builder = None


class _Swallowing:
    """Accepts every assignment and keeps none of them."""

    def __setattr__(self, name: str, value: object) -> None:
        return None


def test_an_object_that_refuses_the_attribute_is_an_error() -> None:
    """§1a: "an object that refuses attribute assignment is an error, never a silently dropped
    declaration" — and the error points at the sidecar."""
    with pytest.raises(GebraContractError, match=r"\[runtime\] table") as caught:
        recursion_limit(_Slotted(), 38, justification="three laps")

    assert caught.value.reason is ContractErrorReason.ATTACHMENT_IMPOSSIBLE


def test_an_object_that_swallows_the_assignment_is_an_error_too() -> None:
    """A ``__setattr__`` that accepts and drops the write would be a silently dropped declaration;
    the call checks that the carrier's own dictionary holds it."""
    with pytest.raises(GebraContractError, match="does not hold it") as caught:
        recursion_limit(_Swallowing(), 38, justification="three laps")

    assert caught.value.reason is ContractErrorReason.ATTACHMENT_IMPOSSIBLE


def test_a_carrier_whose_class_defines_the_attribute_as_a_property_refuses() -> None:
    """:class:`~tests.sample_workflows.sentinel_runtime.ArmedRuntimeBuilder`'s property has no
    setter, so the assignment raises — and the property itself is never read by the call."""
    builder = sr.build_review_loop(sr.ArmedRuntimeBuilder)

    with pytest.raises(GebraContractError) as caught:
        recursion_limit(builder, 38, justification="three laps")

    assert caught.value.reason is ContractErrorReason.ATTACHMENT_IMPOSSIBLE
    assert sg.TRIPPED == []


# ── The shared validator ─────────────────────────────────────────────────────────────────


def test_a_valid_object_resolves_to_the_ir_slot() -> None:
    checked = check_recursion_limit({"value": 38, "justification": "three laps"})

    assert checked.declaration == RecursionLimit(value=38, justification="three laps")
    assert checked.violations == ()


@pytest.mark.parametrize(
    ("declared", "violations"),
    [
        ("38", (V.NOT_AN_OBJECT,)),
        ([38, "x"], (V.NOT_AN_OBJECT,)),
        ({}, (V.VALUE_MISSING, V.JUSTIFICATION_MISSING)),
        ({"value": 38}, (V.JUSTIFICATION_MISSING,)),
        ({"justification": "x"}, (V.VALUE_MISSING,)),
        ({"value": True, "justification": " "}, (V.VALUE_NOT_AN_INTEGER, V.JUSTIFICATION_BLANK)),
        ({"value": 38, "justification": "x", "note": "y"}, (V.MEMBER_UNKNOWN,)),
        ({"value": 38, "justification": "x", 1: "y"}, (V.MEMBER_UNKNOWN,)),
    ],
)
def test_every_violation_is_reported_in_one_verdict(
    declared: object, violations: tuple[RecursionLimitViolation, ...]
) -> None:
    """Shape first, then ``value``, then ``justification`` — every clause the object breaks."""
    checked = check_recursion_limit(declared)

    assert checked.declaration is None
    assert checked.violations == violations
    assert len(checked.reasons) == len(violations)


def test_a_planted_key_is_a_member_unknown_and_never_compared() -> None:
    """A ``str``-subclass key spelled ``value`` is not the member: the key test is exact type, so
    its own ``__eq__``/``__hash__`` never run under the read (DEC-38 §3.2's discipline)."""
    declared = {sr.RecordingKey("value"): 38, "justification": "x"}
    sr.HOOKS.clear()

    checked = check_recursion_limit(declared)

    assert checked.violations == (V.MEMBER_UNKNOWN, V.VALUE_MISSING)
    assert sr.HOOKS == []


def test_the_validator_runs_none_of_a_hostile_declarations_own_methods() -> None:
    """A ``dict`` subclass, an ``int`` subclass and a ``str`` subclass, all recording: the read is
    ``dict.items``, ``int.__index__``, ``str.__str__`` and ``str.strip``, unbound."""
    inner = sr.RecordingDict(
        value=sr.RecordingInt(38), justification=sr.RecordingText("three laps")
    )
    outer = sr.RecordingDict(recursion_limit=inner)
    sr.HOOKS.clear()

    checked = check_runtime_attribute(outer)

    assert checked.declaration == RecursionLimit(value=38, justification="three laps")
    assert type(checked.declaration.value) is int
    assert type(checked.declaration.justification) is str
    assert sr.HOOKS == []


@pytest.mark.parametrize(
    "carried",
    [
        "a string",
        {},
        {"recursion_limit": {"value": 38, "justification": "x"}, "extra": 1},
        {"limit": {"value": 38, "justification": "x"}},
        {sr.RecordingKey("recursion_limit"): {"value": 38, "justification": "x"}},
    ],
)
def test_an_attribute_that_is_not_the_declarations_shape_is_not_a_declaration(
    carried: object,
) -> None:
    """§1a: an attribute "that is not the declaration's shape" is ignored — the outer shape is
    exactly ``{"recursion_limit": {…}}``."""
    sr.HOOKS.clear()

    checked = check_runtime_attribute(carried)

    assert checked.violations == (V.NOT_A_DECLARATION,)
    assert sr.HOOKS == []


def test_the_violation_vocabulary_is_closed_and_spelled_once() -> None:
    assert {violation.value for violation in RecursionLimitViolation} == {
        "value-missing",
        "value-not-an-integer",
        "value-below-one",
        "value-out-of-range",
        "justification-missing",
        "justification-not-a-string",
        "justification-blank",
        "justification-unencodable",
        "not-an-object",
        "member-unknown",
        "not-a-declaration",
    }


# ── own_namespace: the instance dictionary, never through the object's own access ───────


def test_own_namespace_reads_past_a_dunder_dict_property_and_a_recording_getattribute() -> None:
    """``vars()`` and ``getattr(obj, "__dict__")`` would run both; the descriptor read — the
    interpreter's own getset, found on the real MRO past the subclass's property — runs neither."""
    reads: list[str] = []

    class Plain:
        pass

    class Hostile(Plain):
        @property
        def __dict__(self) -> Any:  # type: ignore[override]
            reads.append("__dict__ property")
            raise AssertionError("the __dict__ property ran")

        def __getattribute__(self, name: str) -> Any:
            reads.append(name)
            return object.__getattribute__(self, name)

    target = Hostile()
    object.__setattr__(target, "anything", 1)
    reads.clear()

    namespace = own_namespace(target)

    assert namespace == {"anything": 1}
    assert reads == []


def test_a_class_with_no_dictionary_getset_has_no_readable_namespace_and_refuses_the_call() -> None:
    """A root class whose own body defines ``__dict__`` keeps the interpreter from installing its
    getset at all, so there is no descriptor to read through — no namespace, and the call refuses
    rather than claim a declaration it cannot show landed."""

    class RootProperty:
        @property
        def __dict__(self) -> Any:  # type: ignore[override]
            raise AssertionError("the __dict__ property ran")

    target = RootProperty()

    assert own_namespace(target) is None
    with pytest.raises(GebraContractError) as caught:
        recursion_limit(target, 38, justification="three laps")
    assert caught.value.reason is ContractErrorReason.ATTACHMENT_IMPOSSIBLE


def test_a_foreign_getset_named_dict_is_not_taken_for_the_instance_dictionary() -> None:
    """A class body may bind ``__dict__`` to another class's getset, or to a getset with another
    name: neither is the interpreter's instance-dictionary getset *for that class*, so the read
    passes over it rather than calling it, and the call refuses rather than raising."""

    class Borrowed:
        __dict__ = type.__dict__["__doc__"]

    class Foreign:
        __dict__ = _Plain.__dict__["__dict__"]

    for target in (Borrowed(), Foreign()):
        assert own_namespace(target) is None
        with pytest.raises(GebraContractError) as caught:
            recursion_limit(target, 38, justification="x")
        assert caught.value.reason is ContractErrorReason.ATTACHMENT_IMPOSSIBLE


# ── type_label and describe_declared: naming without running ─────────────────────────────


class _Plain:
    pass


@pytest.mark.parametrize(
    "value",
    [
        1,
        "x",
        True,
        None,
        1.5,
        {},
        [],
        (),
        b"",
        _Plain(),
        sr.RecordingInt(3),
        len,
        lambda: 0,
        int,
        "x".upper,
    ],
    ids=lambda value: type(value).__name__,
)
def test_type_label_spells_an_honest_type_as_type_identity_does(value: object) -> None:
    """The house spelling, ``"<top-level package>:<qualname>"`` (INTROSPECTION-SPEC §7.4) —
    built-in types whose own namespace keeps a descriptor under ``__module__`` (``function``,
    ``builtin_function_or_method``, ``type``) included: their module comes from the C-level
    name, as ``type_identity``'s does."""
    assert type_label(value) == type_identity(value)


@pytest.mark.parametrize(
    ("route", "label"),
    [
        ("module-holds-a-surrogate", ":ModuleHoldsASurrogate"),
        ("qualname-holds-a-surrogate", "tests:<unnamed>"),
    ],
)
def test_type_label_never_carries_a_name_utf8_cannot_encode(route: str, label: str) -> None:
    """A ``__module__`` or ``__qualname__`` assigned by hand can hold a lone surrogate, which no
    report can carry; such a module is the empty package and such a name is ``<unnamed>``, as
    for a name that is not a string at all."""
    named = type_label(sr.UNENCODABLE_NAMED[route]())

    assert named == label
    named.encode("utf-8")


def test_type_label_spells_a_substrate_class_as_type_identity_does() -> None:
    builder = sr.build_review_loop()

    assert type_label(builder) == type_identity(builder) == "langgraph:StateGraph"


@pytest.mark.parametrize("route", sorted(sr.HOSTILE_NAMED))
def test_type_label_runs_none_of_a_hostile_types_name(route: str) -> None:
    """The four routes ``type_identity`` has (a ``str``-subclass ``__module__`` or ``__qualname__``,
    a non-string ``__module__``, a planted key that hashes as ``__module__``): ``type_label`` reads
    the slot, iterates the namespace with an exact-``str`` key test, and copies every string
    before it formats or splits it — so none of them runs."""
    instance = sr.HOSTILE_NAMED[route]()
    sr.HOOKS.clear()

    label = type_label(instance)

    assert sr.HOOKS == []
    assert label.endswith(type(instance).__name__)
    assert type(label) is str


#: The read each hostile name bars, made directly — the reads ``type_identity`` makes. The red
#: half of the test above: each runs the author's code that ``type_label`` never reaches.
_BARRED_READS: dict[str, tuple[str, Callable[[type], object]]] = {
    "module-is-a-string": (
        "text.partition",
        lambda cls: type.__dict__["__module__"].__get__(cls).partition("."),
    ),
    "module-is-an-object": (
        "module-object.__class__",
        lambda cls: isinstance(type.__dict__["__module__"].__get__(cls), str),
    ),
    "qualname-is-a-string": (
        "text.__format__",
        lambda cls: f"{type.__dict__['__qualname__'].__get__(cls)}",
    ),
    "planted-module-key": (
        "planted-module-key.__eq__",
        lambda cls: type.__dict__["__module__"].__get__(cls),
    ),
}


@pytest.mark.parametrize("route", sorted(sr.HOSTILE_NAMED))
def test_each_hostile_name_runs_the_authors_code_on_the_read_it_bars(route: str) -> None:
    """Armed controls: a ``str``-subclass module's ``partition``, ``isinstance`` on a non-string
    module, an f-string of a ``str``-subclass qualified name and a hashing lookup of
    ``__module__`` each record a hook — so the zero the test above asserts is a measurement."""
    entry, barred = _BARRED_READS[route]
    cls = sr.HOSTILE_NAMED[route]
    sr.HOOKS.clear()

    barred(cls)

    assert entry in [name for name, _ in sr.HOOKS]


def test_describe_declared_carries_only_what_a_report_can_serialize() -> None:
    """Exact ``int`` in range, exact encodable ``str``, ``bool`` and ``None`` are themselves;
    everything else is named — never rendered through its own methods."""
    assert describe_declared(38) == 38
    assert describe_declared("a reason") == "a reason"
    assert describe_declared(True) is True
    assert describe_declared(None) is None
    assert describe_declared(2**53) == "an integer outside the I-JSON exact range ±(2**53−1)"
    assert describe_declared(10**5000) == "an integer outside the I-JSON exact range ±(2**53−1)"
    assert describe_declared("x\ud800") == "a string holding a lone surrogate"
    assert describe_declared(sr.RecordingInt(3)).startswith("a tests:")
    assert describe_declared(sr.RecordingText("x")).startswith("a tests:")
    assert sr.HOOKS == []


def test_the_unknown_members_are_reported_by_name() -> None:
    checked = check_recursion_limit({"value": 38, "justification": "x", "note": 1, 2: 3})

    assert checked.violations == (V.MEMBER_UNKNOWN,)
    assert checked.unknown_members == ("note", "a builtins:int key")


# ── WA-07: the call, in an interpreter that cannot import the substrate ─────────────────

#: The guarded child. Substrate imports, sockets, name resolution and connections all raise from
#: the first line — before ``import gebra`` — because declaring a graph's limit must not drag in
#: the substrate or the extractor (the reason the name resolves out of ``gebra.annotations``).
#: The carriers are stand-ins with the two shapes the call distinguishes: an object with a
#: ``.builder`` and one without. Their values record every own method they have.
_TRIPWIRE = """
import socket, sys

BLOCKED = (
    "langgraph", "langchain", "langchain_core", "langsmith",
    "openai", "anthropic", "httpx", "requests", "aiohttp", "urllib3",
)

attempts = []
hooks = []


class SubstrateBlocker:
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in BLOCKED:
            attempts.append("import:" + fullname)
            print("WA07-TRIP", file=sys.stderr)
            raise ImportError("WA-07 tripwire: the declaration surface imported " + repr(fullname))
        return None


class _TripSocket(socket.socket):
    def __new__(cls, *a, **k):
        attempts.append("socket"); print("WA07-TRIP", file=sys.stderr)
        raise AssertionError("a socket was created on the declaration path")


def _record(name):
    def _seen(*a, **k):
        attempts.append(name); print("WA07-TRIP", file=sys.stderr)
        raise AssertionError(name + " was reached")
    return _seen


sys.meta_path.insert(0, SubstrateBlocker())
socket.socket = _TripSocket
socket.getaddrinfo = _record("getaddrinfo")
socket.gethostbyname = _record("gethostbyname")
socket.create_connection = _record("create_connection")

import gebra
from gebra.annotations import GebraContractError


class Value(int):
    def __index__(self): hooks.append("__index__"); return int.__index__(self)
    def __repr__(self): hooks.append("__repr__"); return "Value"
    def __eq__(self, other): hooks.append("__eq__"); return int.__eq__(self, other)
    __hash__ = int.__hash__


class Text(str):
    def strip(self, *a): hooks.append("strip"); return str.strip(self, *a)
    def __repr__(self): hooks.append("__repr__"); return "Text"
    def __str__(self): hooks.append("__str__"); return str.__str__(self)


class Builder:
    pass


class Compiled:
    def __init__(self):
        self.builder = Builder()


declared = 0
for carrier in (Builder(), Compiled()):
    assert gebra.recursion_limit(carrier, Value(38), justification=Text("a reason")) is carrier
    declared += 1

refused = 0
for value, justification in ((True, "x"), (0, "x"), (38, " "), (38.0, "x"), (2 ** 53, "x")):
    try:
        gebra.recursion_limit(Builder(), value, justification=justification)
    except GebraContractError:
        refused += 1

leaked = sorted(n for n in sys.modules if n.split(".")[0] in BLOCKED)
assert leaked == [], leaked
assert "gebra.extraction" not in sys.modules
assert hooks == [], hooks
assert (declared, refused) == (2, 5), (declared, refused)
"""

_REPORT = "print(attempts)\n"


def _run_guarded(probe: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", _TRIPWIRE + probe + _REPORT],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_the_declaration_invokes_nothing_and_imports_no_substrate() -> None:
    """The WA-07 claim for the §1a call, in a fresh interpreter: no substrate package can be
    imported (the blocker is installed before ``import gebra``), ``gebra.extraction`` is never
    imported, nothing constructs a socket, resolves a name or connects, and the declared value and
    justification have none of their own methods run. The child counts its declarations and
    refusals, so a run that stopped reaching them fails."""
    result = _run_guarded()

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "[]", result.stdout
    assert "WA07-TRIP" not in result.stderr, result.stderr


@pytest.mark.parametrize(
    ("probe", "expected"),
    [
        ("import langgraph\n", "the declaration surface imported 'langgraph'"),
        ("socket.socket()\n", "a socket was created"),
        ("socket.getaddrinfo('example.invalid', 80)\n", "getaddrinfo was reached"),
        ("socket.gethostbyname('example.invalid')\n", "gethostbyname was reached"),
        ("socket.create_connection(('example.invalid', 80))\n", "create_connection was reached"),
        ("repr(Value(1))\nassert hooks == [], hooks\n", "__repr__"),
    ],
    ids=["import", "socket", "getaddrinfo", "gethostbyname", "create_connection", "hooks"],
)
def test_each_raiser_in_the_guarded_child_is_armed(probe: str, expected: str) -> None:
    """A tripwire nobody trips proves nothing: each raiser gets a control, run after the child's
    own assertions, and the hook ledger gets one that seeds a hook and re-asserts it empty."""
    result = _run_guarded(probe)

    assert result.returncode != 0
    assert expected in result.stderr
