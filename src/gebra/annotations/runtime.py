"""The graph-level declaration — ANNOTATION-API-SPEC §1a (ratified — DEC-36, 2026-10-28).

One ledger slot is graph-level **and** declared: ``runtime.recursion_limit {value,
justification}`` (IR-SPEC §3.5), the carrier of P-02's witness form (b). A graph has one step
budget and no node owns it, so the slot is not a ``contract()`` keyword; it has two surfaces of
its own, and this module is the code one::

    gebra.recursion_limit(graph, 38, justification="3 retry laps of 12 supersteps, plus entry")

(the other is the ``[runtime]`` table of ``gebra.toml``, §2 — :mod:`gebra.annotations.sidecar`).

**The carrier is the builder.** The call attaches one namespaced attribute,
:data:`RUNTIME_ATTRIBUTE` (``__gebra_runtime__``), holding ``{"recursion_limit": {"value": …,
"justification": …}}`` — the sibling of ``__gebra_contract__`` — and returns the object it was
given. When that object exposes a ``.builder`` backreference (a compiled graph, a
``with_config`` copy of one), the attribute lands on the builder, which every compiled copy
shares; only an object with no builder carries it itself. The reason is measured (A1 addendum
A1-D36): ``Pregel.with_config()`` rebuilds the compiled object through its constructor and
drops any attribute the constructor does not accept, so a declaration on the compiled object
would vanish on the first binding, while the builder survives compilation and binding intact
(§6's parity). One consequence follows for a graph with no builder: there the declaration sits
on the object itself, so a ``with_config`` copy made *after* the call carries none — bind first
and declare on the copy, or use the sidecar.

**Call-time rules, error-grade** (:class:`~gebra.annotations.errors.GebraContractError`, the
code surface's grade, as for §1's decoration-time rules): ``value`` is an ``int`` that is not a
``bool``, at least ``1`` (the substrate's own floor) and within ±(2⁵³−1) (IR-SPEC §6.3);
``justification`` is a string with at least one non-whitespace character — the attested half of
the witness (TERMINATION-WITNESS-SPEC §2.2); the slot is settable **at most once per carrier**,
so a second call on the builder or on any copy of it is an error, identical value included (the
§1 duplicate rule); and an object that refuses attribute assignment is an error, never a
silently dropped declaration. The call imports no substrate class and checks no object type.

**One validator for three surfaces.** :func:`check_recursion_limit` is the shape and value check
of the ``{value, justification}`` object, and all three places that meet one run it: the call
(an error), the sidecar's ``[runtime]`` table (§2 — a warning) and the extraction-time read of
an attribute an author set by hand (§1a — a warning). So a declaration one surface refuses is
one every surface refuses, and :class:`RecursionLimitViolation` is one closed vocabulary for
what was wrong, whichever surface it was written on. The validator reads what it is handed
through unbound built-in accessors only — ``dict.items``, ``int.__index__``, ``str.__str__``,
``str.strip`` — and names a rejected value's type with :func:`type_label`, which reads the type
through ``type``'s own descriptors and copies every string it finds before using it, because at
extraction time the object is an author's and gebra runs none of its code (WA-07). A value is
carried into a warning only in a form a report can serialize (:func:`describe_declared`), and a
type is named only by a label UTF-8 can encode.

**What is deliberately not a surface** (§1a): a decorator on a graph factory, a module-level
object, and ``contract(recursion_limit=…)``, which stays refused at decoration time with a
message naming this call and the ``[runtime]`` table. Inference and the D-011 defaults never
fill the slot, and LangGraph's default limit is read by no surface (§3).

Nothing here imports langgraph, opens a socket, or executes the object it is handed. Two
residuals, stated rather than implied, in the voice :mod:`gebra.annotations.contract` uses:
reading ``.builder`` to find the carrier is an attribute read through the object's own
attribute access, and attaching is a ``setattr``, so the target's own ``__setattr__`` runs —
both the author's own object in the author's own call, and the call checks afterwards that the
attribute landed in the carrier's instance dictionary.
"""

from __future__ import annotations

import types
from dataclasses import dataclass
from enum import Enum
from typing import Any, Final, TypeVar, cast

