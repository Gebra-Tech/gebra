"""State-schema (Σ) extraction — the INTROSPECTION-SPEC §3 ``state`` row.

Normative authority: INTROSPECTION-SPEC §3 (the ``.channels``/state-schema row), §7.1 (the
knowability entries for ``state`` keys/types/reducers and for ``state.optional``), §7.3 item
4 (managed values land in provenance, not the core IR) and §8 (the warnings taxonomy);
IR-SPEC §2.2 (the Σ shape), §6.3 (representation-normalization, which this path emits
directly) and §7 (H4: "σ's keys, types, ``Annotated[T, reducer]`` reducers, and optionality
map to Σ verbatim"), all under §1's never-invokes discipline.

**This path resolves no type hint of its own.** §3's row names ``.channels`` first, and that
is why: ``StateGraph(S)`` already ran ``typing.get_type_hints(S, include_extras=True)`` when
it built the channels, so the annotation objects are on the builder before extraction starts.
Reading them costs no evaluation, which keeps the §1 rule 3 caveat ("``get_type_hints()``
*evaluates* string/forward-reference annotations") off this path entirely rather than
managed on it. ``tests/extraction/test_state.py`` arms ``typing.get_type_hints``, ``eval``
and ``exec`` after the builders are built, so that is checked rather than reviewed.

**Three things are read, and each is read at arm's length.**

* A **channel** object. Its ``ValueType`` is an abstract property, so on a user-written
  ``BaseChannel`` subclass it is arbitrary code. Only langgraph's own stock channel classes
  are read, matched by **exact type** (:data:`_STOCK_CHANNELS`) — a subclass of a stock class
  is not one of them, because overriding the property is exactly how it would stop being
  library code.
* A **declared type**. It is rendered by :func:`_type_name`, a closed renderer that never
  calls ``repr()`` or ``str()`` on anything the caller supplied; a class is named through the
  unbound ``type.__qualname__`` accessor, so a hostile metaclass cannot observe the read.
* A **reducer**. Named the same way, from the ``Annotated`` metadata the binop channel
  carries; the object is never called and never rendered.

**Where a value has no ir 1.0 spelling, the key survives with a marker.** Σ membership is
what P-03 and P-04 quantify over, so dropping a key would turn "this type has no spelling"
into "this key does not exist" — a stronger and wrong statement, and one that P-03 would
report against the node that reads it. So an unreadable type is
:data:`UNREPRESENTABLE_TYPE` and an unnameable reducer is :data:`UNREPRESENTABLE_REDUCER`,
each with its own ``unsupported-construct`` warning naming the offender's class. Both
markers carry a ``:``, which nothing :func:`_type_name` *renders* can — one exception,
stated rather than implied: a channel constructed with a **string** type carries that string
verbatim, so an author who writes the marker gets the marker back. Their own bytes, and the
one way the two can meet.

**Two residuals, in the voice the sibling modules use for theirs**, because "executes
nothing" would be too strong for a surface that reads objects the caller built:

* the warning strings name an offender through :func:`~gebra.naming.type_identity`, whose own
  documented residual applies — a sufficiently exotic metaclass can observe the attribute
  read, and a metaclass that refuses ``__qualname__`` sends that helper to ``repr``. Nothing
  it produces reaches Σ; it reaches a message, outside hash scope.
* ``issubclass(schema, BaseModel)`` runs pydantic's own ``__subclasscheck__``, and asking a
  model for ``model_fields`` runs a metaclass property body. Both are the "pydantic
  model/JSON-schema introspection" §1 rule 3 permits by name; what comes *back* from either
  is type-checked before anything is read out of it.

**Managed values are not in Σ.** §3: "ir 1.0 has no managed marker slot — extraction records
presence in provenance as P-02 corroborating evidence only", and §7.3 item 4 repeats it
("lands only in provenance, not the core IR"). ``builder.managed`` holds the manager class,
not the annotation, so there is no type to carry either way. They are recorded on
:attr:`~gebra.extraction.envelope.ExtractedFrom.managed_state_keys`; no warning is emitted,
because §8's vocabulary is closed and has no row for a managed value — a borrowed code would
put every ``RemainingSteps`` graph outside the strict-mode bar for declaring something the
substrate supports.

Nothing here invokes a node, a router, a reducer or a channel; nothing opens a connection.
"""

