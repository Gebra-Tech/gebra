"""``runtime.recursion_limit`` at extraction — the reads, the ladder, the binding (DEC-36).

Normative authority: ANNOTATION-API-SPEC §1a (the graph-level declaration and its carrier), §2
(the sidecar's ``[runtime]`` table), §3 (the graph-level ladder), §4 (the graph-scoped registry
rows) and §6 (survival over compilation); INTROSPECTION-SPEC §3 ("``runtime.recursion_limit`` is
… emitted at every level where a declaration resolves"), §4.1 (the ``with_config`` binding) and
§8 (the binding disclosure) — all as DEC-36 re-vendored them, under the §1 never-invokes
discipline. The slot itself is IR-SPEC §3.5's, the carrier of P-02's witness form (b).

**Three sources, two tiers.** The slot resolves by the DEC-07 per-slot strict rule over two
*declaration* tiers — (1) the graph-level ``gebra.recursion_limit`` call, (2) the sidecar's
``[runtime]`` table — and a third source that is **not a tier**: (3) a
``with_config(recursion_limit=…)`` binding on the compiled object, which carries no
justification and therefore **never fills the slot**. Resolution is over the whole ``{value,
justification}`` object, never member by member: a sidecar object that differs from the
graph-level one under §3's value-identity rule (canonical JCS bytes) is an
``annotation-conflict`` and the graph-level object is kept. The binding then corroborates the
resolved declaration, conflicts with it (the declaration is kept: it is the attested witness,
the binding is what one call site configured), or — with no declaration on either surface — is
disclosed (``recursion-limit-bound-without-justification``) and the slot stays absent. There is
no inference tier and no default: LangGraph's default limit is not on the object, is read by
nothing here, and would make P-02 vacuous if it were (DEC-36 §3.4).

**Where each source is read, and how.** Every read is of an instance dictionary, through the
dictionary descriptor of the class the read admits, and never through the object's own
attribute access — so no property, ``__getattr__`` or ``__getattribute__`` of the author's runs
for the name (§1a, §4.1):

* the **graph-level declaration**, ``__gebra_runtime__``, from the builder's instance dictionary
  on the builder and builder-primary compiled paths (``StateGraph``'s own descriptor), and from
  the handed object's on the compiled-only path (§4.3 rule 4; the descriptor ``Pregel``'s MRO
  carries, which is ``Runnable``'s at the pins — A1 addendum A1-D39);
* the **binding**, the compiled object's ``config`` member, from its own instance dictionary
  through that same descriptor — then ``recursion_limit`` from the ``config`` mapping;
* the **sidecar** declaration, already parsed and validated once per extraction by
  :mod:`gebra.annotations.sidecar`.

Each dictionary is required to be a ``dict`` instance and is iterated as ``dict.items`` — a key
counting only if ``type(key) is str`` and then ``key == name`` — never probed by hashing
(``in``, ``get``, ``[]``) and never read through a bound method, so neither a planted key's own
``__eq__``/``__hash__`` nor a planted ``dict`` subclass's own ``items``/``__iter__`` runs (the
DEC-38 §3.2 read). A declared or bound value is tested by its type and read through
``int.__index__``/``str.__str__`` only (:func:`gebra.annotations.runtime.check_recursion_limit`).

**What each outcome emits.** A hand-set ``__gebra_runtime__`` that is not the declaration's
shape, or whose value or justification the call-time rules reject, is ignored with an
``annotation-invalid`` of scope ``graph``, surface ``graph-level`` (§1a) — the tier declares
nothing, so the sidecar may still fill the slot, as a carried contract the walk cannot read
declares nothing for a node. A bound value that is not an ``int``, is a ``bool``, is below ``1``
or is outside ±(2⁵³−1) is ``unsupported-construct`` and no binding (§4.1), as is a ``config``
that is not a mapping. No record names a node or slots: the node-slot vocabulary has no
spelling for a graph-level slot (§4, DEC-36). The ``annotation-invalid`` and
``annotation-conflict`` records name it in ``detail["slot"]``; the ``unsupported-construct``
records carry their §8 row's ``location`` (the ``config`` member and its ``recursion_limit``
key) instead. Every foreign value a record carries — what a hand-set attribute or a binding
holds — passes through :func:`~gebra.annotations.runtime.describe_declared`, and every type is
named by :func:`~gebra.annotations.runtime.type_label`, so neither puts into a record a string
UTF-8 cannot encode or a number the interpreter will not render.

**The two conflicts carry two shapes, on purpose.** A sidecar object that differs from the
graph-level one is the DEC-07 conflict between two declaration tiers, carried exactly as a node
conflict is (:mod:`gebra.annotations.resolve`): ``rule: lower-tier-differs``, ``surfaces`` and
``values`` keyed ``kept``/``discarded``, the values whole ``{value, justification}`` objects. A
binding that differs from the resolved declaration is no tier — it never fills the slot and is
not discarded from anything; it is what one call site configured — so its record says that
instead: ``rule: binding-differs``, ``surfaces`` and ``values`` keyed ``declared``/``bound``,
the values the two numbers, and ``kept: declared``. ``rule`` is what a consumer branches on.

**Which paths read what.** The builder path reads the two declaration tiers; the builder-primary
compiled path reads them through the same builder reading, so the builder-level and
compiled-level documents of one declared source carry the same slot (§6's parity), and adds the
binding; the compiled-only path reads the declaration off the handed object, the sidecar and the
binding. The LCEL path reads none of them: DEC-36 rules the declaration's reads on the builder,
compiled and compiled-only paths, and an LCEL fragment's ``runtime`` stays absent there.

Nothing here invokes, imports beyond the substrate's classes, or opens a socket (WA-07);
``tests/extraction/test_runtime.py`` is the tripwire, in a fresh interpreter, with adversarial
carriers whose properties, ``__getattribute__``, planted dictionaries and planted keys record
every call.
"""

