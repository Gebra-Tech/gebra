"""The frozen pydantic base and shared vocabulary of the §0.3 result envelope.

Normative authority: PROPERTY-CATALOG-SPEC §0.1–§0.3, whose model stubs are the interface
this package implements. Two rules bind the whole envelope (§0 preamble): **witnesses and
failures are structured values, never strings** — prose appears only in display-only
fields — and no wording in a report may claim more than the property's claim class
licenses.

The A6 conventions the envelope adopts, and what each one costs a caller:

* **PC-1/PC-3 — one shared frozen base**, ``extra="forbid"``, ``strict=True``. Every
  envelope model is immutable, value-compared by its fields, and *hashable*: unlike the IR
  models (IR-SPEC §2.5 note 3) no envelope model carries a ``dict``-typed member, so a
  witness or a failure can be a set member — which is what makes the set-comparison of
  :func:`models_equivalent` possible at all.
* **PC-2 — tuples, not lists**, for every repeated member, and unions discriminated on
  ``kind``.
* **PC-4 — canonical serialization**: definition order, ``exclude_none=True``.
  :func:`to_data` and :func:`to_json` are that profile; an omitted optional member
  round-trips to omitted rather than to ``null``.
* **PC-6 — one model, two duties.** A fixture's ``expected:`` block and a validator's
  output validate into the *same* class, so a fixture cannot drift from the result type
  (§0.3). ``model_construct()`` is refused for the same reason it is refused on
  :class:`~gebra.ir.base.IRModel`: it skips validation, and the invariants this envelope
  exists to carry — witness-XOR-failure above all — would be skipped with it.

**Strict mode and the ingestion path.** Under ``strict=True`` a ``list`` is not a
``tuple`` in Python-mode validation, so parsed YAML/JSON *data* validates only in JSON
mode. That is why §0.3's ``PropertyReport.model_validate({...})`` is spelled
:func:`~gebra.verify.report.validate_report` here — one re-encoding, then
``model_validate_json`` — exactly the path IR-SPEC §2.5 note 4 forces on
:mod:`gebra.ir.serialization`.

**Node identity and the display sentinels.** §0.3 says every ``NodeId`` reuses the frozen
``ir_version`` 1.0 node-id grammar (IR-SPEC §5) byte-for-byte, and that the reserved
segments ``__start__``/``__end__`` never appear in a serialized report — the report-side
spelling is ``"START"``/``"END"``. Those are one rule here, not two: :data:`NodeId` is
:data:`~gebra.ir.identity.NodeIdStr`, and the §5 grammar already refuses the reserved
segments while admitting ``START`` and ``END`` as ordinary names. A validator that has a
graph-side sentinel in hand projects it with :func:`to_display` before it reaches a model.

Nothing in this module imports langgraph, opens a socket, or executes anything (WA-07).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import cache
from typing import Any, Final, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict

from gebra.ir.identity import NodeIdStr

__all__ = [
    "END",
    "START",
    "ClaimClass",
    "ConditionId",
    "DisplayNodeRef",
    "NodeId",
    "PropertyId",
    "PropertySlug",
    "ReportModel",
    "SetCompared",
    "Severity",
    "from_display",
    "json_text",
    "models_equivalent",
    "set_compared_fields",
    "to_data",
    "to_display",
    "to_json",
]


class ReportModel(BaseModel):
    """Normative base for all envelope models (PROPERTY-CATALOG-SPEC §0.3; A6 PC-1/PC-3)."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    @classmethod
    def model_construct(cls, _fields_set: set[str] | None = None, **values: Any) -> Any:
        """Refuse construction that skips validation (A6 PC-6).

        Raises:
            NotImplementedError: always. Build envelope models through validation —
                ``model_validate_json`` / :func:`~gebra.verify.report.validate_report` —
                or the constructor, both of which run the model validators that carry the
                §0.3 invariants.
        """
        raise NotImplementedError(
            f"{cls.__name__}.model_construct() is banned for the §0.3 envelope models "
            "(PROPERTY-CATALOG-SPEC §0.3, memo A6): it skips validation, and with it the "
            f"witness-XOR-failure rule. Use {cls.__name__}.model_validate_json(), "
            "gebra.verify.validate_report(), or the constructor."
        )