from gebra.annotations.errors import ContractErrorReason, GebraContractError
from gebra.ir.canonical import I_JSON_MAX_INT
from gebra.ir.models import RecursionLimit

__all__ = [
    "RECURSION_LIMIT_KEY",
    "RECURSION_LIMIT_SLOT",
    "RUNTIME_ATTRIBUTE",
    "RecursionLimitCheck",
    "RecursionLimitViolation",
    "check_recursion_limit",
    "check_runtime_attribute",
    "describe_declared",
    "own_namespace",
    "recursion_limit",
    "type_label",
]

#: The one namespaced attribute §1a fixes for the carrier — the sibling of
#: ``__gebra_contract__``. Normative, not a convention: INTROSPECTION-SPEC §3 and §4.3 rule 4
#: read it back under this spelling.
RUNTIME_ATTRIBUTE: Final = "__gebra_runtime__"

#: The attribute's one key, and the ``[runtime]`` table's one admitted key (§1a, §2).
RECURSION_LIMIT_KEY: Final = "recursion_limit"

#: The slot as the graph-level records name it in ``detail`` (§4: the graph-level slot "has no
#: ``slots`` spelling" — the node-slot vocabulary is unchanged — and is named as this instead).
RECURSION_LIMIT_SLOT: Final = "runtime.recursion_limit"

#: The two members of the declared object — the IR slot's own shape (IR-SPEC §3.5).
_MEMBERS: Final = ("value", "justification")

#: The graph object handed to :func:`recursion_limit`, always returned unchanged.
G = TypeVar("G")

#: Absence of a member, told apart from a member whose value is ``None``.
_MISSING: Final = object()

#: ``Py_TPFLAGS_HEAPTYPE`` — a class made by a ``class`` statement or ``type()``, whose
#: ``__module__`` is an entry of its own namespace rather than part of its C-level name.
_HEAP_TYPE: Final = 1 << 9

#: How a number outside the I-JSON exact range is named rather than rendered: rendering it
#: would be digits the canonical form refuses, and past 4300 digits the interpreter refuses to
#: render it at all.
_OUT_OF_RANGE_NUMBER: Final = "an integer outside the I-JSON exact range ±(2**53−1)"


class RecursionLimitViolation(str, Enum):
    """What was wrong with a declared ``{value, justification}`` — one vocabulary, three surfaces.

    The call raises on these, the sidecar warns on them (§2's ``[runtime].recursion_limit``
    bullet) and the extraction-time read of a hand-set attribute warns on them (§1a). Seven are
    the clauses §1a and §2 state (``value`` missing, not an integer, below ``1``, out of range;
    ``justification`` missing, not a string, blank) and ``not-an-object`` is §2's "not a table";
    three are this build's, each the refusal of a shape the slot cannot carry
    (``justification-unencodable``, ``member-unknown``) or of an attribute the call would never
    have attached (``not-a-declaration``).

    Attributes:
        VALUE_MISSING: The object has no ``value`` member.
        VALUE_NOT_AN_INTEGER: ``value`` is not an ``int``, or it is a ``bool`` (a TOML
            boolean included) — §1a: "an ``int`` that is not a ``bool``".
        VALUE_BELOW_ONE: ``value`` is below ``1``, the substrate's own run-time floor.
        VALUE_OUT_OF_RANGE: ``value`` is above ``2**53 − 1``, outside the I-JSON exact range
            IR-SPEC §6.3 fixes for every integer in the canonical form (PD-004).
        JUSTIFICATION_MISSING: The object has no ``justification`` member.
        JUSTIFICATION_NOT_A_STRING: ``justification`` is not a string.
        JUSTIFICATION_BLANK: ``justification`` has no non-whitespace character — "an empty one
            is no declaration" (§1a).
        JUSTIFICATION_UNENCODABLE: ``justification`` holds a lone surrogate, which UTF-8 cannot
            encode, so the IR carrying it would have no canonical form and no ``graph_version``
            (IR-SPEC §6.1 step 6). Not one of §1a's rules: it is the refusal the canonical form
            would otherwise make later, with nothing pointing back at the declaration — the
            same reason the decorator surface refuses a non-finite ``temperature`` where it is
            written. TOML cannot express such a string, so only the code surfaces reach it.
        NOT_AN_OBJECT: The declared ``recursion_limit`` is not a mapping — a TOML table, a
            Python ``dict`` — at all.
        MEMBER_UNKNOWN: The object carries a member other than ``value`` and ``justification``
            (or a key that is not a plain string). The slot's shape is exactly those two
            (IR-SPEC §3.5), as every other object-shaped slot's is closed; the members found are
            named in :attr:`RecursionLimitCheck.unknown_members`.
        NOT_A_DECLARATION: The ``__gebra_runtime__`` attribute itself is not
            ``{"recursion_limit": {…}}`` — not a mapping, or one holding anything else. Reached
            only by an attribute set by hand.
    """

    VALUE_MISSING = "value-missing"
    VALUE_NOT_AN_INTEGER = "value-not-an-integer"
    VALUE_BELOW_ONE = "value-below-one"
    VALUE_OUT_OF_RANGE = "value-out-of-range"
    JUSTIFICATION_MISSING = "justification-missing"
    JUSTIFICATION_NOT_A_STRING = "justification-not-a-string"
    JUSTIFICATION_BLANK = "justification-blank"
    JUSTIFICATION_UNENCODABLE = "justification-unencodable"
    NOT_AN_OBJECT = "not-an-object"
    MEMBER_UNKNOWN = "member-unknown"
    NOT_A_DECLARATION = "not-a-declaration"


