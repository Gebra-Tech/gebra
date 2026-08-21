"""Armed fixtures for the INTROSPECTION §7.4 digest path (DEC-15) — WA-07.

Every object here is a **sentinel**: the operations §7.4 promises never to perform record
themselves in :data:`TRIPPED` and then raise, so a build that performed one fails the run even
if something downstream swallowed the exception. What is armed is the specific list §7.4 and §1
rule 3 rule out on this path:

* a model's ``_generate``/``_stream``/``invoke`` — §1 rule 1;
* a model's **properties**: ``_llm_type``, ``_identifying_params``, ``lc_attributes``,
  ``lc_secrets`` — the surfaces PD-014 finding 4 rejected as config sources precisely because
  reading them runs provider-authored bodies, and (c)'s "no property, method, or ``repr`` read
  ever runs on the model object";
* ``__repr__``/``__str__``/``__format__`` on a config *value* — the rejected byte sources'
  defect, and the one that would put a ``0x…`` address inside a digest (finding 3);
* ``__getattr__`` on a config value — nothing of a foreign value is read, only its class;
* ``__str__``/``__format__`` on a mapping **key** — (d) rule 9 renders builtin keys through the
  JCS emitter and gives everything else the whole-mapping marker, so no key is ever stringified;
* the ordering dunders on a **set member** — (d) rule 11 sorts the *coerced* members by their
  own canonical bytes, so the source objects are never compared;
* ``get_secret_value`` on a ``SecretStr`` — secrets are excluded by *type*, never read;
* every read of an unrecognised prompt template or message item — (b)'s fallback is decided
  from ``type()`` alone;
* a **metaclass's** ``__repr__``, ``__eq__`` and ``__hash__`` — every type dispatch on this
  path is an identity test and every class identity comes off the unbound ``type``
  descriptors, so no class is hashed, compared or rendered either;
* ``kwargs`` on a ``RunnableBinding`` subclass **outside** the §7.4 (a) enumeration — the
  overlay read the DEC-21 admission is bounded by, so the decline is counted (EX-16);
* a bound **tool's own body** — a tool reaches the digest as data through (d)'s coercion K and
  is never called, the same posture §6 takes towards a guard.

Three tables carry the fixtures, and each case declares **its own expected projection** rather
than a digest string, so a test is an equality against §7.4's own rules rather than against a
golden nobody can check by eye:

* :data:`COERCION_CASES` — one row per (d) rule, value → expected JSON;
* :data:`PROMPT_CASES` — one per (b) row, template → the exact digest-input bytes;
* :data:`CONFIG_CASES` — one per (c) member rule, model (+ bindings) → the expected C.

**One thing here records instead of raising, and one records rather than being armed.**
:class:`NameProbeMeta` records because a metaclass that *refuses* to answer ``__name__`` breaks
pytest's own failure rendering and turns every unrelated failure in this file into an internal
error. And :data:`RESIDUE` — the two classes on which §7.4 (c)'s **prescribed** model read
genuinely reaches code — is a separate log precisely because it is a declared residue rather
than a defect; see PD-029.

Nothing here is ever invoked by the fixtures themselves: building a template or a model runs
the substrate's constructors and nothing of this module's own.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any, Final

import langchain_core
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    ChatMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.outputs import ChatResult
from langchain_core.prompts import (
    ChatMessagePromptTemplate,
    ChatPromptTemplate,
    FewShotPromptTemplate,
    HumanMessagePromptTemplate,
    MessagesPlaceholder,
    PromptTemplate,
    SystemMessagePromptTemplate,
)
from langchain_core.prompts.base import BasePromptTemplate
from langchain_core.prompts.message import BaseMessagePromptTemplate
from langchain_core.runnables.base import RunnableBinding
from pydantic import SecretStr

from tests import substrate

#: Every sentinel that was reached, recorded **before** it raises. A ``try: … except: pass``
#: around an extraction would hide the exception; it cannot hide this list.
TRIPPED: list[str] = []

#: **There is no ``PROBED`` half here, and that absence is itself the claim.** The other
#: extraction paths record their *licensed* reads so a reviewer sees the read performed rather
#: than assumed; on this path no source object can observe being read at all. Every container
#: and scalar goes through an unbound built-in accessor, a model field is an
#: instance-``__dict__`` lookup, and a class identity is two attribute reads of the *type* — so
#: there is no hook a fixture could leave live to record with. What carries the "the projection
#: really ran" half instead is the per-case equality in the tables below: a case that stopped
#: being reached stops matching its declared projection.


class DigestSentinelError(BaseException):
    """Raised when the digest path performs an operation §7.4 rules out.

    A ``BaseException`` rather than an ``Exception`` for the reason
    ``sentinel_resolution``'s is: this path's callers catch ``AttributeError`` in one place
    ((e)'s ``model_construct`` degrade) and ``CanonicalizationError`` in another, and a
    sentinel that a narrow ``except`` swallowed would otherwise read as an ordinary miss.
    """


def _trip(what: str) -> Any:
    """Record, then raise — so a swallowed trip is still visible in :data:`TRIPPED`."""
    TRIPPED.append(what)
    raise DigestSentinelError(f"{what} was reached during digest computation")


# ── armed config values ──────────────────────────────────────────────────────────────────


class ArmedClient:
    """A plumbing object of the kind every provider model holds — and never renders.

    (d) rule 12 answers with this class's *identity* and nothing else. Everything that could
    turn it into text, or read anything off it, raises: ``repr`` is what the rejected
    ``dumpd`` byte source reached (PD-014 finding 3), and its ``0x…`` address is exactly the
    run-dependent byte EX-07's determinism acceptance forbids.
    """

    def __repr__(self) -> str:
        return _trip("ArmedClient.__repr__")  # type: ignore[no-any-return]

    def __str__(self) -> str:
        return _trip("ArmedClient.__str__")  # type: ignore[no-any-return]

    def __format__(self, spec: str) -> str:
        return _trip("ArmedClient.__format__")  # type: ignore[no-any-return]

    def __getattr__(self, name: str) -> Any:
        # `__getattr__` fires only for attributes normal lookup did not find, which is every
        # attribute this object has: nothing of a foreign config value is read, only its class.
        return _trip(f"ArmedClient.{name}")

    def __iter__(self) -> Any:
        return _trip("ArmedClient.__iter__")

    def __len__(self) -> int:
        return _trip("ArmedClient.__len__")  # type: ignore[no-any-return]

    def __bool__(self) -> bool:
        return _trip("ArmedClient.__bool__")  # type: ignore[no-any-return]

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return _trip("ArmedClient.__call__")


class ArmedMeta(type):
    """A metaclass whose ``__repr__``, ``__eq__`` and ``__hash__`` are all user code.

    Three distinct claims ride on this one class, and each is about a *class* being handled
    rather than a value:

    * (d) rule 12 names a value by its **class identity**, built from two attribute reads of
      the type. An implementation that reached for ``repr(cls)`` anywhere on that route —
      including as an eagerly-evaluated ``getattr`` default — would run ``__repr__``.
    * (b) dispatches its message rows on ``type(item)``. A ``dict`` keyed by class would call
      ``__hash__``; a ``tuple`` membership test falls through to ``__eq__`` on every miss. Both
      are user code, so the dispatch is identity-only.
    * (d) rule 9 dispatches a mapping key on ``type(key)``, with the same two hazards.

    ``__hash__`` is armed as well as ``__eq__`` because they are reached by different
    operations, and an implementation could avoid one while keeping the other.
    """

    def __repr__(cls) -> str:
        return _trip("ArmedMeta.__repr__")  # type: ignore[no-any-return]

    def __eq__(cls, other: object) -> bool:
        return _trip("ArmedMeta.__eq__")  # type: ignore[no-any-return]

    def __hash__(cls) -> int:
        return _trip("ArmedMeta.__hash__")  # type: ignore[no-any-return]


class ArmedMetaValue(metaclass=ArmedMeta):
    """A config value whose *class* refuses to be rendered."""


#: The three ``type`` slots a class identity is built from, watched by :class:`NameProbeMeta`.
_WATCHED_NAMES: Final[frozenset[str]] = frozenset({"__qualname__", "__name__", "__module__"})


class NameProbeMeta(type):
    """A metaclass that **records** every name read routed through it, and answers truthfully.

    :func:`gebra.naming.type_identity` builds a class identity — which (d) rule 12 puts inside
    ``config_digest`` — out of ``__qualname__`` and ``__module__``. Spelled ``cls.__qualname__``
    those reads go through the metaclass's ``__getattribute__``, i.e. through user code, on a
    value that is digest-bearing; spelled through ``type.__dict__[…].__get__(cls)`` they go
    through the descriptor the interpreter itself uses and the metaclass never sees them.

    This one records rather than raising — the only fixture here that does. A raiser would
    break the *harness*: pytest renders an unexpected failure by reading ``type(obj).__name__``,
    so a class that refuses that name turns every unrelated failure in this file into an
    internal error. The record is what the assertion reads anyway, which is the whole point of
    recording before raising elsewhere.
    """

    def __getattribute__(cls, name: str) -> Any:
        if name in _WATCHED_NAMES:
            TRIPPED.append(f"NameProbeMeta.__getattribute__:{name}")
        return type.__getattribute__(cls, name)


class NameProbedValue(metaclass=NameProbeMeta):
    """A config value whose class notices any identity read that goes through its metaclass."""


class OddlyModuledValue:
    """A class whose ``__module__`` is not a string — legal Python, and no rendering for it.

    ``__module__`` is an ordinary class-dict entry, so this is the one half of a class identity
    a class can genuinely answer with a non-string. :func:`gebra.naming.type_identity` names it
    by qualname alone rather than rendering whatever was put there.
    """


# Set after the class body: the annotation would be a lie and the assignment is the fixture.
setattr(OddlyModuledValue, "__module__", 7)  # noqa: B010


class ArmedKey(metaclass=ArmedMeta):
    """A mapping key with no member name under (d) rule 9 — and no rendering either.

    The *instance's* ``__hash__``/``__eq__`` stay live because a dict cannot be *built* without
    them; what is armed is every way of turning the key into a name. Its **metaclass** is
    armed too, so rule 9's ``type(key)`` dispatch is checked to be identity-only: a
    ``holder in (bool, int, float)`` would fall through to ``ArmedMeta.__eq__``.
    """

    def __repr__(self) -> str:
        return _trip("ArmedKey.__repr__")  # type: ignore[no-any-return]

    def __str__(self) -> str:
        return _trip("ArmedKey.__str__")  # type: ignore[no-any-return]

    def __format__(self, spec: str) -> str:
        return _trip("ArmedKey.__format__")  # type: ignore[no-any-return]

    def __index__(self) -> int:
        return _trip("ArmedKey.__index__")  # type: ignore[no-any-return]


@dataclass(frozen=True)
class ArmedMember:
    """A set member that refuses to be compared — (d) rule 11 never compares source objects.

    ``__hash__``/``__eq__`` come from the frozen dataclass so a ``set`` can hold it; the
    ordering dunders raise, so an implementation that reached for ``sorted(members)`` instead
    of sorting their canonical bytes fails the run.
    """

    name: str

    def __repr__(self) -> str:
        return _trip("ArmedMember.__repr__")  # type: ignore[no-any-return]

    def __str__(self) -> str:
        return _trip("ArmedMember.__str__")  # type: ignore[no-any-return]

    def __format__(self, spec: str) -> str:
        return _trip("ArmedMember.__format__")  # type: ignore[no-any-return]

    def __lt__(self, other: object) -> bool:
        return _trip("ArmedMember.__lt__")  # type: ignore[no-any-return]

    def __gt__(self, other: object) -> bool:
        return _trip("ArmedMember.__gt__")  # type: ignore[no-any-return]

    def __le__(self, other: object) -> bool:
        return _trip("ArmedMember.__le__")  # type: ignore[no-any-return]

    def __ge__(self, other: object) -> bool:
        return _trip("ArmedMember.__ge__")  # type: ignore[no-any-return]


class ArmedSecret(SecretStr):
    """A secret whose value is never read — (c) excludes it by *type*, not by content."""

    def get_secret_value(self) -> str:
        return _trip("ArmedSecret.get_secret_value")  # type: ignore[no-any-return]


class Flavour(enum.Enum):
    """(d) rule 4's ``Enum`` → ``K(value)``, with a value that is itself a rule-9 mapping."""

    FAST = "fast"
    RICH = {"depth": 3}  # noqa: RUF012 - an enum *member* value, not a class attribute


class Reach(enum.IntEnum):
    """An ``IntEnum``: rule 4 comes before rule 5, so it unwraps rather than digesting as int.

    Both give ``2`` here, which is the point — the row order is checked by the *shape* of the
    projection in :data:`COERCION_CASES`, not by an accident of this value.
    """

    NEAR = 2


class ShadowedValue(enum.Enum):
    """An ``Enum`` member class that shadows ``value`` with code of its own.

    (d) rule 4 unwraps through the unbound ``enum.Enum`` descriptor, so this property is never
    called; going through ``getattr`` would call it.
    """

    ONE = "one"

    @property
    def value(self) -> Any:
        return _trip("ShadowedValue.value")


class NonStockBinding(RunnableBinding[Any, Any]):
    """A ``RunnableBinding`` **subclass** outside the enumeration — kept opaque by exact type.

    Declared here rather than obtained from ``model.bind(...)`` because what ``bind()`` answers
    with is a langchain-core version fact: from 1.4.0 it is the ``_ChatModelBinding`` subclass,
    and below that minor it is the stock class. Both are now *admitted* (INTROSPECTION §7.4 (a)
    as amended by DEC-21 — EX-16), so a ``bind()``-based fixture cannot express this claim at
    all; a declared subclass outside :data:`gebra.extraction.stock.STOCK_BINDING_NAMES` is what
    DEC-20's stockness discipline is still about, on every cell of the frozen
    VERSION-COMPAT §3 matrix.

    **Armed at the member the admission would read.** ``kwargs`` is what §7.4 (c)'s ``"bound"``
    overlay comes off, and it is the one member of this object that no other part of extraction
    has any business reading — so a gate that widened past the enumeration and reached for this
    wrapper's overlay records here and raises, and the decline becomes counted rather than
    asserted. ``bound`` is deliberately **not** armed: ANNOTATION §6's wrapper walk reads it by
    name on every stitched node, foreign ones included, which
    :mod:`gebra.extraction.lcel` records as a residue of §6 rather than of this path — arming it
    would fire on a licensed read.
    """

    def __getattribute__(self, name: str) -> Any:
        """Trip on ``kwargs``; answer everything else the way pydantic would."""
        if name == "kwargs":
            _trip("NonStockBinding.kwargs")
        return super().__getattribute__(name)


# ── armed models ─────────────────────────────────────────────────────────────────────────


class ArmedChatModel(BaseChatModel):
    """A model whose every non-field surface raises — (c) reads fields and nothing else.

    The declared fields between them exercise every member rule of (c) and most of (d): a
    float, an int, a ``SecretStr`` (excluded), a sequence, an integer-keyed mapping, a
    frozenset, an ``Enum``, an unrepresentable plumbing object, and a ``None`` (omitted).
    """

    temperature: float = 0.0
    seed: int | None = None
    api_key: SecretStr | None = None
    stop_words: list[str] | None = None
    logit_bias: dict[int, float] | None = None
    flavours: frozenset[str] | None = None
    mode: Any = None
    plumbing: Any = None
    unset: str | None = None

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        return _trip("ArmedChatModel._generate")  # type: ignore[no-any-return]

    def _stream(self, *args: Any, **kwargs: Any) -> Any:
        return _trip("ArmedChatModel._stream")

    @property
    def _llm_type(self) -> str:
        return _trip("ArmedChatModel._llm_type")  # type: ignore[no-any-return]

    @property
    def _identifying_params(self) -> dict[str, Any]:
        return _trip("ArmedChatModel._identifying_params")  # type: ignore[no-any-return]

    @property
    def lc_attributes(self) -> dict[str, Any]:
        return _trip("ArmedChatModel.lc_attributes")  # type: ignore[no-any-return]

    @property
    def lc_secrets(self) -> dict[str, str]:
        return _trip("ArmedChatModel.lc_secrets")  # type: ignore[no-any-return]

    def __repr__(self) -> str:
        return _trip("ArmedChatModel.__repr__")  # type: ignore[no-any-return]

    def __str__(self) -> str:
        return _trip("ArmedChatModel.__str__")  # type: ignore[no-any-return]


#: The one thing on this path that a source object **can** observe, recorded here rather than in
#: :data:`TRIPPED` because it is a *declared residue* rather than a defect: §7.4 (c) prescribes
#: ``getattr(m, name)`` per ``model_fields`` name, and on a pathological class that read can
#: reach code. The two shapes below are those classes. They are deliberately kept out of
#: :data:`CONFIG_CASES` — the WA-07 child iterates that table and asserts ``TRIPPED`` empty, and
#: these record by design. Filed as the WA-03 write-up PD-029.
RESIDUE: list[str] = []


class _ShadowingBase(BaseChatModel):
    """A base carrying a ``@property`` that a subclass then declares as a field.

    pydantic removes a field-shadowing class attribute only from the class being built, so the
    property survives on the base — and a **data descriptor** resolves ahead of the instance
    dict, which means ``getattr(m, "shadowed")`` runs this body. pydantic warns at class
    definition and otherwise permits it.
    """

    @property
    def shadowed(self) -> str:
        RESIDUE.append("_ShadowingBase.shadowed")
        return "from-the-property"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        return _trip("_ShadowingBase._generate")  # type: ignore[no-any-return]

    @property
    def _llm_type(self) -> str:
        return _trip("_ShadowingBase._llm_type")  # type: ignore[no-any-return]


def build_shadowing_model() -> BaseChatModel:
    """A model whose declared field is shadowed by an inherited property (residue route 1)."""
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")

        class ShadowingChatModel(_ShadowingBase):
            shadowed: str = "declared"

    return ShadowingChatModel()


class NeedyChatModel(BaseChatModel):
    """A model with a REQUIRED field, for (e)'s recorded ``model_construct`` edge.

    ``model_construct()`` fills defaults only, so omitting ``model_name`` leaves the name in
    ``model_fields`` and absent from ``__dict__`` — the exact state (e) describes.
    """

    model_name: str
    temperature: float = 0.0

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        return _trip("NeedyChatModel._generate")  # type: ignore[no-any-return]

    @property
    def _llm_type(self) -> str:
        return _trip("NeedyChatModel._llm_type")  # type: ignore[no-any-return]

    def __repr__(self) -> str:
        return _trip("NeedyChatModel.__repr__")  # type: ignore[no-any-return]

    def __str__(self) -> str:
        return _trip("NeedyChatModel.__str__")  # type: ignore[no-any-return]

    def __format__(self, spec: str) -> str:
        return _trip("NeedyChatModel.__format__")  # type: ignore[no-any-return]


class ReachingChatModel(NeedyChatModel):
    """A model that answers a *missing* declared field with code of its own (residue route 2).

    pydantic's own ``BaseModel.__getattr__`` raises ``AttributeError`` for a field absent from
    the instance dict, which is what makes (e)'s ``model_construct`` degrade sound for a stock
    model. A subclass ``__getattr__`` overrides that and feeds a computed value into the digest
    instead — so on this class the degrade never fires and (c)'s "no property, method, or
    ``repr`` read ever runs on the model object" does not hold.
    """

    def __getattr__(self, name: str) -> Any:
        RESIDUE.append(f"ReachingChatModel.{name}")
        return "from-getattr"


# ── armed templates ──────────────────────────────────────────────────────────────────────


class ArmedTemplate(BasePromptTemplate[str]):
    """A ``BasePromptTemplate`` outside (b)'s two exact types — a carrier with no byte source.

    Every member (b)'s two recognised branches would read raises, so "the fallback is decided
    from ``type()`` alone" is checked rather than reviewed.
    """

    @property
    def template(self) -> str:
        return _trip("ArmedTemplate.template")  # type: ignore[no-any-return]

    @property
    def messages(self) -> list[Any]:
        return _trip("ArmedTemplate.messages")  # type: ignore[no-any-return]

    def format(self, **kwargs: Any) -> str:
        return _trip("ArmedTemplate.format")  # type: ignore[no-any-return]

    def format_prompt(self, **kwargs: Any) -> Any:
        return _trip("ArmedTemplate.format_prompt")

    @property
    def _prompt_type(self) -> str:
        return _trip("ArmedTemplate._prompt_type")  # type: ignore[no-any-return]

    def __repr__(self) -> str:
        return _trip("ArmedTemplate.__repr__")  # type: ignore[no-any-return]

    def __str__(self) -> str:
        return _trip("ArmedTemplate.__str__")  # type: ignore[no-any-return]

    def __format__(self, spec: str) -> str:
        return _trip("ArmedTemplate.__format__")  # type: ignore[no-any-return]


class ArmedMessageItem(BaseMessagePromptTemplate):
    """A ``messages`` item outside (b)'s six rows — likewise decided from ``type()`` alone."""

    @property
    def prompt(self) -> Any:
        return _trip("ArmedMessageItem.prompt")

    @property
    def role(self) -> str:
        return _trip("ArmedMessageItem.role")  # type: ignore[no-any-return]

    @property
    def content(self) -> Any:
        return _trip("ArmedMessageItem.content")

    def format_messages(self, **kwargs: Any) -> list[BaseMessage]:
        return _trip("ArmedMessageItem.format_messages")  # type: ignore[no-any-return]

    @property
    def input_variables(self) -> list[str]:
        return []

    def __repr__(self) -> str:
        return _trip("ArmedMessageItem.__repr__")  # type: ignore[no-any-return]

    def __str__(self) -> str:
        return _trip("ArmedMessageItem.__str__")  # type: ignore[no-any-return]

    def __format__(self, spec: str) -> str:
        return _trip("ArmedMessageItem.__format__")  # type: ignore[no-any-return]


# ── (d): the coercion table, one row per rule ────────────────────────────────────────────


@dataclass(frozen=True)
class CoercionCase:
    """One row of (d): the value K is given and the JSON it must produce.

    Attributes:
        rule: The (d) rule number this row exercises — the table's own numbering, so a reader
            checks the case off against the spec line by line.
        value: The source value, built by :func:`build`.
        expected: The JSON data K must return, declared here rather than computed.
    """

    rule: int
    build: Any
    expected: Any


def _marker(what: str) -> dict[str, str]:
    """The marker shape (d) fixes, spelled out here so the table declares it independently."""
    return {"__gebra_unrepresentable__": what}


def _cyclic_mapping() -> dict[str, Any]:
    """A mapping that holds itself — the §2 termination rule's own shape."""
    holder: dict[str, Any] = {"name": "loop"}
    holder["self"] = holder
    return holder


def _cyclic_list() -> list[Any]:
    """A list that holds itself, so the cycle rule is checked on both container shapes."""
    holder: list[Any] = ["head"]
    holder.append(holder)
    return holder


#: One case per (d) row, plus the edges each row names. The expected value is **declared**, so
#: a rule that changed fails the case that states it rather than moving a golden.
COERCION_CASES: dict[str, CoercionCase] = {
    "none": CoercionCase(1, lambda: None, None),
    "true": CoercionCase(2, lambda: True, True),
    "false": CoercionCase(2, lambda: False, False),
    "secret": CoercionCase(3, lambda: SecretStr("sk-live"), _marker("secret")),
    "secret-subclass": CoercionCase(3, lambda: ArmedSecret("sk-live"), _marker("secret")),
    "enum-str": CoercionCase(4, lambda: Flavour.FAST, "fast"),
    "enum-mapping": CoercionCase(4, lambda: Flavour.RICH, {"depth": 3}),
    "enum-int": CoercionCase(4, lambda: Reach.NEAR, 2),
    "enum-shadowed-value": CoercionCase(4, lambda: ShadowedValue.ONE, "one"),
    "int": CoercionCase(5, lambda: 42, 42),
    "int-negative": CoercionCase(5, lambda: -7, -7),
    "int-at-bound": CoercionCase(5, lambda: 2**53 - 1, 2**53 - 1),
    "int-over-bound": CoercionCase(5, lambda: 2**53, _marker("int:i-json-range")),
    "int-under-bound": CoercionCase(5, lambda: -(2**53), _marker("int:i-json-range")),
    "float": CoercionCase(6, lambda: 0.5, 0.5),
    "float-nan": CoercionCase(6, lambda: float("nan"), _marker("float:non-finite")),
    "float-inf": CoercionCase(6, lambda: float("inf"), _marker("float:non-finite")),
    "str": CoercionCase(7, lambda: "hello", "hello"),
    "str-astral": CoercionCase(7, lambda: "e\U0001f600", "e\U0001f600"),
    "str-lone-surrogate": CoercionCase(7, lambda: "a\ud800b", _marker("str:lone-surrogate")),
    "bytes": CoercionCase(8, lambda: b"\x00\x01", _marker("bytes")),
    "bytearray": CoercionCase(8, lambda: bytearray(b"ab"), _marker("bytes")),
    "mapping": CoercionCase(9, lambda: {"b": 1, "a": 2}, {"b": 1, "a": 2}),
    "mapping-null-member": CoercionCase(9, lambda: {"a": None, "b": 1}, {"b": 1}),
    "mapping-secret-member": CoercionCase(9, lambda: {"key": SecretStr("s"), "b": 1}, {"b": 1}),
    "mapping-int-keys": CoercionCase(9, lambda: {1: 0.5, 22: 1.5}, {"1": 0.5, "22": 1.5}),
    "mapping-bool-key": CoercionCase(9, lambda: {True: "y"}, {"true": "y"}),
    "mapping-float-key": CoercionCase(9, lambda: {1.5: "y"}, {"1.5": "y"}),
    "mapping-armed-key": CoercionCase(9, lambda: {ArmedKey(): 1}, _marker("mapping:key")),
    # `{1: …, 1.0: …}` is one Python key, so the collision that reaches rule 9 is between two
    # *distinct* keys with one rendering: the integer `1` and the string `"1"`.
    "mapping-key-collision": CoercionCase(9, lambda: {1: "a", "1": "b"}, _marker("mapping:key")),
    "mapping-nan-key": CoercionCase(9, lambda: {float("nan"): "a"}, _marker("mapping:key")),
    "list": CoercionCase(10, lambda: ["b", "a", None], ["b", "a", None]),
    "tuple": CoercionCase(10, lambda: ("b", "a"), ["b", "a"]),
    "set-of-str": CoercionCase(11, lambda: {"b", "a", "c"}, ["a", "b", "c"]),
    "frozenset-of-int": CoercionCase(11, lambda: frozenset({3, 1, 2}), [1, 2, 3]),
    "set-of-armed-members": CoercionCase(
        11,
        lambda: {ArmedMember("b"), ArmedMember("a")},
        [_marker("tests:ArmedMember"), _marker("tests:ArmedMember")],
    ),
    "foreign": CoercionCase(12, ArmedClient, _marker("tests:ArmedClient")),
    "foreign-armed-metaclass": CoercionCase(12, ArmedMetaValue, _marker("tests:ArmedMetaValue")),
    "callable": CoercionCase(12, lambda: _trip, _marker("builtins:function")),
    "cycle-mapping": CoercionCase(9, _cyclic_mapping, {"name": "loop", "self": _marker("cycle")}),
    "cycle-list": CoercionCase(10, _cyclic_list, ["head", _marker("cycle")]),
    "sibling-repeat": CoercionCase(
        10,
        lambda: [(shared := {"a": 1}), shared],
        [{"a": 1}, {"a": 1}],
    ),
}


# ── (b): the prompt table, one row per item kind ─────────────────────────────────────────


@dataclass(frozen=True)
class PromptCase:
    """One (b) row: the template, and the exact bytes §7.4 says it digests.

    Attributes:
        build: Builds the template. A callable rather than a value so each test gets a fresh
            object, which is how "two equal source objects digest equally" is checkable.
        digest_input: The digest input (b) fixes, declared verbatim. ``None`` where (b)'s
            fallback applies.
        offender: The class identity the ``unsupported-construct`` record must carry, or
            ``None`` when the case digests.
        where: The rest of the record's location members, per §8's row.
    """

    build: Any
    digest_input: bytes | None = None
    offender: str | None = None
    where: dict[str, Any] = field(default_factory=dict)


def _multipart() -> ChatPromptTemplate:
    """A multi-part content template — E(p)'s array branch."""
    return ChatPromptTemplate(
        messages=[
            HumanMessagePromptTemplate.from_template(
                [{"text": "describe {thing}"}, {"text": "then {q}"}]
            )
        ]
    )


def _image_part() -> ChatPromptTemplate:
    """A multi-part template with a non-string part — E(p)'s refusal, at its own index."""
    return ChatPromptTemplate(
        messages=[
            HumanMessagePromptTemplate.from_template(
                [{"text": "look"}, {"image_url": {"url": "{u}"}}]
            )
        ]
    )


#: One case per (b) row. Each declares the digest input, so the assertion is against §7.4's own
#: encoding rather than against a hash nobody can read.
PROMPT_CASES: dict[str, PromptCase] = {
    "string-template": PromptCase(
        lambda: PromptTemplate.from_template("Summarise {doc}."),
        b"Summarise {doc}.",
    ),
    "string-template-untrimmed": PromptCase(
        # Byte-exact: the leading newline and the trailing spaces are digested, because §3.6
        # says "no trimming, no normalization".
        lambda: PromptTemplate.from_template("\n  Summarise {doc}.  "),
        b"\n  Summarise {doc}.  ",
    ),
    "string-template-not-nfc": PromptCase(
        # And deliberately no NFC: §6.3's normalization is for identifier-role strings, which a
        # prompt is not, so the decomposed and composed spellings digest differently.
        lambda: PromptTemplate.from_template("café"),
        "café".encode(),
    ),
    "fixed-role-templates": PromptCase(
        lambda: ChatPromptTemplate.from_messages(
            [("system", "You are {role}."), ("human", "{q}"), ("ai", "Thinking about {q}.")]
        ),
        (
            b'[{"role":"system","template":"You are {role}."},'
            b'{"role":"human","template":"{q}"},'
            b'{"role":"ai","template":"Thinking about {q}."}]'
        ),
    ),
    "chat-message-template": PromptCase(
        lambda: ChatPromptTemplate.from_messages(
            [ChatMessagePromptTemplate.from_template("Approve {x}?", role="reviewer")]
        ),
        b'[{"role":"reviewer","template":"Approve {x}?"}]',
    ),
    "placeholder": PromptCase(
        lambda: ChatPromptTemplate.from_messages([MessagesPlaceholder("history")]),
        b'[{"placeholder":"history"}]',
    ),
    "placeholder-optional": PromptCase(
        lambda: ChatPromptTemplate.from_messages([MessagesPlaceholder("history", optional=True)]),
        b'[{"optional":true,"placeholder":"history"}]',
    ),
    "placeholder-n-messages": PromptCase(
        lambda: ChatPromptTemplate.from_messages(
            [MessagesPlaceholder("history", optional=True, n_messages=4)]
        ),
        b'[{"n_messages":4,"optional":true,"placeholder":"history"}]',
    ),
    "static-messages": PromptCase(
        lambda: ChatPromptTemplate.from_messages(
            [
                SystemMessage(content="Be terse."),
                HumanMessage(content="Hi."),
                AIMessage(content="Hello."),
            ]
        ),
        (
            b'[{"content":"Be terse.","role":"system"},'
            b'{"content":"Hi.","role":"human"},'
            b'{"content":"Hello.","role":"ai"}]'
        ),
    ),
    "static-chat-message": PromptCase(
        # The authored role, never the constant class tag `"chat"` — one of the four
        # amendments folded into (b) at ratification.
        lambda: ChatPromptTemplate.from_messages([ChatMessage(content="Ship it.", role="boss")]),
        b'[{"content":"Ship it.","role":"boss"}]',
    ),
    "static-tool-message": PromptCase(
        lambda: ChatPromptTemplate.from_messages(
            [ToolMessage(content="42", tool_call_id="call-7")]
        ),
        b'[{"content":"42","role":"tool","tool_call_id":"call-7"}]',
    ),
    "static-structured-content": PromptCase(
        lambda: ChatPromptTemplate.from_messages(
            [SystemMessage(content=[{"type": "text", "text": "a"}, "b"])]
        ),
        b'[{"content":[{"text":"a","type":"text"},"b"],"role":"system"}]',
    ),
    "multi-part-content": PromptCase(
        _multipart,
        b'[{"role":"human","template":["describe {thing}","then {q}"]}]',
    ),
    "authored-order-is-semantic": PromptCase(
        # The same two messages the other way round: M is an array in authored order, not a
        # sorted set, so this is a different digest input.
        lambda: ChatPromptTemplate.from_messages([("human", "{q}"), ("system", "You are {role}.")]),
        (b'[{"role":"human","template":"{q}"},{"role":"system","template":"You are {role}."}]'),
    ),
    "empty-chat-template": PromptCase(lambda: ChatPromptTemplate(messages=[]), b"[]"),
    "few-shot": PromptCase(
        lambda: FewShotPromptTemplate(
            examples=[{"q": "a", "a": "b"}],
            example_prompt=PromptTemplate.from_template("{q} -> {a}"),
            suffix="{q}",
            input_variables=["q"],
        ),
        offender="langchain_core:FewShotPromptTemplate",
    ),
    "armed-template": PromptCase(
        lambda: ArmedTemplate(input_variables=[]),
        offender="tests:ArmedTemplate",
    ),
    "unknown-message-item": PromptCase(
        lambda: ChatPromptTemplate(messages=[ArmedMessageItem()]),
        offender="tests:ArmedMessageItem",
        where={"item": 0},
    ),
    "unknown-message-item-after-a-good-one": PromptCase(
        # The gap takes the whole node's digest, never a partial over the messages that were
        # recognised — and the record names *which* item.
        lambda: ChatPromptTemplate(
            messages=[
                SystemMessagePromptTemplate.from_template("ok"),
                ArmedMessageItem(),
            ]
        ),
        offender="tests:ArmedMessageItem",
        where={"item": 1},
    ),
    "unknown-content-part": PromptCase(
        _image_part,
        offender="langchain_core:ImagePromptTemplate",
        where={"item": 0, "part": 1},
    ),
    "surrogate-template": PromptCase(
        lambda: PromptTemplate(template="a\ud800b", input_variables=[]),
        offender="langchain_core:PromptTemplate",
        where={"member": "template", "why": "lone-surrogate"},
    ),
    # The three shapes a *recognised* class can still fail to answer, reachable only through
    # `model_construct` (which skips validation) but reachable — and each takes (b)'s fallback
    # rather than an exception, because §2 puts hard failure at the object boundary and this is
    # not the boundary.
    "template-member-not-a-string": PromptCase(
        lambda: PromptTemplate.model_construct(template=7, input_variables=[]),
        offender="langchain_core:PromptTemplate",
        where={"member": "template", "found": "builtins:int"},
    ),
    "messages-member-not-a-list": PromptCase(
        lambda: ChatPromptTemplate.model_construct(messages=None),
        offender="langchain_core:ChatPromptTemplate",
        where={"member": "messages", "found": "builtins:NoneType"},
    ),
    "message-item-with-an-armed-metaclass": PromptCase(
        # (b)'s per-item dispatch is on `type(item)`, and this item's metaclass answers
        # `__eq__`/`__hash__` with code of its own — so a dict keyed by class, or a tuple
        # membership test, would run it. Identity comparison asks the class nothing.
        lambda: ChatPromptTemplate.model_construct(messages=[ArmedMetaValue()]),
        offender="tests:ArmedMetaValue",
        where={"item": 0},
    ),
    "message-missing-a-required-member": PromptCase(
        # A recognised class that cannot answer a member (b) requires. Coercing the absence to
        # `null` would let §3.6's pipeline drop the member, digesting a shape the author never
        # wrote; the honest fallback is the same one the sibling `model_construct` shapes take.
        lambda: ChatPromptTemplate.model_construct(messages=[SystemMessage.model_construct()]),
        offender="langchain_core:SystemMessage",
        where={"item": 0, "member": "content"},
    ),
    "content-part-missing-its-template": PromptCase(
        lambda: ChatPromptTemplate.model_construct(
            messages=[
                HumanMessagePromptTemplate.model_construct(
                    prompt=[PromptTemplate.model_construct(input_variables=[])]
                )
            ]
        ),
        offender="langchain_core:PromptTemplate",
        where={"item": 0, "member": "template"},
    ),
    "inner-prompt-not-a-template": PromptCase(
        # `model_construct` at both levels: `ChatPromptTemplate.__init__` would itself read the
        # item's `input_variables`, which reaches through to the inner object — the substrate's
        # own construction, not extraction's read, but it would trip the fixture and prove
        # nothing about §7.4.
        lambda: ChatPromptTemplate.model_construct(
            messages=[HumanMessagePromptTemplate.model_construct(prompt=ArmedClient())]
        ),
        offender="tests:ArmedClient",
        where={"item": 0, "member": "prompt"},
    ),
}

#: Which (b) row each prompt case is written for — the coverage claim, checked as an equality
#: rather than as a count.
PROMPT_ROWS: dict[str, str] = {
    "string-template": "string",
    "string-template-untrimmed": "string",
    "string-template-not-nfc": "string",
    "fixed-role-templates": "fixed-role-template",
    "chat-message-template": "chat-message-template",
    "placeholder": "placeholder",
    "placeholder-optional": "placeholder",
    "placeholder-n-messages": "placeholder",
    "static-messages": "static-message",
    "static-chat-message": "static-chat-message",
    "static-tool-message": "static-tool-message",
    "static-structured-content": "static-message",
    "multi-part-content": "fixed-role-template",
    "authored-order-is-semantic": "fixed-role-template",
    "empty-chat-template": "fixed-role-template",
    "few-shot": "fallback",
    "armed-template": "fallback",
    "unknown-message-item": "fallback",
    "unknown-message-item-after-a-good-one": "fallback",
    "unknown-content-part": "fallback",
    "surrogate-template": "fallback",
    "message-item-with-an-armed-metaclass": "fallback",
    "message-missing-a-required-member": "fallback",
    "content-part-missing-its-template": "fallback",
    "template-member-not-a-string": "fallback",
    "messages-member-not-a-list": "fallback",
    "inner-prompt-not-a-template": "fallback",
}

#: The rows (b) closes: five recognised item kinds plus the string branch, plus the fallback.
PROMPT_VOCABULARY: frozenset[str] = frozenset(
    {
        "string",
        "fixed-role-template",
        "chat-message-template",
        "placeholder",
        "static-message",
        "static-chat-message",
        "static-tool-message",
        "fallback",
    }
)


# ── (c): the config table, one row per member rule ───────────────────────────────────────


@dataclass(frozen=True)
class ConfigCase:
    """One (c) row: the model (with its enclosing bindings) and the expected form C.

    Attributes:
        build: Builds ``(model, bindings)``. ``bindings`` is outermost first.
        params: The ``"params"`` members this case adds on top of the base-model defaults —
            declared per case, and merged with :data:`BASE_PARAMS` by the test, so a row states
            only what it is about.
        bound: The expected ``"bound"`` member, or ``None`` when it must be absent.
        degraded: Whether (e)'s ``model_construct`` edge applies, so C does not exist.
    """

    build: Any
    params: dict[str, Any] = field(default_factory=dict)
    bound: dict[str, Any] | None = None
    degraded: bool = False


#: What every ``ArmedChatModel`` digests before its own fields: the ``BaseChatModel``
#: constructor fields whose value is not ``None``.
#:
#: ``metadata`` is the one a reader of a digest needs to know about, and it is declared here
#: with the live version deliberately rather than hidden behind a computed value: from
#: langchain-core 1.4.7 the substrate fills that field with **its own version** at
#: construction, so ``config_digest`` — and therefore ``graph_version`` — moves when
#: langchain-core does, with no user edit behind it. That is (e)'s "a substrate minor release
#: adding a model field with a non-``None`` default moves ``config_digest``; the A1 pin plus
#: the VERSION-COMPAT drift probes are the detection surface", happening on the very first
#: field. Declaring it here makes this table one of those probes: if the substrate stops
#: filling ``metadata``, or fills it differently, the config cases fail rather than the change
#: passing unnoticed.
#:
#: Which is why the member is *conditional* rather than unconditional (EX-17 / PD-038
#: Finding 2): before 1.4.7 the field's default is ``None`` and (c) omits ``None``-valued
#: members, so the digested form legitimately has no ``metadata`` key at all on the two frozen
#: VERSION-COMPAT §3 cells below that patch. The probe keeps its teeth in both directions —
#: a substrate at or above 1.4.7 that stopped filling the field fails these cases, and so does
#: one below it that started.
BASE_PARAMS: dict[str, Any] = {
    "verbose": False,
    "disable_streaming": False,
    "temperature": 0.0,
    **(
        {"metadata": {"lc_versions": {"langchain-core": langchain_core.__version__}}}
        if substrate.CORE_FILLS_LC_VERSIONS_METADATA
        else {}
    ),
}


def _armed(**fields: Any) -> ArmedChatModel:
    """One armed model, with the fields a case is about."""
    return ArmedChatModel(**fields)


#: The mainstream tool-binding shape: the JSON-schema ``dict`` a provider's ``bind_tools``
#: converts its tools to before calling ``bind(tools=…)``. Plain JSON data, so (d)'s coercion K
#: carries it member for member and an edit anywhere inside it moves ``config_digest``.
TOOL_SCHEMA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "lookup_itinerary",
        "description": "Fetch the itinerary legs for a booking reference.",
        "parameters": {
            "type": "object",
            "properties": {"reference": {"type": "string"}},
            "required": ["reference"],
        },
    },
}