# ── The §0.1/§0.2/§0.3 scalar vocabulary ─────────────────────────────────────────────────

#: A node id, in the escaped form of the frozen IR-SPEC §5 grammar, byte-exact (§0.3 "Node
#: identity"). Reports never mint their own naming scheme, so this is the *same* annotation
#: ``nodes[].id`` carries — which also means the reserved segments ``__start__``/``__end__``
#: are refused here, as §0.3 requires of every serialized report field.
NodeId: TypeAlias = NodeIdStr

#: A node id **or** a display sentinel — the annotation for the report fields §0.3 names as
#: sentinel-carrying (``PathLocation.nodes``, ``DataflowCoverage.satisfied_by``, and the
#: other report-level path and writer lists). The runtime constraint is exactly
#: :data:`NodeId`'s, and deliberately so: ``"START"``/``"END"`` satisfy the §5 grammar as
#: ordinary names and the reserved spellings they project from do not, which makes the two
#: aliases coextensive. The distinction this name draws is documentary — it says where a
#: sentinel is expected — and is not enforced by the type.
DisplayNodeRef: TypeAlias = NodeIdStr

#: A member of the §0.4 condition-ID registry — a frozen kebab-case string, and the closed
#: set of them. The registry "is closed: introducing a new condition ID, renaming one, or
#: promoting a RESERVED entry is a spec addendum" (§0.4 registry discipline), so this is a
#: ``Literal`` rather than ``str``: an unregistered string is refused wherever a report is
#: built or loaded, by validation, not by convention. The members are listed in §0.4 table
#: order — RATIFIED, then RESERVED, then PROPOSED.
#:
#: Membership is all this type carries. Whether a member may be **emitted** is a second
#: question with a different answer (a RESERVED or un-ratified PROPOSED entry is a held
#: name, not an emittable one), and it is not a type-level one: the corpus carries RESERVED
#: IDs in ``expected:`` blocks, which PC-6 makes these same classes' duty to load. The
#: emission side lives in :mod:`gebra.verify.conditions`, which also holds the per-ID
#: severity, claim class and provenance this list deliberately does not repeat.
ConditionId: TypeAlias = Literal[
    # RATIFIED — the wedge-five conditions, frozen with the spec (DEC-05 lineage).
    "node-unreachable-from-start",
    "dead-end-node-not-wired-to-end",
    "path-map-target-undefined",
    "cycle-without-termination-witness",
    "counter-guard-without-exit-edge",
    "read-key-never-written-on-path",
    "unprotected-effect-in-cycle",
    "unprotected-effect-in-retry-region",
    "irreversible-with-keyless-idempotent",
    "deterministic-llm-seed-unpinned",
    "deterministic-llm-temperature-unpinned",
    # RESERVED — non-wedge strings already in the corpus, held for their properties.
    "reentrant-node-neither-pure-nor-idempotent",
    "idempotency-key-not-in-declared-reads",
    "concurrent-writers-without-reducer",
    "send-fanout-writer-without-reducer",
    "fanout-retry-duplicate-accumulation",
    "read-key-removed",
    "termination-witness-removed",
    "sole-writer-severed",
    # PROPOSED — filed 2026-07-18 at the §P-01 merge; registered names, ratified one by one.
    "orphan-node",
    "edge-target-undefined",
]

#: The thirteen catalog slugs of Verification-Properties §1.3 (§0.3).
PropertySlug: TypeAlias = Literal[
    "graph-well-formed",
    "termination-witness",
    "signature-soundness",
    "dataflow-completeness",
    "guard-exhaustiveness",
    "effect-safety",
    "retry-coherence",
    "determinism-replay",
    "parallel-safety",
    "subgraph-consistency",
    "join-key-soundness",
    "evolution-safety",
    "interrupt-gate-coverage",
]