@dataclass(frozen=True)
class RecursionLimitCheck:
    """The verdict of :func:`check_recursion_limit` — a declaration, or why there is none.

    Attributes:
        declaration: The IR slot's own object, its ``value`` an exact ``int`` and its
            ``justification`` an exact ``str``, or ``None`` when anything was violated.
        violations: Every rule the object violates, in a fixed order (the object's shape,
            then ``value``, then ``justification``) — empty iff :attr:`declaration` is set.
        reasons: One sentence per violation, in the same order, for a message.
        declared: What was found, as reportable data for a warning's ``detail`` — the two
            members, each through :func:`describe_declared`; never rendered through the object's
            own methods.
        unknown_members: The members other than ``value`` and ``justification``, each through
            :func:`describe_declared` (a key that is not a plain string by its type) — empty
            unless :attr:`violations` holds ``member-unknown``.
    """

    declaration: RecursionLimit | None
    violations: tuple[RecursionLimitViolation, ...] = ()
    reasons: tuple[str, ...] = ()
    declared: Any = None
    unknown_members: tuple[Any, ...] = ()

    @property
    def message(self) -> str:
        """The reasons as one clause, for a refusal or a warning."""
        return "; ".join(self.reasons)


def recursion_limit(graph: G, value: int, *, justification: str) -> G:
    """Declare the graph's step budget — ``runtime.recursion_limit`` (ANNOTATION-API-SPEC §1a).

    Both members are declared here, together: the number is the budget and the justification is
    the person's statement of why that number, which is what makes it the auditable half of P-02's
    witness form (b) (TERMINATION-WITNESS-SPEC §2.2). A ``with_config(recursion_limit=…)``
    binding on a compiled graph never fills the slot — it corroborates the declared value, or is
    warned as a conflict with it — and LangGraph's default limit is never read (§3). A declared
    limit is a recorded bound for P-02 to read, never a statement that any loop halts.

    Extraction reads the declaration from a graph only — on the builder, compiled and
    compiled-only paths. An LCEL chain's document never carries the slot, whatever is declared on
    the chain: its edges run only from one step to the next, so it has no loop for a step budget
    to bound.

    Args:
        graph: The graph object — a ``StateGraph`` builder or a compiled graph. The declaration
            lands on its ``.builder`` backreference when it has one, which every compiled copy
            shares, and on the object itself otherwise.
        value: The step budget: an ``int`` that is not a ``bool``, at least ``1`` and at most
            ``2**53 − 1``.
        justification: Why that number — a string with at least one non-whitespace character.

    Returns:
        ``graph`` itself — the same object, unchanged apart from the attribute on its carrier.

    Raises:
        GebraContractError: with reason ``slot-value-invalid`` when ``value`` or
            ``justification`` breaks a call-time rule, or when the carrier already holds a
            ``__gebra_runtime__`` this call did not attach; ``duplicate-slot`` when the carrier
            already holds a declaration — a second call on the builder or on any compiled copy
            of it, identical value included; ``attachment-impossible`` when the carrier refuses
            the attribute, or accepts the assignment without holding it in its own instance
            dictionary.
    """
    checked = check_recursion_limit({"value": value, "justification": justification})
    if checked.declaration is None:
        raise GebraContractError(
            f"gebra.recursion_limit() refuses this declaration: {checked.message}. The slot "
            "is the graph's step budget and the reason for it, both written here "
            "(ANNOTATION-API-SPEC §1a; IR-SPEC §3.5)",
            reason=ContractErrorReason.SLOT_VALUE_INVALID,
            slot=RECURSION_LIMIT_SLOT,
        )
    carrier = _carrier(graph)
    _refuse_a_second_declaration(carrier)
    attached: dict[str, dict[str, object]] = {
        RECURSION_LIMIT_KEY: {
            "value": checked.declaration.value,
            "justification": checked.declaration.justification,
        }
    }
    try:
        setattr(carrier, RUNTIME_ATTRIBUTE, attached)
    except (AttributeError, TypeError) as exc:
        raise GebraContractError(
            f"gebra.recursion_limit() cannot attach {RUNTIME_ATTRIBUTE} to a "
            f"{type_label(carrier)} (the write raised {type(exc).__name__}; the original is "
            "chained); declare the limit in the [runtime] table of gebra.toml instead "
            "(ANNOTATION-API-SPEC §1a, §2)",
            reason=ContractErrorReason.ATTACHMENT_IMPOSSIBLE,
            slot=RECURSION_LIMIT_SLOT,
        ) from exc
    namespace = own_namespace(carrier)
    if namespace is None or _held(namespace) is not attached:
        raise GebraContractError(
            f"gebra.recursion_limit() assigned {RUNTIME_ATTRIBUTE} on a "
            f"{type_label(carrier)}, but its instance dictionary does not hold it, and "
            "extraction reads only that dictionary; declare the limit in the [runtime] table "
            "of gebra.toml instead (ANNOTATION-API-SPEC §1a, §2)",
            reason=ContractErrorReason.ATTACHMENT_IMPOSSIBLE,
            slot=RECURSION_LIMIT_SLOT,
        )
    return graph


