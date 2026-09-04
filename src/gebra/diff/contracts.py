"""The contract diff — what moved inside ``nodes[].annotations`` and ``runtime`` (F).

Brief D-11 In-Scope 4 asks the diff engine to "report added/removed/modified nodes, edges …,
**contracts**, and state-schema keys"; W6 is where the contract and state-schema half lands.
This module is the contract half: the F component of V.S.F.E, which D-11's Context defines as
"node/contract changes (``@gebra.contract(...)``, ``@gebra.pure``, ``@gebra.effect(...)``,
``@gebra.idempotent(key="...")``, ``@gebra.deterministic(seed=...)``)" and which SD-02's
:data:`~gebra.versioning.classify.FIELD_COMPONENTS` extends, with its reasoning recorded
there, to the six new-in-1.0 §3 slots and the graph-level ``runtime`` block.

**The delta mirrors the F slice exactly.** :func:`~gebra.versioning.classify.component_slice`
cuts F as ``{"nodes": [[id, annotations], …], "runtime": …}``, and :class:`ContractsDelta`
reports over precisely that: the declared-id set (a node arriving or leaving brings its
contract with it), each persisting node's ``annotations``, and the ``runtime`` block. Nothing
else is in F, and nothing in F is left out — which is what lets the bump class in
:mod:`gebra.diff.workflow` be *derived* from this delta rather than computed a second time.

**Comparison is by canonical bytes, and so are the reported values.** Both sides are read off
:func:`~gebra.versioning.classify.canonical_view`, so §6.3's omit-normalization has already
run, and each slot's two sides are compared through the same RFC 8785 emitter the digest goes
through. Python's ``==`` is strictly coarser and would miss real changes: ``True == 1``, and
``annotations.args_schema`` is a JSON Schema carried verbatim (``dict[str, Any]``, IR-SPEC
§3.1), the one place in ir 1.0 where the JSON *type* at a path is unconstrained. Those same
bytes, decoded, are what :class:`SlotChange` carries — so a reported value is exactly what the
digest saw, is hashable, sorts, and renders without a second serializer.

**Two absences, kept apart.** ``annotations`` absent and ``annotations: {}`` are different
canonical documents (``{"id":"a"}`` versus ``{"annotations":{},"id":"a"}``) and therefore
different digests, so :class:`NodeContractChanged` carries presence flags beside its slot
list; the same is true of the ``runtime`` block. A delta that only compared slots would report
nothing while the version moved — and since PD-012 makes the V.S.F.E label a file name, an
under-reported component is two workflow contents under one file.

**Granularity: slot-level, valued.** Coarser ("node ``book_flight``'s contract changed") would
not show which of the three P-02 witness carriers left or that an ``effect`` list grew; finer
than a slot has no meaning in ir 1.0, where a slot's value is the unit ANNOTATION-API-SPEC §3
calls identical-or-not. The slot vocabulary is never hard-coded here: it is read off the two
canonical views, so a slot added to a future ``annotations`` classifies without an edit.

**No verdicts.** Nothing here says an escalated ``effect`` list or a removed ``variant`` is
breaking, or that an added slot is safe: P-12 ``evolution-safety`` is out of Phase-0 scope
(SOW §8) and its deferral is ratified by PD-006 R4. This module reports which contract slots
moved and to what; :mod:`gebra.diff.workflow` carries the marker that says the classification
is deferred.

Nothing here imports langgraph, opens a socket, or executes anything (WA-07): the input is an
IR model, and there is no user object in reach to invoke.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from gebra.diff.models import ledger_sort_key
from gebra.ir.canonical import canonical_foreign_bytes
from gebra.ir.models import WorkflowIR
from gebra.versioning.classify import canonical_view

__all__ = [
    "ContractsDelta",
    "NodeContractChanged",
    "NodeContractRef",
    "RuntimeDelta",
    "SlotChange",
    "contracts_delta",
    "contracts_diff",
]


def _canonical_text(value: object) -> str:
    """A canonical-view value as the text the digest saw — the reported slot value."""
    return canonical_foreign_bytes(value).decode("utf-8")


def _optional_key(value: str | None) -> tuple[int, bytes]:
    """Sort key for an optional string: absence first, then ledger §6 order."""
    return (0, b"") if value is None else (1, ledger_sort_key(value))


@dataclass(frozen=True, slots=True)
class SlotChange:
    """One declared slot whose value moved — of a node contract, or of ``runtime``.

    ``before`` and ``after`` are the slot's value in canonical JSON text, or ``None`` when the
    slot is not in that side's canonical form at all. The two are never equal: a slot with
    equal canonical bytes on both sides is not a change and is not reported. Absence is
    unambiguous — canonicalization omits ``null`` and defaulted members (IR-SPEC §6.3), so
    ``None`` here means exactly "this side declares nothing at this slot".

    The text is the **canonical** form of the value, not the authored one: member names are
    JCS-sorted, set-valued arrays are in ledger §6 order, and ``null`` members inside an
    ``args_schema`` are already dropped (IR-SPEC §3.6's foreign-object rule). That is the
    right thing for a report whose job is to explain a digest move — it is what the digest
    saw — but a renderer must not caption it "your source said this".

    Attributes:
        slot: The member name inside ``annotations`` or ``runtime`` — ``"effect"``,
            ``"deterministic"``, ``"variant"``, ``"recursion_limit"``, and so on.
        before: The canonical JSON text of the value on the before side, or ``None``.
        after: The canonical JSON text on the after side, or ``None``.
    """

    slot: str
    before: str | None
    after: str | None

    @property
    def added(self) -> bool:
        """Whether the slot is declared only on the after side."""
        return self.before is None

    @property
    def removed(self) -> bool:
        """Whether the slot is declared only on the before side."""
        return self.after is None

    def sort_key(self) -> tuple[bytes, tuple[int, bytes], tuple[int, bytes]]:
        """The deterministic report order: ledger §6 on the slot name, then on the values."""
        return (ledger_sort_key(self.slot), _optional_key(self.before), _optional_key(self.after))


def _slot_changes(
    before: Mapping[str, Any] | None, after: Mapping[str, Any] | None
) -> tuple[SlotChange, ...]:
    """Every member of two canonical objects whose bytes differ, in ledger §6 order.

    An absent object contributes no members, which is why the callers carry presence flags
    beside the result: ``None`` and ``{}`` produce the same (empty) slot list and are
    different canonical documents.
    """
    left: Mapping[str, Any] = {} if before is None else before
    right: Mapping[str, Any] = {} if after is None else after
    changes = [
        SlotChange(
            slot=slot,
            before=None if slot not in left else _canonical_text(left[slot]),
            after=None if slot not in right else _canonical_text(right[slot]),
        )
        for slot in left.keys() | right.keys()
        if slot not in left
        or slot not in right
        or canonical_foreign_bytes(left[slot]) != canonical_foreign_bytes(right[slot])
    ]
    return tuple(sorted(changes, key=SlotChange.sort_key))


@dataclass(frozen=True, slots=True)
class NodeContractRef:
    """A node whose contract arrived or left, with the contract it carried on that side.

    Attributes:
        node: The node id.
        contract: That side's ``annotations`` object in canonical JSON text, or ``None`` when
            the node declared none at all. Same text as :attr:`SlotChange.before`/``after``,
            for the whole object rather than one slot.
    """

    node: str
    contract: str | None = None

    def sort_key(self) -> bytes:
        """The deterministic report order: ledger §6 on the node id (ids are unique)."""
        return ledger_sort_key(self.node)


@dataclass(frozen=True, slots=True)
class NodeContractChanged:
    """A node declared on both sides whose contract moved.

    Emitted only for persisting node identities: a node that arrived or left is reported by
    :attr:`ContractsDelta.added`/:attr:`~ContractsDelta.removed` instead, and a *renamed* node
    is both, because IR-SPEC §5.3 makes a rename a new identity rather than a modification.

    Attributes:
        node: The node id, declared on both sides.
        present_before: Whether the node carried an ``annotations`` object at all before.
        present_after: Whether it carries one after. The two differ when a contract arrived
            or was dropped wholesale — including the empty-versus-absent case, which moves the
            digest and which no slot entry would show.
        slots: The members whose value moved, in ledger §6 order.
    """

    node: str
    present_before: bool
    present_after: bool
    slots: tuple[SlotChange, ...] = ()

    def sort_key(self) -> bytes:
        """The deterministic report order: ledger §6 on the node id (ids are unique)."""
        return ledger_sort_key(self.node)


@dataclass(frozen=True, slots=True)
class RuntimeDelta:
    """The graph-level ``runtime`` block's delta (IR-SPEC §3.5/§3.7).

    ``runtime`` is neither topology nor Σ; SD-02 classifies it under F, with the reasoning in
    :mod:`gebra.versioning.classify`. It matters to a reader of this diff for one concrete
    reason: ``recursion_limit`` is P-02 witness form (b), so it is one of the three places a
    termination witness can leave from — the other two being ``edges[].condition`` (form (a),
    reported under topology) and ``nodes[].annotations.variant`` (form (c), a
    :class:`SlotChange` above).

    Attributes:
        present_before: Whether a ``runtime`` block was in the before side's canonical form.
        present_after: Whether one is in the after side's.
        slots: ``recursion_limit`` / ``interrupts`` / ``checkpointer`` entries that moved.
    """

    present_before: bool = False
    present_after: bool = False
    slots: tuple[SlotChange, ...] = ()

    def __bool__(self) -> bool:
        return self.present_before != self.present_after or bool(self.slots)


@dataclass(frozen=True, slots=True)
class ContractsDelta:
    """The F-level delta: node contracts and the graph-level ``runtime`` block.

    Read it forward, as everywhere in this package: ``added`` means present on the after side
    only. Swapping the two sides swaps ``added`` with ``removed`` and the ``before``/``after``
    halves of every :class:`SlotChange`.

    Attributes:
        added: Nodes declared only on the after side, with the contract each arrived
            carrying — brief D-11 In-Scope 4 asks for added and removed *contracts*, not only
            for the ids, and :class:`~gebra.diff.state.StateDelta` reports its own additions
            the same way.
        removed: Nodes declared only on the before side, with the contract each took away.
        changed: Persisting ids whose contract moved.
        runtime: The graph-level block's delta.
    """

    added: tuple[NodeContractRef, ...] = ()
    removed: tuple[NodeContractRef, ...] = ()
    changed: tuple[NodeContractChanged, ...] = ()
    runtime: RuntimeDelta = RuntimeDelta()

    @classmethod
    def of(
        cls,
        added: Iterable[NodeContractRef] = (),
        removed: Iterable[NodeContractRef] = (),
        changed: Iterable[NodeContractChanged] = (),
        runtime: RuntimeDelta | None = None,
    ) -> ContractsDelta:
        """Build with every member sorted into the ledger §6 report order.

        ``runtime=None`` means the empty delta — a construction with nothing to say about the
        graph-level block, which is most of them.
        """
        return cls(
            added=tuple(sorted(added, key=NodeContractRef.sort_key)),
            removed=tuple(sorted(removed, key=NodeContractRef.sort_key)),
            changed=tuple(sorted(changed, key=NodeContractChanged.sort_key)),
            runtime=RuntimeDelta() if runtime is None else runtime,
        )

    def __bool__(self) -> bool:
        return bool(self.added or self.removed or self.changed or self.runtime)


def contracts_delta(
    before_view: Mapping[str, Any], after_view: Mapping[str, Any]
) -> ContractsDelta:
    """The contract delta between two canonical views (IR-SPEC §6.1 steps 2–6, parsed).

    Internal to :mod:`gebra.diff` — the view-taking form, for a caller that already
    canonicalized both sides, as :func:`~gebra.diff.workflow.workflow_diff` has when it gets
    here. It is not part of the package's public surface, and it assumes what
    :func:`canonical_view` produces: hand-built mappings are the caller's risk.
    :func:`contracts_diff` is the same thing from two IRs, and is what a caller wants.

    Raises:
        ValueError: if either view declares one node id twice — see :func:`_contracts_by_id`.
    """
    before_nodes = _contracts_by_id(before_view)
    after_nodes = _contracts_by_id(after_view)
    shared = before_nodes.keys() & after_nodes.keys()
    changed = [
        NodeContractChanged(
            node=node_id,
            present_before=before_nodes[node_id] is not None,
            present_after=after_nodes[node_id] is not None,
            slots=slots,
        )
        for node_id in shared
        for slots in [_slot_changes(before_nodes[node_id], after_nodes[node_id])]
        if slots or (before_nodes[node_id] is None) != (after_nodes[node_id] is None)
    ]
    before_runtime = _object_at(before_view, "runtime")
    after_runtime = _object_at(after_view, "runtime")
    return ContractsDelta.of(
        added=[
            NodeContractRef(node_id, _contract_text(after_nodes[node_id]))
            for node_id in after_nodes.keys() - before_nodes.keys()
        ],
        removed=[
            NodeContractRef(node_id, _contract_text(before_nodes[node_id]))
            for node_id in before_nodes.keys() - after_nodes.keys()
        ],
        changed=changed,
        runtime=RuntimeDelta(
            present_before=before_runtime is not None,
            present_after=after_runtime is not None,
            slots=_slot_changes(before_runtime, after_runtime),
        ),
    )


def contracts_diff(before: WorkflowIR, after: WorkflowIR) -> ContractsDelta:
    """The contract delta between two IRs.

    Raises:
        ValueError: if either IR declares one node id twice — see :func:`_contracts_by_id`.
        CanonicalizationError: if either IR carries a value the canonical form refuses
            (IR-SPEC §6.1 step 5) — such a document has no digest, so it has no version and
            nothing to diff against.
    """
    return contracts_delta(canonical_view(before), canonical_view(after))


def _contract_text(annotations: Mapping[str, Any] | None) -> str | None:
    """One whole ``annotations`` object as canonical JSON text; ``None`` when absent."""
    return None if annotations is None else _canonical_text(annotations)


def _contracts_by_id(view: Mapping[str, Any]) -> dict[str, Mapping[str, Any] | None]:
    """Each declared node's canonical ``annotations`` object, keyed by id; ``None`` if absent.

    **Keying by id is faithful because ids are unique**, which IR-SPEC §2.1's ``nodes`` row
    makes a MUST — "**Node ``id``s MUST be unique within a document** … loaders MUST reject
    it" (ratified DEC-22) — and on which §6.2's ``nodes[]`` sort states its own totality as a
    consequence. A document repeating an id has no canonical form worth the name: the sort key
    ties, so the tied entries' authored order survives into the digest, which is exactly what
    §6.4 excludes ("authored array order (normalized away per §6.2)").

    ``WorkflowIR`` refuses such a document at validation (card IR-07), and
    :func:`~gebra.diff.topology.resolve_subject` refuses it again before any delta runs, so
    no caller of the public entry points reaches here with one; this is the view-level floor
    for the same rule, still load-bearing because ``model_copy(update=...)`` builds a model
    past validation. Reporting instead would be the harmful option: two
    nodes under one id make the F and S counters under-report, and PD-012 makes a V.S.F.E
    label a snapshot's file name, so an under-reported counter is a second workflow content
    under a file that already holds one — which is how SD-05's pre-review found the defect
    PD-032 records and DEC-22 resolves.

    Raises:
        ValueError: if ``view`` declares one node id twice (§2.1, DEC-22).
    """
    nodes: list[Any] = view.get("nodes", [])
    contracts: dict[str, Mapping[str, Any] | None] = {}
    for node in nodes:
        node_id: str = node["id"]
        if node_id in contracts:
            raise ValueError(
                f"node id {node_id!r} is declared twice, which IR-SPEC §2.1 forbids: node "
                "ids MUST be unique within a document (ratified DEC-22). A diff is anchored "
                "on node identity (§5.3), so such a document has no total canonical node "
                "order and cannot be diffed without under-reporting the F and S counters. "
                "Refused rather than misreported. `WorkflowIR` rejects such a document at "
                "validation, so this one was built past validation"
            )
        contracts[node_id] = node.get("annotations")
    return contracts


def _object_at(view: Mapping[str, Any], member: str) -> Mapping[str, Any] | None:
    """A top-level canonical object member, or ``None`` when the member is absent."""
    value: Any = view.get(member)
    if value is None:
        return None
    typed: Mapping[str, Any] = value
    return typed