from __future__ import annotations

import dataclasses
import types
import typing
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Final, TypeGuard, cast

from langgraph.channels.any_value import AnyValue
from langgraph.channels.binop import BinaryOperatorAggregate
from langgraph.channels.ephemeral_value import EphemeralValue
from langgraph.channels.last_value import LastValue, LastValueAfterFinish
from langgraph.channels.named_barrier_value import (
    NamedBarrierValue,
    NamedBarrierValueAfterFinish,
)
from langgraph.channels.topic import Topic
from langgraph.channels.untracked_value import UntrackedValue
from pydantic import BaseModel
from pydantic.fields import FieldInfo

from gebra.extraction.base import type_identity
from gebra.extraction.warnings import ExtractionWarning, ExtractionWarningCode
from gebra.ir.models import StateField

if TYPE_CHECKING:
    from langgraph.graph.state import StateGraph

__all__ = [
    "UNREPRESENTABLE_REDUCER",
    "UNREPRESENTABLE_TYPE",
    "StateReading",
    "read_state",
]

#: The ``type`` a state key carries when its declared type has no rendered spelling.
#:
#: A marker rather than a dropped key: Σ membership is what P-03/P-04 quantify over (§2.3
#: "MUST ⊆ keys(``state``)"), so omitting the key would report "no such key" for a key the
#: schema declares. IR-SPEC §2.2 makes types "opaque declared strings in 1.0; no type algebra
#: is normatively imposed on them", so a marker is admitted content rather than a shape
#: violation. The ``:`` is what makes it collision-proof — :func:`_type_name` emits none.
UNREPRESENTABLE_TYPE: Final = "type:unrepresentable"

#: The ``reducer`` a merge channel carries when its declared function has no rendered name.
#:
#: Emitted rather than omitted for the reason the empty ``retry_on`` is emitted rather than
#: omitted (§3, DEC-18): the absent form is a positive claim. "No ``reducer``" is what P-09
#: reads as an unreduced shared write — an ERROR grade for a ``send`` template (IR-SPEC
#: §2.4) — so an unnameable reducer must not be spelled as an absent one.
UNREPRESENTABLE_REDUCER: Final = "reducer:unrepresentable"

#: How deep :func:`_type_name` descends into a parameterized type before giving up.
#:
#: Far above anything a state annotation carries; it exists so a pathologically nested (or
#: self-referential) alias yields the marker rather than a :class:`RecursionError` out of
#: ``gebra.extract()``.
_MAX_TYPE_DEPTH: Final = 12

#: The channel classes this path reads a ``ValueType`` off, by **exact** type.
#:
#: ``BaseChannel.ValueType`` is an abstract property: on a user-written subclass it is
#: arbitrary code, which §1 rule 3's closed operation list does not admit. These are
#: langgraph's own, whose implementations return the stored annotation. Exact type rather
#: than ``isinstance``, because a subclass of ``LastValue`` that overrides the property is
#: precisely the case the closure exists to exclude.
_STOCK_CHANNELS: Final[frozenset[type]] = frozenset(
    {
        LastValue,
        LastValueAfterFinish,
        BinaryOperatorAggregate,
        EphemeralValue,
        UntrackedValue,
        AnyValue,
        Topic,
        NamedBarrierValue,
        NamedBarrierValueAfterFinish,
    }
)

