"""Structural diff between workflow definitions — topology, contracts, state schema.

Given two snapshots or IRs, :func:`~gebra.diff.workflow.workflow_diff` reports everything that
moved and which V.S.F.E counters that bumps (brief D-11 In-Scope 4–5, W5–W6)::

    from gebra.diff import workflow_diff

    diff = workflow_diff(store.read("1.0.0.0"), store.read("1.1.0.0"))

    diff.topology.nodes.added        # ("audit",)
    diff.contracts.changed           # (NodeContractChanged(node="book_flight", …),)
    diff.state.added                 # (StateKeyRef(key="hotel", …),)
    diff.bump_class                  # frozenset({Component.S, Component.F, Component.E})
    str(diff.bump(Version.parse("1.4.2.0")))    # '1.5.3.1'

The three deltas partition the ``graph_version`` hash scope, which is what lets the bump class
be *derived* from them: S from :attr:`~gebra.diff.workflow.WorkflowDiff.topology` (SD-04's
diff over networkx, plus the ``regrouped`` flag for authoring changes the routing graph
normalizes away), F from :mod:`~gebra.diff.contracts`, E from :mod:`~gebra.diff.state`.
:func:`~gebra.diff.topology.topology_diff` remains available on its own for a caller that
wants only the graph.

**Anchoring, stated precisely.** Node identity is the id and nothing else: a renamed node is a
new node (IR-SPEC §5.3), reported as one removal plus one addition — no similarity matching
exists here. Both sides are named by their recomputed §6 content digest, and each side taken
from a snapshot carries its V.S.F.E label on the anchor; a snapshot whose stored digest
disagrees with its own IR is refused rather than diffed under a wrong anchor.

**What a diff never says** is whether a change is safe. P-12 ``evolution-safety`` is out of
Phase-0 scope (SOW §8), a deferral ratified by PD-006 R4, and every diff carries
:data:`~gebra.diff.workflow.EVOLUTION_SAFETY_DEFERRED` — the property registry's own
structured not-implemented marker — in the slot where a classification would go. The engine
reports structure and which counters move; nothing here grades a change.

**One document class is refused rather than diffed.** Node ids MUST be unique within a
document (IR-SPEC §2.1, ratified DEC-22). One that repeats an id has no identity to anchor on
— and every delta here is keyed by id — so :func:`~gebra.diff.topology.resolve_subject` raises
rather than under-report it.

Nothing in this package imports langgraph, opens a socket, or executes anything (WA-07). Its
inputs are IR models; networkx is in reach by design — it is the representation brief D-11
mandates — and the tripwires in ``tests/diff/`` pin that the substrate and the network stay
out.
"""

from gebra.diff.contracts import (
    ContractsDelta,
    NodeContractChanged,
    NodeContractRef,
    RuntimeDelta,
    SlotChange,
    contracts_diff,
)
from gebra.diff.graph import (
    END_LITERAL,
    END_VERTEX,
    START_VERTEX,
    EdgeOrigin,
    VertexRole,
    topology_graph,
    wired_set,
)
from gebra.diff.models import (
    DiffAnchor,
    EdgeChanged,
    EdgeKind,
    EdgeRef,
    EdgesDelta,
    NodesDelta,
    TopologyDiff,
    WiringDelta,
    ledger_sort_key,
)
from gebra.diff.state import (
    KeyDeclaration,
    StateDelta,
    StateKeyChanged,
    StateKeyRef,
    state_diff,
)
from gebra.diff.topology import DiffSubject, resolve_subject, topology_diff
from gebra.diff.workflow import EVOLUTION_SAFETY_DEFERRED, WorkflowDiff, workflow_diff

__all__ = [
    "END_LITERAL",
    "END_VERTEX",
    "EVOLUTION_SAFETY_DEFERRED",
    "START_VERTEX",
    "ContractsDelta",
    "DiffAnchor",
    "DiffSubject",
    "EdgeChanged",
    "EdgeKind",
    "EdgeOrigin",
    "EdgeRef",
    "EdgesDelta",
    "KeyDeclaration",
    "NodeContractChanged",
    "NodeContractRef",
    "NodesDelta",
    "RuntimeDelta",
    "SlotChange",
    "StateDelta",
    "StateKeyChanged",
    "StateKeyRef",
    "TopologyDiff",
    "VertexRole",
    "WiringDelta",
    "WorkflowDiff",
    "contracts_diff",
    "ledger_sort_key",
    "resolve_subject",
    "state_diff",
    "topology_diff",
    "topology_graph",
    "wired_set",
    "workflow_diff",
]