#: The same tool with one member edited — the knob EX-16's first acceptance turns.
EDITED_TOOL_SCHEMA: dict[str, Any] = {
    "type": "function",
    "function": {
        **TOOL_SCHEMA["function"],
        "description": "Fetch the itinerary legs, including cancelled ones.",
    },
}


def _armed_tool_body(reference: str) -> str:
    """A tool body that must never run — bound tools are metadata to extraction, not code."""
    return _trip("tool body")  # type: ignore[no-any-return]


def armed_tool(name: str) -> Any:
    """A ``BaseTool`` object whose body is armed, for the K rule 12 limit below."""
    from langchain_core.tools import StructuredTool

    return StructuredTool.from_function(_armed_tool_body, name=name, description=f"the {name} tool")


def bound_with_tools(tools: Any, **fields: Any) -> tuple[ArmedChatModel, tuple[Any, ...]]:
    """A model inside the wrapper ``model.bind(tools=…)`` actually answers with.

    Deliberately the substrate's own ``bind()`` rather than a hand-built ``RunnableBinding``:
    which class comes back is a langchain-core version fact (the stock class below core 1.4.0,
    ``_ChatModelBinding`` at and above it), and after EX-16 the §7.4 (a) enumeration admits both,
    so this fixture states the *authored* shape and lets every cell of the frozen
    VERSION-COMPAT §3 matrix answer it its own way. Before the admission the two cells
    disagreed about the node set for this very workflow — the finding EX-17 handed over.

    ``fields`` are the model's own, so a caller can rebuild the exact model a whole-workflow
    fixture uses and compare the projection against what the extraction produced.
    """
    model = _armed(**fields)
    return model, (model.bind(tools=tools),)


