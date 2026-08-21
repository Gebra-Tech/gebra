"""The §7.4 (a) stock binding-wrapper enumeration, and the drift probe that keeps it honest.

INTROSPECTION-SPEC §7.4 (a) as amended by DEC-21 (2026-08-04) admits "the enumerated STOCK
langchain-core ``RunnableBinding`` subclasses … by exact type (``_ChatModelBinding`` at the
pinned substrate; enumeration per A1-D21)". An enumeration pinned to one substrate version is a
claim about *that* version, so A1-D21 gives it a re-enumeration instruction —
"``RunnableBinding.__subclasses__()`` filtered to ``langchain_core.*`` modules" — and this module
is that instruction executed against whatever is installed. Three things are checked:

1. **the table agrees with the substrate** — nothing stock is missing from it, and nothing in it
   is a class this substrate does not have;
2. **the admission is exact-type** — a subclass of an admitted class is not admitted, which is
   the DEC-20 stockness discipline the amendment is bounded by;
3. **an admitted class overrides none of the members the gate reads** — the ``bound``/``kwargs``
   read is only hazard-free because the class carrying them is the stock one, so a future stock
   subclass that shadowed either fails here rather than being read.

**Nothing here executes substrate behaviour.** The walk reads ``__subclasses__``, ``__module__``
and ``__mro__``; no ``Runnable`` is built, bound or invoked (WA-07).
"""

from __future__ import annotations

import importlib
import pkgutil

import pytest
from langchain_core.runnables.base import RunnableBinding, RunnableBindingBase

from gebra.extraction.lcel import FragmentKind, kind_of
from gebra.extraction.stock import (
    ADMITTED_BINDING_CLASSES,
    STOCK_BINDING_NAMES,
    STOCK_BINDING_SUBCLASSES,
    _resolve,
    is_binding,
)
from tests import substrate

#: The substrate packages whose every submodule is imported before the walk below.
#: ``__subclasses__()`` reports what the *process* has defined, so a probe that did not import
#: the substrate's runnable and model surfaces would report an empty set and pass vacuously —
#: and a hand-written module list would pass vacuously again the day a stock subclass appears in
#: a module nobody thought to list. These two packages are walked with ``pkgutil`` instead, so
#: the probe's reach is "everywhere a `Runnable` lives" rather than a snapshot of where one did.
_SUBSTRATE_PACKAGES: tuple[str, ...] = (
    "langchain_core.language_models",
    "langchain_core.runnables",
)

#: The names an admitted class may not carry between itself and ``RunnableBinding``. The first
#: two are the composition members the gate reads. The last two are the *other* way a class can
#: make a plain attribute read run its own code — the route ``sentinel_digests.NonStockBinding``
#: itself uses, and the one a shadow probe that only looked for properties would miss.
_FORBIDDEN_MEMBERS: tuple[str, ...] = ("bound", "kwargs", "__getattribute__", "__getattr__")


def _walk(root: type) -> set[type]:
    """Every subclass of ``root``, transitively.

    A1-D21 words the probe as one level of ``__subclasses__()``. One level does not reach
    ``_ChatModelBinding`` on the pinned substrate: pydantic generics interpose a real class —
    ``RunnableBinding[LanguageModelInput, AIMessage]``, created by ``__class_getitem__`` — between
    it and ``RunnableBinding``, so the direct subclasses are parametrizations and the classes the
    addendum is about sit one level below. Walking transitively is the reading that finds what
    the instruction is looking for; the parametrizations are filtered out below.
    """
    seen: set[type] = set()
    frontier = [root]
    while frontier:
        for child in frontier.pop().__subclasses__():
            if child not in seen:
                seen.add(child)
                frontier.append(child)
    return seen


def _stock_subclasses() -> set[type]:
    """The classes A1-D21's probe finds on the installed substrate.

    "Filtered to ``langchain_core.*`` modules", plus the pydantic-generic filter the addendum had
    no reason to name: a parametrization carries an ``origin`` in its generic metadata and is not
    a class anyone authored, so it is not part of an enumeration of authored stock classes.
    """
    for package in _SUBSTRATE_PACKAGES:
        module = importlib.import_module(package)
        for found in pkgutil.walk_packages(module.__path__, prefix=f"{package}."):
            try:
                importlib.import_module(found.name)
            except ImportError:
                # An optional-extra submodule this install does not have. Skipping it can only
                # narrow the probe, and narrowing it cannot admit anything — the enumeration is
                # a name table, and an unimported class simply does not appear on either side.
                continue
    return {
        cls
        for cls in _walk(RunnableBinding)
        if cls.__module__.split(".")[0] == "langchain_core"
        and getattr(cls, "__pydantic_generic_metadata__", {}).get("origin") is None
    }


def test_the_enumeration_matches_the_installed_substrate() -> None:
    """A1-D21's re-enumeration instruction, run against whatever is installed.

    This is the drift surface the card's third acceptance names. A langchain-core release that
    adds a stock ``RunnableBinding`` subclass fails here — which is the point: admitting it is a
    ruling (the enumeration is spec text), not an implementation detail, so the build must stop
    and ask rather than widen or silently under-report.
    """
    assert set(STOCK_BINDING_SUBCLASSES) == _stock_subclasses()


