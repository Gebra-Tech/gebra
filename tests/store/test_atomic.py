"""The atomic-write primitive — the first half of SD-01 acceptance 2.

Normative authority: brief D-11 In-Scope 2 ("atomic writes via temp file + rename") and
PD-012, which fixed the mechanism — temp file in the target's own directory, ``flush`` +
``fsync``, ``os.replace``, best-effort directory sync — and put it in the store layer rather
than inside ``gebra.ir.serialization.write_ir``.

The interruption is injected at each of the three points where a real one could land: while
the bytes are being written, after they are written and before they are durable, and at the
swap itself. The invariant under test is the same at all three: **the file at the target path
is either exactly what it was or exactly what it was going to be, and never a prefix of
either.**
"""

from __future__ import annotations

import io
import os
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import IO, Any

import pytest

from gebra.store import TEMP_PREFIX, TEMP_SUFFIX, is_temp_name, write_atomic

OLD = "before: 1\n"
NEW = "after: 2\n"


def _residue(directory: Path) -> list[Path]:
    return sorted(path for path in directory.iterdir() if is_temp_name(path.name))


# ── The ordinary path ────────────────────────────────────────────────────────────────────


def test_it_writes_the_exact_bytes(tmp_path: Path) -> None:
    target = tmp_path / "meta.yaml"

    write_atomic(target, "clé: valeur\n")

    assert target.read_bytes() == "clé: valeur\n".encode()


def test_it_writes_lf_endings_on_every_platform(tmp_path: Path) -> None:
    """Binary mode, so the newline translation a Windows text-mode write would apply cannot
    reach the bytes and one store emits one set of them everywhere."""
    target = tmp_path / "meta.yaml"

    write_atomic(target, "a: 1\nb: 2\n")

    assert b"\r" not in target.read_bytes()


def test_it_replaces_an_existing_file(tmp_path: Path) -> None:
    target = tmp_path / "meta.yaml"
    target.write_text(OLD)

    write_atomic(target, NEW)

    assert target.read_text() == NEW


def test_it_leaves_no_temp_file_behind(tmp_path: Path) -> None:
    target = tmp_path / "meta.yaml"

    write_atomic(target, NEW)

    assert _residue(tmp_path) == []
    assert list(tmp_path.iterdir()) == [target]


def test_a_missing_parent_directory_is_reported_rather_than_created(tmp_path: Path) -> None:
    """A store that conjures directories on the way to a write hides a mistyped path."""
    with pytest.raises(OSError):
        write_atomic(tmp_path / "nowhere" / "meta.yaml", NEW)


def test_temp_names_are_recognizable_and_out_of_the_snapshot_glob() -> None:
    assert is_temp_name(f"{TEMP_PREFIX}1.0.0.0.yaml.abc123{TEMP_SUFFIX}")
    assert not is_temp_name("1.0.0.0.yaml")
    assert not is_temp_name("meta.yaml")


# ── Interruption ─────────────────────────────────────────────────────────────────────────