CONFIG_CASES: dict[str, ConfigCase] = {
    "defaults": ConfigCase(lambda: (_armed(), ())),
    "scalars": ConfigCase(
        lambda: (_armed(temperature=0.7, seed=11), ()),
        params={"temperature": 0.7, "seed": 11},
    ),
    "secret-excluded": ConfigCase(
        lambda: (_armed(api_key=ArmedSecret("sk-live")), ()),
    ),
    "null-omitted": ConfigCase(lambda: (_armed(unset=None), ())),
    "sequence": ConfigCase(
        lambda: (_armed(stop_words=["b", "a"]), ()),
        params={"stop_words": ["b", "a"]},
    ),
    "integer-keyed-mapping": ConfigCase(
        lambda: (_armed(logit_bias={50256: -100.0}), ()),
        params={"logit_bias": {"50256": -100.0}},
    ),
    "frozenset": ConfigCase(
        lambda: (_armed(flavours=frozenset({"b", "a"})), ()),
        params={"flavours": ["a", "b"]},
    ),
    "enum": ConfigCase(lambda: (_armed(mode=Flavour.FAST), ()), params={"mode": "fast"}),
    "unrepresentable": ConfigCase(
        lambda: (_armed(plumbing=ArmedClient()), ()),
        params={"plumbing": {"__gebra_unrepresentable__": "tests:ArmedClient"}},
    ),
    "bound-overlay": ConfigCase(
        lambda: _bound(({"stop": ["x"], "seed": 3},)),
        bound={"stop": ["x"], "seed": 3},
    ),
    "bound-outermost-wins": ConfigCase(
        lambda: _bound(({"a": 1, "b": 2}, {"b": 3})),
        bound={"a": 1, "b": 3},
    ),
    "bound-outer-null-removes": ConfigCase(
        lambda: _bound(({"a": 1, "b": 2}, {"b": None})),
        bound={"a": 1},
    ),
    "bound-secret-excluded": ConfigCase(
        lambda: _bound(({"a": 1, "api_key": ArmedSecret("sk")},)),
        bound={"a": 1},
    ),
    "bound-empty-is-absent": ConfigCase(lambda: _bound(({},))),
    "bound-all-omitted-is-absent": ConfigCase(lambda: _bound(({"api_key": ArmedSecret("sk")},))),
    "bound-tools-as-schema-dicts": ConfigCase(
        # EX-16 / DEC-21: the wrapper `bind()` answers with is admitted by exact type, so the
        # tool overlay reaches the digest. The expected form is the schema verbatim under K,
        # which is what makes an edit to any member of it move `config_digest`.
        lambda: bound_with_tools([TOOL_SCHEMA]),
        bound={"tools": [TOOL_SCHEMA]},
    ),
    "bound-tools-as-objects-are-named-by-class": ConfigCase(
        # The recorded limit (PD-043): a `BaseTool` is not JSON data, so K rule 12 answers with
        # its class identity. The tool *set*'s shape moves the digest; swapping one
        # `StructuredTool` for another does not. Declared here rather than described.
        lambda: bound_with_tools([armed_tool("alpha")]),
        bound={"tools": [{"__gebra_unrepresentable__": "langchain_core:StructuredTool"}]},
    ),
    "non-stock-binding-contributes-no-overlay": ConfigCase(
        # DEC-20 stockness intact past the DEC-21 admission: a subclass outside the enumeration
        # contributes nothing, and the fixture's armed `kwargs` makes that a counted decline.
        lambda: _outside_the_enumeration(),
    ),
    "retry-wrapper-is-not-a-binding": ConfigCase(lambda: _not_a_binding()),
    "bound-kwargs-not-a-mapping": ConfigCase(lambda: _malformed_binding(None)),
    "bound-key-with-no-name": ConfigCase(
        lambda: _malformed_binding({ArmedKey(): 1}),
        bound={"__gebra_unrepresentable__": "mapping:key"},
    ),
    "bound-key-collision": ConfigCase(
        # Two keys of **one** binding rendering to one name: (d) rule 9's collision clause, which
        # (c)'s "same member rules" carries into the overlay. Two bindings sharing a key is the
        # outermost-wins rule instead, and `bound-outermost-wins` is that case.
        lambda: _malformed_binding({1: "a", "1": "b"}),
        bound={"__gebra_unrepresentable__": "mapping:key"},
    ),
    "model-construct": ConfigCase(
        lambda: (NeedyChatModel.model_construct(temperature=0.5), ()),
        degraded=True,
    ),
}


