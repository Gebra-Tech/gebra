"""The snapshot engine — a live workflow, extracted and recorded in a `.gebra/` store.

This is brief D-11's pipeline joined up end to end: ``gebra.extract()`` produces an IR, the
IR-SPEC §4.1 envelope wraps it with a V.S.F.E label and its provenance, and
:class:`~gebra.store.store.SnapshotStore` writes it::

    from gebra.snapshot import record, snapshot
    from gebra.store import SnapshotStore

    store = SnapshotStore.for_project(project_root)

    outcome = snapshot(build_travel_booking_agent(), store=store)
    outcome.version         # '1.0.0.0' — the store was empty
    outcome.recorded        # True
    outcome.path            # <project_root>/.gebra/snapshots/1.0.0.0.yaml

    again = snapshot(build_travel_booking_agent(), store=store)
    again.recorded          # False — the definition did not move
    again.version           # '1.0.0.0', the version it already holds

    outcome = snapshot(build_travel_booking_agent_v2(), store=store)
    outcome.version         # '1.1.1.0' — S and F moved
    outcome.bump_class      # frozenset({Component.S, Component.F})

:func:`~gebra.snapshot.engine.snapshot` takes a live workflow;
:func:`~gebra.snapshot.engine.record` takes an
:class:`~gebra.extraction.envelope.ExtractionEnvelope` that already exists, which is what a
caller who has already verified the same IR wants; and
:func:`~gebra.snapshot.engine.record_document` (CLI-05) takes a serialized IR document that
was never extracted at all — ``gebra snapshot --ir``'s path, under the same label policy
with document-honest provenance. All three answer with a
:class:`~gebra.snapshot.models.SnapshotOutcome`.

**What the engine decides, and what it only carries.** It decides two things and they are the
two the card reserved: the API above, and the re-snapshot policy —
:mod:`gebra.snapshot.engine`'s docstring states that policy in full. Everything else it
composes without re-deciding: which bytes a snapshot file holds is PD-012 and
:mod:`gebra.store`, what a label means is :mod:`gebra.versioning`, and which counters a change
moves is :mod:`gebra.diff`. It computes no digest of its own beyond calling
:func:`~gebra.ir.canonical.graph_version`, and it runs no validator.

**Nothing here classifies a change as safe or breaking.** P-12 ``evolution-safety`` is
deferred out of Phase 0 (SOW §8; PD-006 R4), and the diff a
:class:`~gebra.snapshot.models.SnapshotOutcome` carries says which domain moved and carries
the property registry's own not-implemented marker where a classification would go.

**WA-07.** Importing this package imports the extractor, and with it the substrate — unlike
:mod:`gebra.store`, :mod:`gebra.versioning`, :mod:`gebra.diff` and :mod:`gebra.lineage`, which
stay langgraph-free and are tripwired for it. That is what "wired to extract" costs, and the
never-invokes claim is held in the strong form instead:
``tests/snapshot/test_travel_booking.py`` snapshots the sentinel-guarded travel-booking agent
twice in a fresh interpreter where name resolution and connection opening raise from the first
line and ``StateGraph.compile`` raises from before gebra is imported.
"""

from gebra.snapshot.engine import record, record_document, snapshot
from gebra.snapshot.models import (
    SnapshotAction,
    SnapshotError,
    SnapshotErrorReason,
    SnapshotOutcome,
)

__all__ = [
    "SnapshotAction",
    "SnapshotError",
    "SnapshotErrorReason",
    "SnapshotOutcome",
    "record",
    "record_document",
    "snapshot",
]
