"""State-schema fixtures for the INTROSPECTION-SPEC §3 ``state`` row, each armed.

Every builder here is a real ``StateGraph`` whose nodes raise if they are called, and every
*schema* is armed too — which is what this module adds over
:mod:`tests.sample_workflows.sentinel_graph`. Reading a state schema touches surfaces a
topology read never does: a pydantic model's validators and its ``model_fields`` metaclass
property, a class's ``__init_subclass__``, a channel's ``ValueType`` property, and a declared
reducer object. Each of those is a place where "extraction inspects, it never invokes" could
quietly stop being true, so each has a fixture that raises if it is reached.

Every case declares **its own expected Σ**, so the suite in ``tests/extraction/test_state.py``
is an equality against a table rather than a set of hand-checked assertions: a projection
that changed would fail the case that declares it, and a case with no declared outcome could
not be added.

Import safety: importing this module builds the graphs (registering a node never calls it),
compiles nothing, invokes nothing, and needs no network.
"""

from __future__ import annotations

import dataclasses
import enum
import operator
import typing
from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated, Any, Literal, NoReturn, TypedDict, TypeVar

from langgraph.channels.base import BaseChannel
from langgraph.channels.binop import BinaryOperatorAggregate
from langgraph.channels.last_value import LastValue
from langgraph.channels.topic import Topic
from langgraph.graph import END, START, StateGraph
from langgraph.managed import RemainingSteps
from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic._internal._model_construction import ModelMetaclass

# `NotRequired` is stdlib only from 3.11 and this package's floor is 3.10 (`requires-python`),
# so the fixture imports it from the back-port — which pydantic pins, so it is always present.
from typing_extensions import NotRequired

from gebra.extraction.state import UNREPRESENTABLE_REDUCER, UNREPRESENTABLE_TYPE
from gebra.ir.models import StateField
from tests.sample_workflows.sentinel_graph import SentinelExecutedError, raiser

__all__ = [
    "STATE_CASES",
    "SentinelExecutedError",
    "StateCase",
    "add_notes",
    "build",
]

#: This module's dotted path, which is half of every reducer spelling declared below.
#: Written as ``__name__`` rather than as a literal so that the table states the *rule*
#: (``module.qualname``) rather than a string that would survive the module being moved.
_HERE = __name__

#: Every sentinel this module fires, recorded **before** it raises.
#:
#: A raise alone is not enough here, and that is a fact about this path rather than a
#: precaution: the state row reads objects a caller built, so it wraps two reads in
#: ``except Exception`` — and ``SentinelExecutedError`` is a ``RuntimeError``, so a sentinel
#: that fired *inside* one of those would be swallowed and the tripwire would pass with
#: nothing to show. The list is the observable half: the guarded child clears it once the
#: builders exist and asserts it empty after every extraction, so a swallowed sentinel is
#: still a failure.
TRIPPED: list[str] = []

#: Every attribute name an extractor asked a reducer *instance* for.
#:
#: The twin of :data:`TRIPPED` for the probe that cannot raise: the substrate itself asks a
#: declared reducer for ``__name__`` and ``__wrapped__`` while building the channel, so
#: :class:`Merger` has to answer those with an ordinary ``AttributeError`` — which means an
#: extractor probing the instance would be invisible. Recording every name makes it visible
#: without arming anything the substrate needs.
PROBED: list[str] = []


class ModelFieldsRefused(RuntimeError):
    """What :class:`HostileMeta` raises — a *permitted* introspection that declines to answer.

    Deliberately not a :class:`SentinelExecutedError`: reading ``model_fields`` is
    introspection INTROSPECTION §1 rule 3 permits by name, and the metaclass property body
    genuinely does run. Sharing a class with "user code that must never run" is what would
    make the swallow that catches this one look benign.
    """


def _trip(what: str) -> NoReturn:
    """Record a sentinel, then raise it — so a swallowed one is still observable."""
    TRIPPED.append(what)
    raise SentinelExecutedError(f"{what} — extraction must never reach it")


