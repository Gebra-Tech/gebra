"""The `.gebra/` store — the layout of PD-012, and reading and writing it.

Brief D-11 In-Scope 1 names three paths and calls the store "git-friendly, append-only";
PD-012 fixed the rest. The layout is::

    .gebra/
    ├── snapshots/
    │   └── <version>.yaml          one Snapshot document per V.S.F.E version
    ├── reports/
    │   └── <version>.report.json   the per-version audit export (SD-07 writes these;
    │                               the naming rule is fixed here, the content is not)
    └── meta.yaml                   the store index: pointer + append-only history

``<version>`` is the V.S.F.E label used **verbatim** as the file base name. Its grammar is
SD-02's card; what this layer owns is the path-safety floor that keeps a label from writing
outside the store (:data:`~gebra.store.models.VersionLabel`).

**Two writes, in the order that makes the interruption survivable.** A snapshot lands as a
snapshot file and a ``meta.yaml`` row, and no filesystem makes two files change together. So
the order is chosen rather than incidental: the snapshot file is written first and
``meta.yaml`` second. A process that dies between them leaves a snapshot file no history row
references — an **orphan**, which :meth:`SnapshotStore.check` reports and which every reader
ignores, because readers go through the history. The reverse order would leave a history row
pointing at a file that does not exist, which is a store that reads broken. Re-running the
interrupted write is the repair: :meth:`SnapshotStore.write` overwrites an orphan file for
exactly this reason, while still refusing a version the history already holds.

**Corruption is reported, never repaired.** SD-01's card leaves corruption handling to the
implementer, and the choice here is that the store never edits its way out of a problem:

* a read of a damaged snapshot raises :class:`StoreError` carrying a
  :class:`StoreErrorReason`, so a caller branches on a code rather than on message text;
* the one *content* corruption the store can detect on its own is a digest that no longer
  describes the IR beside it — checked by recompute-and-string-compare (IR-SPEC §6.1 step 9)
  on every write and every read;
* :meth:`SnapshotStore.check` walks the whole store and *returns* what is wrong instead of
  raising at the first thing, so "is this store consistent?" is one call with a complete
  answer. Orphan snapshot files and leftover temp files are reported separately from
  problems: neither is damage, and a store carrying them still reads correctly.

**No clock is read here.** A snapshot's history timestamp defaults to its own
``extracted_from.extracted_at`` and can be given explicitly; nothing in this module calls
``now()``. A store write is therefore a function of its arguments, which is what lets a test
hold the emitter to "identical content, identical bytes".

Nothing in this module imports langgraph, opens a socket, or executes anything (WA-07). The
store's input is an IR *model*; there is no user object in reach to invoke.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Final

from pydantic import TypeAdapter, ValidationError

from gebra.ir.canonical import CanonicalizationError
from gebra.store.atomic import is_temp_name, write_atomic
from gebra.store.models import Snapshot, SnapshotRecord, StoreMeta, VersionLabel
from gebra.store.serialization import dump_meta, dump_snapshot, load_meta, load_snapshot

__all__ = [
    "META_FILENAME",
    "REPORTS_DIRNAME",
    "REPORT_SUFFIX",
    "SNAPSHOTS_DIRNAME",
    "SNAPSHOT_SUFFIX",
    "STORE_DIRNAME",
    "SnapshotStore",
    "StoreCheck",
    "StoreError",
    "StoreErrorReason",
    "StoreProblem",
]

#: The store directory, relative to a project root (D-11 In-Scope 1).
STORE_DIRNAME: Final = ".gebra"

#: ``.gebra/snapshots/`` — one file per version.
SNAPSHOTS_DIRNAME: Final = "snapshots"

#: ``.gebra/reports/`` — the per-version audit export (SD-07's content, this layer's naming).
REPORTS_DIRNAME: Final = "reports"

#: ``.gebra/meta.yaml`` — the store index.
META_FILENAME: Final = "meta.yaml"

#: What a snapshot file is called after its version label.
SNAPSHOT_SUFFIX: Final = ".yaml"

#: What a report file is called after its version label.
REPORT_SUFFIX: Final = ".report.json"

#: One validator for the version label, so a path built here and a label validated inside a
#: model can never disagree about what is admissible.
_VERSION = TypeAdapter(VersionLabel)


class StoreErrorReason(str, Enum):
    """Why the store refused — a stable code to branch on, never message text.

    Like :class:`~gebra.ir.serialization.IRSerializationErrorReason` these are store-integrity
    codes, not condition IDs: the PROPERTY-CATALOG-SPEC §0.4 registry neither contains nor
    needs them, and no verification envelope reports one.
    """

    UNSAFE_VERSION = "unsafe-version"
    SNAPSHOT_MISSING = "snapshot-missing"
    SNAPSHOT_UNREADABLE = "snapshot-unreadable"
    META_UNREADABLE = "meta-unreadable"
    DIGEST_MISMATCH = "digest-mismatch"
    VERSION_MISMATCH = "version-mismatch"
    DUPLICATE_VERSION = "duplicate-version"


class StoreError(ValueError):
    """A store operation that could not be completed, or a document that is not intact.

    Subclassing :class:`ValueError` mirrors
    :class:`~gebra.ir.serialization.IRSerializationError` and
    :class:`~gebra.ir.canonical.CanonicalizationError`.

    Attributes:
        reason: The :class:`StoreErrorReason` code — match on this, not on text.
        path: The file the fault belongs to, or the store directory for a fault that belongs
            to the store as a whole.
    """

    def __init__(self, message: str, *, reason: StoreErrorReason, path: Path) -> None:
        super().__init__(message)
        self.reason = reason
        self.path = path


@dataclass(frozen=True)
class StoreProblem:
    """One thing :meth:`SnapshotStore.check` found wrong.

    Attributes:
        reason: The same code the equivalent read would have raised.
        path: The file it belongs to.
        version: The version label it belongs to, or ``None`` for a store-wide fault.
        detail: One sentence for a person, never the thing to branch on.
    """

    reason: StoreErrorReason
    path: Path
    version: str | None
    detail: str


@dataclass(frozen=True)
class StoreCheck:
    """The state of a whole store — what :meth:`SnapshotStore.check` returns.

    Attributes:
        problems: Everything wrong, in history order then store order. Empty means every
            version the index claims is present, readable, self-consistent, and hashes to
            what the index says.
        orphans: Snapshot files present on disk that no history row references. Not damage:
            an orphan is what a process killed between the snapshot write and the index
            update leaves behind, and no reader follows a path that is not in the index.
        residue: Leftover temp files from an interrupted write. Not damage either — a temp
            name is never the target of anything that reads.
    """

    problems: tuple[StoreProblem, ...] = ()
    orphans: tuple[Path, ...] = ()
    residue: tuple[Path, ...] = ()

    @property
    def ok(self) -> bool:
        """Whether the store is consistent — no problems. Orphans and residue are not."""
        return not self.problems


class SnapshotStore:
    """A `.gebra/` directory: where snapshots are written, and how they are read back.

    Construct it on the store directory itself, or on the project that owns one::

        store = SnapshotStore.for_project(Path.cwd())      # <cwd>/.gebra
        store = SnapshotStore(some_path / ".gebra")        # that exact directory

    Nothing is created until the first :meth:`write`; a store that does not exist yet reads
    as an empty one.
    """

    def __init__(self, path: str | os.PathLike[str]) -> None:
        self._path = Path(path)

    @classmethod
    def for_project(cls, project_root: str | os.PathLike[str]) -> SnapshotStore:
        """The store of the project rooted at ``project_root`` — its ``.gebra/`` directory."""
        return cls(Path(project_root) / STORE_DIRNAME)

    def __repr__(self) -> str:
        return f"{type(self).__name__}({str(self._path)!r})"

    # ── Where things are ─────────────────────────────────────────────────────────────────

    @property
    def path(self) -> Path:
        """The store directory itself."""
        return self._path

    @property
    def snapshots_dir(self) -> Path:
        """``.gebra/snapshots/``."""
        return self._path / SNAPSHOTS_DIRNAME

    @property
    def reports_dir(self) -> Path:
        """``.gebra/reports/`` — where SD-07's audit export goes."""
        return self._path / REPORTS_DIRNAME

    @property
    def meta_path(self) -> Path:
        """``.gebra/meta.yaml``."""
        return self._path / META_FILENAME

    @property
    def exists(self) -> bool:
        """Whether the store directory is there. A store that is not reads as empty."""
        return self._path.is_dir()

    def snapshot_path(self, version: str) -> Path:
        """Where the snapshot for ``version`` lives — ``snapshots/<version>.yaml``.

        Raises:
            StoreError: ``unsafe-version`` if ``version`` could not be a file base name. The
                check is the path-safety floor, not the V.S.F.E grammar (SD-02's card).
        """
        return self.snapshots_dir / f"{self._checked(version)}{SNAPSHOT_SUFFIX}"

    def report_path(self, version: str) -> Path:
        """Where the audit export for ``version`` lives — ``reports/<version>.report.json``.

        The path rule is PD-012's and lives here so SD-07 does not re-derive it; the report's
        JSON content is that card's decision and nothing here writes one.

        Raises:
            StoreError: ``unsafe-version``, as for :meth:`snapshot_path`.
        """
        return self.reports_dir / f"{self._checked(version)}{REPORT_SUFFIX}"

    def _checked(self, version: str) -> str:
        """``version`` if it can be a file base name, else a coded refusal."""
        try:
            return str(_VERSION.validate_python(version))
        except ValidationError as exc:
            raise StoreError(
                f"{version!r} cannot be used as a file name, so no snapshot can be stored "
                "under it; a version label is used verbatim as the file base name (PD-012)",
                reason=StoreErrorReason.UNSAFE_VERSION,
                path=self._path,
            ) from exc

    # ── Reading ──────────────────────────────────────────────────────────────────────────

    def read_meta(self) -> StoreMeta:
        """The store index. A store with no ``meta.yaml`` reads as an empty one.

        Raises:
            StoreError: ``meta-unreadable`` if ``meta.yaml`` is there and is not a store
                index — unparseable, carrying an unknown member, or breaking one of the two
                history invariants.
        """
        meta_path = self.meta_path
        if not meta_path.is_file():
            return StoreMeta()
        try:
            return load_meta(meta_path.read_text(encoding="utf-8"))
        # `ValueError` is the one branch, not three: `IRSerializationError` (the surface),
        # pydantic's `ValidationError` (the model) and `UnicodeDecodeError` (bytes that are
        # not UTF-8) are all `ValueError`s, and all three mean the same thing here.
        except ValueError as exc:
            raise StoreError(
                f"{meta_path} is not a readable store index: {exc}",
                reason=StoreErrorReason.META_UNREADABLE,
                path=meta_path,
            ) from exc

    def versions(self) -> tuple[str, ...]:
        """Every version the store holds, oldest first."""
        return tuple(record.version for record in self.read_meta().history)

    def holds(self, version: str) -> bool:
        """Whether the index holds ``version`` — the append-only question :meth:`write` asks.

        Raises:
            StoreError: ``unsafe-version`` if ``version`` is not a usable label;
                ``meta-unreadable`` if the index is damaged.
        """
        return self.read_meta().record_for(self._checked(version)) is not None

    def read(self, version: str, *, verify: bool = True) -> Snapshot:
        """The snapshot stored under ``version``.

        Args:
            version: The V.S.F.E label.
            verify: Whether to recompute the digest and compare it to the stored one
                (IR-SPEC §6.1 step 9). Left on: it is the store's one content-integrity
                check. Turn it off to load a snapshot the check refuses — to look at what is
                damaged, which is the one thing a refusing reader cannot do.

        Raises:
            StoreError: ``unsafe-version``; ``snapshot-missing``; ``snapshot-unreadable`` for
                a file that is not a snapshot document; ``version-mismatch`` if the document's
                own ``version`` is not the one its file name claims; ``digest-mismatch`` if
                the stored digest is not the digest of the stored IR.
        """
        path = self.snapshot_path(version)
        if not path.is_file():
            raise StoreError(
                f"the store holds no snapshot at {path}",
                reason=StoreErrorReason.SNAPSHOT_MISSING,
                path=path,
            )
        snapshot = self._load(path)
        if snapshot.version != self._checked(version):
            raise StoreError(
                f"{path} holds version {snapshot.version!r}, not the {version!r} its file "
                "name claims; a snapshot names itself and the two have to agree",
                reason=StoreErrorReason.VERSION_MISMATCH,
                path=path,
            )
        if verify and not self._digest_matches(snapshot, path):
            raise StoreError(
                f"{path} carries {snapshot.graph_version}, which is not the digest of the "
                "IR beside it; the file has been edited or was written damaged",
                reason=StoreErrorReason.DIGEST_MISMATCH,
                path=path,
            )
        return snapshot

    def current(self) -> Snapshot | None:
        """The snapshot the index points at, or ``None`` for an empty store.

        Raises:
            StoreError: as for :meth:`read`, if the pointed-at snapshot is not intact.
        """
        pointer = self.read_meta().current
        return None if pointer is None else self.read(pointer)

    def _load(self, path: Path) -> Snapshot:
        """Read and validate one snapshot file, faults coded to the file."""
        try:
            return load_snapshot(path.read_text(encoding="utf-8"))
        except ValueError as exc:  # surface, model and decoding faults alike — see read_meta
            raise StoreError(
                f"{path} is not a readable snapshot: {exc}",
                reason=StoreErrorReason.SNAPSHOT_UNREADABLE,
                path=path,
            ) from exc

    def _digest_matches(self, snapshot: Snapshot, path: Path) -> bool:
        """The §6.1 step-9 comparison, with an unhashable IR coded as unreadable.

        An IR that validates but cannot be canonicalized — a non-NFC identifier, an integer
        outside the I-JSON range — has no digest to compare, so the file is not a snapshot
        anything could have written.
        """
        try:
            return snapshot.digest_matches()
        except CanonicalizationError as exc:
            raise StoreError(
                f"{path} holds an IR that has no canonical form, so its digest cannot be "
                f"checked: {exc}",
                reason=StoreErrorReason.SNAPSHOT_UNREADABLE,
                path=path,
            ) from exc

    # ── Writing ──────────────────────────────────────────────────────────────────────────

    def initialize(self) -> None:
        """Create the store's directory tree if it is not there. Writes no files."""
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)
        self.reports_dir.mkdir(parents=True, exist_ok=True)

    def write(self, snapshot: Snapshot, *, created_at: str | None = None) -> Path:
        """Store ``snapshot`` and record it in the index. Returns the file it was written to.

        Two atomic writes, snapshot first: a process killed between them leaves an orphan
        file rather than an index row pointing at nothing, and re-running this call completes
        the interrupted write.

        Args:
            snapshot: The snapshot to store. Its digest is checked against its IR first — the
                store will not record a snapshot that already disagrees with itself.
            created_at: When to say the version landed, in the store's timestamp spelling.
                Defaults to the snapshot's own ``extracted_from.extracted_at``, which keeps a
                write a function of its arguments; pass one to say when it was *stored* rather
                than when it was made.

        Raises:
            StoreError: ``duplicate-version`` if the index already holds this version — the
                store is append-only, and whether an unchanged workflow is re-snapshot at all
                is :mod:`gebra.snapshot`'s policy, not this layer's; ``digest-mismatch`` if the
                snapshot's digest is not the digest of its IR; ``meta-unreadable`` if the
                index cannot be read first.
            pydantic.ValidationError: if ``created_at`` is not a store timestamp.
            OSError: if a file cannot be written. Nothing has changed if the snapshot write
                is the one that failed; the snapshot is on disk as an orphan if the index
                write is.
        """
        path = self.snapshot_path(snapshot.version)
        if not self._digest_matches(snapshot, path):
            raise StoreError(
                f"the snapshot for {snapshot.version!r} carries {snapshot.graph_version}, "
                "which is not the digest of its own IR; build it with Snapshot.of()",
                reason=StoreErrorReason.DIGEST_MISMATCH,
                path=path,
            )
        meta = self.read_meta()
        if meta.record_for(snapshot.version) is not None:
            raise StoreError(
                f"the store already holds version {snapshot.version!r}; the store is "
                "append-only, so a changed workflow gets a new version rather than a "
                "rewritten one",
                reason=StoreErrorReason.DUPLICATE_VERSION,
                path=path,
            )
        record = SnapshotRecord(
            version=snapshot.version,
            graph_version=snapshot.graph_version,
            created_at=created_at
            if created_at is not None
            else snapshot.extracted_from.extracted_at,
        )
        appended = meta.appended(record)

        self.initialize()
        write_atomic(path, dump_snapshot(snapshot))
        write_atomic(self.meta_path, dump_meta(appended))
        return path

    # ── Integrity ────────────────────────────────────────────────────────────────────────

    def check(self) -> StoreCheck:
        """Walk the whole store and report its state — the complete answer, never the first.

        A store that does not exist, or exists and holds nothing, checks out fine: an empty
        store is a consistent store.
        """
        if not self.exists:
            return StoreCheck()
        try:
            meta = self.read_meta()
        except StoreError as exc:
            return StoreCheck(
                problems=(
                    StoreProblem(reason=exc.reason, path=exc.path, version=None, detail=str(exc)),
                ),
                residue=self._residue(),
            )

        problems = [problem for record in meta.history for problem in self._check_record(record)]
        indexed = {record.version for record in meta.history}
        orphans = tuple(
            path
            for path in self._snapshot_files()
            if path.name.removesuffix(SNAPSHOT_SUFFIX) not in indexed
        )
        return StoreCheck(problems=tuple(problems), orphans=orphans, residue=self._residue())

    def _check_record(self, record: SnapshotRecord) -> list[StoreProblem]:
        """Everything wrong with one indexed version."""
        try:
            snapshot = self.read(record.version)
        except StoreError as exc:
            return [
                StoreProblem(
                    reason=exc.reason, path=exc.path, version=record.version, detail=str(exc)
                )
            ]
        if snapshot.graph_version != record.graph_version:
            return [
                StoreProblem(
                    reason=StoreErrorReason.DIGEST_MISMATCH,
                    path=self.snapshot_path(record.version),
                    version=record.version,
                    detail=(
                        f"the index records {record.graph_version} for "
                        f"{record.version!r} and the snapshot carries "
                        f"{snapshot.graph_version}"
                    ),
                )
            ]
        return []

    def _snapshot_files(self) -> tuple[Path, ...]:
        """Every ``snapshots/*.yaml``, in name order so a check reads the same twice."""
        if not self.snapshots_dir.is_dir():
            return ()
        return tuple(sorted(self.snapshots_dir.glob(f"*{SNAPSHOT_SUFFIX}")))

    def _residue(self) -> tuple[Path, ...]:
        """Every leftover temp file anywhere in the store, in path order."""
        return tuple(
            sorted(
                path for path in self._path.rglob("*") if path.is_file() and is_temp_name(path.name)
            )
        )