#: The two channel classes whose semantics ir 1.0 carries exactly.
#:
#: ``LastValue`` is "no reducer" and ``BinaryOperatorAggregate`` is "this reducer" — between
#: them they are the whole of what a ``state`` value can say about merging (§2.2). Every
#: other channel means something ir 1.0 has no slot for (topic accumulation, barrier
#: arrival, ephemerality), so it takes an ``unsupported-construct`` naming what was dropped
#: — §8's row covers exactly this ("a supported object contains a construct extraction
#: cannot map", with the beta ``DeltaChannel`` named in terms).
_CARRIED_CHANNELS: Final[frozenset[type]] = frozenset({LastValue, BinaryOperatorAggregate})

#: ``typing.Union`` and the PEP 604 ``|`` form, which are distinct objects for ``get_origin``.
_UNION_ORIGINS: Final = (typing.Union, types.UnionType)

#: The two function types whose ``__module__``/``__qualname__`` are read unbound, each keyed
#: to the type that carries its own descriptors — ``FunctionType``'s do not work on a builtin.
_FUNCTION_TYPES: Final[Mapping[type, type]] = {
    types.FunctionType: types.FunctionType,
    types.BuiltinFunctionType: types.BuiltinFunctionType,
}

#: The scalar types a ``Literal`` member may be for the literal to be rendered.
#:
#: Exact types only, and rendered through their own ``repr`` — ``str``/``int``/``bool``'s,
#: never a user subclass's. A ``Literal`` over anything else (an enum member, an object) has
#: no spelling this path will invent, so the whole annotation takes the marker.
_LITERAL_SCALARS: Final[tuple[type, ...]] = (bool, int, str)


@dataclass(frozen=True)
class StateReading:
    """One pass over a builder's state schema — Σ, its provenance, and what it could not map.

    Attributes:
        state: The IR ``state`` block in canonical representation (IR-SPEC §6.3: a value
            carrying neither ``reducer`` nor ``optional`` is already collapsed to its bare
            type-name string), or ``None`` when the schema declares no keys at all. ``None``
            rather than ``{}`` because canonical form **preserves** an empty object, so
            ``state: {}`` is the positive claim "Σ is empty" and reaches ``graph_version``
            as one.
        managed: The managed-value keys, in declaration order — §3's "records presence in
            provenance", carried out of the core IR (§7.3 item 4).
        warnings: The ``unsupported-construct`` records for what Σ could not carry.
    """

    state: dict[str, str | StateField] | None
    managed: tuple[str, ...]
    warnings: tuple[ExtractionWarning, ...]


@dataclass
class _Collector:
    """The mutable half of one pass — kept out of :class:`StateReading`, which is a value."""

    state: dict[str, str | StateField] = field(default_factory=dict)
    warnings: list[ExtractionWarning] = field(default_factory=list)

    def warn(self, construct: str, why: str, *, key: str, ir_partial: bool) -> None:
        """Record one ``unsupported-construct`` carrying its §8 row's four facts.

        The location is the state key rather than a node or an edge: §8's row asks for "the
        location (node/edge)" of the construct, and a state key is neither — naming the key
        is the honest answer to the same question.
        """
        self.warnings.append(
            ExtractionWarning(
                code=ExtractionWarningCode.UNSUPPORTED_CONSTRUCT,
                message=f"{construct}: {why}",
                detail={
                    "construct": construct,
                    "location": {"state_key": key},
                    "why": why,
                    "ir_partial": ir_partial,
                },
            )
        )