def add_notes(left: list[str], right: list[str]) -> list[str]:
    """A declared reducer that raises if it is ever called — extraction only names it."""
    _trip("the reducer 'add_notes' was invoked")


class Merger:
    """A callable *object* used as a reducer: it has no ``__qualname__`` of its own.

    Extraction names it by its class rather than asking the instance for a name, so this
    fixture is what makes that rule observable — ``__call__`` raises, ``__qualname__`` raises,
    and every other probe of the instance is recorded in :data:`PROBED`.
    """

    def __call__(self, left: Any, right: Any) -> Any:
        _trip("the reducer object was invoked")

    def __getattr__(self, name: str) -> Any:
        """Raise for ``__qualname__``; record every other probe rather than raising.

        Scoped rather than blanket, and the scope is forced: the substrate runs
        ``inspect.signature`` over the declared reducer while it builds the channel, and
        CPython's ``_signature_is_functionlike`` probes ``__name__`` — with a default, so
        only ``AttributeError`` is suppressed. A fixture that raised on every attribute would
        fail at ``StateGraph(...)`` and never reach the extraction it exists to test. So the
        rest of the surface is *recorded* instead: an extractor that asked this instance for
        ``__name__`` or ``__module__`` would run this method, and :data:`PROBED` is where
        that shows up.
        """
        PROBED.append(name)
        if name == "__qualname__":
            _trip(f"the reducer object was asked for {name!r}")
        raise AttributeError(name)


class ArmedChannel(BaseChannel[Any, Any, Any]):
    """A user-written channel whose type properties raise — never read (§1 rule 3).

    ``BaseChannel.ValueType`` is an *abstract* property: on a subclass it is whatever the
    author wrote. This one raises, so an extractor that read it rather than restricting
    itself to the substrate's own channel classes would fail the run instead of shipping.
    """

    @property
    def ValueType(self) -> Any:
        _trip("ArmedChannel.ValueType was read — that is a user property")

    @property
    def UpdateType(self) -> Any:
        _trip("ArmedChannel.UpdateType was read — that is a user property")

    def checkpoint(self) -> Any:
        _trip("ArmedChannel.checkpoint was called")

    def from_checkpoint(self, checkpoint: Any) -> ArmedChannel:
        _trip("ArmedChannel.from_checkpoint was called")

    def update(self, values: Any) -> bool:
        _trip("ArmedChannel.update was called")

    def get(self) -> Any:
        _trip("ArmedChannel.get was called")


class Colour(enum.Enum):
    """An enum used as a ``Literal`` member — a spelling this build refuses to invent."""

    RED = "red"


Unbound = TypeVar("Unbound")


# ── The schemas ──────────────────────────────────────────────────────────────────────────


class Plain(TypedDict):
    """No reducer, no default, no narrowing — the shape §2.2's bare type names describe."""

    task: str
    count: int


class Reduced(TypedDict):
    """A reducer key beside a plain one — ``Annotated[T, reducer]``, §3's own example."""

    task: str
    notes: Annotated[list[str], add_notes]


class Wide(TypedDict):
    """A state with more keys than the graph takes as input."""

    task: str
    notes: Annotated[list[str], operator.add]
    draft: str
    answer: NotRequired[str]


class Narrow(TypedDict):
    """The declared graph input: one key of :class:`Wide`."""

    task: str


class NoInput(TypedDict):
    """An input schema declaring nothing — the graph takes no key from outside."""


class PydanticState(BaseModel):
    """A pydantic state schema whose validators raise if anything ever validates."""

    task: str
    note: str = "none"
    tags: Annotated[list[str], operator.add] = Field(default_factory=list)

    @field_validator("task")
    @classmethod
    def _never_validates(cls, value: str) -> str:
        _trip("a pydantic field validator ran during extraction")

    @model_validator(mode="after")
    def _never_validates_model(self) -> PydanticState:
        _trip("a pydantic model validator ran during extraction")

    def __init_subclass__(cls, **kwargs: Any) -> None:
        _trip("the state schema was subclassed during extraction")


