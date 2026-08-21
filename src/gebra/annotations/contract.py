"""The decorator declaration surface — ANNOTATION-API-SPEC §1.

``@gebra.contract`` and its six shorthands are how an author declares a node contract next to
the node. §1 fixes what they do in one sentence: they "attach metadata under one namespaced
attribute (``__gebra_contract__``) and return the function unchanged — they never wrap,
reorder, or invoke it".

Three properties carry the whole surface, and each is enforced rather than documented.

**Identity.** Every decorator here returns the object it was given — the *same* object, not
an equal one. This is not tidiness: §6 requires annotations to survive ``.compile()``, and
they do so precisely because gebra adds no wrapper for LangGraph's own wrapping to replace.
It also settles the never-invokes question at this surface by construction (WA-07): a
decorator that builds no callable has nothing to call, and one that returns its input
unchanged cannot have run that input's body.

**One attribute, in IR spellings.** The attached value is a :class:`NodeContract` — a frozen
model whose members are exactly the nine annotatable slots of
:data:`~gebra.annotations.slots.ANNOTATION_SLOTS`, named as the IR names the slots rather
than as the decorator arguments spell them (``reads``→``input``, ``writes``→``output``,
``effects``→``effect``). That is the vocabulary §5's (node id, slot) grade lookup and §3's
per-slot precedence chain are written in, so the carrier speaks it directly, and
``extra="forbid"`` makes the nine-slot closure structural rather than a convention.

**Errors at import time, and only these four.** §1's consistency rules raise
:class:`~gebra.annotations.errors.GebraContractError` "at import time — cheap, early, never
at extraction". Exactly four rules live here: the at-most-once slot rule, ``pure``/``effects``
exclusivity, the closed effect vocabulary, and the ``deterministic`` object form's required
``seed``. The two decision D-012 checks §1 states in the same list — an idempotency key that
must appear in the resolved ``input``, and ``irreversible`` together with ``idempotent=True``
— are deliberately **not** here: §1 says both "need the *resolved* contract, so they run at
extraction, not decoration — warning-grade, never an error". Enforcing either here would turn
a warning into an import failure and would judge a stack against an ``input`` set that does
not exist yet.

**No decorator argument is rendered before it is checked.** Error messages name a rejected
value's *type* (:func:`~gebra.naming.type_identity`) and show its value only once it is known
to be a plain string, number or bool. A message built with ``{value!r}`` would run the
value's own ``__repr__``, which would let a decorator argument replace gebra's error with an
exception of its own — the same hazard EX-02's pre-review found on the extraction path, in
the one other place this package reads user-supplied values. Foreign containers are read
through unbound built-in accessors for the same reason (:mod:`gebra.ir.canonical` established
the pattern), and a ``**kwargs`` key is copied into a plain ``str`` before anything looks at
it, since CPython admits a ``str`` subclass there.

Nothing here imports langgraph or opens a socket, and no decoration path calls the object it
decorates. **Two residuals, stated rather than implied**, because "executes nothing" would be
too strong a claim for a surface whose whole job is to accept caller-supplied values:

* §1 types ``reads``/``writes``/``effects`` as ``Iterable[str]``, and an iterable has to be
  iterated to be read. ``list``/``tuple`` go through the unbound accessors, but anything else
  — a generator, a ``set``, a custom container — runs its own ``__iter__``/``__next__``. That
  is the caller's own value in the caller's own import, not a node being invoked, and there
  is no way to accept §1's declared type without it. Nothing re-iterates afterwards:
  extraction reads the already-materialized tuple. The bound is stated, not enforced — a
  generator that never stops would hang decoration, and capping the length would be inventing
  a limit §1 does not have.
* Attachment is a ``setattr``, so a target's own ``__setattr__`` or a data descriptor on its
  metaclass runs. That is inherent to §1's "attach metadata under one namespaced attribute",
  and the failure case is handled: a target that cannot carry one is pointed at §6's sidecar.
"""

from __future__ import annotations

import difflib
import math
from collections.abc import Callable, Iterable, Mapping
from types import MappingProxyType
from typing import Any, Final, TypeVar, overload

from pydantic import BaseModel, ConfigDict

from gebra.annotations.errors import ContractErrorReason, GebraContractError
from gebra.annotations.slots import ANNOTATION_SLOTS, EFFECT_TAGS, AnnotationSlot
from gebra.ir.canonical import I_JSON_MAX_INT, I_JSON_MIN_INT
from gebra.ir.models import Compensation, DeterministicSpec, IdempotentKey, Variant
from gebra.naming import type_identity

__all__ = [
    "CONTRACT_ATTRIBUTE",
    "SLOT_KEYWORDS",
    "NodeContract",
    "compensation",
    "contract",
    "deterministic",
    "effect",
    "idempotent",
    "normalize_declared_value",
    "normalize_effect_members",
    "pure",
    "read_contract",
    "variant",
]

#: The one namespaced attribute §1 and §6 fix for the carrier. Normative, not a convention:
#: §6 relies on the name being gebra's own, so that LangGraph's wrapping of a node callable
#: "cannot strip it by replacing a wrapper Gebra never added", and INTROSPECTION §3 reads it
#: back under this spelling.
CONTRACT_ATTRIBUTE: Final = "__gebra_contract__"

#: The decorated callable, always returned unchanged (§1's own ``F``).
F = TypeVar("F", bound=Callable[..., object])

#: How deep an ``args_schema`` may nest. Set far above anything a JSON Schema needs; it
#: exists so a self-referential mapping becomes a message rather than a ``RecursionError``.
_MAX_SCHEMA_DEPTH: Final = 64