def read_state(builder: StateGraph[Any]) -> StateReading:
    """Read Σ off an uncompiled builder — INTROSPECTION-SPEC §3's ``state`` row.

    The row maps ``.channels``/state schema, the resolved type hints and
    ``Annotated[T, reducer]`` onto "key → ``{type, reducer?, optional?}``", with
    ``optional: true`` for graph-input/defaulted keys. All three §7.1 sources are static and
    already on the builder, so nothing is evaluated, called or compiled here.

    Args:
        builder: The ``StateGraph`` §3 applies to.

    Returns:
        The reading: Σ in canonical representation, the managed keys for provenance, and one
        ``unsupported-construct`` per value the block could not carry.
    """
    collector = _Collector()
    optional_keys = _optional_keys(builder)
    seen: dict[str, str] = {}
    for declared_key, channel in _channels(builder).items():
        key = unicodedata.normalize("NFC", declared_key)
        if not _is_serializable(key):
            # A key canonical form cannot serialize is a key no IR can carry: §6.1 step 6
            # emits UTF-8 and a surrogate code point is not a Unicode scalar value, so
            # emitting it would produce a document that exists and raises the moment anyone
            # asks it for a `graph_version` — extraction total in name only. Dropped, warned,
            # and the IR is honestly partial at that key.
            collector.warn(
                "state-key-unserializable",
                f"the declared key {declared_key!r} holds a code point that is not a Unicode "
                "scalar value, so no canonical serialization of it exists and the key has no "
                "ir 1.0 form",
                key=key,
                ir_partial=True,
            )
            continue
        if key in seen:
            # Two declared keys with one canonical spelling. Overwriting would drop a key
            # from Σ in silence; §6.3 puts state keys in the NFC identifier role, so the
            # spellings *are* one key downstream and no ir 1.0 form distinguishes them.
            collector.warn(
                "state-key-collision",
                f"the declared keys {seen[key]!r} and {declared_key!r} normalize to one NFC "
                f"identifier {key!r}; ir 1.0 has one state entry per key, so the first "
                "declaration is kept and this one is dropped",
                key=key,
                ir_partial=True,
            )
            continue
        seen[key] = declared_key
        collector.state[key] = _value(
            channel, key=key, optional=key in optional_keys, collector=collector
        )
    return StateReading(
        state=collector.state or None,
        managed=tuple(_managed_keys(builder)),
        warnings=tuple(collector.warnings),
    )


def _is_serializable(key: str) -> bool:
    """Whether ``key`` has a UTF-8 encoding — the §6.1 step-6 precondition, checked early.

    The same test :mod:`gebra.ir.canonical` applies to every serialized string, applied here
    so that the failure is a warning about one key rather than a
    :class:`~gebra.ir.canonical.CanonicalizationError` about the whole document.
    """
    try:
        key.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def _channels(builder: StateGraph[Any]) -> Mapping[str, Any]:
    """``builder.channels`` — the state keys, in declaration order.

    Managed keys are deliberately absent from this mapping: the substrate splits them into
    ``builder.managed`` (A1 §8), which is the split §3 and §7.3 item 4 ask extraction to keep.
    """
    channels = getattr(builder, "channels", None)
    return channels if isinstance(channels, Mapping) else {}


def _managed_keys(builder: StateGraph[Any]) -> tuple[str, ...]:
    """``builder.managed`` — the managed-value keys, for the provenance record."""
    managed = getattr(builder, "managed", None)
    if not isinstance(managed, Mapping):  # pragma: no cover - the substrate always sets one
        return ()
    return tuple(key for key in managed if isinstance(key, str))


def _value(
    channel: Any,
    *,
    key: str,
    optional: bool,
    collector: _Collector,
) -> str | StateField:
    """One Σ entry, already in the §6.3 canonical representation.

    "A ``state`` value collapses to the bare type-name string **iff** it carries no
    ``reducer`` and no ``optional`` flag; the object form is used otherwise …
    ``gebra.extract()`` emits these collapsed forms directly." So the collapse happens here
    rather than being left to canonicalization: an extracted model is compared as a *model*
    against goldens and against other extractions, and only one of the two representations is
    the canonical one.

    ``optional`` is emitted as ``True`` or not at all. An explicit ``optional: false`` is a
    *carried* flag rather than the schema default, so it would block the collapse and change
    canonical bytes while saying exactly what absence says.
    """
    declared = _declared_type(channel, key=key, collector=collector)
    reducer = _reducer(channel, key=key, collector=collector)
    if reducer is None and not optional:
        return declared
    return StateField(type=declared, reducer=reducer, optional=optional or None)


