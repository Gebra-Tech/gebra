"""Fixtures for the ``runtime.recursion_limit`` declaration surface (ANNOTATION-API-SPEC §1a, §2,
§3; INTROSPECTION-SPEC §4.1, §8; DEC-36).

**One loop, in every shape the surface reads.** :func:`build_review_loop` is ``START → draft →
review → (again: draft | done: END)`` — one cycle with no counter guard on its declared condition
and no loop variant, so the only termination witness P-02 can find on it is form (b), a declared
``runtime.recursion_limit``. Undeclared, P-02 fails it; declared, P-02 passes it with the
WARNING-grade note (TERMINATION-WITNESS-SPEC §2.2, §2.4). The factories below build that loop
undeclared, declared through ``gebra.recursion_limit`` on the builder, on the compiled graph (the
declaration lands on the builder) and on a ``with_config`` copy, and bound through ``with_config``
beside or without a declaration; and a builderless ``Pregel`` for the compiled-only path. Every
node and router body raises :class:`~tests.sample_workflows.sentinel_graph.SentinelExecutedError`,
which records into ``sentinel_graph.TRIPPED`` as it is built.

**The adversarial carriers (WA-07).** The reads under test are instance-dictionary reads, so the
carriers here are built to catch any read that is not one:

* :class:`ArmedRuntimeBuilder` — a ``StateGraph`` whose class defines ``__gebra_runtime__`` as a
  property that raises, and whose ``__getattribute__`` records every read of a watched name; its
  declaration is planted straight into the instance dictionary, where the ruled read finds it;
* :class:`ArmedConfigCompiled` and :class:`ArmedConfigPregel` — a compiled graph and a builderless
  ``Pregel`` whose class defines ``config`` as a property that **raises when gebra's own code reads
  it** and records every other read with the module that made it. LangGraph's ``get_graph()``
  reads ``self.config`` while it draws (``langgraph/pregel/main.py``), and the compiled path's
  cross-check — the compiled-only path's topology surface — is that drawing, so the property
  answers the substrate (recorded, so the read is pinned rather than narrated) and refuses gebra;
* :class:`RecordingDict` — planted as an instance dictionary, as a ``config`` mapping and as a
  hand-set declaration: every read method it overrides records;
* :class:`RecordingKey` — a ``str`` subclass planted as a key spelled ``__gebra_runtime__`` or
  ``recursion_limit``, whose hash, comparisons and renderings record;
* :class:`RecordingInt` and :class:`RecordingText` — a bound or declared value and a justification
  whose conversions, comparisons and renderings record.

Every recording hook writes into :data:`HOOKS` before it answers, and :data:`CARRIER_READS`
holds the property and ``__getattribute__`` records — both as ``(name, module)`` pairs naming the
module whose code triggered the record, so a test can tell the substrate's own drawing (which
reads ``self.config`` and merges its keys) apart from gebra. The reads the ruling makes run none
of them: :func:`outside_the_substrate` of either ledger stays
empty.

Import safety: importing this module builds nothing; each factory builds when it is called, and
the ``compile()``/``with_config()`` it calls is the fixture's step, never extraction's.
"""

from __future__ import annotations

import sys
import types
from collections.abc import Callable
from typing import Any, TypedDict

from langgraph.channels.last_value import LastValue
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.pregel import NodeBuilder, Pregel

import gebra
from tests.sample_workflows.sentinel_graph import SentinelExecutedError, raiser

#: The declared step budget the factories use — deliberately not a substrate default.
LIMIT = 38

#: Its justification: why that number, in the author's words.
JUSTIFICATION = "three review laps of twelve supersteps each, plus entry and exit"

#: A second declaration, for the sidecar tier and for the conflicts.
SIDECAR_LIMIT = 12
SIDECAR_JUSTIFICATION = "the reviewer gives up after a dozen supersteps"

#: A bound value that differs from :data:`LIMIT`, for the binding conflict.
OTHER_BOUND = 9

#: The ``gebra.toml`` text that declares :data:`SIDECAR_LIMIT` in the ``[runtime]`` table.
SIDECAR_TEXT = (
    'schema = "gebra-sidecar-v1"\n\n[runtime]\n'
    f'recursion_limit = {{ value = {SIDECAR_LIMIT}, justification = "{SIDECAR_JUSTIFICATION}" }}\n'
)