#: The thirteen catalog property ids (§0.3); carried by ``subsumed_by`` (DEC-05 D2).
PropertyId: TypeAlias = Literal[
    "P-01", "P-02", "P-03", "P-04", "P-05", "P-06", "P-07",
    "P-08", "P-09", "P-10", "P-11", "P-12", "P-13",
]  # fmt: skip

#: The §0.2 severity ladder, in its serialized lowercase form.
Severity: TypeAlias = Literal["fatal", "error", "warning"]

#: The §0.1 claim classes, in their serialized lowercase form. Exactly three members:
#: ESTIMATED (decision D-026) is arc-side and never appears in a ``gebra verify`` report.
ClaimClass: TypeAlias = Literal["defensible", "defensible-a", "heuristic"]


# ── The START/END display-sentinel convention (§0.3) ──────────────────────────────────────

#: The report-side spelling of the graph-side reserved segment ``__start__`` (§0.3).
START: Final = "START"

#: The report-side spelling of the graph-side reserved segment ``__end__`` (§0.3).
END: Final = "END"

#: The projection §0.3 fixes, in the one direction reports are written in.
_TO_DISPLAY: Final[dict[str, str]] = {"__start__": START, "__end__": END}
_FROM_DISPLAY: Final[dict[str, str]] = {START: "__start__", END: "__end__"}


def to_display(node_id: str) -> str:
    """Project a graph-side vertex id to its report-side spelling (§0.3).

    Exactly ``__start__ ↦ "START"``, ``__end__ ↦ "END"``; every other id is returned
    unchanged. This is the one call between the sentinel-augmented graph a validator builds
    and the report it emits — the reserved spellings are refused by :data:`NodeId`, so
    forgetting it is a validation error rather than a silently non-conforming report.
    """
    return _TO_DISPLAY.get(node_id, node_id)


def from_display(reference: str) -> str:
    """Invert :func:`to_display` — the report-side spelling back to the graph-side id.

    ``"START" ↦ "__start__"``, ``"END" ↦ "__end__"``; every other reference is returned
    unchanged. For reading a report back into graph terms; nothing in the envelope stores
    the reserved form. §0.3 states the projection in the forward direction only, and the
    inverse is ambiguous in one corner: IR-SPEC §5.1 reserves ``__start__``/``__end__``, not
    the display spellings, so a user node genuinely named ``START`` is a legal node id that
    this maps to the sentinel. Where that matters, carry the graph-side id rather than
    recovering it.
    """
    return _FROM_DISPLAY.get(reference, reference)


# ── Set-comparison marking (§0.3: "set-comparison where order is not normative") ──────────


@dataclass(frozen=True)
class SetCompared:
    """Marks a repeated field whose element *order* is not normative (§0.3).

    §0.3 makes comparison model equality "(set-comparison where order is not normative)".
    Which fields those are is a per-property spec statement, never a guess, so the marker
    carries the citation that licenses it and :func:`set_compared_fields` reads the marks
    back off the model.

    Attributes:
        reason: The spec passage that says this field's order is not normative.
    """

    reason: str


@cache
def set_compared_fields(model_type: type[ReportModel]) -> frozenset[str]:
    """The names of ``model_type``'s fields marked :class:`SetCompared`."""
    return frozenset(
        name
        for name, field in model_type.model_fields.items()
        if any(isinstance(mark, SetCompared) for mark in field.metadata)
    )