def test_the_table_names_what_this_substrate_has_and_nothing_else() -> None:
    """The table is by name; the resolved tuple is what this substrate answers to those names.

    Below langchain-core 1.4.0 ``_ChatModelBinding`` does not exist and the resolved tuple is
    empty — the gate then behaves exactly as it did before DEC-21 for a class that is not there,
    while ``bind()`` returns the stock ``RunnableBinding`` the gate already admitted. At and
    above 1.4.0 the one name resolves. Both directions are asserted, so neither end of the frozen
    matrix can drift without failing.
    """
    resolved = {(cls.__module__, cls.__qualname__) for cls in STOCK_BINDING_SUBCLASSES}
    assert resolved <= set(STOCK_BINDING_NAMES)

    expected = set(STOCK_BINDING_NAMES) if substrate.CORE_BINDS_TO_A_SUBCLASS else set()
    assert resolved == expected, substrate.CHAT_MODEL_BINDING_REASON


def test_a_name_this_substrate_does_not_carry_resolves_to_nothing() -> None:
    """The version-portability rule, exercised on this substrate rather than on another.

    Two ways a table entry can fail to name an admissible class, and both must resolve to *no
    admission* rather than to an error or to an unchecked read: the attribute is absent (which is
    ``_ChatModelBinding`` on every langchain-core below 1.4.0, two cells of the frozen
    VERSION-COMPAT §3 matrix), and the attribute exists but is not a ``RunnableBinding``
    subclass (which is what a rename or a repurposing would look like). Declining is the
    conservative direction: the gate then behaves exactly as it did before the DEC-21 amendment.
    """
    absent = _resolve((("langchain_core.runnables.base", "_NoSuchBindingClass"),))
    wrong_kind = _resolve(
        (
            ("langchain_core.runnables.base", "RunnableBindingBase"),
            ("langchain_core.runnables.base", "__doc__"),
        )
    )

    assert absent == ()
    assert wrong_kind == ()
    assert _resolve(STOCK_BINDING_NAMES) == STOCK_BINDING_SUBCLASSES


@pytest.mark.parametrize("cls", ADMITTED_BINDING_CLASSES, ids=lambda cls: cls.__qualname__)
def test_an_admitted_class_overrides_none_of_the_members_the_gate_reads(cls: type) -> None:
    """Why admitting these classes is not the WA-07 hazard admitting *any* subclass would be.

    The gate reads exactly two members off a binding — ``bound`` (§5 rule 3's child) and
    ``kwargs`` (§7.4 (c)'s overlay) — and they are safe to read because on the stock class they
    are plain pydantic fields, resolved out of the instance ``__dict__``. A class that shadowed
    either with a property, a descriptor or a method would make that read run code, and so would
    one that overrode attribute access itself, which is a distinct route and the one this repo's
    own decline fixture uses: both are checked. Over every class between the admitted one and
    ``RunnableBinding``, so an intermediate cannot hide one, and re-derived from the installed
    substrate rather than from the source it was read in.

    ``RunnableBinding`` itself is the boundary rather than a subject: its ``bound``/``kwargs``
    are the pinned fields (A1) this whole gate has always read, so the row for the stock class
    checks nothing and is here only because it is one of the admitted classes.
    """
    for klass in cls.__mro__:
        if klass is RunnableBinding:
            break
        for member in _FORBIDDEN_MEMBERS:
            assert member not in vars(klass), (cls, klass, member)


def test_the_admission_is_by_exact_type_and_not_by_inheritance() -> None:
    """DEC-20 stockness, intact past the amendment: a subclass of an admitted class is declined.

    Declared here rather than reached for, because the claim is about the predicate itself and
    the shape it must refuse is by definition one no substrate ships.
    """

    class Downstream(RunnableBinding):  # type: ignore[type-arg]
        """A subclass of the stock class — outside the enumeration, and stays outside it."""

    assert is_binding(RunnableBinding)
    assert not is_binding(Downstream)
    for admitted in STOCK_BINDING_SUBCLASSES:
        assert is_binding(admitted)
        assert not is_binding(type("Below", (admitted,), {}))


def test_a_binding_base_sibling_is_not_admitted() -> None:
    """``RunnableBindingBase`` and its non-``RunnableBinding`` children are a different family.

    ``RunnableRetry`` holds retry settings rather than the generation-config overlay (c) names,
    and ``RunnableWithMessageHistory`` holds a ``bound`` of its own; neither is a
    ``RunnableBinding`` at all, and the enumeration cannot reach them — ``_resolve`` requires a
    ``RunnableBinding`` subclass, so even a table entry naming one would be skipped.
    """
    from langchain_core.runnables.history import RunnableWithMessageHistory
    from langchain_core.runnables.retry import RunnableRetry

    for cls in (RunnableBindingBase, RunnableRetry, RunnableWithMessageHistory):
        assert not is_binding(cls)
        assert not issubclass(cls, RunnableBinding)


def test_every_admitted_class_answers_the_bind_token() -> None:
    """The two gates agree: what §7.4 (a) admits is what §5 stitching names ``%bind[…]``.

    Two predicates in two modules would drift apart silently; this is the assertion that they
    are one gate seen twice. ``kind_of`` takes an *object*, so the check goes through a
    ``__class__``-shaped stand-in rather than constructing a binding — building one would need a
    ``bound`` runnable and prove nothing more.
    """
    for cls in ADMITTED_BINDING_CLASSES:
        instance: object = object.__new__(cls)
        assert kind_of(instance) is FragmentKind.BIND, cls
