"""The topology-diff data model — what a diff reports, and the order it reports it in.

Brief D-11 In-Scope 4 fixes the engine's job — "given two IR snapshots, report
added/removed/modified nodes, edges (kind normal | conditional | send), … over networkx
representations" — and W5 scopes this first engine to topology: "nodes; edges kind normal |
conditional | send; START/END wiring". The card leaves the diff data model to the
implementer; these shapes are that decision, taken under two rules:

* **Anchored on node identity.** A node is its ``id`` and nothing else (IR-SPEC §5.3:
  "Renaming a node … is a **new identity**; lineage across such changes is the job of the
  V.S.F.E diff layer" — this layer). So a rename reports as one removal and one addition,
  never as a match, and no similarity heuristic exists anywhere in the engine.
* **Anchored on ``graph_version``.** Both compared sides are named by their IR-SPEC §6
  content digest (:class:`DiffAnchor`), recomputed from the IR itself. Equal digests mean
  byte-equal canonical content (§1.2), so an :attr:`~TopologyDiff.identical` diff is empty
  by construction. The reverse is deliberately not claimed: an empty topology diff with
  unequal digests means the change lives outside this engine's slice — in a contract or the
  state schema (:mod:`gebra.diff.contracts` and :mod:`gebra.diff.state` report those), or in
  an authoring regrouping the §4.1 label expansion normalizes away (two routers merged into
  one with every labeled route preserved — :attr:`~gebra.diff.workflow.WorkflowDiff.regrouped`
  is where that one surfaces). :func:`~gebra.diff.workflow.workflow_diff` composes all three.

**What "changed" means here.** A changed entry requires an authored identity that persists
across the pair; content changes with no such anchor are a removal plus an addition. The
anchors used, both spec-grounded and both applied only when exactly one unmatched edge on
each side carries the key (anything wider is ambiguity, reported as removed/added):

* a **conditional routing slot** ``(source, label)`` — ledger §4 reads each ``path_map``
  label as one logical directed edge carrying that label, so the label is the edge's name
  and its target and guard are values that can move under it;
* a **normal/send source** ``(kind, source)`` — the one remaining unmatched out-edge of
  that kind carried by a persisting source reference, whose target or ``condition`` moved.
  A label rename, like a node rename, is a new identity; a kind change is a different edge
  (a ``send`` is a fan-out template, T-W-SPEC §1), so neither ever matches.

**No verdicts.** The diff says what is different, never what the difference means: no
safe/breaking classification exists in Phase 0 (P-12 ``evolution-safety`` is deferred by
SOW §8). The S bump class *is* derived from these categories, by
:attr:`~gebra.diff.workflow.WorkflowDiff.bump_class`; which domain moved is a structural
fact, and what the move means is not.

Everything is a frozen dataclass over sorted tuples: two equal diffs are one value, and one
diff prints the same way every run. Every ordering is the ledger §6 comparator (UTF-16 code
units — RFC 8785 §3.2.3's member sort, the order every other deterministic surface in this
package uses), with absent optionals sorting before present ones.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal, TypeAlias

__all__ = [
    "DiffAnchor",
    "EdgeChanged",
    "EdgeKind",
    "EdgeRef",
    "EdgesDelta",
    "NodesDelta",
    "TopologyDiff",
    "WiringDelta",
    "ledger_sort_key",
]

#: The three edge kinds of IR-SPEC §2.4 (``kind`` defaults to ``normal`` on the surface).
EdgeKind: TypeAlias = Literal["normal", "conditional", "send"]


def ledger_sort_key(value: str) -> bytes:
    """The ledger §6 comparator: UTF-16 code units, as sortable bytes.

    The same key :mod:`gebra.verify.graph` and the canonical emitter use — big-endian UTF-16
    bytes compare exactly as UTF-16 code units (RFC 8785 §3.2.3), which differs from code
    point order where non-BMP characters meet U+E000..U+FFFF. Restated here rather than
    imported because the spelling is frozen by the ledger, not by any one module, and this is
    the diff's lowest layer: it must not depend on the layers that also want it. (The
    package's closure is ``gebra.ir`` + ``gebra.store`` + ``gebra.versioning`` +
    ``gebra.verify`` + networkx — the last of the first four arrived with the deferred-P-12
    marker in :mod:`gebra.diff.workflow`, and the WA-07 tripwires cover it.)
    """
    return value.encode("utf-16-be")


def _optional_key(value: str | None) -> tuple[int, bytes]:
    """Sort key for an optional string: absence first, then ledger order."""
    return (0, b"") if value is None else (1, ledger_sort_key(value))


@dataclass(frozen=True, slots=True)
class DiffAnchor:
    """One side of a diff, named by content — the anchoring the card asks for.

    Attributes:
        graph_version: The IR-SPEC §6 content digest of this side's IR, recomputed by the
            engine from the IR it actually diffed — never taken on faith from an envelope.
        version: The V.S.F.E label, when this side came from a
            :class:`~gebra.store.models.Snapshot`; ``None`` for a bare IR, which has no
            label until a store gives it one.
    """

    graph_version: str
    version: str | None = None


@dataclass(frozen=True, slots=True)
class EdgeRef:
    """One logical directed edge, in authored vocabulary — the unit the edge diff counts.

    A ``normal`` or ``send`` edge maps to one of these; a ``conditional`` edge contributes
    one per ``path_map`` label (ledger §4 label expansion — the diff runs on the expanded
    graph, not on how routers were grouped). Parallel identical edges are distinct copies:
    the canonical form keeps duplicate edge objects (IR-SPEC §6.2 sorts ``edges[]`` and
    removes nothing), so multiplicity is content and the diff treats these as a multiset.

    Attributes:
        kind: The IR-SPEC §2.4 kind of the authored edge.
        source: The authored ``from`` reference, verbatim.
        target: The authored target, verbatim: ``to`` for ``normal``/``send``, the
            ``path_map`` value for ``conditional``. On a conditional edge the spelling
            ``"END"`` is the END sentinel (IR-SPEC §4.1 m3 — the one blessed literal); on a
            ``normal``/``send`` edge it is an ordinary reference (PD-007 Q2 left m4
            unadopted, so ``to: "END"`` names a node or fails to resolve — P-01's question
            either way, never this engine's).
        label: The ``path_map`` label on a conditional expansion; ``None`` otherwise.
        condition: The authored guard/router expression, on any kind (admitted for fixture
            fidelity on ``normal``/``send``, IR-SPEC §2.4) — declared content, never
            evaluated, and inside the hash scope, so a rewrite is a reportable change.
    """

    kind: EdgeKind
    source: str
    target: str
    label: str | None = None
    condition: str | None = None

    def sort_key(self) -> tuple[str, bytes, bytes, tuple[int, bytes], tuple[int, bytes]]:
        """The deterministic report order: kind, then ledger §6 on every string member."""
        return (
            self.kind,
            ledger_sort_key(self.source),
            ledger_sort_key(self.target),
            _optional_key(self.label),
            _optional_key(self.condition),
        )


@dataclass(frozen=True, slots=True)
class EdgeChanged:
    """A persisting edge identity whose content moved — the card's "rewired", plus guards.

    Emitted only under the two identity anchors of the module docstring, and only when the
    pairing is exact (one unmatched edge each side under the key). Whatever did not change
    reads equal across the ``before``/``after`` members.

    Attributes:
        kind: The edge kind — equal on both sides by construction (a kind change never
            pairs).
        source: The persisting source reference.
        label: The persisting ``path_map`` label for a conditional slot; ``None`` for a
            ``normal``/``send`` pairing.
        target_before: The authored target on the before side (``"END"`` spelling as in
            :attr:`EdgeRef.target`).
        target_after: The authored target on the after side.
        condition_before: The authored guard on the before side.
        condition_after: The authored guard on the after side.
    """

    kind: EdgeKind
    source: str
    label: str | None
    target_before: str
    target_after: str
    condition_before: str | None = None
    condition_after: str | None = None

    @property
    def rewired(self) -> bool:
        """Whether the target moved — the "edges rewired" of the card's objective."""
        return self.target_before != self.target_after

    @property
    def condition_changed(self) -> bool:
        """Whether the guard/router expression moved."""
        return self.condition_before != self.condition_after

    def sort_key(
        self,
    ) -> tuple[str, bytes, tuple[int, bytes], bytes, bytes, tuple[int, bytes], tuple[int, bytes]]:
        """The deterministic report order, mirroring :meth:`EdgeRef.sort_key`."""
        return (
            self.kind,
            ledger_sort_key(self.source),
            _optional_key(self.label),
            ledger_sort_key(self.target_before),
            ledger_sort_key(self.target_after),
            _optional_key(self.condition_before),
            _optional_key(self.condition_after),
        )


@dataclass(frozen=True, slots=True)
class NodesDelta:
    """The node identities that appeared, disappeared, or kept their id but not their edges.

    Attributes:
        added: Ids declared only on the after side, in ledger §6 order.
        removed: Ids declared only on the before side.
        rewired: Ids declared on **both** sides that are incident to some entry of the edge
            or wiring deltas — the node kept its identity while its connections moved. A
            rename never lands here: IR-SPEC §5.3 makes it a new identity, so it reads as
            one removal and one addition.
    """

    added: tuple[str, ...] = ()
    removed: tuple[str, ...] = ()
    rewired: tuple[str, ...] = ()

    @classmethod
    def of(
        cls, added: Iterable[str] = (), removed: Iterable[str] = (), rewired: Iterable[str] = ()
    ) -> NodesDelta:
        """Build with every member sorted into the ledger §6 report order."""
        return cls(
            added=tuple(sorted(added, key=ledger_sort_key)),
            removed=tuple(sorted(removed, key=ledger_sort_key)),
            rewired=tuple(sorted(rewired, key=ledger_sort_key)),
        )

    def __bool__(self) -> bool:
        return bool(self.added or self.removed or self.rewired)


@dataclass(frozen=True, slots=True)
class WiringDelta:
    """A change to one sentinel wiring set — START's (``entry``) or END's (``finish``).

    The members are the wired references themselves: ``added=("triage",)`` on the entry
    delta reads "``triage`` is wired from START on the after side and was not before"
    (IR-SPEC §4.1 m1/m2). The sets compared are the *wired sets* — §6.3 collapses a
    duplicated member and §4.2 (m5) gives the set one canonical surface, so a re-spelled
    ``entry`` list is not a change, exactly as it is not a ``graph_version`` change.

    Attributes:
        added: References wired only on the after side, in ledger §6 order.
        removed: References wired only on the before side.
    """

    added: tuple[str, ...] = ()
    removed: tuple[str, ...] = ()

    @classmethod
    def of(cls, added: Iterable[str] = (), removed: Iterable[str] = ()) -> WiringDelta:
        """Build with both members sorted into the ledger §6 report order."""
        return cls(
            added=tuple(sorted(added, key=ledger_sort_key)),
            removed=tuple(sorted(removed, key=ledger_sort_key)),
        )

    def __bool__(self) -> bool:
        return bool(self.added or self.removed)


@dataclass(frozen=True, slots=True)
class EdgesDelta:
    """The edge multiset difference, with exact identity matches folded into changes.

    Attributes:
        added: Expanded edges present only on the after side — multiset semantics, so a
            second parallel copy of an existing edge appears here as one entry.
        removed: Expanded edges present only on the before side.
        changed: Persisting edge identities whose target or guard moved (see
            :class:`EdgeChanged` for exactly when a pairing is made).
    """

    added: tuple[EdgeRef, ...] = ()
    removed: tuple[EdgeRef, ...] = ()
    changed: tuple[EdgeChanged, ...] = ()

    @classmethod
    def of(
        cls,
        added: Iterable[EdgeRef] = (),
        removed: Iterable[EdgeRef] = (),
        changed: Iterable[EdgeChanged] = (),
    ) -> EdgesDelta:
        """Build with every member sorted into the deterministic report order."""
        return cls(
            added=tuple(sorted(added, key=EdgeRef.sort_key)),
            removed=tuple(sorted(removed, key=EdgeRef.sort_key)),
            changed=tuple(sorted(changed, key=EdgeChanged.sort_key)),
        )

    def __bool__(self) -> bool:
        return bool(self.added or self.removed or self.changed)


@dataclass(frozen=True, slots=True)
class TopologyDiff:
    """The topology delta between two workflow definitions, anchored by content digest.

    Read it forward: ``added`` means present on the :attr:`after` side only, ``removed``
    present on the :attr:`before` side only. Diffing the pair the other way round swaps the
    added/removed members and the before/after halves of every changed entry — the engine
    reports differences, in a direction, and nothing else.

    Attributes:
        before: The side compared from.
        after: The side compared to.
        nodes: Declared node identities added/removed/rewired.
        entry: The START wiring delta (IR-SPEC §4.1 m1).
        finish: The END wiring delta (m2). END reachability declared through ``path_map``
            labels valued ``"END"`` (m3) is edge structure and reports under :attr:`edges`.
        edges: The expanded-edge multiset delta.
    """

    before: DiffAnchor
    after: DiffAnchor
    nodes: NodesDelta = NodesDelta()
    entry: WiringDelta = WiringDelta()
    finish: WiringDelta = WiringDelta()
    edges: EdgesDelta = EdgesDelta()

    @property
    def identical(self) -> bool:
        """Whether the two sides carry one ``graph_version`` — byte-equal canonical content.

        ``True`` implies every delta is empty (the engine short-circuits on it). The
        converse does not hold: :attr:`has_changes` can be ``False`` while the digests
        differ, when the change lives in a contract, the state schema, or a router
        regrouping the label expansion normalizes away — see the module docstring.
        """
        return self.before.graph_version == self.after.graph_version

    @property
    def has_changes(self) -> bool:
        """Whether any delta is non-empty — "did the topology move", not "did anything"."""
        return bool(self.nodes or self.entry or self.finish or self.edges)
