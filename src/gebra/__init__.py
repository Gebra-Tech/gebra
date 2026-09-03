"""gebra — design-time verification and versioning for LangGraph agent workflows.

gebra introspects an existing LangGraph ``StateGraph``, ``CompiledStateGraph``,
or LCEL ``Runnable`` — without ever invoking user code — and emits the frozen
Gebra IR (``ir_version`` 1.0); property validators verify that IR and return
structured witnesses or failures; and content-addressed snapshots with
structural diffs (V.S.F.E) record how workflow definitions evolve. gebra
verifies definitions; LangGraph runs them. Normative authority for every
contract implemented in this package: the frozen project specifications
(IR-SPEC, INTROSPECTION-SPEC, ANNOTATION-API-SPEC, PROPERTY-CATALOG-SPEC,
TERMINATION-WITNESS-SPEC, VERSION-COMPAT).

Two surfaces are exported from this module directly, because the specs spell
them at the top level: ``gebra.extract(workflow)`` (INTROSPECTION-SPEC §2) and
the ``@gebra.contract`` decorator family with its ``GebraContractError``
(ANNOTATION-API-SPEC §1). Both are resolved lazily (PEP 562) rather than
imported here, and the laziness is load-bearing rather than tidy:
:mod:`gebra.extraction` reads the substrate's classes to dispatch on them,
while the validator lane and the fixture-load path are proven — in a guarded
interpreter, by ``tests/verify/test_base.py`` and
``tests/testing/test_hermeticity.py`` — to reach no langgraph import at all.
Importing the extractor here would put langgraph in the closure of ``import
gebra``, and with it in the closure of everything that imports anything from
this package. The decorators resolve out of :mod:`gebra.annotations` for the
same reason, one step further: annotating a node function must not drag in
either the substrate or the extractor. Everything else lives in its
subpackage: :mod:`gebra.ir`, :mod:`gebra.verify`, :mod:`gebra.extraction`,
:mod:`gebra.annotations`, :mod:`gebra.store`, :mod:`gebra.versioning`,
:mod:`gebra.diff`, :mod:`gebra.snapshot`, :mod:`gebra.lineage`,
:mod:`gebra.audit`, :mod:`gebra.testing`. Of those, :mod:`gebra.snapshot` is
the one that imports the extractor — it is the wiring from a live workflow to a
stored snapshot — so importing it imports the substrate, while the store,
version, diff, lineage and audit engines stay free of it.
"""

from typing import TYPE_CHECKING, Any, Final

if TYPE_CHECKING:  # resolved for type checkers only; at runtime `__getattr__` does it
    from gebra.annotations import (
        GebraContractError,
        compensation,
        contract,
        deterministic,
        effect,
        idempotent,
        pure,
        variant,
    )
    from gebra.extraction import ExtractionError, extract

__version__ = "0.0.1"

__all__ = [
    "ExtractionError",
    "GebraContractError",
    "compensation",
    "contract",
    "deterministic",
    "effect",
    "extract",
    "idempotent",
    "pure",
    "variant",
]

#: The names :func:`__getattr__` resolves out of :mod:`gebra.extraction`.
_EXTRACTION_EXPORTS: Final[frozenset[str]] = frozenset({"ExtractionError", "extract"})

#: The names it resolves out of :mod:`gebra.annotations`. The split is the point: touching a
#: decorator must not import the extractor, and with it the substrate.
_ANNOTATION_EXPORTS: Final[frozenset[str]] = frozenset(
    {
        "GebraContractError",
        "compensation",
        "contract",
        "deterministic",
        "effect",
        "idempotent",
        "pure",
        "variant",
    }
)

#: Every lazy export, for :func:`__dir__` and for the membership test.
_LAZY_EXPORTS: Final[frozenset[str]] = _EXTRACTION_EXPORTS | _ANNOTATION_EXPORTS


def __getattr__(name: str) -> Any:
    """Resolve an entry point out of its subpackage on first access (PEP 562).

    Written as two literal imports rather than a name→module table so that neither branch
    reaches ``importlib``: this module is in the closure of every hermeticity tripwire in the
    suite, and those scan for a dynamic-import primitive as well as running one.

    Raises:
        AttributeError: for every other name, as attribute access normally would.
    """
    if name in _EXTRACTION_EXPORTS:
        import gebra.extraction

        value = getattr(gebra.extraction, name)
    elif name in _ANNOTATION_EXPORTS:
        import gebra.annotations

        value = getattr(gebra.annotations, name)
    else:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    globals()[name] = value  # bind it, so the import happens once
    return value


def __dir__() -> list[str]:
    """List the lazy exports alongside what is already bound (PEP 562)."""
    return sorted(set(globals()) | _LAZY_EXPORTS)