def _declared_type(channel: Any, *, key: str, collector: _Collector) -> str:
    """The channel's declared type as an opaque type-name string (§2.2).

    Two refusals, one marker. A channel outside :data:`_STOCK_CHANNELS` is not read at all —
    its ``ValueType`` is a property a user wrote — and a stock channel whose annotation has
    no rendered spelling takes the same marker. Both are warned with the offender named by
    class identity, which reads two attributes of a *type* and calls nothing on the value
    (:func:`~gebra.naming.type_identity`).
    """
    if type(channel) not in _STOCK_CHANNELS:
        collector.warn(
            "state-channel-not-carried",
            f"the key is bound to a {type_identity(channel)}, which is not one of the channel "
            "classes this build reads a declared type off; the type is behind a property this "
            "build does not run, so it is recorded as unrepresentable",
            key=key,
            ir_partial=True,
        )
        return UNREPRESENTABLE_TYPE
    if type(channel) not in _CARRIED_CHANNELS:
        collector.warn(
            "state-channel-semantics-not-carried",
            f"the key is bound to a {type_identity(channel)}; ir 1.0 states a state value as "
            "a type with an optional declared reducer, and this channel's own merge "
            "semantics has no carrier — the type is projected and no reducer is claimed",
            key=key,
            ir_partial=True,
        )
    # Read once, and only after the class check above: the property is asked for exactly one
    # time per key, so nothing here depends on a second read answering the same way.
    declared = channel.ValueType
    rendered = _type_name(_strip_annotated(declared), depth=0)
    if rendered is None:
        collector.warn(
            "state-type-unrepresentable",
            f"the declared type is a {type_identity(declared)} with no type-name "
            "spelling this build renders; the key stays in the state schema because Σ "
            "membership is what the dataflow properties quantify over",
            key=key,
            ir_partial=True,
        )
        return UNREPRESENTABLE_TYPE
    return rendered


def _reducer(channel: Any, *, key: str, collector: _Collector) -> str | None:
    """The declared channel-merge function (§2.2), or ``None`` when the channel declares none.

    Only ``BinaryOperatorAggregate`` carries one: it is the channel the substrate builds for
    ``Annotated[T, reducer]``, and ``.operator`` is that declared object. Every other channel
    class has no declared function to name — which is why the caller has already warned about
    the ones whose merge semantics is nonetheless not ``LastValue``'s.
    """
    if type(channel) is not BinaryOperatorAggregate:
        return None
    named = _callable_name(channel.operator)
    if named is None:
        collector.warn(
            "state-reducer-unnameable",
            f"the declared reducer is a {type_identity(channel.operator)} with no readable "
            "name; `reducer` records that a merge function is declared, so the marker is "
            "kept rather than the slot omitted — an absent reducer is the claim that the "
            "key merges by last-write",
            key=key,
            ir_partial=True,
        )
        return UNREPRESENTABLE_REDUCER
    return named


def _optional_keys(builder: StateGraph[Any]) -> frozenset[str]:
    """The keys §3 marks ``optional: true`` — "graph-input/defaulted keys".

    §7.1 names the builder-level sources in the same two parts as §2.2's sentence names the
    condition: ``builder.input_schema`` for "the key is graph input", and schema-default
    inspection for "or carries a default". This function is that sentence, and the pair is
    read exactly as the union it is written as.

    **What this means for a single-schema builder, stated because it is consequential.**
    ``StateGraph(S)`` leaves ``input_schema`` equal to ``S``, so *every* key of ``S`` is a
    graph input — the caller may supply any of them at invocation — and every key is
    therefore ``optional: true``. P-04 treats an optional key as written at START (§2.2), so
    on such a builder its boundary set is the whole of Σ and it has nothing to report. That
    is the honest reading of a graph whose whole state is caller-suppliable, and it is
    recoverable by the author rather than by the extractor: declaring a narrower
    ``StateGraph(S, input_schema=I)`` makes the distinction, and Σ then carries exactly the
    keys the graph really takes from outside. The alternative readings — "required in the
    input schema", "not required in the input schema" — invent a discriminator §2.2/§3/§7.1
    never mention and turn the mainstream shape into a FATAL false positive with no
    authoring remedy. Recorded as PD-021 D1, because the choice lands in canonical bytes.
    """
    optional: set[str] = set()
    for schema, members in _schemas(builder).items():
        keys = tuple(key for key in members if isinstance(key, str))
        if schema is builder.input_schema:
            optional.update(keys)
        optional.update(_defaulted(schema, keys))
    return frozenset(unicodedata.normalize("NFC", key) for key in optional)