def models_equivalent(left: object, right: object) -> bool:
    """Compare two envelope values as §0.3 defines comparison.

    Model equality field by field — same class, same values — except that a field marked
    :class:`SetCompared` is compared as a **multiset**: order is not normative there, but a
    duplicated entry still is a difference. Everything else, including the ordering rules
    each property section fixes for its own findings, is compared exactly. ``certificate``
    is the sharpest case of why the default is exact: a permutation of a topological order
    is not a topological order.

    This is what a fixture-vs-output assertion means (PC-6). ``==`` remains the stricter
    comparison and stays available; it differs only on the marked fields.

    **One transitional mode is deliberately absent.** §6.3's shape-normalization callout 2
    has the corpus's cycle lists authored in traversal order and normalizing to the §0.3
    least-id-first canonical rotation, "until then, comparison is cyclic-order equality" —
    a third mode, neither exact nor multiset, that would touch ``CycleLocation.nodes``,
    ``P06NodeLocation.cycle``, ``P06EffectRecord.cycle`` and ``EffectSafetyWitness.cycles``.
    It is not implemented here because the models already carry the canonical rotation and
    the corpus is what is pending: the relaxation belongs to whatever harness has to bridge
    the un-normalized corpus, and encoding a transitional state in the envelope would
    outlive the pass that ends it.
    """
    if isinstance(left, ReportModel):
        if type(left) is not type(right):
            return False
        marked = set_compared_fields(type(left))
        return all(
            _multiset_equivalent(getattr(left, name), getattr(right, name))
            if name in marked
            else models_equivalent(getattr(left, name), getattr(right, name))
            for name in type(left).model_fields
        )
    if isinstance(right, ReportModel):
        return False
    if isinstance(left, tuple) and isinstance(right, tuple):
        return len(left) == len(right) and all(
            models_equivalent(item, other) for item, other in zip(left, right)
        )
    return type(left) is type(right) and bool(left == right)


def _multiset_equivalent(left: object, right: object) -> bool:
    """``left`` and ``right`` hold the same elements, in any order.

    Elements are matched with :func:`models_equivalent` rather than hashed, so a marked
    field nested inside a marked field still compares by the §0.3 rule. A non-tuple value
    (an unset optional) falls back to the exact comparison.
    """
    if not isinstance(left, tuple) or not isinstance(right, tuple):
        return models_equivalent(left, right)
    if len(left) != len(right):
        return False
    unmatched = list(right)
    for item in left:
        for index, candidate in enumerate(unmatched):
            if models_equivalent(item, candidate):
                del unmatched[index]
                break
        else:
            return False
    return True


# ── The serialization profile (A6 PC-4) ──────────────────────────────────────────────────


def to_data(model: ReportModel) -> dict[str, Any]:
    """Serialize an envelope model as JSON data, in the PC-4 profile.

    Members in definition order, ``None``-valued optionals dropped. Dropping them is what
    makes absence round-trip: every optional member of the envelope defaults to ``None``,
    so an omitted fixture key and a validator that did not set it produce the same model
    and the same data.
    """
    return model.model_dump(mode="json", exclude_none=True)


def to_json(model: ReportModel, *, indent: int | None = 2) -> str:
    """Serialize an envelope model as JSON text, in the PC-4 profile of :func:`to_data`.

    Two-space indentation matching ``.editorconfig``; ``indent=None`` gives the compact
    single-line form. Non-ASCII characters are kept as themselves. No trailing newline is
    added: unlike an IR document, a report is not primarily a file on disk — the run-level
    file format is REPORT-FORMAT-SPEC's to own (§0.3 scope boundary).
    """
    return json.dumps(to_data(model), indent=indent, ensure_ascii=False)


def json_text(data: object) -> str:
    """JSON text for parsed document data, so validation can run in JSON mode.

    The envelope models are strict (A6 PC-3), and a YAML sequence is a ``list``: under
    strict Python-mode validation it never lands in a tuple-typed member. Re-encoding and
    validating the text is the ingestion path IR-SPEC §2.5 note 4 fixes for the IR models,
    reused here so a fixture's ``expected:`` block and a validator's output really are
    checked by one code path.

    Raises:
        TypeError: if ``data`` holds a value JSON has no form for.
        ValueError: if ``data`` contains a cycle, or a value past a written-form limit.
    """
    return json.dumps(data, allow_nan=False)
