"""The `.gebra/` snapshot store — the IR-SPEC §4.1 envelope, written and read.

A snapshot is a workflow's core IR plus the three envelope fields IR-SPEC §4.1 fixes:
``version`` (the V.S.F.E label), ``extracted_from`` (provenance) and ``graph_version`` (the
§6 content digest). §4.1 names those fields and gives their semantics to brief D-11; PD-012
(ratified 2026-07-31) is where D-11's track fixed the field-level shape, the store layout and
the emitter rules, and this package is that ruling as code::

    from gebra.store import ExtractedFrom, Snapshot, SnapshotStore

    snapshot = Snapshot.of(
        ir,
        version="1.0.0.0",
        extracted_from=ExtractedFrom(
            source="travel_booking:build_graph",
            extractor_version="0.0.1",
            extracted_at="2026-08-04T09:00:00Z",
        ),
    )
    store = SnapshotStore.for_project(project_root)
    store.write(snapshot)
    store.read("1.0.0.0") == snapshot        # True — a snapshot reloads equal to itself

:class:`~gebra.store.models.Snapshot` and :class:`~gebra.store.models.StoreMeta` are the two
documents; :class:`~gebra.store.store.SnapshotStore` is the directory they live in;
:func:`~gebra.store.serialization.dump_snapshot` and its three siblings are the emitter and
the loader on their own, for a caller who has bytes rather than a store; and
:func:`~gebra.store.atomic.write_atomic` is the temp-file-plus-rename primitive every write
goes through.

**What the digest gives you, and what it does not.** ``graph_version`` is the digest of the
core IR and of nothing else — the envelope is outside the hash scope by construction, since
the digest is computed from the ``ir`` member alone (IR-SPEC §6.4). Because IR-SPEC §6.4 puts
the per-node ``prompt_digest``/``config_digest`` *inside* the scope, two versions of a
workflow that differ only in prompt text carry different digests and are two distinct
snapshots — the opaque-body gap decision D-025 exists to close. It is a content digest: two
snapshots with the same ``graph_version`` hold IRs with the same canonical form. It says
nothing about what the workflow does when it runs.

**What is not here.** The V.S.F.E label is a string this layer stores and never parses; its
grammar, comparison and bump rules live in :mod:`gebra.versioning`, which the store does not
import — a label reaches here already decided, and is checked only for being usable as a file
name. Deciding *which* version a newly extracted workflow gets, and whether an unchanged
workflow is re-snapshot at all, is :mod:`gebra.snapshot`'s: it extracts, assigns the label the
diff engine's bump class lands on, and calls :meth:`SnapshotStore.write
<gebra.store.store.SnapshotStore.write>`. Structural diff between two snapshots lives in
:mod:`gebra.diff` — topology, contracts and the state schema, with the V.S.F.E bump class
derived from them. Listing what a store holds — versions, digests, and the V.S.F.E step
between each neighbouring pair — is :mod:`gebra.lineage`, which reads this package's
``meta.yaml`` and never a snapshot file. The ``reports/<version>.report.json`` audit export is
SD-07's, written against ``docs/specs/REPORT-FORMAT-SPEC.md`` §6: this package fixes that
file's path and writes none. There is no ``gebra snapshot``
command: the CLI verbs are the D-12 track's.

Nothing in this package imports langgraph, opens a socket, or executes anything (WA-07). Its
input is an IR *model*; no user object is ever in reach to invoke.
"""

from gebra.store.atomic import TEMP_PREFIX, TEMP_SUFFIX, is_temp_name, write_atomic
from gebra.store.base import StoreModel
from gebra.store.models import (
    MAX_VERSION_LENGTH,
    TIMESTAMP_FORMAT,
    Digest,
    ExtractedFrom,
    Snapshot,
    SnapshotRecord,
    StoreMeta,
    Timestamp,
    VersionLabel,
    format_timestamp,
    parse_timestamp,
)
from gebra.store.serialization import dump_meta, dump_snapshot, load_meta, load_snapshot
from gebra.store.store import (
    META_FILENAME,
    REPORT_SUFFIX,
    REPORTS_DIRNAME,
    SNAPSHOT_SUFFIX,
    SNAPSHOTS_DIRNAME,
    STORE_DIRNAME,
    SnapshotStore,
    StoreCheck,
    StoreError,
    StoreErrorReason,
    StoreProblem,
)

__all__ = [
    "MAX_VERSION_LENGTH",
    "META_FILENAME",
    "REPORTS_DIRNAME",
    "REPORT_SUFFIX",
    "SNAPSHOTS_DIRNAME",
    "SNAPSHOT_SUFFIX",
    "STORE_DIRNAME",
    "TEMP_PREFIX",
    "TEMP_SUFFIX",
    "TIMESTAMP_FORMAT",
    "Digest",
    "ExtractedFrom",
    "Snapshot",
    "SnapshotRecord",
    "SnapshotStore",
    "StoreCheck",
    "StoreError",
    "StoreErrorReason",
    "StoreMeta",
    "StoreModel",
    "StoreProblem",
    "Timestamp",
    "VersionLabel",
    "dump_meta",
    "dump_snapshot",
    "format_timestamp",
    "is_temp_name",
    "load_meta",
    "load_snapshot",
    "parse_timestamp",
    "write_atomic",
]