#: The keywords :func:`contract` accepts, in signature order — the seven of the nine slots
#: that have a ``contract()`` route. ``variant`` and ``compensation`` are annotatable too,
#: but only through their own decorators (§1).
_CONTRACT_KEYWORDS: Final[tuple[str, ...]] = (
    "reads",
    "writes",
    "effects",
    "pure",
    "idempotent",
    "deterministic",
    "args_schema",
)

#: Ledger slots §1 puts "out of annotation reach", each with why. Reaching for one is a
#: specific misunderstanding, so it gets a specific answer rather than "unknown keyword".
_OUT_OF_REACH: Final[Mapping[str, str]] = MappingProxyType(
    {
        "retry_policy": (
            "extracted, never annotated: it is projected from the builder's "
            "StateNodeSpec.retry_policy (INTROSPECTION-SPEC §3)"
        ),
        "prompt_digest": (
            "computed, never annotated: the extractor digests the node's prompt template "
            "(ir-field-ledger §3)"
        ),
        "config_digest": (
            "computed, never annotated: the extractor digests the node's generation config "
            "(ir-field-ledger §3)"
        ),
        "interrupts": (
            "extracted, never annotated: interrupt gates are a compile() kwarg, read into "
            "runtime.interrupts (INTROSPECTION-SPEC §4)"
        ),
        "checkpointer": (
            "extracted, never annotated: checkpointing is a compile() kwarg, read into "
            "runtime.checkpointer (INTROSPECTION-SPEC §4)"
        ),
        "recursion_limit": (
            "a graph-level runtime slot rather than a node contract (IR-SPEC §3.5)"
        ),
        "source": "part of the parked data-isolation track (D-017), with no surface in this spec",
        "map": "part of the parked data-isolation track (D-017), with no surface in this spec",
    }
)

#: The IR names of the three slots whose ``contract()`` keyword is spelled differently. A
#: caller who reaches for the IR spelling has the right slot and the wrong word, which is a
#: different mistake from a typo and gets a different answer.
_IR_SPELLINGS: Final[Mapping[str, str]] = MappingProxyType(
    {"input": "reads", "output": "writes", "effect": "effects"}
)

#: The declaration spelling of each annotatable slot → the IR slot it fills. §1 states the
#: nine as pairs (``reads``→``input``, ``writes``→``output``, ``effects``→``effect``) and §2's
#: sidecar example writes the left-hand side, so this table is the *one* vocabulary both
#: declaration surfaces are keyed by — "the decorator (§1) and sidecar (§2) share the set
#: byte-for-byte" (§1).
SLOT_KEYWORDS: Final[Mapping[str, AnnotationSlot]] = MappingProxyType(
    {
        "reads": "input",
        "writes": "output",
        "effects": "effect",
        "pure": "pure",
        "idempotent": "idempotent",
        "deterministic": "deterministic",
        "args_schema": "args_schema",
        "variant": "variant",
        "compensation": "compensation",
    }
)


