"""Synthetic registrations — a registry row moved to ``catalog`` for one test, never shipped.

DEC-35 §4 has the catalog charter's mechanism exercised "by a synthetic registration and no
real property": no §P-nn section beyond the wedge five is ratified, so no shipped row carries the
``catalog`` scope yet. This module is that synthetic registration, for tests only. It swaps one
row of the registry's table for a copy in scope ``catalog`` — the edit a landing build makes to
the table — optionally registers a throwaway validator for it through the public
:func:`gebra.verify.register_validator`, and puts both back on exit. The shipped table and the
shipped registrations are never edited, and nothing here executes a workflow node, calls a
model or opens a connection (WA-07): a throwaway validator is a local function returning a
fixed report.

The swap reaches every reader because the registry has one table: :data:`PROPERTY_REGISTRY`
and the lookup :func:`gebra.verify.property_entry` both read ``registry._TABLE``, and every
deferral reader asks the row's scope when it runs (DEC-35 §3.5 (b)) rather than a tuple frozen
at import. :func:`move_to_catalog` is the bare swap, for a subprocess child that discards it with
the process; :func:`synthetic_catalog_row` is the scoped form a test in this process uses.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest

from gebra.ir import WorkflowIR
from gebra.verify import (
    NodeLocation,
    PropertyEntry,
    PropertyReport,
    PropertySlug,
    Validator,
    WellFormednessWitness,
    is_emittable,
    property_entry,
    property_for_condition,
    register_validator,
    unregister_validator,
)
from gebra.verify import registry as _registry
from gebra.verify.report import Failure

__all__ = [
    "failing_validator",
    "move_to_catalog",
    "passing_validator",
    "synthetic_catalog_row",
]


def move_to_catalog(property_slug: PropertySlug, **changes: Any) -> PropertyEntry:
    """Put a copy of ``property_slug``'s row in scope ``catalog`` into the table; return it.

    Unscoped — the caller (a subprocess child) never restores it. ``changes`` override further
    fields of the copy, e.g. ``arity="two-snapshot"`` for a row that keeps P-12's shape.
    """
    moved = dataclasses.replace(property_entry(property_slug), scope="catalog", **changes)
    _registry._TABLE[property_slug] = moved
    return moved


@contextmanager
def synthetic_catalog_row(
    property_slug: PropertySlug, validator: Validator | None = None, **changes: Any
) -> Iterator[PropertyEntry]:
    """``property_slug``'s row moved to ``catalog`` for the block, with ``validator`` registered.

    On exit the throwaway validator is unregistered and the shipped row restored, whatever the
    block raised — a synthetic registration must never leak into another test's dispatch.
    """
    shipped = _registry.validator_for(property_slug)
    with pytest.MonkeyPatch.context() as patch:
        moved = dataclasses.replace(property_entry(property_slug), scope="catalog", **changes)
        patch.setitem(_registry._TABLE, property_slug, moved)
        try:
            if validator is not None:
                register_validator(property_slug, validator)
            yield moved
        finally:
            unregister_validator(property_slug)
            if shipped is not None:  # pragma: no cover - a deferred row ships no validator
                _registry._IMPLEMENTATIONS[property_slug] = shipped


def passing_validator(property_slug: PropertySlug) -> Validator:
    """A throwaway validator that answers ``property_slug`` with a fixed pass.

    The witness is a well-formedness one because §0.3's union has no member for a property
    whose section is not ratified; ``PropertyReport`` pairs any witness with any slug, and the
    report is never compared against a fixture.
    """

    def _passes(ir: WorkflowIR, /) -> PropertyReport:
        node = ir.nodes[0].id
        return PropertyReport.passing(
            property_slug,
            WellFormednessWitness(
                kind="well-formedness",
                reachable_from_start=(node,),
                terminal_nodes=(node,),
                orphan_nodes=(),
                unresolved_targets=(),
            ),
        )

    return _passes


def failing_validator(
    property_slug: PropertySlug,
    condition: Any,
    severity: Any,
    claim_class: Any = "defensible-a",
) -> Validator:
    """A **test double**: a throwaway validator that answers with one finding on its first node.

    ``condition`` must be one of ``property_slug``'s RESERVED §0.4 strings — a name held for
    the property in the corpus and not emittable in this build (§0.4: a validator never
    emits one before its section's addendum ratifies it). The double returns it all the same,
    which no shipped validator could: the record is built directly, never through the §0.4
    emission gate, so that a synthetic registration has a finding to gate on before any
    section is ratified. Both facts are checked here rather than assumed. Its output reaches
    ``verify()`` and a plugin run's stdout in the tests that register it, and no golden, SARIF
    log or fixture.
    """
    if is_emittable(condition) or property_for_condition(condition) != property_slug:
        raise AssertionError(
            f"{condition!r} must be a RESERVED string held for {property_slug!r}, not an "
            "emittable or foreign one — the double stands in for a property not yet ratified"
        )

    def _fails(ir: WorkflowIR, /) -> PropertyReport:
        return PropertyReport.failing(
            property_slug,
            Failure(
                property_condition=condition,
                location=NodeLocation(kind="node", node=ir.nodes[0].id),
                severity=severity,
                claim_class=claim_class,
            ),
        )

    return _fails