class _TornHandle(io.RawIOBase):
    """A file handle that writes half of what it is given and then fails.

    The faithful simulation of the interruption that matters: the temp file exists and holds
    a prefix of the document. What the test then checks is that no name anything reads ever
    points at it.

    Subclassing :class:`io.RawIOBase` rather than duck-typing the file protocol: the context
    manager and its ``close`` on exit come from there, so the descriptor is released on the
    failure path exactly as it would be for the real handle.
    """

    def __init__(self, handle: IO[bytes]) -> None:
        super().__init__()
        self._handle = handle

    def writable(self) -> bool:
        return True

    def write(self, b: Any) -> int:
        payload = bytes(b)
        self._handle.write(payload[: len(payload) // 2])
        self._handle.flush()
        raise OSError(28, "No space left on device")

    def fileno(self) -> int:  # pragma: no cover — unreachable past the raise above
        return self._handle.fileno()

    def close(self) -> None:
        self._handle.close()
        super().close()


@pytest.fixture
def interruptions(monkeypatch: pytest.MonkeyPatch) -> Iterator[dict[str, Callable[[], None]]]:
    """Three ways to interrupt a write, each armed by calling it."""
    real_fdopen = os.fdopen

    def torn_write() -> None:
        def fdopen(descriptor: int, mode: str = "r", *args: Any, **kwargs: Any) -> Any:
            return _TornHandle(real_fdopen(descriptor, "wb"))

        monkeypatch.setattr(os, "fdopen", fdopen)

    def failed_sync() -> None:
        def fsync(_: int) -> None:
            raise OSError(5, "Input/output error")

        monkeypatch.setattr(os, "fsync", fsync)

    def failed_swap() -> None:
        def replace(*_: Any, **__: Any) -> None:
            raise OSError(18, "Invalid cross-device link")

        monkeypatch.setattr(os, "replace", replace)

    yield {"torn write": torn_write, "failed sync": failed_sync, "failed swap": failed_swap}


@pytest.mark.parametrize("point", ["torn write", "failed sync", "failed swap"])
def test_an_interrupted_write_leaves_the_previous_file_exactly_as_it_was(
    tmp_path: Path, interruptions: dict[str, Callable[[], None]], point: str
) -> None:
    target = tmp_path / "meta.yaml"
    target.write_text(OLD)
    interruptions[point]()

    with pytest.raises(OSError):
        write_atomic(target, NEW)

    assert target.read_text() == OLD


@pytest.mark.parametrize("point", ["torn write", "failed sync", "failed swap"])
def test_an_interrupted_write_creates_no_file_where_there_was_none(
    tmp_path: Path, interruptions: dict[str, Callable[[], None]], point: str
) -> None:
    target = tmp_path / "meta.yaml"
    interruptions[point]()

    with pytest.raises(OSError):
        write_atomic(target, NEW)

    assert not target.exists()


@pytest.mark.parametrize("point", ["torn write", "failed sync", "failed swap"])
def test_an_interrupted_write_cleans_up_after_itself(
    tmp_path: Path, interruptions: dict[str, Callable[[], None]], point: str
) -> None:
    """The half-written temp file goes with the failure it belongs to. A process killed
    outright can still leave one — that is what
    :attr:`~gebra.store.StoreCheck.residue` is for — but a failure this call *observes*
    leaves nothing."""
    target = tmp_path / "meta.yaml"
    target.write_text(OLD)
    interruptions[point]()

    with pytest.raises(OSError):
        write_atomic(target, NEW)

    assert _residue(tmp_path) == []
    assert list(tmp_path.iterdir()) == [target]


def test_the_temp_file_is_written_in_the_targets_own_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``os.replace`` is atomic only within a filesystem, so a temp file elsewhere — the
    system temp directory, on many machines a different one — would not be atomic at all."""
    seen: list[Path] = []
    real_replace = os.replace

    def replace(src: Any, dst: Any) -> None:
        seen.append(Path(src))
        real_replace(src, dst)

    monkeypatch.setattr(os, "replace", replace)
    target = tmp_path / "snapshots" / "1.0.0.0.yaml"
    target.parent.mkdir()

    write_atomic(target, NEW)

    assert [path.parent for path in seen] == [target.parent]


def test_the_bytes_reach_the_device_before_anything_points_at_them(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Order, not just presence: an ``fsync`` after the rename would leave a crash able to
    produce a correctly-named file holding nothing."""
    order: list[str] = []
    real_fsync, real_replace = os.fsync, os.replace

    def fsync(descriptor: int) -> None:
        order.append("fsync")
        real_fsync(descriptor)

    def replace(src: Any, dst: Any) -> None:
        order.append("replace")
        real_replace(src, dst)

    monkeypatch.setattr(os, "fsync", fsync)
    monkeypatch.setattr(os, "replace", replace)

    write_atomic(tmp_path / "meta.yaml", NEW)

    assert order[: order.index("replace")] == ["fsync"]


@pytest.mark.skipif(os.name == "nt", reason="a directory has no file descriptor on Windows")
def test_the_containing_directory_is_synced_after_the_swap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    order: list[str] = []
    real_fsync, real_replace = os.fsync, os.replace

    def fsync(descriptor: int) -> None:
        order.append("fsync")
        real_fsync(descriptor)

    def replace(src: Any, dst: Any) -> None:
        order.append("replace")
        real_replace(src, dst)

    monkeypatch.setattr(os, "fsync", fsync)
    monkeypatch.setattr(os, "replace", replace)

    write_atomic(tmp_path / "meta.yaml", NEW)

    assert order == ["fsync", "replace", "fsync"]


def test_a_directory_that_cannot_be_synced_does_not_fail_the_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The Windows path, forced: the file was written, and a platform with no directory
    descriptor to sync is not a failed write."""
    real_open = os.open

    def refuse(path: Any, flags: int, *args: Any, **kwargs: Any) -> int:
        if Path(path).is_dir():
            raise PermissionError(13, "Permission denied")
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", refuse)
    target = tmp_path / "meta.yaml"

    write_atomic(target, NEW)

    assert target.read_text() == NEW