def _bound(overlays: tuple[dict[str, Any], ...]) -> tuple[ArmedChatModel, tuple[Any, ...]]:
    """A model inside ``len(overlays)`` bindings — ``overlays`` innermost first.

    Returned outermost first, which is the order §7.4 (a)'s chain and :func:`digests_for` both
    take.
    """
    model = _armed()
    bindings: list[Any] = []
    inner: Any = model
    for overlay in overlays:
        inner = RunnableBinding(bound=inner, kwargs=dict(overlay))
        bindings.append(inner)
    return model, tuple(reversed(bindings))


def _malformed_binding(kwargs: Any) -> tuple[ArmedChatModel, tuple[Any, ...]]:
    """A binding whose ``kwargs`` the substrate's own validation would have refused.

    Reachable only through ``model_construct``, and reachable — so (c)'s overlay read guards
    both shapes rather than assuming them: a ``kwargs`` that is not a mapping contributes
    nothing, and a key with no member name under (d) rule 9 takes the whole overlay to a marker
    rather than to a half-read object.
    """
    model = _armed()
    return model, (RunnableBinding.model_construct(bound=model, kwargs=kwargs),)


def _outside_the_enumeration() -> tuple[ArmedChatModel, tuple[Any, ...]]:
    """A model inside a ``RunnableBinding`` subclass the §7.4 (a) enumeration does not name.

    Its ``kwargs`` is armed, so "contributes no overlay" is checked as a read that did not
    happen rather than as an absent member that might have several causes.
    """
    model = _armed()
    return model, (NonStockBinding(bound=model, kwargs={"stop": ["x"]}),)


