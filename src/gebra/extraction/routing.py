"""Declared return-type hints on routers — the INTROSPECTION-SPEC §6 classification read.

Normative authority: INTROSPECTION-SPEC §6 (the ``send``/``conditional`` classification rule,
the target-set-completeness rule and the codomain-capture rule) under §1 rule 3's closed list
of permitted operations.

**What §6 asks for, and the one operation it names.** "Extraction classifies a routing
declaration as ``kind: send`` **iff** a declared return-type hint licenses it: the branch path
callable (or ``Command``-returning node function) carries a return-type hint naming ``Send`` —
bare ``Send``, ``list[Send]``/``Sequence[Send]``, or a ``Union``/``Command`` form admitting one
— **read via ``typing.get_type_hints()`` (§1), never via body inspection**. Every other
declaration form … classifies as ``kind: conditional``." So this module reads one thing off one
callable and decides one bit. It never reads a body, never calls the router, and never looks at
what the router *returns* — only at what its author *declared*.

**The hazard, and the three things this module does about it** (§1 rule 3): "Caveat on
``get_type_hints()``: it *evaluates* string/forward-reference annotations — arbitrary annotation
expressions run at extraction time. Extraction MUST evaluate hints against module namespaces
only and degrade any evaluation failure to an unknown hint (never abort, never execute repair
logic)."

1. **Module namespaces only.** :func:`typing.get_type_hints` is called with no ``localns``, so
   the only namespace an annotation is resolved against is the callable's own
   ``__globals__`` — the module it was written in. Nothing here constructs a namespace, and no
   name is supplied that the author's module does not already have.
2. **Evaluation only where it is needed.** A return annotation that is already a type object
   with no forward reference inside it is read as it is: it was evaluated when the module was
   imported, and asking ``get_type_hints`` for it again would evaluate *every* annotation on
   the callable — including the parameter annotations, which this module never reads. So the
   hazard surface is the callables whose annotations genuinely are strings (a module written
   under ``from __future__ import annotations``, or an explicitly quoted hint), and for those
   §6's named mechanism is what runs.
3. **Every failure degrades to "no hint".** Not to an error, not to a guess, and not to a
   repair attempt: a hint that cannot be read leaves the router at §6's conservative pole,
   ``kind: conditional``, which "never invents targets or upgrades knowledge". The reason is
   carried out in :attr:`RouterHint.degraded` so the caller can say so rather than being
   silent about it.

**Where the classification is conservative, and in which direction.** Failing to read a hint,
failing to recognise a hint, and reading a hint that names no ``Send`` all land on the same
answer — ``conditional`` — which is the pole §6 sends an unclassifiable router to, because a
conditional edge over declared targets claims strictly less than a send template does. There is
no path here from an unreadable declaration to ``send``.

Nothing in this module invokes a router, a node, an LLM or a network connection (WA-07). The
hazard it *does* carry — annotation evaluation, §1 rule 4's named tripwire obligation — has its
own tripwire in ``tests/extraction/test_routing.py``.
"""

from __future__ import annotations

import typing
from dataclasses import dataclass
from typing import Any, Final, Literal, get_args, get_origin

from langgraph.types import Send

from gebra.extraction.contracts import walk

__all__ = ["RouterHint", "declared_return_hint"]

#: How deep the walk over a type expression goes.
#:
#: A bound rather than a policy, for the same reason the wrapper walk has one: a type
#: expression nested past this is not a routing declaration anyone wrote, and "no hint" is a
#: better answer than a ``RecursionError`` out of ``gebra.extract()``.
_MAX_DEPTH: Final = 16

#: The annotation member a declared return hint lives in.
_RETURN: Final = "return"


@dataclass(frozen=True)
class RouterHint:
    """What §6's declared-return-hint read found on one routing callable.

    Attributes:
        declared: Whether a return annotation was declared at all. ``False`` covers both "no
            annotation" and "the callable could not be located", which §6 treats identically:
            both are the no-hint case.
        names_send: Whether the declared hint names ``Send`` — §6's classification bit. Only
            ever ``True`` on a hint that was actually read; a degraded read is ``False``.
        codomain: The ``Literal`` string labels the hint declares, in declaration order, or
            ``()`` when it declares none. §6's codomain-capture rule is what reads this.
        degraded: Why the read fell back to "no hint", or ``None`` when it did not. Present iff
            an annotation was declared and could not be turned into a hint — which is a fact
            about *this* declaration and is worth reporting, unlike the absence of one.
    """

    declared: bool = False
    names_send: bool = False
    codomain: tuple[str, ...] = ()
    degraded: str | None = None

    @property
    def kind(self) -> Literal["send", "conditional"]:
        """The §6 classification: ``send`` iff a declared hint names ``Send``.

        The whole rule in one expression, and deliberately not a lookup table: §6 states one
        licensing condition and sends everything else — ``Literal`` labels, a plain ``str``, a
        ``Command`` form naming no ``Send``, an unreadable hint, no hint at all — to the same
        conservative pole.
        """
        return "send" if self.names_send else "conditional"