@dataclasses.dataclass
class DataclassState:
    """A dataclass state schema — ``default`` and ``default_factory`` are the default sources."""

    task: str
    note: str = "none"
    tags: Annotated[list[str], operator.add] = dataclasses.field(default_factory=list)


class ManagedState(TypedDict):
    """A managed value beside two ordinary keys (A1 §8)."""

    task: str
    remaining: RemainingSteps
    answer: str


class CustomChannelState(TypedDict):
    """A key bound to a user-written channel — its type is never read."""

    task: str
    guarded: Annotated[str, ArmedChannel(str)]


class StockChannelState(TypedDict):
    """A key bound to a stock channel whose merge semantics ir 1.0 has no slot for."""

    task: str
    items: Annotated[list[str], Topic(str, accumulate=True)]


class UnnameableReducerState(TypedDict):
    """A merge channel whose declared operator is not a callable at all."""

    task: str
    total: Annotated[int, BinaryOperatorAggregate(int, "not-a-function")]


class ObjectReducerState(TypedDict):
    """A merge channel whose reducer is a callable object rather than a function."""

    task: str
    merged: Annotated[dict[str, int], Merger()]


class UnrepresentableState(TypedDict):
    """Four annotations with no type-name spelling — a whole spelling fails, never half of it.

    A type variable and an enum literal have no spelling of their own; the other two are
    parameterized forms whose *member* has none, and they are here because "render what can be
    rendered" would otherwise produce a type name nobody wrote.
    """

    task: str
    unbound: Unbound  # type: ignore[valid-type]
    colour: Literal[Colour.RED]
    either: Unbound | None  # type: ignore[valid-type]
    holder: dict[str, Unbound]  # type: ignore[valid-type]
    caller: Callable[[Unbound], str]


class GenericState(TypedDict):
    """The parameterized spellings a real state schema is written in."""

    mapping: dict[str, list[int]]
    pair: tuple[str, ...]
    render: Callable[[int], str]
    maybe: int | None
    either: str | int
    label: Literal["draft", "final", 1, True] | None
    anything: Any
    nothing: None
    absent: Literal[None]  # noqa: PYI061 - the one-member form is the fixture


class HostileMeta(ModelMetaclass):
    """A model metaclass that raises when asked for ``model_fields``.

    ``model_fields`` is a metaclass property, so what a model answers is the model's
    business. Extraction reads it to learn which fields carry defaults; a model that will
    not say is read as "declares none" rather than allowed to abort the extraction. The
    exception class says which of the two things this is: a permitted introspection
    declining, not user code running where it must not.
    """

    @property
    def model_fields(cls) -> Any:
        raise ModelFieldsRefused("model_fields was read from a model that refuses to say")


class HostileModel(BaseModel, metaclass=HostileMeta):
    """A pydantic state schema that refuses to enumerate its fields."""

    task: str
    note: str = "none"


class ForgedFieldInfo:
    """Something that sits where a ``FieldInfo`` should and runs code if it is asked anything.

    ``model_fields`` is caller-controlled by construction, so its *values* are too. This is
    the fixture for that: an extractor that called ``is_required()`` on whatever the mapping
    handed back — rather than checking the value's type first — would run this.
    """

    def is_required(self) -> bool:
        _trip("is_required() was called on a forged model_fields member")

    def __getattr__(self, name: str) -> Any:
        _trip(f"a forged model_fields member was asked for {name!r}")


class ForgedFieldsMapping:
    """A mapping-shaped object sitting where ``model_fields``' ``dict`` should be.

    Everything an extractor would reach a member through runs code, so a build that read a
    member out of whatever ``model_fields`` returned — rather than checking that it is the
    ``dict`` pydantic builds — would fail the run here.
    """

    def get(self, key: str, default: Any = None) -> Any:
        _trip("`get` was called on a forged model_fields mapping")

    def __getitem__(self, key: str) -> Any:
        _trip("`__getitem__` was called on a forged model_fields mapping")

    def __contains__(self, key: str) -> bool:
        _trip("`__contains__` was called on a forged model_fields mapping")