from __future__ import annotations

import types
from dataclasses import dataclass
from typing import Any, Final, cast

from langgraph.graph.state import StateGraph
from langgraph.pregel import Pregel

from gebra.annotations.runtime import (
    RECURSION_LIMIT_KEY,
    RECURSION_LIMIT_SLOT,
    RUNTIME_ATTRIBUTE,
    check_runtime_attribute,
    describe_declared,
    type_label,
)
from gebra.annotations.sidecar import SidecarReading
from gebra.extraction.disclosures import ExtractionDisclosure, recursion_limit_binding_disclosure
from gebra.extraction.envelope import BindingOutcome, RecursionLimitBinding
from gebra.extraction.warnings import ExtractionWarning, ExtractionWarningCode
from gebra.ir.canonical import I_JSON_MAX_INT, canonical_foreign_bytes
from gebra.ir.models import RecursionLimit

__all__ = [
    "GRAPH_LEVEL",
    "SIDECAR",
    "WITH_CONFIG",
    "BindingReading",
    "DeclarationReading",
    "DeclaredLimit",
    "read_binding",
    "read_builder_declaration",
    "read_compiled_only_declaration",
]

#: The three sources as the registry rows name their surfaces (ANNOTATION §4: "at graph level
#: ``graph-level``/``sidecar``/``with_config``").
GRAPH_LEVEL: Final = "graph-level"
SIDECAR: Final = "sidecar"
WITH_CONFIG: Final = "with_config"

#: The compiled object's member a ``with_config`` binding lands in (A1 addendum A1-D36:
#: ``Pregel.config`` is a declared attribute, ``None`` unbound).
_CONFIG: Final = "config"

#: Absence of a member, told apart from a member whose value is ``None``.
_MISSING: Final = object()


def _dictionary_descriptor(cls: type) -> Any:
    """The C-level ``__dict__`` descriptor ``cls``'s MRO carries — read from stock classes only.

    Found once, at import, on the substrate's own classes: the first class-namespace entry
    ``__dict__`` along ``cls.__mro__`` that is the interpreter's instance-dictionary getset for
    that very class (named ``__dict__``, owned by the class). Asked for an object's dictionary it
    refuses (``TypeError``) an object that is not an instance of its owner — by the object's real
    type, never its ``__class__`` — which is what makes it the admitted class's read rather than
    the object's. Any real instance of the owner is read: at the pins ``Pregel``'s owner is
    ``Runnable``, so an object that claims ``Pregel`` through ``__class__`` while being another
    ``Runnable`` has its own dictionary read — harmlessly, since the read is the dictionary
    itself, iterated.
    """
    for klass in type.__dict__["__mro__"].__get__(cls):
        entry = type.__dict__["__dict__"].__get__(klass).get("__dict__")
        if (
            type(entry) is types.GetSetDescriptorType
            and entry.__name__ == "__dict__"
            and entry.__objclass__ is klass
        ):
            return entry
    raise TypeError(
        f"{cls.__qualname__} instances carry no instance dictionary"
    )  # pragma: no cover


