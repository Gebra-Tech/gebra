"""One hand-built workflow and a builder for editing it — the constructed deltas' base.

The version engine compares two IRs, so every test here needs a *pair*: a base workflow and
one deliberately edited from it. :func:`workflow` is the base with every part overridable,
so a delta is written as the one argument that differs and reads as the edit it is::

    changed_components(workflow(), workflow(edges=(*EDGES, NormalEdge(...))))

Everything is built with the IR model constructors — no extractor, no substrate, no user
object anywhere in reach to invoke (WA-07). The base is a three-node plan → work → report
workflow rather than a two-node one so that an edit can leave a node untouched, and it
carries a contract on every node, a two-key Σ and a ``runtime`` block so that each of S, F
and E has something to change.
"""

from __future__ import annotations

from typing import Final

from gebra.ir.models import (
    Annotations,
    Edge,
    Node,
    NormalEdge,
    RecursionLimit,
    Runtime,
    StateField,
    WorkflowIR,
)

#: The base workflow's nodes, contracts included.
NODES: Final[tuple[Node, ...]] = (
    Node(id="plan", annotations=Annotations(pure=True, output=("task",))),
    Node(
        id="work",
        annotations=Annotations(effect=("write",), input=("task",), output=("result",)),
    ),
    Node(id="report", annotations=Annotations(pure=True, input=("result",))),
)

#: The base workflow's edges — a straight line.
EDGES: Final[tuple[Edge, ...]] = (
    NormalEdge(kind="normal", **{"from": "plan"}, to="work"),
    NormalEdge(kind="normal", **{"from": "work"}, to="report"),
)

#: The base workflow's Σ.
STATE: Final[dict[str, str | StateField]] = {"task": "str", "result": "str"}

#: The base workflow's graph-level block — a P-02 witness of form (b) (IR-SPEC §3.5).
RUNTIME: Final = Runtime(
    recursion_limit=RecursionLimit(value=10, justification="the line is three nodes long")
)


def workflow(
    *,
    entry: str | tuple[str, ...] = "plan",
    finish: str | tuple[str, ...] = "report",
    state: dict[str, str | StateField] | None = STATE,
    nodes: tuple[Node, ...] = NODES,
    edges: tuple[Edge, ...] = EDGES,
    runtime: Runtime | None = RUNTIME,
) -> WorkflowIR:
    """The base workflow, with any part replaced.

    ``state=None`` and ``runtime=None`` mean the slot is *absent*, which the canonical form
    keeps distinct from an empty one — so a delta can edit either way round.
    """
    return WorkflowIR(
        ir_version="1.0",
        entry=entry,
        finish=finish,
        state=state,
        nodes=nodes,
        edges=edges,
        runtime=runtime,
    )


def node(name: str, annotations: Annotations | None) -> Node:
    """One node, spelled short enough to sit inline in a delta table."""
    return Node(id=name, annotations=annotations)


def contract_of(name: str) -> Annotations:
    """The base workflow's contract for the node called ``name``."""
    for existing in NODES:
        if existing.id == name:
            assert existing.annotations is not None
            return existing.annotations
    raise KeyError(name)


def with_contract(name: str, annotations: Annotations) -> tuple[Node, ...]:
    """:data:`NODES`, with the node called ``name`` carrying ``annotations`` instead."""
    return tuple(
        Node(id=existing.id, annotations=annotations) if existing.id == name else existing
        for existing in NODES
    )