class NodeContract(BaseModel):
    """A declared node contract — what ``__gebra_contract__`` holds (ANNOTATION §1).

    Exactly the nine annotatable slots, in their IR spellings and IR shapes, so that §3's
    precedence chain and §5's grade lookup read it without translating. A slot is **declared
    iff its value is not** ``None`` — §3's "Set means not-``None``" rule, which is why an
    explicit ``pure=False`` occupies its slot and an omitted one does not, and why no
    separate record of "which slots were set" is needed.

    Frozen, ``extra="forbid"`` and ``strict=True``, following the A6 conventions the IR and
    envelope bases carry: the value reaches ``graph_version`` through the §3 resolution, so
    an unknown member has to be an error rather than silently-dropped content, and a slot
    that could be *rebound* after attachment could move a digest with no re-decoration in
    sight. One residual, stated because ``frozen`` is easy to over-read: freezing prevents
    rebinding a slot, not mutation *inside* one, and ``args_schema`` is the one slot whose
    value has an interior. Its arrays are frozen into tuples, but its objects stay ordinary
    ``dict``s — a read-only proxy could not be canonicalized, since
    :func:`gebra.ir.canonical.graph_version` reads foreign content with ``isinstance(...,
    dict)``. So a holder of the carrier can still edit the schema in place.

    Values arrive here already normalized by this module's decorators — plain strings, bools,
    ints, floats, tuples, JSON data, and the four IR sub-models — so this model never
    validates a raw user value and never renders one.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    input: tuple[str, ...] | None = None
    """Declared state-key reads (``reads=``) — IR ``input`` (decision D-010 @INPUT)."""
    output: tuple[str, ...] | None = None
    """Declared state-key writes (``writes=``) — IR ``output`` (decision D-010 @OUTPUT)."""
    effect: tuple[str, ...] | None = None
    """Declared effect tags (``effects=``), each from :data:`EFFECT_TAGS` (decision D-011)."""
    pure: bool | None = None
    idempotent: bool | IdempotentKey | None = None
    deterministic: bool | DeterministicSpec | None = None
    args_schema: dict[str, Any] | None = None
    """A JSON Schema object; 1.0 imposes no schema algebra on its contents (ledger §3)."""
    variant: Variant | None = None
    compensation: Compensation | None = None

    @classmethod
    def model_construct(cls, _fields_set: set[str] | None = None, **values: Any) -> Any:
        """Refuse construction that skips validation (A6 PC-6).

        Raises:
            NotImplementedError: always. A contract built without validation would carry an
                unchecked value into the §3 resolution and from there into ``graph_version``.
        """
        raise NotImplementedError(
            f"{cls.__name__}.model_construct() is banned (A6 PC-6): it skips validation, and a "
            "declared contract is resolved into the IR and digested. Use the decorators of "
            "gebra.annotations, or the constructor."
        )

    def declared_slots(self) -> tuple[AnnotationSlot, ...]:
        """The slots this contract declares, in :data:`ANNOTATION_SLOTS` order.

        "Declared" is §3's test — not ``None``. An explicit negative (``pure=False``) is a
        declaration and appears here; an omitted slot does not.
        """
        return tuple(slot for slot in ANNOTATION_SLOTS if getattr(self, slot) is not None)

    def slot_value(self, slot: AnnotationSlot) -> object:
        """The value of ``slot``, or ``None`` when it is not declared."""
        return getattr(self, slot)


def read_contract(target: object) -> NodeContract | None:
    """The contract ``target`` itself carries, or ``None``.

    Reads the object's **own** namespace rather than using ``getattr``, so a class that
    inherits a decorated base is not reported as carrying its base's contract. This answers
    the single-object question only: §6's walk along ``functools.wraps`` chains, and its
    outermost-carrier rule for a chain with several carriers, belong to the extraction-time
    resolution, not here.

    The namespace is read through the unbound built-in accessor, because an instance
    ``__dict__`` may be *assigned* a ``dict`` subclass — so ``namespace.get(...)`` would run
    that subclass's own ``get`` on a target gebra was merely asked to decorate (WA-07).
    ``mappingproxy``, which a class carries, cannot be subclassed, but is read the same way
    so the two branches say the same thing.

    Raises:
        GebraContractError: if ``target`` carries a ``__gebra_contract__`` that is not a
            :class:`NodeContract`. Overwriting it silently would discard whatever set it.
    """
    namespace = getattr(target, "__dict__", None)
    if isinstance(namespace, dict):
        carried = dict.get(namespace, CONTRACT_ATTRIBUTE)
    elif isinstance(namespace, MappingProxyType):
        carried = MappingProxyType.get(namespace, CONTRACT_ATTRIBUTE)
    else:
        return None
    if carried is None:
        return None
    if not isinstance(carried, NodeContract):
        raise GebraContractError(
            f"{CONTRACT_ATTRIBUTE} is already set to a {type_identity(carried)}, which is not a "
            "NodeContract; gebra owns this attribute (ANNOTATION-API-SPEC §1) and will not "
            "overwrite something it did not attach",
            reason=ContractErrorReason.SLOT_VALUE_INVALID,
        )
    return carried


def normalize_declared_value(keyword: str, value: object) -> object:
    """One declared slot value in its carrier form — the shape :class:`NodeContract` holds.

    The normalization seam the two declaration surfaces share. §1 fixes the shapes; §2 says
    the sidecar carries "the same slot vocabulary (the §1 closed annotatable-slot set,
    byte-for-byte)"; and §3 decides "identical values are not a conflict" **structurally** —
    by byte-equality of the two canonicalizations. So the sidecar loader must land on the same
    value the decorator does, down to the type: a TOML ``temperature = 0`` and a decorator
    ``temperature=0.0`` have to become one value, or §3's rule reports a conflict between two
    spellings of the same declaration. Sharing the code is what makes that true by
    construction rather than by two implementations agreeing today.

    Args:
        keyword: The declaration spelling — a key of :data:`SLOT_KEYWORDS`.
        value: The authored value, unchecked.

    Returns:
        The normalized value for the slot ``SLOT_KEYWORDS[keyword]``.

    Raises:
        GebraContractError: if ``value`` is not of its slot's kind. On the decorator surface
            that is §1's import-time error; the sidecar loader catches it and degrades to an
            ``annotation-invalid`` warning (§2), which is why the reason code and ``slot`` are
            carried rather than only a message.
        KeyError: if ``keyword`` is not one of the nine. Callers check membership first —
            both surfaces have their own answer for an unknown key.
    """
    slot = SLOT_KEYWORDS[keyword]
    if keyword in ("reads", "writes"):
        return _state_keys(value, slot=slot, argument=keyword)
    if keyword == "effects":
        return _effect_tags(value)
    if keyword == "pure":
        return _flag(value, slot=slot, argument=keyword)
    if keyword == "idempotent":
        return _idempotent_value(value)
    if keyword == "deterministic":
        return _deterministic_value(value)
    if keyword == "args_schema":
        return _args_schema_value(value)
    if keyword == "variant":
        return _variant_value(value)
    return _compensation_value(value)


def normalize_effect_members(tags: object) -> tuple[str, ...]:
    """The declared effect tags as plain strings, **without** the D-011 vocabulary check.

    Split out because the two surfaces reject an unknown tag at different granularities: §1
    makes it an error for the whole decoration, while §2 rejects "the tag" and keeps the
    entry. Both need the same reading of the container first — a bare string refused, members
    checked rather than coerced — so that half lives here and each surface applies the closed
    :data:`~gebra.annotations.slots.EFFECT_TAGS` set in its own way.

    Raises:
        GebraContractError: if ``tags`` is not a non-string iterable of strings.
    """
    members = _sequence(tags, slot="effect", argument="effects", unit="effect tag")
    return _strings(members, slot="effect", argument="effects", unit="effect tag")


# ── The decorators ───────────────────────────────────────────────────────────────────────


def contract(
    *,
    reads: Iterable[str] | None = None,
    writes: Iterable[str] | None = None,
    effects: Iterable[str] | None = None,
    pure: bool | None = None,
    idempotent: bool | dict[str, str] | None = None,
    deterministic: bool | dict[str, int | float] | None = None,
    args_schema: dict[str, object] | None = None,
    **unknown: object,
) -> Callable[[F], F]:
    """Declare a node contract, and return the decorated callable unchanged (§1).

    Every argument is optional, and every omitted one leaves its slot open for the lower
    precedence tiers of §3 (tool-carried schema, sidecar, inference). An explicit negative is
    a declaration and closes its slot: ``pure=False`` says "not pure", not "unstated".

    Args:
        reads: State keys the node reads — IR ``input``. Any iterable of strings *except* a
            bare string, which is refused: a string is an iterable of characters, and
            silently reading ``"budget"`` as six state keys would land in the digest.
        writes: State keys the node writes — IR ``output``. Same rule.
        effects: Effect tags, each from the closed decision D-011 vocabulary
            :data:`~gebra.annotations.slots.EFFECT_TAGS`.
        pure: Whether the node is pure. Mutually exclusive with a non-empty ``effects``.
        idempotent: ``True``/``False``, or ``{"key": "<state key>"}``. Whether the key is a
            member of the node's resolved ``input`` is checked at *extraction*, warning-grade
            (§1) — a decorator cannot know the resolved input set.
        deterministic: ``True``/``False``, or ``{"seed": <int>}`` with an optional
            ``"temperature"``. The object form requires ``seed``.
        args_schema: A JSON Schema object for the node/tool argument shape. JSON data
            throughout, since it is serialized into the IR and digested.
        **unknown: Accepted only in order to be refused, with a message saying why. No
            keyword here is ever attached: the surface is the nine slots and nothing else.

    Returns:
        A decorator that attaches the declared slots and returns its argument unchanged.

    Raises:
        GebraContractError: on any §1 consistency violation, on a keyword outside the nine
            annotatable slots, or on a value that is not of its slot's kind.
    """
    if unknown:
        _refuse_unknown_keywords(unknown)

    declared: dict[str, object] = {}
    if reads is not None:
        declared["input"] = _state_keys(reads, slot="input", argument="reads")
    if writes is not None:
        declared["output"] = _state_keys(writes, slot="output", argument="writes")
    if effects is not None:
        declared["effect"] = _effect_tags(effects)
    if pure is not None:
        declared["pure"] = _flag(pure, slot="pure", argument="pure")
    if idempotent is not None:
        declared["idempotent"] = _idempotent_value(idempotent)
    if deterministic is not None:
        declared["deterministic"] = _deterministic_value(deterministic)
    if args_schema is not None:
        declared["args_schema"] = _args_schema_value(args_schema)

    def decorate(fn: F) -> F:
        return _attach(fn, declared, surface="@gebra.contract")

    return decorate


def pure(fn: F) -> F:
    """Declare the node pure — ``@gebra.pure``, sugar for ``contract(pure=True)`` (§1).

    The bare form is the only one §1 gives this shorthand; ``contract(pure=False)`` is how a
    node is declared explicitly *not* pure.
    """
    return _attach(fn, {"pure": True}, surface="@gebra.pure")


def effect(*tags: str) -> Callable[[F], F]:
    """Declare effect tags — ``@gebra.effect("irreversible", "billable")`` (§1).

    Raises:
        GebraContractError: if any tag is outside the closed decision D-011 vocabulary, or if
            the decorator was applied bare (``@gebra.effect``), which would otherwise read
            the decorated function itself as a tag.
    """
    # Typed `object` on purpose: the declared parameter is `str`, so a type checker reads
    # `tags[0]` as one and would call the guard below dead — but `@gebra.effect` written bare
    # puts the decorated function here at runtime, which is exactly what this catches.
    sole: object = tags[0] if len(tags) == 1 else None
    if sole is not None and not isinstance(sole, str) and callable(sole):
        raise GebraContractError(
            "@gebra.effect takes its tags and has no bare form: write "
            '@gebra.effect("network") rather than @gebra.effect',
            reason=ContractErrorReason.SLOT_VALUE_INVALID,
            slot="effect",
        )
    declared: dict[str, object] = {"effect": _effect_tags(tags)}

    def decorate(fn: F) -> F:
        return _attach(fn, declared, surface="@gebra.effect")

    return decorate


@overload
def idempotent(fn: F) -> F: ...


@overload
def idempotent(fn: None = None, *, key: str | None = None) -> Callable[[F], F]: ...


def idempotent(fn: Any = None, *, key: str | None = None) -> Any:
    """Declare idempotence — ``@gebra.idempotent`` or ``@gebra.idempotent(key="...")`` (§1).

    The bare form declares ``idempotent: true``; the keyed form declares
    ``{"key": "<state key>"}``. Whether the key is a member of the node's resolved ``input``
    is an *extraction*-time check and warning-grade (§1), because the resolved input set does
    not exist at decoration time.
    """
    declared: dict[str, object] = {
        "idempotent": True if key is None else IdempotentKey(key=_reference(key, argument="key"))
    }

    def decorate(inner: F) -> F:
        return _attach(inner, declared, surface="@gebra.idempotent")

    return decorate if fn is None else decorate(fn)


@overload
def deterministic(fn: F) -> F: ...


@overload
def deterministic(
    fn: None = None, *, seed: int | None = None, temperature: float | None = None
) -> Callable[[F], F]: ...


def deterministic(
    fn: Any = None, *, seed: int | None = None, temperature: float | None = None
) -> Any:
    """Declare determinism — ``@gebra.deterministic`` or ``(seed=42, temperature=0.0)`` (§1).

    Raises:
        GebraContractError: if ``temperature`` is given without ``seed``. §1 names this case
            outright; the frozen ledger §3 shape ``{seed: int, temperature?: number}`` is
            what owns the ruling, since the dict type hint cannot express requiredness.
    """
    declared: dict[str, object] = {"deterministic": _deterministic_form(seed, temperature)}

    def decorate(inner: F) -> F:
        return _attach(inner, declared, surface="@gebra.deterministic")

    return decorate if fn is None else decorate(fn)


def variant(*, key: str, measure: str) -> Callable[[F], F]:
    """Declare a loop variant — ``@gebra.variant(key="remaining", measure="len")`` (§1).

    The P-02 witness form (c) carrier. What measures are admissible, and what discharge
    requires, are owned by R-05's TERMINATION-WITNESS-SPEC; §1 and the ledger fix only the
    two field names, so nothing here interprets either value.
    """
    declared: dict[str, object] = {
        "variant": Variant(
            key=_reference(key, argument="key"),
            measure=_reference(measure, argument="measure"),
        )
    }

    def decorate(fn: F) -> F:
        return _attach(fn, declared, surface="@gebra.variant")

    return decorate


def compensation(*, hook: str) -> Callable[[F], F]:
    """Declare a compensation hook — ``@gebra.compensation(hook="cancel_booking")`` (§1).

    ``hook`` is a node id under the ledger §5 grammar. It is stored as written and not
    checked against that grammar here, for the reason :mod:`gebra.ir.models` records for
    every reference-role string: whether a reference *resolves* is the reporting stage's
    question, and §1's consistency rules — the closed list this module enforces — do not
    include it.
    """
    declared: dict[str, object] = {
        "compensation": Compensation(hook=_reference(hook, argument="hook"))
    }

    def decorate(fn: F) -> F:
        return _attach(fn, declared, surface="@gebra.compensation")

    return decorate


# ── Attachment ───────────────────────────────────────────────────────────────────────────


def _attach(fn: F, declared: Mapping[str, object], *, surface: str) -> F:
    """Merge ``declared`` into ``fn``'s contract and return ``fn`` — the same object (§1).

    The merge is where §1's at-most-once rule lives, because a decorator *stack* applies
    bottom-up to one object: each decorator sees what the ones below it attached.
    """
    existing = read_contract(fn)
    _refuse_duplicate_slots(existing, declared, surface=surface)

    merged: dict[str, object] = (
        {slot: existing.slot_value(slot) for slot in existing.declared_slots()}
        if existing is not None
        else {}
    )
    merged.update(declared)
    # Validated rather than constructed positionally: the merge is a mapping of slot name to
    # already-normalized value, and `model_validate` is the one path that keeps `extra="forbid"`
    # meaningful for it — a key that is not a slot is an error here rather than a silent drop.
    declaration = NodeContract.model_validate(merged)
    _refuse_pure_with_effects(declaration, surface=surface)

    try:
        setattr(fn, CONTRACT_ATTRIBUTE, declaration)
    except (AttributeError, TypeError) as exc:
        raise GebraContractError(
            f"{surface} cannot attach {CONTRACT_ATTRIBUTE} to a {type_identity(fn)} ({exc}); "
            "for a target that cannot carry attributes — a slotted or frozen object, a bound "
            "method of one, a remote tool — the gebra.toml sidecar is the designated fallback "
            "(ANNOTATION-API-SPEC §6)",
            reason=ContractErrorReason.ATTACHMENT_IMPOSSIBLE,
        ) from exc
    return fn


def _refuse_duplicate_slots(
    existing: NodeContract | None, declared: Mapping[str, object], *, surface: str
) -> None:
    """§1's at-most-once rule: a duplicate is an error, identical values included.

    Both values are safe to render: each has already been through this module's
    normalization, so neither is a raw decorator argument.
    """
    if existing is None:
        return
    for slot in ANNOTATION_SLOTS:
        if slot not in declared:
            continue
        held = existing.slot_value(slot)
        if held is None:
            continue
        raise GebraContractError(
            f"{surface} sets {slot!r} to {declared[slot]!r}, but a decorator below it in this "
            f"stack already set it to {held!r}. A slot is settable at most once across a "
            "decorator stack, and a duplicate is an error rather than a merge — identical "
            "values included, because one author's stack has no drift to excuse "
            "(ANNOTATION-API-SPEC §1). Declare the slot once.",
            reason=ContractErrorReason.DUPLICATE_SLOT,
            slot=slot,
        )


def _refuse_pure_with_effects(declaration: NodeContract, *, surface: str) -> None:
    """Decision D-011 exclusivity, over the whole stack rather than one decorator call."""
    if declaration.pure is True and declaration.effect:
        raise GebraContractError(
            f"this stack declares pure=True together with the effects "
            f"{list(declaration.effect)!r}; the two are mutually exclusive (decision D-011, "
            "ANNOTATION-API-SPEC §1). A node that touches the world is not pure — drop "
            f"whichever of the two is not true of it (reached at {surface})",
            reason=ContractErrorReason.PURE_EFFECT_EXCLUSIVE,
            slot="pure",
        )


# ── Value normalization ──────────────────────────────────────────────────────────────────


def _refuse_unknown_keywords(unknown: Mapping[str, object]) -> None:
    """Refuse everything outside the nine annotatable slots, saying which kind of outside.

    The keyword is copied into a plain ``str`` before anything else touches it. CPython
    admits a ``str`` *subclass* as a ``**kwargs`` key, and every operation below would
    otherwise resolve through that subclass's own hooks — ``__eq__`` and ``__hash__`` on the
    membership tests, ``__iter__`` on the close-match search, ``__str__`` and ``__repr__`` on
    the message — which is the module's own no-rendering-before-checking rule broken on the
    one value that never goes through slot normalization (WA-07). The copy also keeps
    :attr:`GebraContractError.slot` a plain string, as its type says.
    """
    name = str.__str__(next(iter(unknown)))
    suggestion = ""
    if name in ("variant", "compensation"):
        arguments = "key=..., measure=..." if name == "variant" else "hook=..."
        detail = "an annotatable slot, but one with its own decorator"
        suggestion = f" Write @gebra.{name}({arguments})."
    elif name in _OUT_OF_REACH:
        detail = _OUT_OF_REACH[name]
    elif name in _IR_SPELLINGS:
        detail = "an annotatable slot under its IR name rather than its keyword"
        suggestion = f" Write {_IR_SPELLINGS[name]}=."
    else:
        detail = "not one of the nine annotatable slots"
        close = difflib.get_close_matches(name, _CONTRACT_KEYWORDS, n=1, cutoff=0.6)
        if close:
            suggestion = f" Did you mean {close[0]!r}?"
    raise GebraContractError(
        f"@gebra.contract() got {name!r}, which is {detail}. It accepts "
        f"{', '.join(_CONTRACT_KEYWORDS)}; the annotatable-slot set is closed at nine "
        f"(ANNOTATION-API-SPEC §1).{suggestion}",
        reason=ContractErrorReason.UNKNOWN_SLOT,
        slot=name,
    )


def _sequence(value: object, *, slot: str, argument: str, unit: str) -> tuple[Any, ...]:
    """A declared repeated slot as a tuple, refusing the bare-string reading of it.

    A bare ``str``/``bytes`` is refused rather than iterated, and nothing else would catch
    it: ``str`` satisfies ``Iterable[str]``, so a type checker passes ``reads="budget"``, and
    reading it as six one-character state keys would reach canonical bytes and the digest.
    """
    if isinstance(value, (str, bytes)):
        raise GebraContractError(
            f"{argument}= is a single {type_identity(value)}, which would be read as one "
            f"{unit} per character; pass a sequence instead, e.g. {argument}=[...]",
            reason=ContractErrorReason.SLOT_VALUE_INVALID,
            slot=slot,
        )
    if not isinstance(value, Iterable):
        raise GebraContractError(
            f"{argument}= is a {type_identity(value)}, which is not iterable; it declares "
            f"{unit}s, so it is a sequence of strings",
            reason=ContractErrorReason.SLOT_VALUE_INVALID,
            slot=slot,
        )
    # The two shapes an author actually writes are read through unbound built-in accessors,
    # so a `list`/`tuple` subclass cannot interpose its own `__iter__` (WA-07). Anything else
    # is iterated normally: §1 types the argument `Iterable[str]`, and materializing an
    # arbitrary iterable is the one thing this surface cannot do without touching it.
    if isinstance(value, list):
        return tuple(list.__iter__(value))
    if isinstance(value, tuple):
        return tuple(tuple.__iter__(value))
    return tuple(value)


def _strings(members: tuple[Any, ...], *, slot: str, argument: str, unit: str) -> tuple[str, ...]:
    """Every member as a plain ``str``; a non-string member is refused, never coerced."""
    checked: list[str] = []
    for index, member in enumerate(members):
        if not isinstance(member, str):
            raise GebraContractError(
                f"{argument}=[{index}] is a {type_identity(member)}; each {unit} is a string",
                reason=ContractErrorReason.SLOT_VALUE_INVALID,
                slot=slot,
            )
        checked.append(str.__str__(member))
    return tuple(checked)


def _state_keys(value: object, *, slot: str, argument: str) -> tuple[str, ...]:
    """A declared state-key set as a tuple of plain strings, in the order authored."""
    members = _sequence(value, slot=slot, argument=argument, unit="state key")
    return _strings(members, slot=slot, argument=argument, unit="state key")


def _effect_tags(tags: object) -> tuple[str, ...]:
    """The declared effect tags, each checked against the closed D-011 vocabulary.

    Order and multiplicity are kept as authored: §1 closes the *vocabulary* and says nothing
    about either, and canonical serialization is where the IR's own ordering rules apply.
    """
    checked = normalize_effect_members(tags)
    for tag in checked:
        if tag not in EFFECT_TAGS:
            raise GebraContractError(
                f"{tag!r} is not an effect tag. The decision D-011 vocabulary is closed: "
                f"{', '.join(sorted(EFFECT_TAGS))} (ANNOTATION-API-SPEC §1)",
                reason=ContractErrorReason.UNKNOWN_EFFECT_TAG,
                slot="effect",
            )
    return checked


def _flag(value: object, *, slot: str, argument: str) -> bool:
    """A boolean slot. ``1``/``0`` are refused rather than read as ``True``/``False``."""
    if not isinstance(value, bool):
        raise GebraContractError(
            f"{argument}= is a {type_identity(value)}; it is a boolean declaration",
            reason=ContractErrorReason.SLOT_VALUE_INVALID,
            slot=slot,
        )
    return bool(value)


def _reference(value: object, *, argument: str) -> str:
    """A declared reference-role string — a state key, a measure name, a node id."""
    if not isinstance(value, str):
        raise GebraContractError(
            f"{argument}= is a {type_identity(value)}; it is a string",
            reason=ContractErrorReason.SLOT_VALUE_INVALID,
        )
    return str.__str__(value)


def _idempotent_value(value: object) -> bool | IdempotentKey:
    """``idempotent=`` as ``True``/``False`` or the ledger §3 ``{key: string}`` object."""
    if isinstance(value, bool):
        return bool(value)
    if not isinstance(value, dict):
        raise GebraContractError(
            f"idempotent= is a {type_identity(value)}; it is True, False, or "
            '{"key": "<state key>"} (ir-field-ledger §3)',
            reason=ContractErrorReason.SLOT_VALUE_INVALID,
            slot="idempotent",
        )
    members = _object_members(value, slot="idempotent", known=("key",))
    if "key" not in members:
        raise GebraContractError(
            'idempotent= is an object without "key"; the ledger §3 shape is {"key": "<state key>"}',
            reason=ContractErrorReason.SLOT_VALUE_INVALID,
            slot="idempotent",
        )
    return IdempotentKey(key=_reference(members["key"], argument="idempotent key"))


def _deterministic_value(value: object) -> bool | DeterministicSpec:
    """``deterministic=`` as ``True``/``False`` or the ledger §3 ``{seed, temperature?}``."""
    if isinstance(value, bool):
        return bool(value)
    if not isinstance(value, dict):
        raise GebraContractError(
            f"deterministic= is a {type_identity(value)}; it is True, False, or "
            '{"seed": <int>, "temperature"?: <number>} (ir-field-ledger §3)',
            reason=ContractErrorReason.SLOT_VALUE_INVALID,
            slot="deterministic",
        )
    members = _object_members(value, slot="deterministic", known=("seed", "temperature"))
    if "seed" not in members:
        raise GebraContractError(
            'deterministic= is an object without "seed". The object form requires it: the '
            'frozen ledger §3 shape is {"seed": <int>, "temperature"?: <number>} '
            "(ANNOTATION-API-SPEC §1, DEC-09)",
            reason=ContractErrorReason.DETERMINISTIC_SEED_REQUIRED,
            slot="deterministic",
        )
    return _deterministic_spec(members["seed"], members.get("temperature"))


def _deterministic_form(seed: object, temperature: object) -> bool | DeterministicSpec:
    """The ``@gebra.deterministic`` shorthand's forms, and the one §1 names as an error."""
    if seed is None:
        if temperature is None:
            return True
        raise GebraContractError(
            "@gebra.deterministic(temperature=...) without seed= declares nothing replayable: "
            "the object form requires seed (ANNOTATION-API-SPEC §1; the frozen ledger §3 shape "
            'is {"seed": <int>, "temperature"?: <number>})',
            reason=ContractErrorReason.DETERMINISTIC_SEED_REQUIRED,
            slot="deterministic",
        )
    return _deterministic_spec(seed, temperature)