def _schemas(builder: StateGraph[Any]) -> Mapping[Any, Mapping[Any, Any]]:
    """``builder.schemas`` — schema class → its member keys.

    Iterated rather than looked up: a mapping keyed by *classes* is looked up by hashing the
    key, and a metaclass may define ``__hash__``/``__eq__``. The caller compares with ``is``,
    so no user code decides which schema is which.
    """
    schemas = getattr(builder, "schemas", None)
    return schemas if isinstance(schemas, Mapping) else {}


def _defaulted(schema: object, keys: tuple[str, ...]) -> frozenset[str]:
    """The members of ``schema`` that carry a default — the second half of §7.1's source.

    Three declaration surfaces, in the order they are asked about: a pydantic model (a field
    is defaulted iff it is not required), a dataclass (a ``default`` or a ``default_factory``
    that is not ``MISSING``), and anything else — a ``TypedDict`` among them, which has no
    defaults to carry at all. A model that answers either question by raising is read as
    "declares no defaults" rather than allowed to abort the extraction: that is the same
    posture the inference engine takes for ``model_fields``, and for the same reason —
    ``model_fields`` is a metaclass property, so what a class answers is the class's business.

    **Both mappings are caller-controlled, so nothing in them is used before its type is
    checked.** ``model_fields`` is that metaclass property and ``__dataclass_fields__`` is an
    ordinary class attribute, so what comes back is whatever the class put there — and
    ``is_required()`` is a *method call*, ``default``/``default_factory`` are attribute reads
    that a property makes executable. A member that is not a real :class:`FieldInfo` or
    :class:`dataclasses.Field` is therefore read as "not defaulted" rather than asked
    anything: the ``except`` below would otherwise be the only thing standing between a
    forged member and arbitrary code running inside ``gebra.extract()`` — and it would
    *swallow* a tripwire's own exception, which is the failure mode that would make WA-07
    unobservable here rather than merely violated.
    """
    if isinstance(schema, type) and _is_pydantic_model(schema):
        try:
            declared_fields = schema.model_fields
        except Exception:  # noqa: BLE001 - a metaclass property answers however it likes
            return frozenset()
        if type(declared_fields) is not dict:
            # Not the mapping pydantic builds. Reading a member out of it would run its own
            # `get`/`__getitem__`, and this tier's whole job is to notice a default.
            return frozenset()
        return frozenset(
            key
            for key in keys
            # `isinstance` rather than an exact type, because a model layer that subclasses
            # `FieldInfo` (SQLModel does) would otherwise read as "declares no defaults" and
            # lose every `optional` flag — which lands in canonical bytes. `FieldInfo` carries
            # no custom metaclass, so the check is `type.__instancecheck__` and nothing else;
            # the *call* below stays unbound, so a subclass override cannot answer it.
            if isinstance(dict.get(cast("dict[str, object]", declared_fields), key), FieldInfo)
            and not FieldInfo.is_required(dict.__getitem__(declared_fields, key))
        )
    try:
        if not dataclasses.is_dataclass(schema):
            return frozenset()
        declared = {
            entry.name: entry
            for entry in dataclasses.fields(schema)
            if type(entry) is dataclasses.Field
        }
    except Exception:  # noqa: BLE001 - `fields()` reads a class attribute a class may forge
        return frozenset()
    return frozenset(
        key
        for key in keys
        if key in declared
        and not (
            declared[key].default is dataclasses.MISSING
            and declared[key].default_factory is dataclasses.MISSING
        )
    )