def check_recursion_limit(declared: object) -> RecursionLimitCheck:
    """Check one declared ``{value, justification}`` object against §1a's and §2's rules.

    Total and side-effect free over any object: a mapping is read through ``dict.items`` only
    if its type derives from ``dict`` (so a subclass's own ``items``/``__iter__`` never runs), a
    key counts only if it is exactly ``str``, a value is tested by its type with ``issubclass``
    and read through ``int.__index__``/``str.__str__``, and nothing is rendered through the
    object's own methods.

    Returns:
        The :class:`RecursionLimitCheck`: the IR object when every rule holds, every violation
        otherwise.
    """
    if not issubclass(type(declared), dict):
        reason = (
            f"the declaration is a {type_label(declared)}, not an object with a value and a "
            "justification"
        )
        return RecursionLimitCheck(
            None,
            (RecursionLimitViolation.NOT_AN_OBJECT,),
            (reason,),
            describe_declared(declared),
        )
    members: dict[str, object] = {}
    unknown: list[Any] = []
    for key, member in dict.items(cast("dict[object, object]", declared)):
        if type(key) is str and key in _MEMBERS:
            members[key] = member
            continue
        unknown.append(describe_declared(key) if type(key) is str else f"a {type_label(key)} key")
    violations: list[RecursionLimitViolation] = []
    reasons: list[str] = []
    if unknown:
        violations.append(RecursionLimitViolation.MEMBER_UNKNOWN)
        reasons.append(
            f"it carries {len(unknown)} member(s) besides value and justification, and the "
            "slot's shape is exactly those two"
        )
    value_violation, value_reason, number = _check_value(members.get("value", _MISSING))
    if value_violation is not None:
        violations.append(value_violation)
        reasons.append(value_reason)
    text_violation, text_reason, text = _check_justification(members.get("justification", _MISSING))
    if text_violation is not None:
        violations.append(text_violation)
        reasons.append(text_reason)
    found = {name: describe_declared(member) for name, member in members.items()}
    if violations or number is None or text is None:
        return RecursionLimitCheck(None, tuple(violations), tuple(reasons), found, tuple(unknown))
    return RecursionLimitCheck(RecursionLimit(value=number, justification=text), (), (), found)