class ForgedMappingMeta(ModelMetaclass):
    """A model metaclass whose ``model_fields`` is not a ``dict`` at all."""

    @property
    def model_fields(cls) -> Any:
        return ForgedFieldsMapping()


class ForgedMappingModel(BaseModel, metaclass=ForgedMappingMeta):
    """A pydantic state schema whose field mapping is an object of its own."""

    task: str
    note: str = "none"


class ForgedFieldsMeta(ModelMetaclass):
    """A model metaclass whose ``model_fields`` is a real dict of forged members."""

    @property
    def model_fields(cls) -> Any:
        return {"task": ForgedFieldInfo(), "note": ForgedFieldInfo()}


class ForgedFieldsModel(BaseModel, metaclass=ForgedFieldsMeta):
    """A pydantic state schema whose declared fields are not ``FieldInfo`` at all."""

    task: str
    note: str = "none"


#: The sentinel a real ``dataclasses.Field`` carries, read off one rather than named.
#:
#: ``dataclasses.fields()`` filters on ``f._field_type`` **before** it returns, so a forgery
#: without this attribute never reaches the type check it exists to exercise — it dies inside
#: the stdlib call instead. Carrying it is what puts the fixture in front of the guard.
_REAL_FIELD_TYPE: Any = getattr(dataclasses.fields(DataclassState)[0], "_field_type")  # noqa: B009


class ForgedDataclassField:
    """Something that sits where a ``dataclasses.Field`` should and runs code when read.

    ``__dataclass_fields__`` is an ordinary class attribute, so a class can put anything in
    it; ``default``/``default_factory`` are attribute reads, which a property makes
    executable. Extraction checks the member's type before reading either — and this fixture
    survives ``dataclasses.fields()`` (see :data:`_REAL_FIELD_TYPE`) so that it reaches that
    check rather than failing earlier for an unrelated reason.
    """

    name = "note"
    _field_type = _REAL_FIELD_TYPE

    @property
    def default(self) -> Any:
        _trip("`default` was read off a forged dataclass field")

    @property
    def default_factory(self) -> Any:
        _trip("`default_factory` was read off a forged dataclass field")


class ForgedFieldTypeField:
    """A forgery whose ``_field_type`` itself runs code — the one read gebra cannot guard.

    ``dataclasses.fields()`` performs it, on an object the caller controls, before extraction
    sees anything. It is swallowed by the ``except`` around that call, which is exactly why
    the fixtures record before they raise: :data:`TRIPPED` is what makes a swallowed sentinel
    fail the run anyway.
    """

    name = "note"

    @property
    def _field_type(self) -> Any:
        _trip("`_field_type` was read off a forged dataclass field")


class ForgedDataclass:
    """A class that answers ``dataclasses.is_dataclass`` but has no fields to read."""

    __dataclass_fields__ = "not a mapping"
    task: str
    note: str


class ForgedFieldsDataclass:
    """…and one whose ``__dataclass_fields__`` *is* a mapping, of forged members."""

    __dataclass_fields__ = {"note": ForgedDataclassField()}  # noqa: RUF012 - the forgery
    task: str
    note: str


class ForgedFieldTypeDataclass:
    """…and one whose members run code inside ``dataclasses.fields()`` itself."""

    __dataclass_fields__ = {"note": ForgedFieldTypeField()}  # noqa: RUF012 - the forgery
    task: str
    note: str


class DeclaredAsText(TypedDict):
    """A channel constructed with a *string* type — a declared type given as text."""

    task: str
    declared: Annotated[Any, LastValue("SomeDeclaredType")]


class BareGenericState(TypedDict):
    """The bare (unparameterized) alias form, which carries an origin and no argument."""

    task: str
    items: typing.List  # type: ignore[type-arg]  # noqa: UP006 - the bare alias is the fixture


def _nest(depth: int) -> Any:
    """``list[list[…[int]]]`` nested ``depth`` deep — deeper than the renderer descends."""
    nested: Any = int
    for _ in range(depth):
        nested = list[nested]
    return nested


