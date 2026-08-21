"""Atomic file replacement — the store's one write primitive (PD-012).

Brief D-11 In-Scope 2 asks for "atomic writes via temp file + rename", and SD-01's acceptance
is that an interrupted write "leaves the store consistent". PD-012 fixed the mechanism and
where it lives: a store-layer helper, deliberately **not** a change inside
:func:`gebra.ir.serialization.write_ir`, whose other callers — fixture authoring, round-trip
tests, docs examples — have no atomicity requirement and whose module is gated behind the
signed G1 exit.

The sequence, and what each step is for:

1. write the text to a temp file **in the target's own directory** — ``os.replace`` is atomic
   only within a filesystem, and a temp directory elsewhere is a different one often enough
   to matter;
2. ``flush()`` then :func:`os.fsync` the temp file, so the bytes are on the device before
   anything points at them. Without it a crash can leave the rename durable and the contents
   not — the file exists, under the right name, holding nothing;
3. :func:`os.replace`, which is atomic and overwrite-safe on POSIX **and** on Windows, unlike
   ``os.rename``. A reader concurrent with this call sees the old file or the new one;
4. best-effort :func:`os.fsync` of the containing directory, so the rename itself is durable.
   POSIX only — opening a directory for reading is not a thing a Windows filesystem does, and
   the failure is caught and ignored rather than made into the caller's problem.

**What this does not claim.** Step 3 is atomic with respect to *this* file: a reader never
observes a half-written document. It says nothing about two files — a process killed between
two ``write_atomic`` calls has completed the first and not the second, which is why
:class:`~gebra.store.store.SnapshotStore` orders its two writes so that the survivable
outcome is the one that leaves the store readable.

**The temp file is cleaned up on every failure path** this function can observe, so a
completed-but-failed call leaves no residue. A process that dies outright can still leave one
behind; :meth:`~gebra.store.store.SnapshotStore.check` looks for those and reports them as
residue rather than as damage, since by construction they are never the target of a name
anything reads.

Nothing in this module imports langgraph, opens a socket, or executes anything (WA-07).
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Final

__all__ = ["TEMP_PREFIX", "TEMP_SUFFIX", "is_temp_name", "write_atomic"]

#: Temp files are named ``.<target name>.<random>.tmp``. The leading dot hides them from a
#: POSIX directory listing, and the suffix keeps them out of the ``*.yaml`` glob that finds
#: snapshots — so a residue file is never mistaken for a stored version.
TEMP_PREFIX: Final = "."
TEMP_SUFFIX: Final = ".tmp"

#: The one encoding the store reads and writes (IR-SPEC §6.1 step 6 is UTF-8, and PD-012's
#: emitter rules restate it for the surface).
_ENCODING: Final = "utf-8"


def is_temp_name(name: str) -> bool:
    """Whether ``name`` is one of this module's temp files."""
    return name.startswith(TEMP_PREFIX) and name.endswith(TEMP_SUFFIX)


def write_atomic(path: str | os.PathLike[str], text: str) -> None:
    """Replace the file at ``path`` with ``text``, atomically.

    The text is written as UTF-8 with LF line endings — binary mode, so the newline
    translation a Windows text-mode write would apply cannot reach it and one store emits the
    same bytes on every platform.

    The parent directory must already exist; creating it is the caller's, because a store
    that conjures directories on the way to a write hides a mistyped path instead of
    reporting it.

    Raises:
        OSError: if the file cannot be written or replaced. The temp file is removed first,
            and the file at ``path`` is left exactly as it was.
    """
    target = Path(path)
    descriptor, temp_name = tempfile.mkstemp(
        dir=target.parent, prefix=f"{TEMP_PREFIX}{target.name}.", suffix=TEMP_SUFFIX
    )
    temp = Path(temp_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(text.encode(_ENCODING))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, target)
    except BaseException:
        _discard(temp)
        raise
    _sync_directory(target.parent)


def _discard(temp: Path) -> None:
    """Remove a temp file that will never be renamed, without masking why it exists.

    ``missing_ok`` covers the case where the failure *was* the rename half-succeeding, and a
    second ``OSError`` from the cleanup would replace the one worth reading.
    """
    try:
        temp.unlink(missing_ok=True)
    except OSError:  # pragma: no cover — a directory that refuses an unlink refused the write
        pass


def _sync_directory(directory: Path) -> None:
    """Best-effort ``fsync`` of ``directory``, so the rename survives a power loss.

    POSIX only. Windows has no file descriptor for a directory to sync, and every way of
    asking for one raises — which is caught here rather than turned into a failed write of a
    file that was, in fact, written.
    """
    try:
        descriptor = os.open(directory, os.O_RDONLY)
    except OSError:  # pragma: no cover — the Windows path
        return
    try:
        os.fsync(descriptor)
    except OSError:  # pragma: no cover — a filesystem that refuses a directory sync
        pass
    finally:
        os.close(descriptor)