def check_runtime_attribute(carried: object) -> RecursionLimitCheck:
    """Check a ``__gebra_runtime__`` value: ``{"recursion_limit": {…}}``, then the inner object.

    What :func:`recursion_limit` writes always passes. Anything else reached this attribute by
    hand, and §1a ignores it with an ``annotation-invalid``: a value that is not a mapping, a
    mapping with any key but ``recursion_limit`` (or none), or an inner object the call-time
    rules reject — "so a hand-set blank justification or boolean value never reaches the IR".
    """
    inner: object = _MISSING
    shape_ok = issubclass(type(carried), dict)
    if shape_ok:
        for key, member in dict.items(cast("dict[object, object]", carried)):
            if type(key) is str and key == RECURSION_LIMIT_KEY and inner is _MISSING:
                inner = member
            else:
                shape_ok = False
    if not shape_ok or inner is _MISSING:
        return RecursionLimitCheck(
            None,
            (RecursionLimitViolation.NOT_A_DECLARATION,),
            (
                (
                    f"{RUNTIME_ATTRIBUTE} holds a {type_label(carried)} that is not "
                    f'{{"{RECURSION_LIMIT_KEY}": {{"value": …, "justification": …}}}}, the '
                    "shape gebra.recursion_limit() attaches"
                ),
            ),
            describe_declared(carried),
        )
    return check_recursion_limit(inner)


def describe_declared(value: object) -> Any:
    """``value`` as data a report can carry, without running any of its code.

    ``None``, an exact ``bool``, an exact ``int`` within ±(2⁵³−1) and an exact ``str`` that
    UTF-8 can encode are themselves. A larger ``int`` is named as one rather than rendered — its
    digits are what the canonical form refuses, and the interpreter refuses to render one past
    4300 digits. A ``str`` holding a lone surrogate, and everything else — a subclass of any of
    these included — is named by its type (:func:`type_label`), read off the type and never off
    the value. So a ``detail`` built from these always serializes to UTF-8 JSON.
    """
    kind = type(value)
    if value is None or kind is bool:
        return value
    if kind is int:
        number = cast("int", value)
        return number if -I_JSON_MAX_INT <= number <= I_JSON_MAX_INT else _OUT_OF_RANGE_NUMBER
    if kind is str:
        text = cast("str", value)
        return text if _encodable(text) else "a string holding a lone surrogate"
    return f"a {type_label(value)}"


def type_label(value: object) -> str:
    """``value``'s type as ``"<top-level package>:<qualname>"``, read so that nothing of it runs.

    The spelling of :func:`gebra.naming.type_identity`, for messages and warning ``detail`` on
    the paths this module and :mod:`gebra.extraction.runtime` own; it is never digest input.
    It reads the type only through ``type``'s own descriptors — the qualified name from its
    slot; for a class defined in Python, the module from an iteration of the class's own
    namespace with an exact-``str`` key test (never a hashing lookup, so a planted key's
    ``__eq__`` never runs); for a built-in type, the module from its C-level name — and copies
    each string with ``str.__str__`` before it formats or splits it, so a ``str`` subclass
    stored as a class's ``__qualname__`` or ``__module__`` has none of its own methods run. A
    name the class does not carry as a string, or carries as one UTF-8 cannot encode, is
    ``"<unnamed>"``; such a module is the empty package. So the label always encodes.
    """
    cls = type(value)
    return f"{_package_of(cls)}:{_qualname_of(cls)}"