#: A type nested past :data:`~gebra.extraction.state._MAX_TYPE_DEPTH`.
DeeplyNested = TypedDict("DeeplyNested", {"task": str, "deep": _nest(15)})  # type: ignore[misc]


class Keyless:
    """A schema class that declares no annotation at all — Σ has no key to carry."""


#: A key holding a lone surrogate: it has no UTF-8 encoding, so it has no canonical form.
#:
#: Built at runtime rather than written as a ``TypedDict`` literal, and the key is composed
#: with :func:`chr` rather than spelled with an escape: a surrogate inside a *type* is not
#: something a type checker can carry — mypy stores its cache as UTF-8 and cannot encode one —
#: so the shape has to reach the substrate without passing through a static annotation. The
#: substrate reads a schema by ``get_type_hints`` over ``__annotations__``, which this class
#: has.
SURROGATE_KEY: str = "bad" + chr(0xD800) + "key"
SurrogateKey: Any = type("SurrogateKey", (), {"__annotations__": {"task": str, SURROGATE_KEY: str}})


#: Two keys that are one NFC identifier: composed ``é`` and ``e`` + combining acute.
CollidingKeys = TypedDict(
    "CollidingKeys",
    {"café": str, "café": int},
)


def build(schema: Any, **kwargs: Any) -> StateGraph[Any]:
    """A one-node graph over ``schema`` — the topology is deliberately the smallest possible.

    The node raises if it is called, and the wiring is a straight ``START → a → END`` so that
    every difference between two cases in the table is a difference of *state*.
    """
    builder: StateGraph[Any] = StateGraph(schema, **kwargs)
    builder.add_node("a", raiser("a"))
    builder.add_edge(START, "a")
    builder.add_edge("a", END)
    return builder


@dataclass(frozen=True)
class StateCase:
    """One state-schema shape and the Σ it must extract to.

    Attributes:
        why: What the case is here to pin, in one line.
        make: Builds the graph. A factory rather than a constant so that importing this
            module stays cheap and so that each test gets an untouched builder.
        state: The expected ``ir.state`` — already in the §6.3 canonical representation, so
            a bare string here *is* the claim that the value collapsed.
        managed: The expected ``extracted_from.managed_state_keys``.
        constructs: The expected ``unsupported-construct`` slugs, in emission order.
    """

    why: str
    make: Callable[[], StateGraph[Any]]
    state: dict[str, str | StateField] | None
    managed: tuple[str, ...] = ()
    constructs: tuple[str, ...] = ()