def _not_a_binding() -> tuple[ArmedChatModel, tuple[Any, ...]]:
    """A model whose enclosing frame is not an exact ``RunnableBinding`` — it contributes none.

    A ``RunnableRetry`` is a ``RunnableBindingBase`` sibling holding retry settings rather than
    a generation-config overlay, and (c) names ``RunnableBinding``.
    """
    from langchain_core.runnables.retry import RunnableRetry

    model = _armed()
    return model, (RunnableRetry(bound=model, max_attempt_number=3),)


# ── whole-workflow fixtures, for the acceptance claims ───────────────────────────────────


def build_chain(prompt_text: str = "You are a careful assistant.") -> Any:
    """``prompt | model``: one prompt carrier and one model carrier in one fragment.

    ``prompt_text`` is the knob the prompt-only-edit acceptance turns: everything else about
    the two workflows it builds is identical, so a ``graph_version`` difference can only have
    come from the prompt.
    """
    template = ChatPromptTemplate.from_messages(
        [("system", prompt_text), ("human", "{q}"), MessagesPlaceholder("history", optional=True)]
    )
    return template | _armed(temperature=0.2, seed=7, stop_words=["END"])


def build_bound_chain(prompt_text: str = "You are a careful assistant.") -> Any:
    """The same chain with the model inside two bindings — the (a) carrier rule under a wrapper."""
    template = ChatPromptTemplate.from_messages([("system", prompt_text)])
    model = _armed(temperature=0.2)
    inner = RunnableBinding(bound=model, kwargs={"stop": ["x"], "seed": 1})
    outer = RunnableBinding(bound=inner, kwargs={"seed": 2})
    return template | outer


