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

**Four states, and the fourth is the recorder's own refusal read back.** A working definition
that is the stored content under another ``ir_version`` stamp — an over-stamped twin, admitted
at the loader by DEC-34 — has a different digest and moves no V.S.F.E counter (IR-SPEC §8 keeps
format migrations out of the label). The recorder refuses to record it, so a ``stale`` answer
here would prescribe the one remedy the recorder declines — the CI failure with no remedy the
paragraph above forbids. It answers :attr:`~gebra.audit.models.Freshness.RESTAMPED` instead,
naming both stamps and the remedy the recorder honours — re-stamp the working definition to the
stored stamp, or record it after a real change, leading with whichever the direction admits
(:attr:`~gebra.audit.models.FreshnessOutcome.working_stamp_is_higher`) — and the pytest gate
passes the item on it, surfacing the summary as a warning: the definition did not change, so a
red item would be the failure with no remedy this module forbids (PD-059 D7b as ratified at its
second pass).

**It answers about an ir 1.1 document as about any other.** A ``dynamic`` edge (ratified —
DEC-28, 2026-08-09) declares a router whose target set is not statically known. Until card
SD-13 this check declined such a document at the mouth, on both sides (SD-12; PD-044 D11's
interim posture), because the diff a ``stale`` answer carries had no ruled representation for
an edge with no target and the recorder an ``unsnapshotted`` answer names refused the same
document. PD-059 ruled the representation and lifted both declines together, so the three
content states are reachable for a 1.1 document and each names a next step the recorder will
take (the fourth state cannot arise for a ``dynamic``-bearing document: ``"1.1"`` is its only
admissible stamp, floored from below by IR-SPEC §2.5 note 7 and from above by
:data:`~gebra.ir.IR_VERSIONS`).
The one document precondition left is :func:`~gebra.diff.topology.resolve_subject`'s — unique
node ids and a stamp at or above the floor its edges require — and it is a fault to report,
never a freshness verdict.
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
            both supplies its digest and applies the diff engine's document preconditions
            (node ids are unique — IR-SPEC §2.1, DEC-22; the ``ir_version`` stamp is at or
            above the floor its edges require — §2.5 note 7, DEC-34). A document that could
            never be snapshotted is refused rather than reported stale against, on the same
            terms and in the same order :func:`gebra.snapshot.snapshot` refuses it.
        store: The store to check against. A store that does not exist reads as an empty one,
            so a project that has never snapshotted gets
            :attr:`~gebra.audit.models.Freshness.UNSNAPSHOTTED` rather than an error.

    Returns:
        The :class:`~gebra.audit.models.FreshnessOutcome`: which of the four states holds,
        both digests, and — when stale or restamped — the whole
        :class:`~gebra.diff.workflow.WorkflowDiff`, so a caller can say which of S/F/E moved
        (or that only the stamp did) without reading the store a second time. A ``dynamic``
        edge that arrived, left or changed its guard is in that diff's ``topology.edges`` like
        any other edge, with no target (PD-059).

    Raises:
        ValueError: if ``ir`` declares one node id twice (IR-SPEC §2.1, DEC-22) or is stamped
            below the ``ir_version`` its edges require (§2.5 note 7, DEC-34) — a model built
            past validation, the only way either can still be held.
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
    diff = workflow_diff(current, working)
    return FreshnessOutcome(
        # The digests differ. Either content moved (stale — the case the check exists for) or
        # only the `ir_version` stamp did (restamped — PD-059 D7b as ratified: the one pair the
        # recorder refuses to record, so it is never reported as a change to record).
        state=Freshness.RESTAMPED if diff.stamp_only else Freshness.STALE,
        graph_version=anchor.graph_version,
        store=store.path,
        version=current.version,
        snapshot_graph_version=current.graph_version,
        diff=diff,
    )