def _is_pydantic_model(schema: type) -> TypeGuard[type[BaseModel]]:
    """Whether ``schema`` is a pydantic model class.

    ``issubclass`` consults pydantic's own ``__subclasscheck__``, which is library code; the
    ``isinstance(schema, type)`` guard the caller applies first is what keeps a parameterized
    generic (which is not a class, and makes ``issubclass`` raise) out of here.
    """
    try:
        return issubclass(schema, BaseModel)
    except TypeError:  # pragma: no cover - the caller's `isinstance` guard covers this
        return False


def _strip_annotated(annotation: object) -> object:
    """``Annotated[T, …]`` → ``T``; anything else unchanged.

    The metadata is where the reducer lives, and the substrate has already read it into the
    channel — so for the *type* it is noise. ``typing.get_origin`` recognizes the form
    without touching the annotation's own attributes.
    """
    if typing.get_origin(annotation) is typing.Annotated:
        args = typing.get_args(annotation)
        return args[0] if args else annotation
    return annotation


def _type_name(annotation: object, *, depth: int) -> str | None:
    """A declared type as an opaque type-name string, or ``None`` when it has no spelling.

    A closed renderer rather than ``repr()``. Two reasons, and the second is the load-bearing
    one: ``repr()`` on a class runs its metaclass's ``__repr__`` — arbitrary user code, on a
    value that lands in ``graph_version`` — and the default spelling it produces
    (``<class 'pkg.mod.Thing'>``) is not a type name at all. The vocabulary here is the one
    IR-SPEC §2.2 illustrates ("``str``, ``int``, ``list``, …") extended to the parameterized
    forms an ``Annotated`` state schema is written in, and nothing else.

    None of the branches calls anything on the annotation: ``typing.get_origin``/``get_args``
    read ``__origin__``/``__args__`` off typing's own alias classes, a class is named through
    the unbound ``type.__qualname__`` accessor, and a ``Literal`` member is rendered only
    when its type is exactly ``str``/``int``/``bool``.
    """
    if depth > _MAX_TYPE_DEPTH:
        return None
    if annotation is None or annotation is types.NoneType:
        return "None"
    if annotation is typing.Any:
        return "Any"
    if isinstance(annotation, str):
        # An annotation the substrate left as text — a string annotation is already a
        # declared type name, and rendering it as anything else would be inventing one.
        return annotation
    origin = typing.get_origin(annotation)
    if origin is not None:
        return _parameterized_name(origin, typing.get_args(annotation), depth=depth)
    if isinstance(annotation, type):
        return _qualname(annotation)
    return None


def _parameterized_name(origin: object, args: tuple[Any, ...], *, depth: int) -> str | None:
    """``origin[args]`` — the union, ``Literal`` and generic-alias spellings."""
    if origin in _UNION_ORIGINS:
        members = [_type_name(arg, depth=depth + 1) for arg in args]
        if not members or any(member is None for member in members):
            return None
        return " | ".join(member for member in members if member is not None)
    if origin is typing.Literal:
        members = [_literal_name(arg) for arg in args]
        if not members or any(member is None for member in members):
            return None
        return f"Literal[{', '.join(member for member in members if member is not None)}]"
    base = _type_name(origin, depth=depth + 1)
    if base is None:
        return None
    if not args:
        return base
    rendered = [_argument_name(arg, depth=depth) for arg in args]
    if any(item is None for item in rendered):
        return None
    return f"{base}[{', '.join(item for item in rendered if item is not None)}]"


def _argument_name(argument: object, *, depth: int) -> str | None:
    """One type argument — ``...`` for the ``Ellipsis`` of ``tuple[T, ...]``/``Callable``."""
    if argument is Ellipsis:
        return "..."
    if isinstance(argument, list):
        # `Callable[[int], str]`'s parameter list, which is an ordinary list of types.
        members = [_type_name(item, depth=depth + 1) for item in argument]
        if any(member is None for member in members):
            return None
        return f"[{', '.join(member for member in members if member is not None)}]"
    return _type_name(argument, depth=depth + 1)