def _deterministic_spec(seed: object, temperature: object) -> DeterministicSpec:
    """The ledger §3 object, from a checked seed and an optional checked temperature."""
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise GebraContractError(
            f"seed is a {type_identity(seed)}; the ledger §3 shape types it as an integer",
            reason=ContractErrorReason.SLOT_VALUE_INVALID,
            slot="deterministic",
        )
    if temperature is None:
        return DeterministicSpec(seed=_exact_integer(seed, path="seed"))
    if isinstance(temperature, bool) or not isinstance(temperature, (int, float)):
        raise GebraContractError(
            f"temperature is a {type_identity(temperature)}; the ledger §3 shape types it as a "
            "number",
            reason=ContractErrorReason.SLOT_VALUE_INVALID,
            slot="deterministic",
        )
    # An integer *is* a JSON number and the ledger shape reads `temperature?: number`, while
    # the model types it `float`; widening here is what keeps `temperature=0` from being a
    # strict-mode error at the one place a reader would not expect one.
    number = float(temperature)
    if not math.isfinite(number):
        # Refused where it is written, for the reason `args_schema` is: the slot is
        # serialized into the IR and digested, and JSON has no form for an infinity or a NaN.
        # Left to canonicalization it would surface as a `CanonicalizationError` at
        # `graph_version()` time, with nothing pointing back at the declaration that
        # introduced it — extraction total in name only. (TOML has a literal `nan`, so the
        # §2 sidecar surface can reach this too, where it degrades to a warning instead.)
        raise GebraContractError(
            f"temperature is {number!r}; JSON has no form for it, so it could not be "
            "serialized into the IR or digested",
            reason=ContractErrorReason.SLOT_VALUE_INVALID,
            slot="deterministic",
        )
    return DeterministicSpec(seed=_exact_integer(seed, path="seed"), temperature=number)