def declared_return_hint(path: object) -> RouterHint:
    """Read the declared return-type hint off a routing callable (§6).

    Args:
        path: The routing declaration's callable as the substrate holds it —
            ``BranchSpec.path`` for a router, ``StateNodeSpec.runnable`` for a
            ``Command``-returning node function. Both arrive wrapped (a
            ``RunnableCallable`` at the pinned substrate), and the declared hint lives on the
            callable inside, so the ANNOTATION §6 wrapper walk is what locates it — the same
            walk contract attachment uses, rather than a second reading of the same chain.

    Returns:
        The hint. Total: every failure is a :class:`RouterHint` carrying ``degraded``, never an
        exception, because a routing declaration that cannot be read is §6's no-hint case and
        extraction is total over supported objects (§2).
    """
    try:
        callable_object = walk(path).innermost
        annotations = _declared_annotations(callable_object)
        if annotations is None or _RETURN not in annotations:
            return RouterHint()
        return _read_hint(callable_object, annotations[_RETURN])
    # §1 rule 3's degradation covers the WHOLE read (WA-07 pre-review F2 + R2,
    # 2026-08-10): a raising `__annotations__` property escapes `getattr`'s
    # AttributeError-only swallow; a type expression whose `__args__` raises inside
    # `_needs_evaluation`'s pre-fence walk escaped the `_read_hint` handler; and `walk()`'s
    # wrapper-member reads (a raising `func` property) sat one call above the fence. All
    # must degrade, never abort — this function's contract is total (§2).
    except Exception as error:  # noqa: BLE001 — the degradation is the whole handler
        return RouterHint(
            declared=True,
            degraded=(
                f"the routing declaration could not be read at all "
                f"({type(error).__name__}: {error})"
            ),
        )


def _declared_annotations(callable_object: object) -> dict[str, Any] | None:
    """The callable's own ``__annotations__`` mapping, or ``None`` when it has none to read.

    An attribute read (§1 rule 3's first permitted operation) and a type test, so that the
    common case — a router with no return annotation, which is most of them — is answered
    without evaluating anything at all. The mapping's *values* are not touched here.

    ``dict`` exactly, not any mapping: reading members off a foreign mapping would call that
    object's own code, and a function's ``__annotations__`` is a ``dict``.
    """
    annotations = getattr(callable_object, "__annotations__", None)
    if type(annotations) is dict:
        return annotations
    return None


def _read_hint(callable_object: object, raw: object) -> RouterHint:
    """One declared return annotation as a :class:`RouterHint`.

    The raw annotation is used as it is when it is already a resolved type expression, and
    ``typing.get_type_hints()`` is called only when something inside it still needs evaluating
    (a string, or a ``ForwardRef``). See the module docstring for why the evaluation is scoped
    that way rather than run unconditionally.
    """
    hint: object = raw
    if _needs_evaluation(raw):
        resolved = _evaluated_return_hint(callable_object)
        if isinstance(resolved, str):
            return RouterHint(declared=True, degraded=resolved)
        hint = resolved
    try:
        return RouterHint(
            declared=True,
            names_send=_names_send(hint),
            codomain=_literal_labels(hint),
        )
    # A hint is an arbitrary object, and reading its shape means reading `__origin__` and
    # `__args__` off it — members a user type can implement however it likes. §1 rule 3's
    # degradation rule covers the whole read, not only the evaluation step, so an object that
    # answers those reads by raising leaves the router at the conservative pole.
    except Exception as error:  # noqa: BLE001
        return RouterHint(
            declared=True,
            degraded=(
                f"the declared return hint could not be read as a type expression "
                f"({type(error).__name__}: {error})"
            ),
        )


def _needs_evaluation(raw: object) -> bool:
    """Whether ``raw`` still holds a string or forward reference that must be evaluated.

    ``from __future__ import annotations`` makes the whole annotation one string, which the
    top-level test catches; an explicitly quoted inner hint (``list["Leg"]``) arrives as a
    :class:`typing.ForwardRef` nested inside the expression, which the walk catches.
    """
    for member in _expression(raw):
        if isinstance(member, (str, typing.ForwardRef)):
            return True
    return False