def _literal_name(value: object) -> str | None:
    """One ``Literal`` member, rendered through its own exact type's ``repr``.

    ``type(value) in _LITERAL_SCALARS`` rather than ``isinstance``: a ``str`` subclass
    carries its own ``__repr__``, and running it is the thing this module does not do. Every
    other member — an enum member, an object — has no spelling here, and the whole annotation
    falls to the marker rather than being rendered partly: naming an enum member means asking
    the member for its name, and half a rendered ``Literal`` would be a type name nobody
    wrote.
    """
    if value is None:
        return "None"
    if type(value) in _LITERAL_SCALARS:
        return repr(value)
    return None


def _qualname(cls: type) -> str:
    """A class's ``__qualname__``, read through the unbound accessor.

    ``cls.__qualname__`` goes through the metaclass, which may define ``__getattribute__``;
    ``type.__dict__["__qualname__"]`` is the descriptor the interpreter itself uses, so a
    metaclass cannot observe or answer the read. The fallback covers a class whose metaclass
    is not a subclass of ``type`` at all, which the descriptor refuses.
    """
    try:
        name = type.__dict__["__qualname__"].__get__(cls)
    except Exception:  # noqa: BLE001  # pragma: no cover - defensive; see below
        # Unreachable through this module: the caller has already established that the
        # object is a class (``isinstance(x, type)`` or ``type(value)``), and the descriptor
        # answers for every one of those. Kept because the alternative to a caught failure
        # here is an aborted extraction over a *name*, which no reading of §2 licenses.
        return UNREPRESENTABLE_TYPE
    return name if isinstance(name, str) else UNREPRESENTABLE_TYPE


def _module(cls: type) -> str | None:
    """A class's ``__module__``, read through the unbound accessor — the twin of :func:`_qualname`.

    Both halves of a reducer spelling land inside ``graph_version``, so both are read the same
    way: ``cls.__module__`` goes through the metaclass, which may answer or observe it, and
    this value is digest-bearing rather than message-bearing.
    """
    try:
        module = type.__dict__["__module__"].__get__(cls)
    except Exception:  # noqa: BLE001  # pragma: no cover - defensive, as in `_qualname`
        return None
    return module if isinstance(module, str) else None


def _callable_name(value: object) -> str | None:
    """A declared reducer's name as ``module.qualname``, or ``None`` when it has none.

    §2.2 illustrates the slot with ``"operator.add"`` and fixes no spelling, so this is the
    spelling chosen: the dotted path Python itself carries. Two facts about it are recorded
    rather than smoothed over (PD-021 D3): ``operator.add`` names its module ``_operator``,
    because the C accelerator is where the object comes from and nothing on the object
    remembers the alias; and a reducer defined inside a function carries a ``<locals>``
    segment. Both are deterministic and both are what Python says.

    A **function** is read through the unbound accessors of its own exact type, so nothing
    user-defined answers. Anything else callable is named by its class identity instead — an
    instance has no ``__qualname__`` of its own, and asking it for one would run its
    ``__getattr__``.
    """
    carrier = _FUNCTION_TYPES.get(type(value))
    if carrier is not None:
        module = carrier.__dict__["__module__"].__get__(value)
        qualname = carrier.__dict__["__qualname__"].__get__(value)
        if isinstance(qualname, str):
            return f"{module}.{qualname}" if isinstance(module, str) else qualname
        return None  # pragma: no cover - a function always carries a string qualname
    if not callable(value):
        # Not a merge function at all. The substrate types the metadata `Callable`, so this
        # is a declaration outside its own contract; naming it would claim it is a reducer.
        return None
    cls = type(value)
    module = _module(cls)
    qualname = _qualname(cls)
    if qualname == UNREPRESENTABLE_TYPE:  # pragma: no cover - covered by `_qualname`'s own
        return None
    return f"{module}.{qualname}" if isinstance(module, str) else qualname