def _variant_value(value: object) -> Variant:
    """``variant`` in its object form — ``{key, measure}``, both required (§1, §2).

    The decorator spells the slot as two keywords (``@gebra.variant(key=…, measure=…)``) and
    the sidecar as one inline table (``variant = { key = "...", measure = "..." }``, §2). Both
    build the same :class:`~gebra.ir.models.Variant` out of :func:`_reference`, so neither
    surface can drift into accepting a value the other refuses.
    """
    if not isinstance(value, dict):
        raise GebraContractError(
            f"variant is a {type_identity(value)}; it is an object with a state key and a "
            'measure — { key = "...", measure = "..." } (ANNOTATION-API-SPEC §1/§2)',
            reason=ContractErrorReason.SLOT_VALUE_INVALID,
            slot="variant",
        )
    members = _object_members(value, slot="variant", known=("key", "measure"))
    missing = tuple(name for name in ("key", "measure") if name not in members)
    if missing:
        raise GebraContractError(
            f"variant is an object without {', '.join(repr(name) for name in missing)}; the "
            "P-02 witness form (c) carries both a key and a measure",
            reason=ContractErrorReason.SLOT_VALUE_INVALID,
            slot="variant",
        )
    return Variant(
        key=_reference(members["key"], argument="variant key"),
        measure=_reference(members["measure"], argument="variant measure"),
    )


