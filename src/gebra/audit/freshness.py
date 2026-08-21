"""The snapshot-freshness check — has this definition been snapshotted since it last changed?

Brief D-11 In-Scope 7: "fail CI if the workflow definition changed but no ``gebra snapshot``
was taken; the companion to the pytest gate". This module is the question; the pytest plugin's
``@pytest.mark.gebra_freshness`` is the gate that asks it in CI::

    from gebra.audit import freshness
    from gebra.store import SnapshotStore

    outcome = freshness(extract(build_agent()).ir, store=SnapshotStore.for_project(root))
    outcome.fresh           # False
    outcome.moved           # (Component.S, Component.F)
    print(outcome.summary())

**One comparison, and it is the recorder's.** The working IR's ``graph_version`` against the
store's **current** snapshot — the same comparison :func:`gebra.snapshot.snapshot` makes before
deciding whether to record. That is deliberate rather than incidental: if the check asked a
different question than the recorder answers, a run could report "stale" where a re-snapshot
would record nothing, which would be a CI failure with no remedy. Because the store's index
does not require ``current`` to be its newest row (SD-01's ruling on ``meta.yaml``), "current"
is the precise word and "latest" is not.

**This module takes an IR, never a live workflow**, and that is what keeps
:mod:`gebra.audit` free of the substrate: the extractor is imported by nobody here, so the
package's WA-07 tripwire can assert that langgraph never enters its import closure at all. A
caller holding a live workflow passes ``gebra.extract(workflow).ir``; the pytest plugin passes
what its own hardened resolver produced.

**It never writes.** A freshness check that recorded the snapshot it was missing would be a
gate that always passes, and the artifact it wrote would be one nobody reviewed. Recording is
:func:`gebra.snapshot.snapshot`'s, and the outcome's message names it.

**It grades nothing.** P-12 ``evolution-safety`` is deferred out of Phase 0 (SOW §8, PD-006
R4). A stale outcome says the content moved and which of S/F/E moved with it; no word here
says whether that is safe or breaking, and the diff it carries holds the property registry's
own not-implemented marker where a classification would go.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from gebra.audit.models import Freshness, FreshnessOutcome
from gebra.diff.topology import resolve_subject
from gebra.diff.workflow import workflow_diff

if TYPE_CHECKING:
    from gebra.ir import WorkflowIR
    from gebra.store.store import SnapshotStore

__all__ = ["freshness"]


def freshness(ir: WorkflowIR, *, store: SnapshotStore) -> FreshnessOutcome:
    """Compare a working definition against the snapshot the store currently points at.

    Args:
        ir: The IR of the definition as it stands now — an extraction of the live workflow, or
            a hand-built IR. It is routed through
            :func:`~gebra.diff.topology.resolve_subject` before the store is looked at, which
            both supplies its digest and applies the diff engine's one document precondition
            (node ids are unique — IR-SPEC §2.1, DEC-22). A document that could never be
            snapshotted is refused rather than reported stale against, on the same terms and
            in the same order :func:`gebra.snapshot.snapshot` refuses it.
        store: The store to check against. A store that does not exist reads as an empty one,
            so a project that has never snapshotted gets
            :attr:`~gebra.audit.models.Freshness.UNSNAPSHOTTED` rather than an error.

    Returns:
        The :class:`~gebra.audit.models.FreshnessOutcome`: which of the three states holds,
        both digests, and — when stale — the whole :class:`~gebra.diff.workflow.WorkflowDiff`,
        so a caller can say which of S/F/E moved without reading the store a second time.

    Raises:
        ValueError: if ``ir`` declares one node id twice (IR-SPEC §2.1, DEC-22).
        gebra.store.StoreError: if the store's index or its current snapshot cannot be read.
            A damaged store is a fault to report, never a freshness verdict — reading it as
            "stale" would ask a user to re-snapshot their way out of a corrupt file.
    """
    working, anchor = resolve_subject(ir)
    current = store.current()
    if current is None:
        return FreshnessOutcome(
            state=Freshness.UNSNAPSHOTTED, graph_version=anchor.graph_version, store=store.path
        )
    if current.graph_version == anchor.graph_version:
        return FreshnessOutcome(
            state=Freshness.FRESH,
            graph_version=anchor.graph_version,
            store=store.path,
            version=current.version,
            snapshot_graph_version=current.graph_version,
        )
    return FreshnessOutcome(
        state=Freshness.STALE,
        graph_version=anchor.graph_version,
        store=store.path,
        version=current.version,
        snapshot_graph_version=current.graph_version,
        diff=workflow_diff(current, working),
    )