def own_namespace(obj: object) -> dict[Any, Any] | None:
    """``obj``'s own instance dictionary, read through the interpreter's own descriptor.

    The descriptor is found on the MRO of ``obj``'s real type — read through ``type``'s own
    descriptors, so no metaclass hook runs — as the first class-namespace entry ``__dict__``
    that is the interpreter's instance-dictionary getset *for that class* (a getset named
    ``__dict__`` whose owner is the class itself), and only then asked for ``obj``'s dictionary.
    Neither ``vars()`` nor ``getattr(obj, "__dict__")`` is used: both go through ``obj``'s own
    attribute access, where a ``__getattribute__`` or a ``__dict__`` property of the author's
    would run. ``None`` when ``obj`` has no instance dictionary, the descriptor declines it, or
    the dictionary it has is not a ``dict`` instance.
    """
    mro = type.__dict__["__mro__"].__get__(type(obj))
    for klass in mro:
        namespace = type.__dict__["__dict__"].__get__(klass)
        for key, entry in types.MappingProxyType.items(namespace):
            if type(key) is not str or key != "__dict__":
                continue
            if (
                type(entry) is not types.GetSetDescriptorType
                or entry.__name__ != "__dict__"
                or entry.__objclass__ is not klass
            ):
                break  # an author's `__dict__` in a class body: the real one is further up
            try:
                held = entry.__get__(obj)
            except (TypeError, AttributeError):
                return None
            return held if issubclass(type(held), dict) else None
    return None


# ── Internals ────────────────────────────────────────────────────────────────────────────


def _encodable(text: str) -> bool:
    try:
        text.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def _render_number(number: int) -> str:
    """An exact ``int`` for a message: its digits within ±(2⁵³−1), its kind beyond."""
    return str(number) if -I_JSON_MAX_INT <= number <= I_JSON_MAX_INT else _OUT_OF_RANGE_NUMBER


def _check_value(value: object) -> tuple[RecursionLimitViolation | None, str, int | None]:
    """``value``'s rules, in §1a's order: present, an ``int`` not a ``bool``, ≥ 1, in range."""
    if value is _MISSING:
        return RecursionLimitViolation.VALUE_MISSING, "it has no value", None
    kind = type(value)
    if issubclass(kind, bool) or not issubclass(kind, int):
        return (
            RecursionLimitViolation.VALUE_NOT_AN_INTEGER,
            (
                f"its value is a {type_label(value)}, and the step budget is an integer "
                "that is not a boolean"
            ),
            None,
        )
    number = int.__index__(cast("int", value))
    if number < 1:
        return (
            RecursionLimitViolation.VALUE_BELOW_ONE,
            f"its value is {_render_number(number)}, below 1, the substrate's own floor",
            None,
        )
    if number > I_JSON_MAX_INT:
        return (
            RecursionLimitViolation.VALUE_OUT_OF_RANGE,
            (
                f"its value is {_OUT_OF_RANGE_NUMBER}, which every integer in the canonical "
                "form must lie within (IR-SPEC §6.3; PD-004)"
            ),
            None,
        )
    return None, "", number


def _check_justification(
    justification: object,
) -> tuple[RecursionLimitViolation | None, str, str | None]:
    """``justification``'s rules: present, a string, not blank, and encodable as UTF-8."""
    if justification is _MISSING:
        return RecursionLimitViolation.JUSTIFICATION_MISSING, "it has no justification", None
    if not issubclass(type(justification), str):
        return (
            RecursionLimitViolation.JUSTIFICATION_NOT_A_STRING,
            f"its justification is a {type_label(justification)}, not a string",
            None,
        )
    text = str.__str__(cast("str", justification))
    if not str.strip(text):
        return (
            RecursionLimitViolation.JUSTIFICATION_BLANK,
            (
                "its justification has no non-whitespace character, and an empty one is no "
                "declaration (TERMINATION-WITNESS-SPEC §2.2)"
            ),
            None,
        )
    if not _encodable(text):
        return (
            RecursionLimitViolation.JUSTIFICATION_UNENCODABLE,
            (
                "its justification holds a lone surrogate, which UTF-8 cannot encode, so the "
                "IR carrying it could not be canonicalized (IR-SPEC §6.1)"
            ),
            None,
        )
    return None, "", text