def _compensation_value(value: object) -> Compensation:
    """``compensation`` in its object form — ``{hook}``, a node id (§1, §2)."""
    if not isinstance(value, dict):
        raise GebraContractError(
            f"compensation is a {type_identity(value)}; it is an object naming the hook — "
            '{ hook = "<node id>" } (ANNOTATION-API-SPEC §1/§2)',
            reason=ContractErrorReason.SLOT_VALUE_INVALID,
            slot="compensation",
        )
    members = _object_members(value, slot="compensation", known=("hook",))
    if "hook" not in members:
        raise GebraContractError(
            'compensation is an object without "hook"; the slot carries the compensating '
            "node's id (ir-field-ledger §3/§5)",
            reason=ContractErrorReason.SLOT_VALUE_INVALID,
            slot="compensation",
        )
    return Compensation(hook=_reference(members["hook"], argument="compensation hook"))


def _exact_integer(value: int, *, path: str) -> int:
    """An integer the canonical form can carry — the I-JSON exact range (IR-SPEC §6.3).

    The twin of the non-finite ``temperature`` refusal, and refused for the same reason at the
    same place: §6.3 fixes both scalar constraints *before* the hash, so a value outside them
    can never be valid IR. Left through, it would reach the §3 resolution, land in a slot, and
    surface as a :class:`~gebra.ir.canonical.CanonicalizationError` the moment anyone asked for
    a ``graph_version`` — with nothing pointing back at the declaration that introduced it.
    Checked where it is written, so the message names the slot instead.

    The bound is imported from the canonicalizer rather than restated: two copies of ±(2**53−1)
    is one copy too many, and this check exists precisely to agree with that one.
    """
    number = int.__index__(value)
    if not I_JSON_MIN_INT <= number <= I_JSON_MAX_INT:
        raise GebraContractError(
            f"{path} is {number}, outside the I-JSON exact integer range ±(2**53−1) "
            "(IR-SPEC §6.3; PD-004). The value is serialized into the IR and digested, so a "
            "number JSON cannot round-trip exactly could not be carried",
            reason=ContractErrorReason.SLOT_VALUE_INVALID,
            slot="deterministic" if path == "seed" else "args_schema",
        )
    return number


