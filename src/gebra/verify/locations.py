"""Structural anchors — the §0.3 ``Location`` union and the wedge's concrete subtypes.

A location says *where* in the workflow definition a finding sits. §0.3 freezes two things
about it: the ``kind`` discriminator vocabulary (six anchors) and each anchor's own fields.
Everything a specific condition needs beyond the anchor — P-01's ``undefined_target``,
P-02's ``representative_cycle``, P-04's offending ``path``, P-06's declared ``effect`` set,
P-08's ``annotation``/``form`` evidence — arrives on a **concrete subtype** declared by that
property's §P-nn.3 I/O contract, still ``extra="forbid"`` at the concrete class.

That is why this module exports two unions rather than one:

* :data:`Location` — the §0.3 stub verbatim: the six anchors, discriminated on ``kind``.
  It is the frozen anchor vocabulary, and the thing a new property section extends.
* :data:`AnyLocation` — what the envelope actually carries. A tagged union admits one
  member per discriminator value, and the wedge's concrete subtypes reuse their anchor's
  ``kind`` by construction (``P06NodeLocation`` and ``DeterminismNodeLocation`` are both
  ``kind: "node"``), so the carriage union resolves left to right instead.

Left-to-right resolution is deterministic here rather than lucky: every concrete subtype
adds at least one **required** field, and every model is ``extra="forbid"``. So an anchor
payload cannot satisfy a concrete subtype (a required field is missing) and a concrete
payload cannot satisfy its anchor (a field is unknown there). ``tests/verify`` pins the
resulting payload → class table.

Corpus note: the mixed fixtures carry co-findings from the eight non-wedge properties
(P-07's ``declared_inputs``, P-09's ``writers``/``branch_point``, P-12's ``removed_key``).
Those have no concrete subtype here on purpose — a property section fixes its own location
shape when it is drafted, and the §0.4 registry holds their condition IDs as RESERVED, not
emittable (§0.4 registry discipline).
"""

from __future__ import annotations

from typing import Annotated, Literal, TypeAlias

from pydantic import Field

from gebra.verify.base import DisplayNodeRef, NodeId, ReportModel, SetCompared

__all__ = [
    "AnyLocation",
    "CycleLocation",
    "DataflowLocation",
    "DeterminismNodeLocation",
    "EdgeLocation",
    "GuardEdgeLabels",
    "Location",
    "NodeLocation",
    "P01EdgeLocation",
    "P02CycleLocation",
    "P02SccLocation",
    "P06NodeLocation",
    "PathLocation",
    "SccLocation",
    "StateKeyLocation",
]


# ── The six §0.3 anchors ─────────────────────────────────────────────────────────────────


class NodeLocation(ReportModel):
    """One node of the graph."""

    kind: Literal["node"]
    node: NodeId


class EdgeLocation(ReportModel):
    """One directed edge, or one label-expansion of a conditional edge (ledger §4)."""

    kind: Literal["edge"]
    source: NodeId
    #: Omitted when the anchor is a dangling label — there is no resolved target to name.
    target: NodeId | None = None
    #: The ``path_map`` label, when the edge is one label-expansion.
    label: str | None = None


class CycleLocation(ReportModel):
    """A simple cycle, in the §0.3 canonical rotation: lexicographically-least id first."""

    kind: Literal["cycle"]
    nodes: tuple[NodeId, ...]


class SccLocation(ReportModel):
    """A strongly connected component; ``nodes`` sorted ascending."""

    kind: Literal["scc"]
    nodes: tuple[NodeId, ...]


class StateKeyLocation(ReportModel):
    """A key of Σ, optionally attributed to the one node that reads or writes it."""

    kind: Literal["state-key"]
    key: str
    node: NodeId | None = None


class PathLocation(ReportModel):
    """A path through the graph; ``nodes`` may carry the display sentinels START/END."""

    kind: Literal["path"]
    nodes: tuple[DisplayNodeRef, ...]


#: The §0.3 anchor union: the frozen ``kind`` vocabulary, discriminated (A6 PC-2).
Location: TypeAlias = Annotated[
    NodeLocation | EdgeLocation | CycleLocation | SccLocation | StateKeyLocation | PathLocation,
    Field(discriminator="kind"),
]


# ── The wedge's concrete subtypes (§1.3, §2.3, §4.3, §6.3, §8.3) ─────────────────────────


class P01EdgeLocation(EdgeLocation):
    """P-01's edge anchor for an unresolved reference (§1.3).

    ``undefined_target`` names the string that resolves to no node in V; the anchor's
    ``target`` stays omitted, per the §0.3 dangling-label rule.
    """

    undefined_target: str