#: ``StateGraph``'s own instance-dictionary descriptor — the builder's read (§1a).
_BUILDER_DICTIONARY: Final = _dictionary_descriptor(StateGraph)

#: The descriptor ``langgraph.pregel.Pregel``'s MRO carries — ``Runnable``'s at the pins
#: (A1 addendum A1-D39) — the compiled object's read (§4.1, §4.3 rule 4).
_PREGEL_DICTIONARY: Final = _dictionary_descriptor(Pregel)


@dataclass(frozen=True)
class DeclaredLimit:
    """The resolved declaration and the surface it came from.

    Attributes:
        limit: The IR slot's object, both members validated.
        surface: :data:`GRAPH_LEVEL` or :data:`SIDECAR` — which tier won the ladder, named so
            that a binding conflicting with it can say which declaration it contradicts.
    """

    limit: RecursionLimit
    surface: str


@dataclass(frozen=True)
class DeclarationReading:
    """What the two declaration tiers resolved to, and what they reported on the way.

    Attributes:
        declared: The winning declaration, or ``None`` when neither tier declares the slot (or
            each that tried was rejected).
        warnings: The graph-level ``annotation-invalid`` (an ill-formed hand-set attribute) and
            the graph-level ``annotation-conflict`` (a sidecar object that differs), in that
            order. The sidecar's own rejections are not here: they ride the envelope with the
            sidecar's other findings, once per extraction.
    """

    declared: DeclaredLimit | None = None
    warnings: tuple[ExtractionWarning, ...] = ()


@dataclass(frozen=True)
class BindingReading:
    """What the compiled object's binding did beside the declaration.

    Attributes:
        record: The provenance record (:class:`~gebra.extraction.envelope.RecursionLimitBinding`)
            when the object binds a usable limit, else ``None``.
        warnings: An ``annotation-conflict`` when the binding contradicts the declaration, or
            an ``unsupported-construct`` when the bound value is not usable.
        disclosures: The graph-scoped ``recursion-limit-bound-without-justification`` record
            when there is a binding and no declaration.
    """

    record: RecursionLimitBinding | None = None
    warnings: tuple[ExtractionWarning, ...] = ()
    disclosures: tuple[ExtractionDisclosure, ...] = ()


def read_builder_declaration(builder: object, sidecar: SidecarReading) -> DeclarationReading:
    """The ladder over a builder: its ``__gebra_runtime__``, then the sidecar's ``[runtime]``.

    The builder and builder-primary compiled paths' read (§1a: the carrier is the builder, which
    every compiled copy shares). ``builder`` is the ``StateGraph`` §2's dispatch admitted.
    """
    return _resolve(_carried(builder, _BUILDER_DICTIONARY), sidecar)


def read_compiled_only_declaration(compiled: object, sidecar: SidecarReading) -> DeclarationReading:
    """The ladder over a builderless compiled object: its own attribute, then the sidecar.

    §1a: "only an object with no builder carries the attribute itself", and on the compiled-only
    path (§4.3 rule 4) extraction reads it "from the object handed in". The sidecar's table is
    read here too — the surface for a graph whose code an adopter cannot annotate (§2, §6).
    """
    return _resolve(_carried(compiled, _PREGEL_DICTIONARY), sidecar)