def _object_members(value: dict[Any, Any], *, slot: str, known: tuple[str, ...]) -> dict[str, Any]:
    """A declared object's members, with its keys checked against the slot's closed shape.

    Read through ``dict.items`` rather than ``value.items()`` so a ``dict`` subclass cannot
    interpose its own accessor — the pattern :mod:`gebra.ir.canonical` uses on foreign
    content, for the same WA-07 reason.
    """
    members: dict[str, Any] = {}
    for key, member in dict.items(value):
        name = _json_key(key, path=f"{slot}=", slot=slot)
        if name not in known:
            raise GebraContractError(
                f"{slot}= has the member {name!r}, which its shape does not carry; the ledger "
                f"§3 shape has {', '.join(known)}",
                reason=ContractErrorReason.SLOT_VALUE_INVALID,
                slot=slot,
            )
        members[name] = member
    return members


def _args_schema_value(value: object) -> dict[str, Any]:
    """``args_schema=`` as JSON data, checked where it was written.

    Checked here rather than left to canonicalization because the value is serialized into
    the IR and digested: something JSON cannot carry would otherwise surface as a
    ``CanonicalizationError`` at ``graph_version()`` time, with nothing pointing back at the
    decorator that introduced it. §1 is silent on the interior — "a JSON Schema object" — so
    nothing here reads the schema's *meaning*; only that it is data.
    """
    if not isinstance(value, dict):
        raise GebraContractError(
            f"args_schema= is a {type_identity(value)}; it is a JSON Schema object "
            "(ir-field-ledger §3)",
            reason=ContractErrorReason.SLOT_VALUE_INVALID,
            slot="args_schema",
        )
    members: dict[str, Any] = {}
    for key, member in dict.items(value):
        name = _json_key(key, path="args_schema", slot="args_schema")
        members[name] = _json_data(member, path=f"args_schema.{name}", depth=1)
    return members


