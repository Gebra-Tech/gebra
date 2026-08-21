"""Armed fixtures for the annotation-decorator tripwire (ANNOTATION-API-SPEC §1; WA-07).

Everything in this module raises if it is touched, and each kind of touching is a distinct
hazard the decorator surface has to stay clear of:

* **Calling the decorated object.** Every target is an :func:`armed` callable whose body is a
  single ``raise``. §1 says decoration "never wraps, reorders, or invokes"; a decorator that
  invoked its argument would fail the run rather than be caught in review.
* **Rendering a rejected value.** :class:`HostileValue` raises from ``__repr__`` *and*
  ``__str__``. An error message built with ``{value!r}`` would therefore replace
  ``GebraContractError`` with this module's own exception — which is how the hazard EX-02's
  pre-review found on the extraction path (``str(label)`` on a user object) would show up
  here. The refusal paths must name the type instead.
* **Reading a container through its own accessors.** :class:`HostileDict`,
  :class:`HostileList` and :class:`HostileStr` are built-in subclasses whose ``items``,
  ``__iter__``, ``keys``, ``__getitem__`` and ``__str__`` raise. They must be read
  *successfully* — through the unbound built-in accessors — because a decorator argument is
  legitimate data that happens to have hostile hooks.

Importing this module runs every decorator in :data:`ARMED_DECORATIONS` (a decorator factory
is called at import), which is the point: §1 puts these errors "at import time".

Nothing here imports langgraph, opens a socket, or executes anything.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Final

import gebra
from gebra.annotations import NodeContract

#: ``gebra``, with its types erased — the refusals below hand the decorators values of
#: deliberately the wrong kind, and a type checker is right to reject every one of them.
#: What they exercise is the *runtime* refusal, which is the half no type checker makes:
#: a caller who runs none, or a value that is only wrong at run time. Everything in
#: :data:`ARMED_DECORATIONS` goes through the typed surface.
untyped: Any = gebra


class ContractSentinelError(RuntimeError):
    """Raised by any sentinel here that gets touched.

    Decoration must never cause this: a raise means the decorator surface called a node,
    rendered an unchecked value, or read a container through a hook it does not control.
    """


def armed(label: str) -> Callable[..., Any]:
    """A node callable that raises if it is ever called — the target, per decoration."""

    def _sentinel(*args: Any, **kwargs: Any) -> Any:
        raise ContractSentinelError(f"{label!r} was invoked — decoration must never call it")

    _sentinel.__name__ = label
    _sentinel.__qualname__ = f"armed.{label}"
    _sentinel.__doc__ = f"the armed sentinel {label!r}"
    return _sentinel


class HostileValue:
    """A decorator argument that raises if anyone renders it.

    Not iterable on purpose: an ``Iterable`` argument is materialized by design (§1 types
    ``reads``/``writes``/``effects`` as ``Iterable[str]``), so making this one iterable would
    test a rule the surface does not have. What it does test is that every refusal names the
    *type* of what it refused.
    """

    def __repr__(self) -> str:
        raise ContractSentinelError("__repr__ was called on a rejected decorator argument")

    def __str__(self) -> str:
        raise ContractSentinelError("__str__ was called on a rejected decorator argument")


class HostileKey(HostileValue):
    """The same, as a mapping key: hashable, and still never renderable."""

    def __hash__(self) -> int:
        return 0

    def __eq__(self, other: object) -> bool:
        return self is other


class HostileStr(str):
    """A ``str`` subclass whose own accessors raise — read through ``str.__str__`` or not."""

    def __str__(self) -> str:
        raise ContractSentinelError("str.__str__ was resolved through the subclass")

    def __repr__(self) -> str:
        raise ContractSentinelError("repr() reached a str subclass's own hook")


class HostileDict(dict[Any, Any]):
    """A ``dict`` subclass whose own accessors raise — read through ``dict.items`` or not.

    ``get`` is armed alongside the rest because an instance ``__dict__`` can be *assigned* a
    ``dict`` subclass, which puts this class on the namespace-read path of
    :func:`gebra.annotations.read_contract`.
    """

    def items(self) -> Any:
        raise ContractSentinelError("dict.items was resolved through the subclass")

    def get(self, *args: Any, **kwargs: Any) -> Any:
        raise ContractSentinelError("dict.get was resolved through the subclass")

    def keys(self) -> Any:
        raise ContractSentinelError("dict.keys was resolved through the subclass")

    def __getitem__(self, key: Any) -> Any:
        raise ContractSentinelError("dict.__getitem__ was resolved through the subclass")

    def __iter__(self) -> Any:
        raise ContractSentinelError("dict.__iter__ was resolved through the subclass")


class RecordingIterable:
    """A *positive* control: an iterable whose ``__iter__`` is expected to run.

    §1 types ``reads``/``writes``/``effects`` as ``Iterable[str]``, so materializing an
    arbitrary iterable is a residual the decorator surface cannot avoid and states rather
    than hides. Recording the fact makes it a tested residual instead of a reviewed one.
    """

    def __init__(self, *keys: str) -> None:
        self.keys = keys
        self.iterations = 0

    def __iter__(self) -> Any:
        self.iterations += 1
        return iter(self.keys)


class HostileList(list[Any]):
    """A ``list`` subclass whose ``__iter__`` raises — read through ``list.__iter__`` or not."""

    def __iter__(self) -> Any:
        raise ContractSentinelError("list.__iter__ was resolved through the subclass")


class SlottedNode:
    """A callable that cannot carry an attribute — ANNOTATION §6's sidecar-fallback case."""

    __slots__ = ()

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        raise ContractSentinelError("a slotted node was invoked")