#: The names the recording ``__getattribute__`` overrides watch: the two the ruling reads from an
#: instance dictionary, and the dictionary itself.
WATCHED = frozenset({"__gebra_runtime__", "config", "__dict__"})

#: ``(read, module)`` — every watched attribute read of an armed carrier, and the module whose
#: code made it, recorded before it is answered.
CARRIER_READS: list[tuple[str, str]] = []

#: ``(hook, module)`` — every recording hook that ran, and the module whose code triggered it
#: (directly, or through a built-in such as a hashing probe), recorded before it answers.
HOOKS: list[tuple[str, str]] = []


def outside_the_substrate(records: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """The records whose triggering code is not LangGraph's own.

    The one source of records the tests accept is the substrate's own drawing (it reads
    ``self.config`` and merges its contents); every other record — gebra's, or a standard
    library frame gebra called into (``json``, ``copy``) — is a read the ruled path must not make.
    """
    return [record for record in records if record[1].partition(".")[0] != "langgraph"]


class ReviewState(TypedDict):
    draft: str
    verdict: str


# ── The loop ─────────────────────────────────────────────────────────────────────────────


def build_review_loop(cls: type[StateGraph[Any]] = StateGraph) -> StateGraph[ReviewState]:
    """``START → draft → review → (again: draft | done: END)`` — one cycle, no witness of its own."""
    builder: StateGraph[ReviewState] = cls(ReviewState)
    builder.add_node("draft", raiser("draft"))
    builder.add_node("review", raiser("review"))
    builder.add_edge(START, "draft")
    builder.add_edge("draft", "review")
    builder.add_conditional_edges("review", raiser("route_review"), {"again": "draft", "done": END})
    return builder


def build_undeclared_loop() -> StateGraph[ReviewState]:
    """The loop with no declaration — P-02 fails it (no witness of any form)."""
    return build_review_loop()


def build_declared_loop() -> StateGraph[ReviewState]:
    """The loop declared through ``gebra.recursion_limit`` on the builder."""
    return gebra.recursion_limit(build_review_loop(), LIMIT, justification=JUSTIFICATION)


def compile_undeclared_loop() -> CompiledStateGraph[Any, Any, Any, Any]:
    """The undeclared loop, compiled."""
    return build_review_loop().compile()


def compile_declared_loop() -> CompiledStateGraph[Any, Any, Any, Any]:
    """The loop compiled, then declared on the compiled graph — the call lands on its builder."""
    return gebra.recursion_limit(build_review_loop().compile(), LIMIT, justification=JUSTIFICATION)


def bind_declared_loop(bound: object = LIMIT) -> CompiledStateGraph[Any, Any, Any, Any]:
    """The declared loop, compiled and bound: a ``with_config`` copy shares the builder."""
    compiled = gebra.recursion_limit(
        build_review_loop().compile(), LIMIT, justification=JUSTIFICATION
    )
    return compiled.with_config(recursion_limit=bound)


def bind_undeclared_loop(bound: object = LIMIT) -> CompiledStateGraph[Any, Any, Any, Any]:
    """The undeclared loop, compiled and bound — the binding alone, which never fills the slot."""
    return build_review_loop().compile().with_config(recursion_limit=bound)


def declare_on_a_copy() -> CompiledStateGraph[Any, Any, Any, Any]:
    """A ``with_config`` copy declared after binding: the call still lands on the shared builder."""
    copy = build_review_loop().compile().with_config(recursion_limit=LIMIT)
    return gebra.recursion_limit(copy, LIMIT, justification=JUSTIFICATION)


# ── The builderless loop (INTROSPECTION-SPEC §4.3 rule 4) ────────────────────────────────


def build_review_pregel(
    cls: type[Pregel[Any, Any, Any, Any]] = Pregel,
) -> Pregel[Any, Any, Any, Any]:
    """A hand-built ``Pregel`` with no ``.builder`` — the compiled-only path's subject."""
    node = NodeBuilder().subscribe_only("question").do(raiser("pregel_step")).write_to("answer")
    return cls(
        nodes={"pregel_step": node},
        channels={"question": LastValue(str), "answer": LastValue(str)},
        input_channels="question",
        output_channels="answer",
    )


def declare_pregel() -> Pregel[Any, Any, Any, Any]:
    """A builderless ``Pregel`` declared on itself — "only an object with no builder carries the
    attribute itself" (ANNOTATION-API-SPEC §1a)."""
    return gebra.recursion_limit(build_review_pregel(), LIMIT, justification=JUSTIFICATION)


def bind_declared_pregel() -> Pregel[Any, Any, Any, Any]:
    """A builderless ``Pregel`` bound first and declared on the copy — the order that keeps both."""
    copy = build_review_pregel().with_config(recursion_limit=LIMIT)
    return gebra.recursion_limit(copy, LIMIT, justification=JUSTIFICATION)


def declare_then_bind_pregel() -> Pregel[Any, Any, Any, Any]:
    """A builderless ``Pregel`` declared, *then* bound: ``with_config`` rebuilds the object and drops
    the declaration (A1 addendum A1-D36), so the copy carries the binding alone — the vector the
    EX-D3 critique named, whose answer is the disclosure."""
    declared = gebra.recursion_limit(build_review_pregel(), LIMIT, justification=JUSTIFICATION)
    return declared.with_config(recursion_limit=LIMIT)


# ── Recording hooks ──────────────────────────────────────────────────────────────────────


def _caller() -> str:
    """The module of the nearest frame outside this one — whose code made the read or triggered
    the hook being answered. This module's own frames (a hook, a ``__getattribute__`` override, a
    property getter) are skipped, since they sit between the reader and the record."""
    frame: types.FrameType | None = sys._getframe(1)
    while frame is not None and frame.f_globals.get("__name__") == __name__:
        frame = frame.f_back
    return "<no caller>" if frame is None else str(frame.f_globals.get("__name__"))


def _hook(name: str) -> None:
    """Record ``name`` with the module of the code that triggered the hook calling this."""
    HOOKS.append((name, _caller()))


class RecordingDict(dict[Any, Any]):
    """A ``dict`` subclass whose read methods record before they answer."""

    def __getitem__(self, key: Any) -> Any:
        _hook("dict.__getitem__")
        return super().__getitem__(key)

    def get(self, key: Any, default: Any = None) -> Any:
        _hook("dict.get")
        return super().get(key, default)

    def __contains__(self, key: object) -> bool:
        _hook("dict.__contains__")
        return super().__contains__(key)

    def __iter__(self) -> Any:
        _hook("dict.__iter__")
        return super().__iter__()

    def __len__(self) -> int:
        _hook("dict.__len__")
        return super().__len__()

    def keys(self) -> Any:
        _hook("dict.keys")
        return super().keys()

    def values(self) -> Any:
        _hook("dict.values")
        return super().values()

    def items(self) -> Any:
        _hook("dict.items")
        return super().items()

    def copy(self) -> dict[Any, Any]:
        _hook("dict.copy")
        return dict(super().items())

    def __repr__(self) -> str:
        _hook("dict.__repr__")
        return dict.__repr__(self)


class RecordingKey(str):
    """A ``str`` subclass planted as a dictionary key; its hash, comparisons and renderings record."""

    __slots__ = ()

    def __hash__(self) -> int:
        _hook("key.__hash__")
        return str.__hash__(self)

    def __eq__(self, other: object) -> bool:
        _hook("key.__eq__")
        return str.__eq__(self, other)

    def __ne__(self, other: object) -> bool:
        _hook("key.__ne__")
        return str.__ne__(self, other)

    def __repr__(self) -> str:
        _hook("key.__repr__")
        return str.__repr__(self)

    def __str__(self) -> str:
        _hook("key.__str__")
        return str.__str__(self)

    def __format__(self, spec: str) -> str:
        _hook("key.__format__")
        return str.__format__(self, spec)

    def __iter__(self) -> Any:
        _hook("key.__iter__")
        return str.__iter__(self)

    def __len__(self) -> int:
        _hook("key.__len__")
        return str.__len__(self)

    def partition(self, separator: str) -> tuple[str, str, str]:
        _hook("key.partition")
        return str.partition(self, separator)

    def __getitem__(self, index: Any) -> str:
        _hook("key.__getitem__")
        return str.__getitem__(self, index)

    def __contains__(self, other: object) -> bool:
        _hook("key.__contains__")
        return str.__contains__(self, other)  # type: ignore[operator]

    def __lt__(self, other: str) -> bool:
        _hook("key.__lt__")
        return str.__lt__(self, other)


class RecordingInt(int):
    """An ``int`` subclass used as a declared or bound value; its own methods record."""

    __slots__ = ()

    def __index__(self) -> int:
        _hook("int.__index__")
        return int.__index__(self)

    def __int__(self) -> int:
        _hook("int.__int__")
        return int.__int__(self)

    def __eq__(self, other: object) -> bool:
        _hook("int.__eq__")
        return int.__eq__(self, other)

    def __hash__(self) -> int:
        _hook("int.__hash__")
        return int.__hash__(self)

    def __lt__(self, other: int) -> bool:
        _hook("int.__lt__")
        return int.__lt__(self, other)

    def __gt__(self, other: int) -> bool:
        _hook("int.__gt__")
        return int.__gt__(self, other)

    def __le__(self, other: int) -> bool:
        _hook("int.__le__")
        return int.__le__(self, other)

    def __ge__(self, other: int) -> bool:
        _hook("int.__ge__")
        return int.__ge__(self, other)

    def __bool__(self) -> bool:
        _hook("int.__bool__")
        return int.__bool__(self)

    def __repr__(self) -> str:
        _hook("int.__repr__")
        return int.__repr__(self)

    def __str__(self) -> str:
        _hook("int.__str__")
        return int.__repr__(self)

    def __format__(self, spec: str) -> str:
        _hook("int.__format__")
        return int.__format__(self, spec)


class RecordingText(str):
    """A ``str`` subclass used as a justification; its own methods record."""

    __slots__ = ()

    def strip(self, chars: str | None = None) -> str:
        _hook("text.strip")
        return str.strip(self, chars)

    def encode(self, encoding: str = "utf-8", errors: str = "strict") -> bytes:
        _hook("text.encode")
        return str.encode(self, encoding, errors)

    def __str__(self) -> str:
        _hook("text.__str__")
        return str.__str__(self)

    def __repr__(self) -> str:
        _hook("text.__repr__")
        return str.__repr__(self)

    def __eq__(self, other: object) -> bool:
        _hook("text.__eq__")
        return str.__eq__(self, other)

    def __hash__(self) -> int:
        _hook("text.__hash__")
        return str.__hash__(self)

    def __len__(self) -> int:
        _hook("text.__len__")
        return str.__len__(self)

    def __bool__(self) -> bool:
        _hook("text.__bool__")
        return str.__len__(self) > 0

    def __format__(self, spec: str) -> str:
        _hook("text.__format__")
        return str.__format__(self, spec)

    def __iter__(self) -> Any:
        _hook("text.__iter__")
        return str.__iter__(self)

    def __getitem__(self, index: Any) -> str:
        _hook("text.__getitem__")
        return str.__getitem__(self, index)

    def __contains__(self, other: object) -> bool:
        _hook("text.__contains__")
        return str.__contains__(self, other)  # type: ignore[operator]

    def partition(self, separator: str) -> tuple[str, str, str]:
        _hook("text.partition")
        return str.partition(self, separator)


# ── Hostile type names: the four routes a type's own name could run code by ────────────


class _ModuleObject:
    """A non-string stored as a class's ``__module__``: every attribute read of it records."""

    def __getattribute__(self, name: str) -> Any:
        _hook(f"module-object.{name}")
        return object.__getattribute__(self, name)


class _PlantedModuleKey(str):
    """A key that hashes as ``__module__`` and records any comparison — planted in a class's
    namespace, where a hashing lookup of ``__module__`` would compare it."""

    __slots__ = ()

    def __hash__(self) -> int:
        return str.__hash__("__module__")

    def __eq__(self, other: object) -> bool:
        _hook("planted-module-key.__eq__")
        return False


class ModuleIsAString:
    """Its ``__module__`` is a :class:`RecordingText` — a ``str`` subclass."""


class ModuleIsAnObject:
    """Its ``__module__`` is a :class:`_ModuleObject` — not a string at all."""


class QualnameIsAString:
    """Its ``__qualname__`` is a :class:`RecordingText`."""


ModuleIsAString.__module__ = RecordingText("hostile.module")
ModuleIsAnObject.__module__ = _ModuleObject()  # type: ignore[assignment]
QualnameIsAString.__qualname__ = RecordingText("QualnameIsAString")

#: A class whose namespace holds a planted key that hashes as ``__module__``.
PlantedModuleKey: type = type("PlantedModuleKey", (), {_PlantedModuleKey("planted"): 1})

#: One class per route, by name — instances of each are placed at every position a rejected
#: value's type is named from (:func:`hostile_positions`).
HOSTILE_NAMED: dict[str, type] = {
    "module-is-a-string": ModuleIsAString,
    "module-is-an-object": ModuleIsAnObject,
    "qualname-is-a-string": QualnameIsAString,
    "planted-module-key": PlantedModuleKey,
}


class ModuleHoldsASurrogate:
    """Its ``__module__`` is an exact ``str`` holding a lone surrogate, which UTF-8 cannot
    encode — a name only an assignment by hand can give a class."""


class QualnameHoldsASurrogate:
    """Its ``__qualname__`` is an exact ``str`` holding a lone surrogate."""


ModuleHoldsASurrogate.__module__ = "hostile\ud800module"
QualnameHoldsASurrogate.__qualname__ = "Qualname\ud800"

#: Classes whose name runs nothing but is no text a report can carry: a type named from either
#: must still give a record that encodes (the IR-contract pre-review's round 2, R1).
UNENCODABLE_NAMED: dict[str, type] = {
    "module-holds-a-surrogate": ModuleHoldsASurrogate,
    "qualname-holds-a-surrogate": QualnameHoldsASurrogate,
}


# ── The armed carriers ───────────────────────────────────────────────────────────────────


def _armed_runtime(self: object) -> Any:
    raise SentinelExecutedError("the __gebra_runtime__ property ran — extraction reads the dict")


class ArmedRuntimeBuilder(StateGraph[Any]):
    """A builder whose ``__gebra_runtime__`` is a raising property and whose watched reads record.

    ``gebra.recursion_limit`` cannot attach to it — the property has no setter, so the
    assignment is refused — so its declaration is planted in the instance dictionary directly
    (:func:`build_armed_runtime_loop`), which is where the ruled read looks and the property
    never answers.
    """

    __gebra_runtime__ = property(_armed_runtime)

    def __getattribute__(self, name: str) -> Any:
        if name in WATCHED:
            CARRIER_READS.append((f"builder.{name}", _caller()))
        return super().__getattribute__(name)


def instance_dictionary(obj: object, owner: type) -> dict[str, Any]:
    """``obj``'s instance dictionary through ``owner``'s own descriptor — the fixture's write path."""
    for klass in owner.__mro__:
        entry = vars(klass).get("__dict__")
        if entry is not None:
            held: dict[str, Any] = entry.__get__(obj)
            return held
    raise TypeError(owner)  # pragma: no cover


def _declaration(value: object = LIMIT, justification: object = JUSTIFICATION) -> dict[str, Any]:
    return {"recursion_limit": {"value": value, "justification": justification}}


def build_armed_runtime_loop() -> StateGraph[Any]:
    """:class:`ArmedRuntimeBuilder`'s loop, with its declaration planted in the instance dictionary."""
    builder = build_review_loop(ArmedRuntimeBuilder)
    instance_dictionary(builder, StateGraph)["__gebra_runtime__"] = _declaration()
    CARRIER_READS.clear()
    return builder


def _config_property() -> property:
    """A ``config`` that refuses gebra's own code, answers everyone else, and records each read."""

    def _get(self: object) -> Any:
        module = _caller()
        CARRIER_READS.append(("config", module))
        if module.partition(".")[0] == "gebra":
            raise SentinelExecutedError(f"{module} read `config` through the object's own access")
        return instance_dictionary(self, Pregel).get("config")

    def _set(self: object, value: Any) -> None:
        instance_dictionary(self, Pregel)["config"] = value

    return property(_get, _set)


class ArmedConfigCompiled(CompiledStateGraph[Any, Any, Any, Any]):
    """A compiled graph whose ``config`` is :func:`_config_property` and whose watched reads record."""

    config = _config_property()

    def __getattribute__(self, name: str) -> Any:
        if name in WATCHED - {"config"}:
            CARRIER_READS.append((f"compiled.{name}", _caller()))
        return super().__getattribute__(name)


class ArmedConfigPregel(Pregel[Any, Any, Any, Any]):
    """A builderless ``Pregel`` whose ``config`` is :func:`_config_property` and whose watched reads
    record."""

    config = _config_property()

    def __getattribute__(self, name: str) -> Any:
        if name in WATCHED - {"config"}:
            CARRIER_READS.append((f"pregel.{name}", _caller()))
        return super().__getattribute__(name)


def build_armed_config_compiled() -> CompiledStateGraph[Any, Any, Any, Any]:
    """The declared, bound loop with its class swapped to :class:`ArmedConfigCompiled`."""
    bound = bind_declared_loop()
    bound.__class__ = ArmedConfigCompiled
    CARRIER_READS.clear()
    return bound


def build_armed_config_pregel() -> Pregel[Any, Any, Any, Any]:
    """The declared, bound builderless loop with its class swapped to :class:`ArmedConfigPregel`."""
    pregel = bind_declared_pregel()
    pregel.__class__ = ArmedConfigPregel
    CARRIER_READS.clear()
    return pregel


# ── Planted dictionaries, keys and values ────────────────────────────────────────────────


def build_planted_dict_builder() -> StateGraph[ReviewState]:
    """A declared builder whose instance dictionary has been replaced by a :class:`RecordingDict`."""
    builder = build_declared_loop()
    held = instance_dictionary(builder, StateGraph)
    object.__setattr__(builder, "__dict__", RecordingDict(held))
    HOOKS.clear()
    return builder


def build_planted_key_builder() -> StateGraph[ReviewState]:
    """A builder whose instance dictionary holds a :class:`RecordingKey` spelled
    ``__gebra_runtime__`` — and no exact-``str`` key: a planted key is never the declaration."""
    builder = build_review_loop()
    instance_dictionary(builder, StateGraph)[RecordingKey("__gebra_runtime__")] = _declaration()
    HOOKS.clear()
    return builder


def build_hand_set_recording_declaration() -> StateGraph[ReviewState]:
    """A builder whose hand-set declaration is a :class:`RecordingDict` holding a
    :class:`RecordingInt` value and a :class:`RecordingText` justification — a valid declaration
    the read must take without running any of the three."""
    builder = build_review_loop()
    inner = RecordingDict(value=RecordingInt(LIMIT), justification=RecordingText(JUSTIFICATION))
    outer = RecordingDict(recursion_limit=inner)
    instance_dictionary(builder, StateGraph)["__gebra_runtime__"] = outer
    HOOKS.clear()
    return builder


def build_planted_config_compiled() -> CompiledStateGraph[Any, Any, Any, Any]:
    """An undeclared compiled loop whose ``config`` is a :class:`RecordingDict` binding a
    :class:`RecordingInt`."""
    compiled = compile_undeclared_loop()
    instance_dictionary(compiled, Pregel)["config"] = RecordingDict(
        recursion_limit=RecordingInt(OTHER_BOUND), configurable={}
    )
    HOOKS.clear()
    return compiled


def build_planted_config_key_compiled() -> CompiledStateGraph[Any, Any, Any, Any]:
    """A compiled loop whose ``config`` binds through a :class:`RecordingKey` — never a binding."""
    compiled = compile_undeclared_loop()
    instance_dictionary(compiled, Pregel)["config"] = {RecordingKey("recursion_limit"): LIMIT}
    HOOKS.clear()
    return compiled


def build_planted_config_attribute_key_compiled() -> CompiledStateGraph[Any, Any, Any, Any]:
    """A bound loop whose instance dictionary holds its ``config`` under a :class:`RecordingKey`
    instead of the exact ``str`` key: the ruled read never compares the planted key, so it finds
    no binding. (LangGraph's own drawing looks ``self.config`` up by hashing, so it compares the
    planted key and reads the mapping — the substrate's read, which :data:`HOOKS` attributes.)"""
    compiled = bind_undeclared_loop()
    namespace = instance_dictionary(compiled, Pregel)
    namespace[RecordingKey("config")] = namespace.pop("config")
    HOOKS.clear()
    return compiled


def hostile_positions(value: object) -> dict[str, Callable[[], Any]]:
    """Every position at which a rejected value's type is named, holding ``value``.

    Five on a builder's hand-set ``__gebra_runtime__`` — the attribute itself, the declaration
    object under its ``recursion_limit`` key, that object's ``value``, its ``justification``, a
    member key — and two in a compiled graph's ``config``: the ``config`` itself and its bound
    ``recursion_limit``.
    """

    def hand_set(carried: object) -> Callable[[], StateGraph[Any]]:
        def build() -> StateGraph[Any]:
            builder = build_review_loop()
            instance_dictionary(builder, StateGraph)["__gebra_runtime__"] = carried
            return builder

        return build

    def configured(config: object) -> Callable[[], CompiledStateGraph[Any, Any, Any, Any]]:
        def build() -> CompiledStateGraph[Any, Any, Any, Any]:
            compiled = compile_undeclared_loop()
            instance_dictionary(compiled, Pregel)["config"] = config
            return compiled

        return build

    return {
        "attribute": hand_set(value),
        "declaration": hand_set({"recursion_limit": value}),
        "value": hand_set(_declaration(value=value)),
        "justification": hand_set(_declaration(justification=value)),
        "member-key": hand_set(
            {"recursion_limit": {"value": LIMIT, "justification": JUSTIFICATION, value: 1}}
        ),
        "config": configured(value),
        "bound-value": configured({"recursion_limit": value}),
    }


def _armed_pregel_runtime(self: object) -> Any:
    raise SentinelExecutedError("the __gebra_runtime__ property ran on a Pregel")


class ArmedRuntimePregel(Pregel[Any, Any, Any, Any]):
    """A builderless ``Pregel`` whose ``__gebra_runtime__`` is a raising property and whose
    watched reads record — the compiled-only path's twin of :class:`ArmedRuntimeBuilder`."""

    __gebra_runtime__ = property(_armed_pregel_runtime)

    def __getattribute__(self, name: str) -> Any:
        if name in WATCHED:
            CARRIER_READS.append((f"pregel.{name}", _caller()))
        return super().__getattribute__(name)


def build_armed_runtime_pregel() -> Pregel[Any, Any, Any, Any]:
    """:class:`ArmedRuntimePregel`, its declaration planted in its instance dictionary."""
    pregel = build_review_pregel(ArmedRuntimePregel)
    instance_dictionary(pregel, Pregel)["__gebra_runtime__"] = _declaration()
    CARRIER_READS.clear()
    return pregel


def build_planted_dict_pregel() -> Pregel[Any, Any, Any, Any]:
    """A declared builderless ``Pregel`` whose instance dictionary is a :class:`RecordingDict`."""
    pregel = declare_pregel()
    held = instance_dictionary(pregel, Pregel)
    object.__setattr__(pregel, "__dict__", RecordingDict(held))
    HOOKS.clear()
    return pregel


def build_planted_key_pregel() -> Pregel[Any, Any, Any, Any]:
    """A builderless ``Pregel`` holding a :class:`RecordingKey` spelled ``__gebra_runtime__``
    and no exact-``str`` key — never the declaration."""
    pregel = build_review_pregel()
    instance_dictionary(pregel, Pregel)[RecordingKey("__gebra_runtime__")] = _declaration()
    HOOKS.clear()
    return pregel


def build_recording_declaration_pregel() -> Pregel[Any, Any, Any, Any]:
    """A builderless ``Pregel`` whose hand-set declaration is recording ``dict``/``int``/``str``
    subclasses — a valid declaration the read must take without running any of them."""
    pregel = build_review_pregel()
    inner = RecordingDict(value=RecordingInt(LIMIT), justification=RecordingText(JUSTIFICATION))
    instance_dictionary(pregel, Pregel)["__gebra_runtime__"] = RecordingDict(recursion_limit=inner)
    HOOKS.clear()
    return pregel


# ── Registries the tests and the guarded child iterate ───────────────────────────────────

#: Builders — extracted on the builder path, and compiled for the builder-primary path.
BUILDERS: dict[str, Callable[[], StateGraph[Any]]] = {
    "undeclared": build_undeclared_loop,
    "declared": build_declared_loop,
    "armed-runtime": build_armed_runtime_loop,
    "planted-dict": build_planted_dict_builder,
    "planted-key": build_planted_key_builder,
    "hand-set-recording": build_hand_set_recording_declaration,
}

#: Compiled graphs with a builder — the builder-primary path.
COMPILED: dict[str, Callable[[], CompiledStateGraph[Any, Any, Any, Any]]] = {
    "undeclared": compile_undeclared_loop,
    "declared": compile_declared_loop,
    "bound-equal": bind_declared_loop,
    "bound-differs": lambda: bind_declared_loop(OTHER_BOUND),
    "bound-undeclared": bind_undeclared_loop,
    "bound-bool": lambda: bind_undeclared_loop(True),
    "bound-string": lambda: bind_undeclared_loop("7"),
    "bound-negative": lambda: bind_undeclared_loop(-3),
    "bound-too-large": lambda: bind_undeclared_loop(2**53),
    "declared-on-a-copy": declare_on_a_copy,
    "armed-config": build_armed_config_compiled,
    "planted-config": build_planted_config_compiled,
    "planted-config-key": build_planted_config_key_compiled,
    "planted-config-attribute-key": build_planted_config_attribute_key_compiled,
}

#: Builderless ``Pregel`` objects — the compiled-only path.
PREGELS: dict[str, Callable[[], Pregel[Any, Any, Any, Any]]] = {
    "undeclared": build_review_pregel,
    "declared": declare_pregel,
    "bound-and-declared": bind_declared_pregel,
    "declared-then-bound": declare_then_bind_pregel,
    "armed-config": build_armed_config_pregel,
    "armed-runtime": build_armed_runtime_pregel,
    "planted-dict": build_planted_dict_pregel,
    "planted-key": build_planted_key_pregel,
    "hand-set-recording": build_recording_declaration_pregel,
}

__all__ = [
    "BUILDERS",
    "CARRIER_READS",
    "COMPILED",
    "HOOKS",
    "HOSTILE_NAMED",
    "JUSTIFICATION",
    "LIMIT",
    "OTHER_BOUND",
    "PREGELS",
    "SIDECAR_JUSTIFICATION",
    "SIDECAR_LIMIT",
    "SIDECAR_TEXT",
    "UNENCODABLE_NAMED",
    "WATCHED",
    "ArmedConfigCompiled",
    "ArmedConfigPregel",
    "ArmedRuntimeBuilder",
    "ArmedRuntimePregel",
    "ModuleHoldsASurrogate",
    "ModuleIsAString",
    "ModuleIsAnObject",
    "PlantedModuleKey",
    "QualnameHoldsASurrogate",
    "QualnameIsAString",
    "RecordingDict",
    "RecordingInt",
    "RecordingKey",
    "RecordingText",
    "ReviewState",
    "bind_declared_loop",
    "bind_declared_pregel",
    "bind_undeclared_loop",
    "build_armed_config_compiled",
    "build_armed_config_pregel",
    "build_armed_runtime_loop",
    "build_armed_runtime_pregel",
    "build_declared_loop",
    "build_hand_set_recording_declaration",
    "build_planted_config_attribute_key_compiled",
    "build_planted_config_compiled",
    "build_planted_config_key_compiled",
    "build_planted_dict_builder",
    "build_planted_dict_pregel",
    "build_planted_key_builder",
    "build_planted_key_pregel",
    "build_recording_declaration_pregel",
    "build_review_loop",
    "build_review_pregel",
    "build_undeclared_loop",
    "compile_declared_loop",
    "compile_undeclared_loop",
    "declare_on_a_copy",
    "declare_pregel",
    "declare_then_bind_pregel",
    "hostile_positions",
    "instance_dictionary",
    "outside_the_substrate",
]