def _json_key(key: object, *, path: str, slot: str) -> str:
    """A JSON object member name — a string, read without running a subclass's accessor."""
    if not isinstance(key, str):
        raise GebraContractError(
            f"{path} has a {type_identity(key)} key; a JSON object member name is a string",
            reason=ContractErrorReason.SLOT_VALUE_INVALID,
            slot=slot,
        )
    return str.__str__(key)


def _json_data(value: object, *, path: str, depth: int) -> Any:
    """``value`` as JSON data, with sequences as tuples; raise if it is not.

    Containers and scalars are read through unbound built-in accessors so no subclass hook
    runs on a value this module was handed (WA-07). Sequences become tuples for two reasons:
    the authored container is not aliased into the carrier, so editing it afterwards does not
    reach the declared contract; and a list and a tuple of the same items compare equal, which
    keeps two spellings of one schema from reading as two contracts. It is digest-neutral —
    :func:`gebra.ir.canonical.graph_version` emits both as JSON arrays, in the order given.
    Object members are *not* frozen; see :class:`NodeContract` for why and what that leaves
    open.
    """
    if depth > _MAX_SCHEMA_DEPTH:
        raise GebraContractError(
            f"{path} nests deeper than {_MAX_SCHEMA_DEPTH} levels; a JSON Schema that deep is "
            "more likely to be a cycle than a shape",
            reason=ContractErrorReason.SLOT_VALUE_INVALID,
            slot="args_schema",
        )
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        return _exact_integer(value, path=path)
    if isinstance(value, float):
        number = float.__float__(value)
        if not math.isfinite(number):
            raise GebraContractError(
                f"{path} is {number!r}; JSON has no form for it, so it could not be serialized "
                "into the IR",
                reason=ContractErrorReason.SLOT_VALUE_INVALID,
                slot="args_schema",
            )
        return number
    if isinstance(value, str):
        return str.__str__(value)
    if isinstance(value, dict):
        members: dict[str, Any] = {}
        for key, member in dict.items(value):
            name = _json_key(key, path=path, slot="args_schema")
            members[name] = _json_data(member, path=f"{path}.{name}", depth=depth + 1)
        return members
    if isinstance(value, (list, tuple)):
        items = list.__iter__(value) if isinstance(value, list) else tuple.__iter__(value)
        return tuple(
            _json_data(item, path=f"{path}[{index}]", depth=depth + 1)
            for index, item in enumerate(items)
        )
    raise GebraContractError(
        f"{path} holds a {type_identity(value)}, which JSON cannot carry; args_schema is "
        "serialized into the IR and digested, so every value in it has to be data",
        reason=ContractErrorReason.SLOT_VALUE_INVALID,
        slot="args_schema",
    )
