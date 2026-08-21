"""Two hand-built stores for the lineage tests — an ordinary history and an awkward one.

:func:`evolved_store` is the multi-version store the card's first acceptance criterion is
about: one workflow carried through five versions, each one deliberate edit of the version
before it, with **every label derived by the diff engine** —
``workflow_diff(previous, current).bump(previous_label)`` — rather than written down here. So
the labels in the fixture are what the engines would have assigned, and a test can hold the
lineage's label-derived bump class against the diff's content-derived one on every pair.

*Scope note.* This is a lineage fixture, not brief D-11's evolution scenario: that is card
SD-08's — N ≥ 5 versions over the travel-booking agent covering the three canonical breaking
cases — and nothing here stands in for it. What this sequence needs to be is a store with
more than one version in which each of S, F and E moves at least once, so that a listing has
something to list.

:func:`awkward_store` is the other half of the engine's claim: the store's floor on a version
label is path-safety, not SD-02's grammar (PD-012), and
:meth:`~gebra.store.store.SnapshotStore.write` forbids a duplicate version but not a history
that counts down or repeats a digest. A listing has to stay total over all of that, so this
store holds a label that is not a V.S.F.E label, a step that goes backwards, and two versions
carrying one content.

Every IR here is built with the IR model constructors, reusing ``tests/versioning/workflows``'
base workflow: no extractor, no substrate, no user object anywhere in reach to invoke (WA-07).
"""

from __future__ import annotations

from collections.abc import Callable
from itertools import pairwise
from pathlib import Path
from typing import Final, NamedTuple

from gebra.diff import workflow_diff
from gebra.ir.models import Annotations, Edge, Node, NormalEdge, StateField, WorkflowIR
from gebra.store import ExtractedFrom, Snapshot, SnapshotStore
from gebra.versioning import Version
from tests.versioning.workflows import NODES, STATE, workflow

# ── The evolving workflow, stage by stage ────────────────────────────────────────────────

#: The node stage 2 introduces — a write-effecting audit step between ``work`` and ``report``.
AUDIT: Final = Node(id="audit", annotations=Annotations(effect=("write",), input=("result",)))

#: Stage 2's nodes: the base three plus :data:`AUDIT`.
NODES_WITH_AUDIT: Final[tuple[Node, ...]] = (*NODES, AUDIT)

#: Stage 3's nodes: ``work``'s effect class escalated from ``write`` to billable/irreversible.
NODES_ESCALATED: Final[tuple[Node, ...]] = tuple(
    Node(
        id=existing.id,
        annotations=Annotations(
            effect=("billable", "irreversible"), input=("task",), output=("result",)
        ),
    )
    if existing.id == "work"
    else existing
    for existing in NODES_WITH_AUDIT
)

#: Stage 2's edges: the straight line, rerouted through ``audit``.
EDGES_WITH_AUDIT: Final[tuple[Edge, ...]] = (
    NormalEdge(kind="normal", **{"from": "plan"}, to="work"),
    NormalEdge(kind="normal", **{"from": "work"}, to="audit"),
    NormalEdge(kind="normal", **{"from": "audit"}, to="report"),
)

#: Stage 4's Σ: the base two keys plus one new optional key.
STATE_EXTENDED: Final[dict[str, str | StateField]] = {
    **STATE,
    "receipt": StateField(type="str", optional=True),
}


class Stage(NamedTuple):
    """One version of the evolving workflow, named by the edit that made it."""

    edit: str
    build: Callable[[], WorkflowIR]


#: The evolution, oldest first. Each stage is the whole IR at that point, so a stage reads on
#: its own; the edit each one carries is named in its first field and asserted in the tests.
STAGES: Final[tuple[Stage, ...]] = (
    Stage("the base workflow", lambda: workflow()),
    Stage(
        "an audit node added and wired in",  # S (nodes, edges) + F (its contract)
        lambda: workflow(nodes=NODES_WITH_AUDIT, edges=EDGES_WITH_AUDIT),
    ),
    Stage(
        "work's effect class escalated",  # F
        lambda: workflow(nodes=NODES_ESCALATED, edges=EDGES_WITH_AUDIT),
    ),
    Stage(
        "an optional receipt key added to the state schema",  # E
        lambda: workflow(nodes=NODES_ESCALATED, edges=EDGES_WITH_AUDIT, state=STATE_EXTENDED),
    ),
    Stage(
        "the finish wiring widened to audit",  # S
        lambda: workflow(
            nodes=NODES_ESCALATED,
            edges=EDGES_WITH_AUDIT,
            state=STATE_EXTENDED,
            finish=("audit", "report"),
        ),
    ),
)

#: When each stage landed. Fixed rather than read from a clock: the whole point of the golden
#: file is that identical input produces identical bytes, and a timestamp is the one member a
#: clock could reach.
LANDED: Final[tuple[str, ...]] = (
    "2026-08-04T09:00:00Z",
    "2026-08-04T10:15:00Z",
    "2026-08-04T11:30:00Z",
    "2026-08-05T08:00:00Z",
    "2026-08-05T14:45:00Z",
)


def provenance(source: str, at: str) -> ExtractedFrom:
    """A fixed provenance record — no clock is read anywhere in these fixtures."""
    return ExtractedFrom(source=source, extractor_version="0.0.1.dev0", extracted_at=at)


def evolved_labels() -> tuple[str, ...]:
    """The labels the engines assign to :data:`STAGES`, starting from ``1.0.0.0``.

    Derived, not written down: each stage's label is the previous label bumped by the class
    :func:`~gebra.diff.workflow_diff` derives for that pair.
    """
    label = Version.initial()
    labels = [str(label)]
    for previous, stage in pairwise(STAGES):
        label = workflow_diff(previous.build(), stage.build()).bump(label)
        labels.append(str(label))
    return tuple(labels)


def evolved_store(root: Path) -> SnapshotStore:
    """A five-version store under ``root``, written in evolution order."""
    store = SnapshotStore.for_project(root)
    for stage, label, at in zip(STAGES, evolved_labels(), LANDED, strict=True):
        store.write(
            Snapshot.of(
                stage.build(),
                version=label,
                extracted_from=provenance(f"tests.lineage.stores:{stage.edit}", at),
            ),
            created_at=at,
        )
    return store


def awkward_store(root: Path) -> SnapshotStore:
    """A store the engine must still list: a bare label, a backwards step, a repeated digest,
    and a V step.

    Nothing here is what this package's own engines would write — the store's label floor and
    its append-only rule simply do not forbid it, and a listing that raised on such a history
    could not list a store the store itself accepts.
    """
    store = SnapshotStore.for_project(root)
    first, second = workflow(), workflow(finish=("report", "work"))
    written = (
        ("1.2.0.0", first),
        ("1.1.0.0", second),  # counts down: S is lower than on the row before it
        ("draft", second),  # not a V.S.F.E label, and the same content as the row before it
        ("2.0.0.0", first),  # a V.S.F.E label whose predecessor is not one
        ("3.0.0.0", second),  # a V step — the one component no content diff can ever report
    )
    for offset, (label, ir) in enumerate(written):
        at = f"2026-08-04T0{offset}:00:00Z"
        store.write(
            Snapshot.of(ir, version=label, extracted_from=provenance("hand-assembled", at)),
            created_at=at,
        )
    return store
