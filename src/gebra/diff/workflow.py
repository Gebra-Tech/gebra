"""The whole-workflow diff — topology, contracts and Σ together, with the V.S.F.E bump class.

This is the card's engine: :func:`workflow_diff` puts SD-04's topology diff beside the
contract and state-schema deltas of :mod:`gebra.diff.contracts` and :mod:`gebra.diff.state`,
and **derives the V.S.F.E bump class from those categories** — S when the topology moved, F
when a contract did, E when Σ did (brief D-11 In-Scope 4–5, W6; SOW §1's vocabulary table).

**The bump class is read off the deltas, not computed a second time.** Each delta is built to
mirror its component's canonical slice exactly (see those modules), so
:attr:`WorkflowDiff.bump_class` is a union over "is this delta non-empty", and the invariant
that matters — ``bump_class == changed_components(before, after)``, the version engine's own
answer — is a *test*, not a definition. It has to be: if the two ever disagreed in the
direction of under-reporting, one workflow content would land under a label another content
already has, and PD-012 makes that label a file name.

**One category exists only to keep that true**, and is worth stating plainly.
:attr:`~WorkflowDiff.regrouped` reports that the authored ``edges[]`` array moved while every
expanded route stayed put. IR-SPEC §2.4 has consumers label-expand conditional edges "before
any graph algorithm runs", so two routers merged into one — or one split into two, or an
empty ``path_map`` router added — leave the routing graph identical and the canonical bytes
different. The graph diff is right to report nothing; the S counter is right to move, because
S counts the ``edges`` field. Without this flag the derivation would silently drop that case.

**And one document class is refused rather than reported.** The deltas mirror their slices on
every document whose node ids are unique — which IR-SPEC §2.1 makes a MUST (ratified DEC-22),
with §6.2's sort totality following from it. A document repeating an id has no total canonical
node order, so the tied entries' authored order reaches the digest (which §6.4 excludes), and
every delta here is keyed by id, so reporting one would collapse it and under-report both S
and F. :func:`~gebra.diff.topology.resolve_subject` refuses it before anything else runs.
That check is a floor rather than the enforcement point: DEC-22's constraint is on the model
itself since card IR-07, so no *loaded* document can violate it — the floor covers a model
built past validation with ``model_copy(update=...)``, which this engine can still be handed.

**What this diff never says is whether a change is safe.** P-12 ``evolution-safety`` is out of
Phase-0 scope (SOW §8), a deferral ratified in PD-006 R4 with the owner's signature, and
PD-006's checklist §S2 requires the diff to carry "the deferred-P-12 marker and no
safe/breaking wording". :attr:`WorkflowDiff.evolution_safety` is that marker, and it is
deliberately **not a new shape**: it is the same structured
:class:`~gebra.verify.registry.NotImplementedMarker` the property registry answers with for
every out-of-scope property (``status="deferred-to-phase-1"``), so a per-version audit export
carrying P-01…P-13 markers and a diff carry one vocabulary, not two. The field sits exactly
where a classification would go — occupied by the statement that there is none.

So a reader gets three structural facts and one honest absence: *what* moved, *which counters*
that bumps, and that nothing here graded the change.

Nothing in this module imports langgraph, opens a socket, or executes anything (WA-07): the
inputs are IR models and snapshots, and there is no user object in reach to invoke.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

from gebra.diff.contracts import ContractsDelta, contracts_delta
from gebra.diff.models import DiffAnchor, TopologyDiff
from gebra.diff.state import StateDelta, state_delta
from gebra.diff.topology import DiffSubject, resolve_subject, topology_deltas
from gebra.ir.canonical import canonical_foreign_bytes
from gebra.verify.registry import NotImplementedMarker, not_implemented
from gebra.versioning.classify import canonical_view
from gebra.versioning.models import Component, Version

__all__ = [
    "EVOLUTION_SAFETY_DEFERRED",
    "WorkflowDiff",
    "workflow_diff",
]

#: The deferred-P-12 marker every :class:`WorkflowDiff` carries — the property registry's own
#: answer for ``evolution-safety``, reused rather than restated. PD-006 R4 (owner-signed,
#: 2026-07-24) reads brief D-11's P-12 clauses down to SOW §8's exclusion for Phase 0, and its
#: checklist §S2 requires this marker in diff output. Immutable (a frozen ``ReportModel``), so
#: one instance is shared by every diff.
EVOLUTION_SAFETY_DEFERRED: Final[NotImplementedMarker] = not_implemented("evolution-safety")


@dataclass(frozen=True, slots=True)
class WorkflowDiff:
    """Everything that moved between two workflow definitions, and which counters that bumps.

    The three *component slices* partition the ``graph_version`` hash scope: between them, S,
    F and E cover the whole canonical document except ``ir_version``, which IR-SPEC §8 puts in
    the other migration regime entirely ("two migration regimes, never conflated" — a format
    migration is not a workflow migration). The three *deltas* mirror those slices on every
    document this engine accepts (see the module docstring on the one it refuses), and that is
    what makes :attr:`has_changes` and ``not`` :attr:`identical` the same answer here.

    Attributes:
        topology: Nodes, edges and START/END wiring — SD-04's diff, over networkx.
        contracts: ``nodes[].annotations`` and the graph-level ``runtime`` block.
        state: The state schema Σ.
        regrouped: Whether the authored ``edges[]`` array moved while every expanded route
            stayed put — routers merged or split, or an empty ``path_map`` router added or
            dropped. Nothing routes differently; the digest and the S counter still move (see
            the module docstring). Independent of :attr:`topology`: both can be non-empty.
        evolution_safety: The deferred-P-12 marker (:data:`EVOLUTION_SAFETY_DEFERRED`). Not a
            verdict, and not a pass — the structured statement that no safe/breaking
            classification was reached, because P-12 is Phase-1 scope.
    """

    topology: TopologyDiff
    contracts: ContractsDelta = field(default_factory=ContractsDelta)
    state: StateDelta = field(default_factory=StateDelta)
    regrouped: bool = False
    evolution_safety: NotImplementedMarker = field(default=EVOLUTION_SAFETY_DEFERRED)

    @property
    def before(self) -> DiffAnchor:
        """The side compared from, named by its recomputed ``graph_version`` (and its
        V.S.F.E label, when it came from a snapshot)."""
        return self.topology.before

    @property
    def after(self) -> DiffAnchor:
        """The side compared to."""
        return self.topology.after

    @property
    def bump_class(self) -> frozenset[Component]:
        """Which of S, F and E this diff bumps — derived from the categories above.

        ``S`` iff the topology moved or the routers were regrouped; ``F`` iff a node contract
        or the ``runtime`` block moved; ``E`` iff Σ moved. Never ``V``: the frozen package
        defines S, F and E and says nothing about what V counts, so the version engine carries
        it through untouched (:class:`~gebra.versioning.models.Component`).

        Equal to :func:`~gebra.versioning.classify.changed_components` over the same pair —
        held by property test rather than by construction, because the whole point of
        deriving it here is that the two can be checked against each other.
        """
        selected = set()
        if self.topology.has_changes or self.regrouped:
            selected.add(Component.S)
        if self.contracts:
            selected.add(Component.F)
        if self.state:
            selected.add(Component.E)
        return frozenset(selected)

    def bump(self, current: Version) -> Version:
        """``current`` with every component of :attr:`bump_class` incremented by one.

        The one-call surface a snapshot writer wants: ``current`` is the label of the
        snapshot being compared against — the store's *current* version, for
        :mod:`gebra.snapshot` — and the result is the label the working workflow gets. Nothing is
        reset — S, F and E are independent counters over their own domains (D-11 In-Scope 2's
        "and/or"), so ``1.4.2.0`` with a topology and a schema change becomes ``1.5.2.1``.

        An identical pair returns ``current`` unchanged. Whether an unchanged workflow is
        re-snapshot at all is :mod:`gebra.snapshot`'s idempotency policy, not this engine's.

        Raises:
            VersionFormatError: with reason ``TOO_LONG`` if the bumped label could no longer
                be a snapshot's file name.
        """
        return current.bump(*self.bump_class)

    @property
    def identical(self) -> bool:
        """Whether the two sides carry one ``graph_version`` — byte-equal canonical content.

        ``True`` implies every delta is empty and :attr:`bump_class` is empty (the engine
        short-circuits on it).
        """
        return self.topology.identical

    @property
    def has_changes(self) -> bool:
        """Whether anything at all moved — equivalently, whether any counter bumps.

        Unlike :attr:`TopologyDiff.has_changes <gebra.diff.models.TopologyDiff.has_changes>`,
        which is silent about contracts and Σ, this one is total over the hash scope: it is
        ``False`` exactly when :attr:`identical` is ``True``, on every document this engine
        accepts. That agreement is checked over generated pairs, not assumed — it is the
        diff-level face of the version engine's covering property, and the document class
        where it would fail is refused at the boundary rather than reported (module
        docstring).
        """
        return bool(self.bump_class)


def workflow_diff(before: DiffSubject, after: DiffSubject) -> WorkflowDiff:
    """The full delta from ``before`` to ``after``, with its V.S.F.E bump class.

    Args:
        before: The side compared from — a ``WorkflowIR``, or a ``Snapshot`` whose ``version``
            label then appears on the anchor.
        after: The side compared to.

    Returns:
        The delta. ``added`` members throughout are present only on the ``after`` side;
        swapping the arguments swaps those members and the before/after halves of every
        changed entry, and leaves :attr:`~WorkflowDiff.bump_class` the same — a bump class
        names domains that moved, not a direction they moved in.

    Raises:
        ValueError: if a ``Snapshot``'s stored ``graph_version`` is not the digest of its own
            IR (IR-SPEC §6.1 step 9) — refused rather than diffed under a wrong anchor.
        CanonicalizationError: if an IR carries a value the canonical form refuses (IR-SPEC
            §6.1 step 5); such a document has no digest to anchor on.
    """
    before_ir, before_anchor = resolve_subject(before)
    after_ir, after_anchor = resolve_subject(after)
    topology = topology_deltas(
        before_ir, after_ir, before_anchor=before_anchor, after_anchor=after_anchor
    )
    if topology.identical:
        return WorkflowDiff(topology=topology)

    before_view = canonical_view(before_ir)
    after_view = canonical_view(after_ir)
    return WorkflowDiff(
        topology=topology,
        contracts=contracts_delta(before_view, after_view),
        state=state_delta(before_view, after_view),
        regrouped=not topology.edges
        and canonical_foreign_bytes(before_view["edges"])
        != canonical_foreign_bytes(after_view["edges"]),
    )
