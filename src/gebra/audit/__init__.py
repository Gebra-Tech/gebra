"""The audit export and the snapshot-freshness check — brief D-11 In-Scope 6 and 7.

Two halves of one job: making a store's history readable as a record of what the validators
found on each stored version, and making CI notice when the definition has moved away from it.

**The export** writes one JSON property report per stored version, to the PD-012 path
``.gebra/reports/<version>.report.json``::

    from gebra.audit import export_store, read_export
    from gebra.store import SnapshotStore

    store = SnapshotStore.for_project(project_root)
    for outcome in export_store(store):
        outcome.version, outcome.path, outcome.report.gate.exit_code

    read_export(store, "1.0.0.0")       # parsed back through the same model, profile checked

That document is **not this package's schema**. It is ``docs/specs/REPORT-FORMAT-SPEC.md``
§1's :class:`~gebra.verify.RunReport` in the snapshot profile of its §6, ratified at CLI-01,
which §6.3 states in terms: "SD-07 defines no export schema of its own and carries no second
version line." Everything in :mod:`gebra.audit.export` is assembly above
:func:`gebra.verify.verify`, plus :func:`~gebra.audit.export.check_profile` — the §6.2
obligations as a function, run before every write.

**The freshness check** compares a working definition's ``graph_version`` against the snapshot
the store currently points at::

    from gebra.audit import freshness

    outcome = freshness(ir, store=store)
    outcome.fresh                       # False
    outcome.moved                       # (Component.S, Component.F)
    print(outcome.summary())

It answers in three states rather than two — fresh, stale, and a store that holds nothing at
all, which is not the same event and does not want the same words. It never writes, and it
grades nothing: P-12 ``evolution-safety`` is deferred out of Phase 0 (SOW §8, PD-006 R4), so a
stale outcome reports that the content moved and which of S/F/E moved with it, and stops.

**In CI**, the check runs through the pytest harness (D-11 deliverable 6) as
``@pytest.mark.gebra_freshness``, which fails its item when the store is stale, and as the
``gebra_freshness`` fixture for a suite that would rather assert on the outcome itself. Both
are :mod:`gebra.pytest_plugin`'s surface over this engine.

**Nothing here imports langgraph, opens a socket, or executes anything (WA-07)**, and unlike
:mod:`gebra.snapshot` that holds for the whole package: :func:`~gebra.audit.freshness.freshness`
takes an IR rather than a live workflow, so the substrate never enters this import closure and
``tests/audit/test_freshness.py`` asserts it in an interpreter where it could not.
"""

from gebra.audit.export import (
    check_profile,
    export_store,
    export_version,
    read_export,
    snapshot_report,
)
from gebra.audit.freshness import freshness
from gebra.audit.models import (
    AuditError,
    AuditErrorReason,
    ExportOutcome,
    Freshness,
    FreshnessOutcome,
)

__all__ = [
    "AuditError",
    "AuditErrorReason",
    "ExportOutcome",
    "Freshness",
    "FreshnessOutcome",
    "check_profile",
    "export_store",
    "export_version",
    "freshness",
    "read_export",
    "snapshot_report",
]