#: Every state shape this path handles, each declaring its own outcome.
STATE_CASES: dict[str, StateCase] = {
    "plain": StateCase(
        why="a plain TypedDict: every key is a graph input, so every key carries the flag",
        make=lambda: build(Plain),
        state={
            "task": StateField(type="str", optional=True),
            "count": StateField(type="int", optional=True),
        },
    ),
    "reducer": StateCase(
        why="Annotated[T, reducer] reaches `reducer`, spelled module.qualname",
        make=lambda: build(Reduced),
        state={
            "task": StateField(type="str", optional=True),
            "notes": StateField(type="list[str]", reducer=f"{_HERE}.add_notes", optional=True),
        },
    ),
    "plain-wide": StateCase(
        why="the same state as `declared-input`, with no narrowing — every key is optional",
        make=lambda: build(Wide),
        state={
            "task": StateField(type="str", optional=True),
            "notes": StateField(type="list[str]", reducer="_operator.add", optional=True),
            "draft": StateField(type="str", optional=True),
            "answer": StateField(type="str", optional=True),
        },
    ),
    "declared-input": StateCase(
        why="a narrowed input schema: only the declared graph input carries `optional`",
        make=lambda: build(Wide, input_schema=Narrow),
        state={
            "task": StateField(type="str", optional=True),
            "notes": StateField(type="list[str]", reducer="_operator.add"),
            "draft": "str",
            "answer": "str",
        },
    ),
    "no-declared-input": StateCase(
        why="an input schema with no key: nothing is optional, so every plain value collapses",
        make=lambda: build(Wide, input_schema=NoInput),
        state={
            "task": "str",
            "notes": StateField(type="list[str]", reducer="_operator.add"),
            "draft": "str",
            "answer": "str",
        },
    ),
    "pydantic": StateCase(
        why="a pydantic state schema: fields, reducers, and defaults as the optional source",
        make=lambda: build(PydanticState),
        state={
            "task": StateField(type="str", optional=True),
            "note": StateField(type="str", optional=True),
            "tags": StateField(type="list[str]", reducer="_operator.add", optional=True),
        },
    ),
    "pydantic-defaults-only": StateCase(
        why="the same model with no declared graph input: only the defaulted fields are optional",
        make=lambda: build(PydanticState, input_schema=NoInput),
        state={
            "task": "str",
            "note": StateField(type="str", optional=True),
            "tags": StateField(type="list[str]", reducer="_operator.add", optional=True),
        },
    ),
    "dataclass": StateCase(
        why="a dataclass state schema: `default`/`default_factory` are the same source",
        make=lambda: build(DataclassState, input_schema=NoInput),
        state={
            "task": "str",
            "note": StateField(type="str", optional=True),
            "tags": StateField(type="list[str]", reducer="_operator.add", optional=True),
        },
    ),
    "managed": StateCase(
        why="a managed value is provenance, never a Σ member (§3; §7.3 item 4)",
        make=lambda: build(ManagedState),
        state={
            "task": StateField(type="str", optional=True),
            "answer": StateField(type="str", optional=True),
        },
        managed=("remaining",),
    ),
    "custom-channel": StateCase(
        why="a user-written channel is never read: the key survives with the type marker",
        make=lambda: build(CustomChannelState),
        state={
            "task": StateField(type="str", optional=True),
            "guarded": StateField(type=UNREPRESENTABLE_TYPE, optional=True),
        },
        constructs=("state-channel-not-carried",),
    ),
    "stock-channel": StateCase(
        why="a stock channel outside LastValue/binop: the type is projected, the merge is warned",
        make=lambda: build(StockChannelState),
        state={
            "task": StateField(type="str", optional=True),
            "items": StateField(type="Sequence[str]", optional=True),
        },
        constructs=("state-channel-semantics-not-carried",),
    ),
    "unnameable-reducer": StateCase(
        why="a merge channel whose operator has no name keeps the reducer marker",
        make=lambda: build(UnnameableReducerState),
        state={
            "task": StateField(type="str", optional=True),
            "total": StateField(type="int", reducer=UNREPRESENTABLE_REDUCER, optional=True),
        },
        constructs=("state-reducer-unnameable",),
    ),
    "object-reducer": StateCase(
        why="a callable object is named by its class, never asked for a name of its own",
        make=lambda: build(ObjectReducerState),
        state={
            "task": StateField(type="str", optional=True),
            "merged": StateField(type="dict[str, int]", reducer=f"{_HERE}.Merger", optional=True),
        },
    ),
    "unrepresentable-types": StateCase(
        why="annotations with no spelling: the keys stay in Σ, each with its own warning",
        make=lambda: build(UnrepresentableState),
        state={
            "task": StateField(type="str", optional=True),
            "unbound": StateField(type=UNREPRESENTABLE_TYPE, optional=True),
            "colour": StateField(type=UNREPRESENTABLE_TYPE, optional=True),
            "either": StateField(type=UNREPRESENTABLE_TYPE, optional=True),
            "holder": StateField(type=UNREPRESENTABLE_TYPE, optional=True),
            "caller": StateField(type=UNREPRESENTABLE_TYPE, optional=True),
        },
        constructs=("state-type-unrepresentable",) * 5,
    ),
    "generics": StateCase(
        why="the parameterized spellings, rendered without repr() touching anything",
        make=lambda: build(GenericState, input_schema=NoInput),
        state={
            "mapping": "dict[str, list[int]]",
            "pair": "tuple[str, ...]",
            "render": "Callable[[int], str]",
            "maybe": "int | None",
            "either": "str | int",
            "label": "Literal['draft', 'final', 1, True] | None",
            "anything": "Any",
            "nothing": "None",
            "absent": "Literal[None]",
        },
    ),
    "colliding-keys": StateCase(
        why="two declared keys that are one NFC identifier: the loss is warned, never silent",
        make=lambda: build(CollidingKeys),
        state={"café": StateField(type="str", optional=True)},
        constructs=("state-key-collision",),
    ),
    "unserializable-key": StateCase(
        why="a key with no UTF-8 encoding has no ir 1.0 form: dropped, warned, still digestible",
        make=lambda: build(SurrogateKey, input_schema=NoInput),
        state={"task": "str"},
        constructs=("state-key-unserializable",),
    ),
    "keyless": StateCase(
        why="a schema declaring no key: `state` is absent, not the empty-object claim",
        make=lambda: build(Keyless),
        state=None,
    ),
    "unreadable-model-fields": StateCase(
        why="a model that refuses to enumerate its fields declares no default, and no more",
        make=lambda: build(HostileModel, input_schema=NoInput),
        state={"task": "str", "note": "str"},
    ),
    "forged-dataclass": StateCase(
        why="a class that claims to be a dataclass but has no fields is read the same way",
        make=lambda: build(ForgedDataclass, input_schema=NoInput),
        state={"task": "str", "note": "str"},
    ),
    "forged-model-fields-mapping": StateCase(
        why="a model_fields that is not pydantic's own dict is never read out of",
        make=lambda: build(ForgedMappingModel, input_schema=NoInput),
        state={"task": "str", "note": "str"},
    ),
    "forged-model-fields": StateCase(
        why="a model_fields member that is not a FieldInfo is never asked anything",
        make=lambda: build(ForgedFieldsModel, input_schema=NoInput),
        state={"task": "str", "note": "str"},
    ),
    "forged-dataclass-fields": StateCase(
        why="…and neither is a __dataclass_fields__ member that is not a Field",
        make=lambda: build(ForgedFieldsDataclass, input_schema=NoInput),
        state={"task": "str", "note": "str"},
    ),
    "declared-as-text": StateCase(
        why="a type declared as text is kept verbatim — it is already a type name",
        make=lambda: build(DeclaredAsText, input_schema=NoInput),
        state={"task": "str", "declared": "SomeDeclaredType"},
    ),
    "bare-generic": StateCase(
        why="a bare alias carries an origin and no argument, and spells as the origin",
        make=lambda: build(BareGenericState, input_schema=NoInput),
        state={"task": "str", "items": "list"},
    ),
    "deeply-nested": StateCase(
        why="a type nested past the renderer's bound is the marker, never a RecursionError",
        make=lambda: build(DeeplyNested, input_schema=NoInput),
        state={"task": "str", "deep": UNREPRESENTABLE_TYPE},
        constructs=("state-type-unrepresentable",),
    ),
}