def read_binding(compiled: object, declared: DeclaredLimit | None) -> BindingReading:
    """The ``with_config(recursion_limit=…)`` binding and its outcome beside ``declared`` (§4.1).

    One instance-dictionary read of ``config`` and one member read of ``recursion_limit`` out of
    it. An unbound object (``config`` ``None``) and a ``config`` with no such member bind
    nothing; the merge that builds ``config`` drops a ``None`` (and a ``0``) limit before it ever
    reaches the object, so "no member" is the substrate's own "no binding".
    """
    namespace = _instance_dictionary(compiled, _PREGEL_DICTIONARY)
    config = _MISSING if namespace is None else _member(namespace, _CONFIG)
    if config is _MISSING or config is None:
        return BindingReading()
    if not issubclass(type(config), dict):
        return BindingReading(
            warnings=(
                _unsupported(
                    "recursion-limit-binding-unreadable",
                    f"the compiled object's `config` is a {type_label(config)}, not a "
                    "mapping, so no `with_config` binding is read from it; the substrate's own "
                    "type for it is a RunnableConfig mapping",
                    bound=describe_declared(config),
                ),
            )
        )
    bound = _member(cast("dict[object, object]", config), RECURSION_LIMIT_KEY)
    if bound is _MISSING or bound is None:
        return BindingReading()
    value = _usable(bound)
    if value is None:
        return BindingReading(
            warnings=(
                _unsupported(
                    "recursion-limit-binding-unusable",
                    "the compiled object binds recursion_limit to "
                    f"{_rendered(bound)}, and a bound value is usable only as an int that is "
                    "not a bool, at least 1 and within ±(2**53−1); it is recorded as no binding",
                    bound=describe_declared(bound),
                ),
            )
        )
    if declared is None:
        return BindingReading(
            record=RecursionLimitBinding(value=value, outcome=BindingOutcome.DISCLOSED),
            disclosures=(recursion_limit_binding_disclosure(value),),
        )
    if value == declared.limit.value:
        return BindingReading(
            record=RecursionLimitBinding(value=value, outcome=BindingOutcome.CORROBORATES)
        )
    return BindingReading(
        record=RecursionLimitBinding(value=value, outcome=BindingOutcome.CONFLICTS),
        warnings=(_binding_conflict(declared, value),),
    )


# ── The declaration tiers ────────────────────────────────────────────────────────────────


def _carried(carrier: object, descriptor: Any) -> object:
    """``carrier``'s ``__gebra_runtime__`` from its instance dictionary, or :data:`_MISSING`.

    An object the admitted class's descriptor refuses — one whose ``__class__`` claims a class
    its type does not have — has no instance dictionary this read can take, and so carries no
    readable declaration; nothing of it is read to find out more.
    """
    namespace = _instance_dictionary(carrier, descriptor)
    return _MISSING if namespace is None else _member(namespace, RUNTIME_ATTRIBUTE)


def _resolve(carried: object, sidecar: SidecarReading) -> DeclarationReading:
    """§3's graph-level ladder: graph-level > sidecar, over whole objects."""
    warnings: list[ExtractionWarning] = []
    graph_level: RecursionLimit | None = None
    if carried is not _MISSING:
        checked = check_runtime_attribute(carried)
        if checked.declaration is None:
            warnings.append(
                ExtractionWarning(
                    code=ExtractionWarningCode.ANNOTATION_INVALID,
                    message=(
                        f"the graph's {RUNTIME_ATTRIBUTE} attribute is not a declaration the "
                        f"graph-level surface accepts: {checked.message}. It is ignored, so "
                        "the declaration in code declares nothing; gebra.recursion_limit() "
                        "attaches a valid one (ANNOTATION-API-SPEC §1a)"
                    ),
                    detail={
                        "scope": "graph",
                        "surface": GRAPH_LEVEL,
                        "rule": "recursion-limit-invalid",
                        "slot": RECURSION_LIMIT_SLOT,
                        "attribute": RUNTIME_ATTRIBUTE,
                        "violations": tuple(item.value for item in checked.violations),
                        "declared": checked.declared,
                        "unknown_members": checked.unknown_members,
                    },
                )
            )
        else:
            graph_level = checked.declaration
    in_sidecar = sidecar.recursion_limit
    if graph_level is not None:
        if in_sidecar is not None and not _identical(graph_level, in_sidecar):
            warnings.append(_tier_conflict(graph_level, in_sidecar, sidecar))
        return DeclarationReading(DeclaredLimit(graph_level, GRAPH_LEVEL), tuple(warnings))
    if in_sidecar is not None:
        return DeclarationReading(DeclaredLimit(in_sidecar, SIDECAR), tuple(warnings))
    return DeclarationReading(None, tuple(warnings))


def _identical(first: RecursionLimit, second: RecursionLimit) -> bool:
    """§3's value identity: the two objects' canonical JCS bytes are byte-equal.

    Both are validated declarations — in range, encodable — so the canonical form exists for
    each and the comparison is total.
    """
    return _canonical(first) == _canonical(second)


def _canonical(limit: RecursionLimit) -> bytes:
    return canonical_foreign_bytes({"value": limit.value, "justification": limit.justification})


