"""Version history over the `.gebra/` store — what versions exist, and what moved between them.

Brief D-11 In-Scope 3 owes brief D-12 the engines behind ``gebra snapshot``, ``gebra diff`` and
the version-history verb; W10 names this one. :func:`~gebra.lineage.engine.lineage` is the
listing::

    from gebra.lineage import dump_lineage, lineage

    history = lineage(store)

    history.total                     # 5
    history.versions                  # ('1.0.0.0', '1.1.0.0', '1.1.1.0', '1.2.1.0', '1.2.1.1')
    history.newest.graph_version      # 'sha256:5db68464…'
    history.newest.step.bump_class    # (Component.E,)
    history.newest.step.content_changed   # True

    lineage(store, limit=2).versions  # ('1.2.1.0', '1.2.1.1') — the two most recent
    dump_lineage(history)             # canonical JSON, byte-stable, one trailing newline

**One read, one order.** A listing opens ``meta.yaml`` and no snapshot file: it reports what
the store's index records. The order is the store's own — oldest first, append order, not
configurable. ``since``/``until`` anchor an inclusive window and ``limit`` keeps the most
recent rows of it; whatever the window, ``total``, ``omitted_before``, ``omitted_after`` and
each row's absolute ``index`` ride along, and a row's step names its predecessor in the
*store*, not in the page.

**Two different questions about a pair, and both are available.**
:attr:`~gebra.lineage.models.LineageStep.bump_class` is what the two *labels* record —
arithmetic over data the index already holds. :func:`~gebra.lineage.engine.compare` is what
the *content* says: both snapshots read and run through
:func:`~gebra.diff.workflow_diff`. Nothing in the store makes a label describe what changed,
so the two can disagree, and where they do neither is quietly preferred.

**Nothing here grades a change.** A step reports which counters moved; a comparison returns a
diff carrying the property registry's own deferred-P-12 marker where a safe/breaking
classification would sit. P-12 ``evolution-safety`` is out of Phase-0 scope (SOW §8; PD-006
R4), so no part of this package says whether an evolution is safe.

**And nothing here is a command.** Whether the verb is ``gebra trace`` or ``gebra history``,
and what its output looks like, is D-12's open question OQ-12-04 — routed to card CLI-D4,
unresolved, and named for a collision ("trace" also means runtime traces in a future
hosted surface). This package is therefore named for what it computes, and
:mod:`gebra.lineage.document` offers a stable JSON projection rather than a rendering.

Nothing in this package imports langgraph, opens a socket, or executes anything (WA-07). Its
inputs are a store directory and IR models; networkx is in reach only through
:mod:`gebra.diff`, which :func:`~gebra.lineage.engine.compare` uses and which the tripwires in
``tests/lineage/`` pin the same way ``tests/diff/`` does.
"""

from gebra.lineage.document import (
    LINEAGE_DOCUMENT_VERSION,
    Document,
    dump_lineage,
    lineage_document,
)
from gebra.lineage.engine import LineageError, LineageErrorReason, compare, lineage
from gebra.lineage.models import Lineage, LineageEntry, LineageStep

__all__ = [
    "LINEAGE_DOCUMENT_VERSION",
    "Document",
    "Lineage",
    "LineageEntry",
    "LineageError",
    "LineageErrorReason",
    "LineageStep",
    "compare",
    "dump_lineage",
    "lineage",
    "lineage_document",
]