def _evaluated_return_hint(callable_object: object) -> object | str:
    """The evaluated ``return`` hint, or a ``str`` saying why it could not be evaluated.

    §6's named mechanism, run under §1 rule 3's two constraints: **module namespaces only** —
    no ``localns`` is passed, so evaluation sees the callable's own ``__globals__`` and nothing
    this build made up — and **degrade any failure**, which is what the broad ``except`` is.

    The failure modes are real and none of them is exotic: an unresolvable forward reference
    raises ``NameError``; a hint quoting something defined in a function body raises the same;
    a malformed annotation string raises ``SyntaxError``; an annotation expression that runs
    code raises whatever that code raises. All four are the same outcome here.

    Returning the reason as a ``str`` rather than raising is deliberate: this module is total,
    and a caller has to be able to *say* that a hint went unread.
    """
    try:
        hints = typing.get_type_hints(callable_object)
    # Deliberately blind, per §1 rule 3: "degrade any evaluation failure to an unknown hint
    # (never abort, never execute repair logic)". Narrowing this would let some annotation
    # expressions abort an extraction, which the rule forbids in terms. Nothing is retried,
    # nothing is patched, and no second namespace is tried — degrading is the whole handler.
    except Exception as error:  # noqa: BLE001
        return (
            f"the declared return hint could not be evaluated against the callable's module "
            f"namespace ({type(error).__name__}: {error})"
        )
    resolved: dict[str, object] = hints
    if _RETURN not in resolved:
        # `get_type_hints` drops nothing from `__annotations__`, so reaching this means the
        # member disappeared between the two reads — a mutating `__annotations__`. Degrading
        # is the same answer as any other unreadable hint.
        return "the declared return hint was no longer present when it was evaluated"
    return resolved[_RETURN]


def _names_send(hint: object) -> bool:
    """Whether ``hint`` names ``Send`` anywhere in its type expression (§6).

    §6 enumerates the licensing forms as "bare ``Send``, ``list[Send]``/``Sequence[Send]``, or
    a ``Union``/``Command`` form admitting one" — three shapes and an open "admitting one", so
    the test is membership in the expression rather than a match against a fixed list of
    generic aliases. ``Optional[list[Send]]``, ``Command[Literal["a"]] | list[Send]`` and a
    user's own alias for any of them all license ``send``, and each of them is a declaration
    that the router may return a ``Send``.

    A subclass of ``Send`` counts: it *is* a ``Send``, and ``issubclass`` dispatches on
    ``Send``'s own metaclass (plain ``type``), so no user hook runs on this test.
    """
    for member in _expression(hint):
        if member is Send:
            return True
        if isinstance(member, type) and issubclass(member, Send):
            return True
    return False


def _literal_labels(hint: object) -> tuple[str, ...]:
    """The ``Literal`` string labels ``hint`` declares, in declaration order, deduplicated.

    §6's codomain-capture rule reads this: a ``Literal[...]`` return hint declares the router's
    codomain, and when a ``path_map`` is declared beside it the substrate gives the ``path_map``
    precedence and the hint "never reaches ``BranchSpec.ends``". Only ``str`` members are
    collected — an IR ``path_map`` label is a string, and a non-string ``Literal`` member has no
    more of a spelling here than a non-string ``path_map`` key does.
    """
    labels: list[str] = []
    for member in _expression(hint, literals=True):
        if isinstance(member, str) and member not in labels:
            labels.append(member)
    return tuple(labels)


def _expression(hint: object, *, literals: bool = False) -> tuple[object, ...]:
    """Every member of a type expression, outermost first, bounded and cycle-guarded.

    A breadth-first flattening of ``typing.get_args`` — the read-only introspection accessor
    for a parametrized generic — so that the two questions §6 asks ("does it name ``Send``",
    "which ``Literal`` labels does it declare") are each one pass over the same flattening
    rather than two special-cased recursions.

    ``Literal`` is the one construct whose arguments are *values* rather than types
    (``Literal["a"]``'s argument is the string ``"a"``), so descending into it would put bare
    strings into a walk whose other members are types. It is therefore descended into only when
    the caller is asking for exactly those values, which is what ``literals`` selects.
    """
    members: list[object] = []
    frontier: list[object] = [hint]
    seen: set[int] = set()
    depth = 0
    while frontier and depth < _MAX_DEPTH:
        depth += 1
        next_frontier: list[object] = []
        for member in frontier:
            if id(member) in seen:
                continue
            seen.add(id(member))
            members.append(member)
            if get_origin(member) is Literal and not literals:
                continue
            next_frontier.extend(get_args(member))
        frontier = next_frontier
    return tuple(members)