def _tier_conflict(
    kept: RecursionLimit, discarded: RecursionLimit, sidecar: SidecarReading
) -> ExtractionWarning:
    """The graph-level ``annotation-conflict`` between the two declaration tiers (§3, DEC-07)."""
    return ExtractionWarning(
        code=ExtractionWarningCode.ANNOTATION_CONFLICT,
        message=(
            "the sidecar's [runtime].recursion_limit differs from the graph-level declaration, "
            "which takes precedence (ANNOTATION-API-SPEC §3; DEC-07, DEC-36): the graph-level "
            f"declaration (value {kept.value}) is kept and the sidecar's (value "
            f"{discarded.value}) is not used"
        ),
        detail={
            "scope": "graph",
            "slot": RECURSION_LIMIT_SLOT,
            "rule": "lower-tier-differs",
            "surfaces": {"kept": GRAPH_LEVEL, "discarded": SIDECAR},
            "values": {"kept": _data(kept), "discarded": _data(discarded)},
            "file": None if sidecar.path is None else str(sidecar.path),
        },
    )


def _data(limit: RecursionLimit) -> dict[str, Any]:
    return {"value": limit.value, "justification": limit.justification}


# ── The binding ──────────────────────────────────────────────────────────────────────────


def _usable(bound: object) -> int | None:
    """A bound value as an exact ``int`` when §4.1 calls it usable, else ``None``.

    "An ``int`` that is not a ``bool``, at least ``1`` and within ±(2⁵³−1)". Tested by type
    with ``issubclass`` and read through ``int.__index__``, so an ``int`` subclass's own methods
    never run.
    """
    kind = type(bound)
    if issubclass(kind, bool) or not issubclass(kind, int):
        return None
    number = int.__index__(cast("int", bound))
    return number if 1 <= number <= I_JSON_MAX_INT else None


def _rendered(bound: object) -> str:
    """A bound value for a message: an exact ``int``, ``bool`` or ``str`` as itself (a ``str``
    quoted), anything else by its description — unquoted, since it is not the value — and never
    through the value's own methods."""
    described = describe_declared(bound)
    return repr(described) if described is bound else str(described)


def _binding_conflict(declared: DeclaredLimit, bound: int) -> ExtractionWarning:
    """The binding contradicts the declaration: the declaration is kept, both values named."""
    return ExtractionWarning(
        code=ExtractionWarningCode.ANNOTATION_CONFLICT,
        message=(
            f"the compiled graph binds recursion_limit={bound} through `with_config`, and the "
            f"{declared.surface} declaration says {declared.limit.value}; the declaration is "
            "kept in runtime.recursion_limit — it is the attested witness, the binding is what "
            "one call site configured — so reconcile the two (ANNOTATION-API-SPEC §3; DEC-36)"
        ),
        detail={
            "scope": "graph",
            "slot": RECURSION_LIMIT_SLOT,
            "rule": "binding-differs",
            "surfaces": {"declared": declared.surface, "bound": WITH_CONFIG},
            "values": {"declared": declared.limit.value, "bound": bound},
            "kept": "declared",
        },
    )


def _unsupported(construct: str, why: str, *, bound: object) -> ExtractionWarning:
    """One ``unsupported-construct`` carrying its §8 row's four facts, plus what was bound."""
    return ExtractionWarning(
        code=ExtractionWarningCode.UNSUPPORTED_CONSTRUCT,
        message=f"{construct}: {why}",
        detail={
            "construct": construct,
            "location": {"attribute": _CONFIG, "key": RECURSION_LIMIT_KEY},
            "why": why,
            "ir_partial": False,
            "bound": bound,
        },
    )


# ── Unbound reads ────────────────────────────────────────────────────────────────────────


def _instance_dictionary(obj: object, descriptor: Any) -> dict[object, object] | None:
    """``obj``'s instance dictionary through ``descriptor``, or ``None`` when there is none.

    ``None`` when the descriptor refuses ``obj`` (it is not an instance of the descriptor's
    owner) or when what it holds is not a ``dict`` instance.
    """
    try:
        held = descriptor.__get__(obj)
    except (TypeError, AttributeError):
        return None
    return cast("dict[object, object]", held) if issubclass(type(held), dict) else None


def _member(mapping: dict[object, object], name: str) -> object:
    """The member ``name`` of a mapping known to be a ``dict`` instance, or :data:`_MISSING`.

    Iterated through the unbound ``dict.items`` with an exact-``str`` key test — never a
    hashing probe and never a bound method — so a planted key's ``__eq__``/``__hash__`` and a
    planted ``dict`` subclass's own methods never run.
    """
    for key, value in dict.items(mapping):
        if type(key) is str and key == name:
            return value
    return _MISSING