def _qualname_of(cls: type) -> str:
    """``cls``'s qualified name from its type slot, copied to an exact ``str`` — or
    ``"<unnamed>"`` when the slot holds no string, or one UTF-8 cannot encode (a lone surrogate,
    which only a name assigned by hand can hold)."""
    try:
        name = type.__dict__["__qualname__"].__get__(cls)
    except Exception:  # noqa: BLE001 - a name is never worth failing a refusal over
        return "<unnamed>"
    if not issubclass(type(name), str):
        return "<unnamed>"
    text = str.__str__(name)
    return text if _encodable(text) else "<unnamed>"


def _package_of(cls: type) -> str:
    """The top-level package of ``cls``'s module, without a hashing lookup or a hook.

    A class defined in Python (a heap type) keeps its module as the ``__module__`` entry of its
    own namespace, found by iterating the namespace (an exact ``dict`` behind its proxy) with an
    exact-``str`` key test. A built-in type's module is computed from its C-level name by
    ``type``'s own getset — never read from its namespace, where some built-in types
    (``function``, ``type``) keep a descriptor under that key. Whatever is found is used only as
    an exact ``str`` copy, and only when UTF-8 can encode it; otherwise the package is empty.
    """
    module: object = _MISSING
    try:
        if type.__dict__["__flags__"].__get__(cls) & _HEAP_TYPE:
            namespace = type.__dict__["__dict__"].__get__(cls)
            for key, entry in types.MappingProxyType.items(namespace):
                if type(key) is str and key == "__module__":
                    module = entry
                    break
        else:
            module = type.__dict__["__module__"].__get__(cls)
    except Exception:  # noqa: BLE001 - a name is never worth failing a refusal over
        return ""
    if module is _MISSING or not issubclass(type(module), str):
        return ""
    text = str.__str__(cast("str", module))
    return str.partition(text, ".")[0] if _encodable(text) else ""


def _carrier(graph: object) -> object:
    """The object the attribute lands on: ``graph.builder`` when it has one, else ``graph``.

    §1a: "when the object exposes a ``.builder`` backreference (a compiled graph, including a
    ``with_config`` copy), the attribute lands on that ``StateGraph`` … only an object with no
    builder carries the attribute itself". The read is the one §2's dispatch makes of the same
    object, and like it is an attribute read through the object's own access — the author's
    object, in the author's own call.
    """
    builder = getattr(graph, "builder", None)
    return graph if builder is None else builder


def _held(namespace: dict[Any, Any]) -> object:
    """The ``__gebra_runtime__`` entry of an instance dictionary, or :data:`_MISSING`.

    Iterated through ``dict.items`` with an exact-``str`` key test — never a hashing probe, so a
    planted key with its own ``__eq__`` is never compared.
    """
    for key, entry in dict.items(namespace):
        if type(key) is str and key == RUNTIME_ATTRIBUTE:
            return entry
    return _MISSING


def _refuse_a_second_declaration(carrier: object) -> None:
    """§1a's at-most-once rule, per carrier — identical value included.

    Only a declaration this call could have attached is a duplicate. Anything else under the
    attribute — not the declaration's shape, or a declaration the call-time rules would refuse
    — was set by hand, and gebra will not overwrite what it did not attach.
    """
    namespace = own_namespace(carrier)
    if namespace is None:
        return
    held = _held(namespace)
    if held is _MISSING:
        return
    if check_runtime_attribute(held).violations:
        raise GebraContractError(
            f"{RUNTIME_ATTRIBUTE} is already set on this {type_label(carrier)} to a "
            f"{type_label(held)} gebra did not attach (it is not a declaration "
            "gebra.recursion_limit() would write); gebra owns this attribute "
            "(ANNOTATION-API-SPEC §1a) and will not overwrite something it did not attach",
            reason=ContractErrorReason.SLOT_VALUE_INVALID,
            slot=RECURSION_LIMIT_SLOT,
        )
    raise GebraContractError(
        f"this {type_label(carrier)} already declares runtime.recursion_limit; the slot is "
        "settable at most once per carrier — the builder every compiled copy shares — and a "
        "second declaration is an error rather than a merge, identical value included "
        "(ANNOTATION-API-SPEC §1a). Declare the limit once.",
        reason=ContractErrorReason.DUPLICATE_SLOT,
        slot=RECURSION_LIMIT_SLOT,
    )