#: Every armed surface in this module, as the probe that reaches it.
#:
#: An inventory nothing checks is worse than none in a WA-07 fixture module — a later
#: reviewer reads it as the coverage claim it looks like. So this one is what
#: ``test_the_schema_fixtures_are_armed`` quantifies over: each entry is *called*, each must
#: raise, and each must have recorded itself in :data:`TRIPPED` first. Adding an armed
#: surface without adding its probe leaves the suite passing but the claim narrower, which
#: is why the test also floors the count.
ARMED_PROBES: tuple[Callable[[], object], ...] = (
    lambda: PydanticState(task="t"),
    lambda: ArmedChannel(str).ValueType,
    lambda: ArmedChannel(str).UpdateType,
    lambda: Merger()("a", "b"),
    lambda: Merger().__qualname__,
    lambda: add_notes(["a"], ["b"]),
    lambda: ForgedFieldInfo().is_required(),
    lambda: ForgedFieldInfo().anything,
    lambda: ForgedDataclassField().default,
    lambda: ForgedDataclassField().default_factory,
    lambda: ForgedFieldTypeField()._field_type,
    lambda: ForgedFieldsMapping().get("task"),
    lambda: ForgedFieldsMapping()["task"],
    lambda: "task" in ForgedFieldsMapping(),
)