def build_tool_bound_chain(
    prompt_text: str = "You are a careful assistant.", tools: Any = None
) -> Any:
    """``prompt | model.bind(tools=…)`` — the shape EX-16's admission is about.

    Two knobs, and the tests turn them one at a time: ``prompt_text`` for the prompt-edit claim
    every workflow fixture carries, and ``tools`` for the tool-set edit, which reaches
    ``graph_version`` through the ``"bound"`` overlay of the model's own ``config_digest``.
    """
    template = ChatPromptTemplate.from_messages([("system", prompt_text), ("human", "{q}")])
    model = _armed(temperature=0.2, seed=7)
    return template | model.bind(tools=[TOOL_SCHEMA] if tools is None else tools)


def build_builder(prompt_text: str = "You are a careful assistant.") -> Any:
    """A ``StateGraph`` whose nodes are bound directly to a template and to a model (§3, iii)."""
    from typing import TypedDict

    from langgraph.graph import END, START, StateGraph

    class State(TypedDict):
        q: str

    graph: Any = StateGraph(State)
    graph.add_node("prompt", ChatPromptTemplate.from_messages([("system", prompt_text)]))
    graph.add_node("string_prompt", PromptTemplate.from_template(prompt_text))
    graph.add_node("model", _armed(temperature=0.2, seed=7))
    graph.add_edge(START, "prompt")
    graph.add_edge("prompt", "string_prompt")
    graph.add_edge("string_prompt", "model")
    graph.add_edge("model", END)
    return graph


#: Every whole-workflow fixture, for the tripwire and the determinism claim.
WORKFLOWS: dict[str, Any] = {
    "chain": build_chain,
    "bound-chain": build_bound_chain,
    "tool-bound-chain": build_tool_bound_chain,
    "builder": build_builder,
}