class P02SccLocation(SccLocation):
    """P-02's residual-SCC anchor for ``cycle-without-termination-witness`` (§2.3).

    ``exhaustive: false`` is the whole claim about the cycle list: **one** representative
    witness-free simple cycle per residual SCC, canonically rotated. The SCC may contain
    more, and a re-run after a fix surfaces the next (TERMINATION-WITNESS-SPEC §6.1).

    ``blanket_only`` is the structured field the strict profile distinguishes on
    (TERMINATION-WITNESS-SPEC §6.1, ratified at walkthrough #2 — DEC-11): under
    ``--gebra-strict`` an SCC covered only by a justified ``recursion_limit`` reuses this
    same condition ID with ``blanket_only: true``, so no new condition ID is introduced.

    **It is optional, and emitting ``blanket_only: false`` is a defect.** T-W-SPEC §6.1
    builds its payload with the field always present and has the no-blanket case emit
    ``false``; §2.3's fail shape omits it, and every residual-SCC fixture in the corpus omits
    it too. The catalog owns the wire shape where the two speak, so absence is the default
    here — and since ``exclude_none`` drops ``None`` but not ``False``, a validator that
    followed §6.1 literally would serialize ``blanket_only: false`` onto every P-02 failure
    and lose model equality against six fixtures.
    """

    representative_cycle: tuple[NodeId, ...]
    exhaustive: Literal[False]
    blanket_only: bool | None = None


class GuardEdgeLabels(ReportModel):
    """A conditional guard named by its source node and the labels under test (§2.3)."""

    source: NodeId
    labels: tuple[str, ...]


class P02CycleLocation(CycleLocation):
    """P-02's cycle anchor for ``counter-guard-without-exit-edge`` (§2.3, DEC-05 D4).

    A bounded-counter guard none of whose labels leaves its own SCC is a distinct wiring
    defect, so the anchor carries the counter key and the guard's labels as evidence.
    """

    counter_key: str
    guard_edge: GuardEdgeLabels


class DataflowLocation(StateKeyLocation):
    """P-04's state-key anchor (§4.3).

    The anchor declares ``node`` optional; a dataflow finding always names the reading
    node, so it is required here. ``path`` is the shortest offending START→node path and
    may carry the display sentinel START.

    Boundary worth knowing before implementing P-04's degradation convention: §0.3 has P-04
    "carry the phantom vertex with an empty contract" on P-01-dirty topology, and a phantom
    whose name breaks the IR-SPEC §5 grammar has no spelling in ``path``. §0.3 already puts
    a single-property run on P-01-dirty topology outside the defined result surface, so this
    is a hard model boundary rather than a case to widen the annotation for.
    """

    node: NodeId
    path: tuple[DisplayNodeRef, ...]


class P06NodeLocation(NodeLocation):
    """P-06's node anchor (§6.3).

    ``effect`` carries the node's **full declared effect set** as evidence context, never
    as an obligation source: the trigger set is exactly ``{billable, irreversible}``, and
    ``network``/``external``/``audit``/user tags create no P-06 obligation.
    """

    effect: Annotated[
        tuple[str, ...],
        SetCompared("PROPERTY-CATALOG-SPEC §6.3: the full declared effect set, set-compared"),
    ]
    #: §0.3 canonical rotation; absent for the acyclic FATAL and for retry_policy-only regions.
    cycle: tuple[NodeId, ...] | None = None
    #: Evidence for the FATAL ``irreversible-with-keyless-idempotent`` condition.
    idempotent: Literal["keyless"] | None = None
    #: The node is a send-edge target (``mixed/09``).
    fanout: Literal["send"] | None = None
    #: A declared compensation hook naming no node (DEC-05 D7 side condition).
    dangling_compensation_hook: NodeId | None = None


class DeterminismNodeLocation(NodeLocation):
    """P-08's node anchor (§8.3).

    Every field beyond the anchor is the IR-decidable *evidence* for the finding: the
    annotation form that was declared, the effects co-declared with it, and the seed and
    temperature as pinned — never a prose summary.
    """

    annotation: Literal["deterministic"]
    #: Seed-unpinned evidence (``negative-01``).
    form: Literal["bare-boolean"] | None = None
    #: Seed-unpinned evidence (``negative-01``).
    effects: tuple[str, ...] | None = None
    #: Temperature-unpinned evidence (``negative-02``).
    seed: int | None = None
    #: Omitted when unset.
    temperature: float | None = None


#: What the envelope carries wherever §0.3 writes ``Location``: the wedge's concrete
#: subtypes, then the anchor union. Resolution is left to right — see the module docstring
#: for why that is deterministic, and ``tests/verify/test_locations.py`` for the pinned
#: payload → class table.
AnyLocation: TypeAlias = Annotated[
    P01EdgeLocation
    | P02SccLocation
    | P02CycleLocation
    | DataflowLocation
    | P06NodeLocation
    | DeterminismNodeLocation
    | Location,
    Field(union_mode="left_to_right"),
]