def _stack(fn: Callable[..., Any]) -> Callable[..., Any]:
    """A five-decorator stack over one object — the shape §1's at-most-once rule quantifies."""
    return gebra.contract(reads=["itinerary", "budget"], writes=["booking_ref"])(
        gebra.effect("network", "billable", "irreversible")(
            gebra.idempotent(key="booking_ref")(
                gebra.deterministic(seed=7)(gebra.compensation(hook="cancel_booking")(fn))
            )
        )
    )


def _all_nine(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Every one of the nine annotatable slots, declared across one stack.

    ``pure=False`` rather than ``True`` because the D-011 exclusivity rule makes "pure and
    effectful" unauthorable — which is the point of the rule, and why this fixture is the one
    that shows the surface really does reach all nine.
    """
    return gebra.contract(
        reads=["itinerary"],
        writes=["booking_ref"],
        effects=["network"],
        pure=False,
        idempotent={"key": "booking_ref"},
        deterministic={"seed": 7, "temperature": 0.0},
        args_schema={"type": "object", "required": ["itinerary"]},
    )(gebra.variant(key="remaining", measure="len")(gebra.compensation(hook="undo")(fn)))


#: One entry per decoration shape the §1 surface carries. Every value is applied to a freshly
#: armed callable, so a decorator that invoked its argument would trip the sentinel. The
#: guarded child derives its own counts from this table, so a shape added here joins the
#: WA-07 claim with it.
ARMED_DECORATIONS: Final[dict[str, Callable[[Callable[..., Any]], Callable[..., Any]]]] = {
    "contract-reads-writes": gebra.contract(reads=["query"], writes=["plan"]),
    "contract-negatives": gebra.contract(pure=False, idempotent=False, deterministic=False),
    "contract-empty-sets": gebra.contract(reads=[], writes=[], effects=[]),
    "contract-args-schema": gebra.contract(
        args_schema={"type": "object", "properties": {"q": {"type": "string"}}}
    ),
    "contract-object-forms": gebra.contract(
        idempotent={"key": "booking_ref"}, deterministic={"seed": 42, "temperature": 0.0}
    ),
    "pure": gebra.pure,
    "effect": gebra.effect("network", "billable"),
    "idempotent-bare": gebra.idempotent,
    "idempotent-keyed": gebra.idempotent(key="booking_ref"),
    "deterministic-bare": gebra.deterministic,
    "deterministic-seeded": gebra.deterministic(seed=42, temperature=0.0),
    "variant": gebra.variant(key="remaining", measure="len"),
    "compensation": gebra.compensation(hook="cancel_booking"),
    "hostile-subclass-values": gebra.contract(
        reads=HostileList(["itinerary"]),
        effects=[HostileStr("network")],
        idempotent=HostileDict({"key": "booking_ref"}),
        args_schema=HostileDict({"enum": HostileList([1, 2])}),
    ),
    "stack": _stack,
    "all-nine": _all_nine,
}


def hostile_namespace_target() -> Callable[..., Any]:
    """An armed callable whose own ``__dict__`` *is* a hostile ``dict`` subclass.

    Decoration must succeed on it: reading and writing a target's namespace goes through the
    unbound built-in accessors, so the subclass's ``get`` never runs.
    """
    target = armed("hostile_namespace")
    target.__dict__ = HostileDict()
    return target


def _pre_set_carrier() -> Callable[..., Any]:
    """An armed callable whose ``__gebra_contract__`` was set by something that is not gebra."""
    target = armed("foreign_carrier")
    target.__gebra_contract__ = {"pure": True}  # type: ignore[attr-defined]
    return target


#: One entry per refusal the §1 surface makes, written as a *completed* decoration: some
#: refusals happen when the decorator factory normalizes its arguments and some when the
#: decorator is applied, and writing them uniformly is what keeps the table from quietly
#: testing only the first kind. Each thunk must raise ``GebraContractError`` — and must raise
#: *it*, not this module's sentinel, which is what says the refusal path rendered nothing it
#: had not checked and called nothing it was handed.
REFUSED_DECORATIONS: Final[dict[str, Callable[[], object]]] = {
    # The four §1 consistency rules.
    "duplicate-slot": lambda: gebra.pure(gebra.pure(armed("duplicate"))),
    "duplicate-slot-identical-values": lambda: gebra.contract(reads=["a"])(
        gebra.contract(reads=["a"])(armed("identical"))
    ),
    "pure-with-effects": lambda: gebra.contract(pure=True, effects=["network"])(armed("both")),
    "pure-then-effects": lambda: gebra.effect("network")(gebra.pure(armed("split"))),
    "effects-then-pure": lambda: gebra.pure(gebra.effect("network")(armed("split"))),
    "unknown-effect-tag": lambda: gebra.effect("teleport")(armed("tag")),
    "deterministic-without-seed": lambda: gebra.deterministic(temperature=0.0)(armed("det")),
    # The closed nine-slot surface.
    "out-of-reach-slot": lambda: untyped.contract(retry_policy={"max_attempts": 3})(armed("oor")),
    "slot-with-its-own-decorator": lambda: untyped.contract(variant={"key": "n"})(armed("v")),
    "typo": lambda: untyped.contract(effect=["network"])(armed("typo")),
    "hostile-keyword": lambda: untyped.contract(**{HostileStr("retry_policy"): 1})(armed("hk2")),
    # Values, each rejected without being rendered.
    "hostile-reads": lambda: untyped.contract(reads=HostileValue())(armed("hr")),
    "hostile-tag": lambda: untyped.effect(HostileValue())(armed("ht")),
    "hostile-args-schema-leaf": lambda: untyped.contract(args_schema={"default": HostileValue()})(
        armed("hs")
    ),
    "hostile-args-schema-key": lambda: untyped.contract(args_schema={HostileKey(): 1})(armed("hk")),
    "hostile-seed": lambda: untyped.deterministic(seed=HostileValue())(armed("hd")),
    "hostile-hook": lambda: untyped.compensation(hook=HostileValue())(armed("hh")),
    "bare-string-reads": lambda: gebra.contract(reads="budget")(armed("bs")),
    "bare-effect-decorator": lambda: untyped.effect(armed("bare")),
    # The target itself.
    "slotted-target": lambda: gebra.pure(SlottedNode()),
    "foreign-carrier": lambda: gebra.pure(_pre_set_carrier()),
}


#: A contract with no slot declared — the value every "declared iff not None" test compares
#: against, and proof that the empty contract is constructible rather than special.
EMPTY_CONTRACT: Final = NodeContract()
