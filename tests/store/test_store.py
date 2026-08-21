"""The `.gebra/` store — layout, corruption handling, and SD-01 acceptance 2 and 3.

Normative authority: brief D-11 In-Scope 1 (the three paths, git-friendly and append-only)
and 10 (the D-025 per-snapshot content hash, which MUST include the per-node prompt/config
digests); IR-SPEC §6.4 (what is in the hash scope) and §6.1 step 9 (recompute-and-compare);
PD-012 (the layout and the atomic-write mechanism).

Two of the card's three acceptance criteria live here:

* **acceptance 2** — an interrupted write leaves the store consistent. Interruption is
  injected at the store's *two* writes, which is where a real one is not covered by
  ``os.replace``: no filesystem changes two files together.
* **acceptance 3** — the digest-collision test. Two IRs differing only in a node's
  ``prompt_digest`` carry different ``graph_version``s and land as two distinct snapshots;
  the same two workflows *collide* when the digest slots are empty, which is the opaque-body
  gap decision D-025 exists to close.

Every IR here is hand-built (``tests/store/hand_built.py``): no extractor, no substrate, no
user object anywhere in reach to invoke (WA-07).
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from gebra.ir.canonical import graph_version
from gebra.ir.models import WorkflowIR
from gebra.store import (
    META_FILENAME,
    REPORT_SUFFIX,
    SNAPSHOT_SUFFIX,
    SNAPSHOTS_DIRNAME,
    STORE_DIRNAME,
    Snapshot,
    SnapshotStore,
    StoreError,
    StoreErrorReason,
    dump_snapshot,
    write_atomic,
)
from tests.store.hand_built import (
    ALL_IRS,
    GOLDEN_VECTOR_DIGEST,
    awkward_ir,
    bodiless_ir,
    extracted_from,
    golden_vector_ir,
    minimal_ir,
    prompt_bearing_ir,
    snapshot_of,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def store(tmp_path: Path) -> SnapshotStore:
    """A store on an otherwise empty project directory."""
    return SnapshotStore.for_project(tmp_path)


def _annotations_without_digests(ir: WorkflowIR) -> Any:
    """``ir``'s content with the two §3.6 digest slots removed — the pre-D-025 view of it."""
    return ir.model_dump(by_alias=True, exclude_none=True, exclude={"nodes"}), tuple(
        (
            node.id,
            None
            if node.annotations is None
            else node.annotations.model_dump(
                by_alias=True, exclude_none=True, exclude={"prompt_digest", "config_digest"}
            ),
        )
        for node in ir.nodes
    )


# ── Layout (D-11 In-Scope 1; PD-012) ─────────────────────────────────────────────────────


def test_the_store_is_the_dot_gebra_directory_of_its_project(tmp_path: Path) -> None:
    assert SnapshotStore.for_project(tmp_path).path == tmp_path / STORE_DIRNAME
    assert SnapshotStore(tmp_path / "elsewhere").path == tmp_path / "elsewhere"


def test_the_three_ruled_paths_are_where_the_brief_puts_them(store: SnapshotStore) -> None:
    assert store.snapshot_path("1.0.0.0") == store.path / SNAPSHOTS_DIRNAME / "1.0.0.0.yaml"
    assert store.report_path("1.0.0.0") == store.path / "reports" / f"1.0.0.0{REPORT_SUFFIX}"
    assert store.meta_path == store.path / META_FILENAME


def test_a_store_that_does_not_exist_reads_as_an_empty_one(store: SnapshotStore) -> None:
    assert not store.exists
    assert store.versions() == ()
    assert store.current() is None
    assert store.check().ok


def test_the_first_write_creates_the_ruled_directory_tree(store: SnapshotStore) -> None:
    store.write(snapshot_of(golden_vector_ir()))

    assert store.snapshots_dir.is_dir()
    assert store.reports_dir.is_dir()
    assert store.meta_path.is_file()


def test_a_version_label_that_would_write_outside_the_store_is_refused(
    store: SnapshotStore,
) -> None:
    """The path-safety floor, and the reason it exists: the label is used verbatim as a file
    base name, so an unchecked one is a write anywhere on the disk."""
    for escape in ("../../etc/passwd", "..", "a/b", "/absolute"):
        with pytest.raises(StoreError) as caught:
            store.snapshot_path(escape)
        assert caught.value.reason is StoreErrorReason.UNSAFE_VERSION


# ── Writing and reading ──────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("build", ALL_IRS.values(), ids=ALL_IRS.keys())
def test_a_stored_snapshot_reads_back_equal_to_what_was_written(
    store: SnapshotStore, build: Callable[[], WorkflowIR]
) -> None:
    snapshot = snapshot_of(build())

    path = store.write(snapshot)

    assert path == store.snapshot_path("1.0.0.0")
    assert store.read("1.0.0.0") == snapshot
    assert store.current() == snapshot


def test_the_index_records_the_version_its_digest_and_when_it_landed(
    store: SnapshotStore,
) -> None:
    store.write(snapshot_of(golden_vector_ir()))

    meta = store.read_meta()
    record = meta.record_for("1.0.0.0")

    assert meta.current == "1.0.0.0"
    assert record is not None
    assert record.graph_version == GOLDEN_VECTOR_DIGEST
    assert record.created_at == "2026-08-04T09:00:00Z"


def test_the_landing_time_defaults_to_the_extraction_time_and_can_be_given(
    store: SnapshotStore,
) -> None:
    """No clock is read anywhere in the store: a write is a function of its arguments, which
    is what makes "identical content, identical bytes" a property a test can hold it to."""
    store.write(snapshot_of(golden_vector_ir()), created_at="2026-08-04T12:00:00Z")

    record = store.read_meta().record_for("1.0.0.0")
    assert record is not None
    assert record.created_at == "2026-08-04T12:00:00Z"


def test_versions_come_back_oldest_first(store: SnapshotStore) -> None:
    store.write(snapshot_of(minimal_ir(), version="1.0.0.0"))
    store.write(snapshot_of(golden_vector_ir(), version="2.0.0.0"))
    store.write(snapshot_of(awkward_ir(), version="2.1.0.0"))

    assert store.versions() == ("1.0.0.0", "2.0.0.0", "2.1.0.0")
    assert store.holds("2.0.0.0")
    assert not store.holds("9.9.9.9")


def test_the_store_is_append_only(store: SnapshotStore) -> None:
    """A changed workflow gets a new version rather than a rewritten one. Whether an
    *unchanged* one is re-snapshot at all is SD-03's policy, not this layer's."""
    store.write(snapshot_of(golden_vector_ir()))

    with pytest.raises(StoreError) as caught:
        store.write(snapshot_of(awkward_ir()))

    assert caught.value.reason is StoreErrorReason.DUPLICATE_VERSION
    assert store.read("1.0.0.0").ir == golden_vector_ir()


def test_a_snapshot_that_disagrees_with_itself_is_never_stored(store: SnapshotStore) -> None:
    inconsistent = Snapshot(
        version="1.0.0.0",
        extracted_from=extracted_from(),
        graph_version=GOLDEN_VECTOR_DIGEST,
        ir=minimal_ir(),
    )

    with pytest.raises(StoreError) as caught:
        store.write(inconsistent)

    assert caught.value.reason is StoreErrorReason.DIGEST_MISMATCH
    assert not store.snapshot_path("1.0.0.0").exists()


def test_two_stores_of_the_same_snapshot_hold_identical_bytes(tmp_path: Path) -> None:
    """Acceptance 1 at the file level: the store adds no per-write variation of its own."""
    snapshot = snapshot_of(awkward_ir())
    first, second = SnapshotStore(tmp_path / "one"), SnapshotStore(tmp_path / "two")

    first.write(snapshot)
    second.write(snapshot)

    assert (
        first.snapshot_path("1.0.0.0").read_bytes() == second.snapshot_path("1.0.0.0").read_bytes()
    )
    assert first.meta_path.read_bytes() == second.meta_path.read_bytes()


# ── Corruption handling ──────────────────────────────────────────────────────────────────


def test_reading_a_version_the_store_does_not_hold_is_a_coded_refusal(
    store: SnapshotStore,
) -> None:
    with pytest.raises(StoreError) as caught:
        store.read("1.0.0.0")

    assert caught.value.reason is StoreErrorReason.SNAPSHOT_MISSING


def test_a_snapshot_file_that_is_not_a_snapshot_is_a_coded_refusal(
    store: SnapshotStore,
) -> None:
    store.write(snapshot_of(golden_vector_ir()))
    store.snapshot_path("1.0.0.0").write_text("not: [a snapshot\n")

    with pytest.raises(StoreError) as caught:
        store.read("1.0.0.0")

    assert caught.value.reason is StoreErrorReason.SNAPSHOT_UNREADABLE


def test_an_edited_ir_is_caught_by_the_digest_it_no_longer_matches(
    store: SnapshotStore,
) -> None:
    """The store's one detectable content corruption, and the check that finds it: IR-SPEC
    §6.1 step 9, recompute and string-compare. Editing the IR inside a snapshot file without
    touching its digest is exactly the tamper the §1.2 conformance operation is for."""
    store.write(snapshot_of(golden_vector_ir()))
    path = store.snapshot_path("1.0.0.0")
    path.write_text(path.read_text().replace("value: 10", "value: 99"))

    with pytest.raises(StoreError) as caught:
        store.read("1.0.0.0")

    assert caught.value.reason is StoreErrorReason.DIGEST_MISMATCH


def test_a_damaged_snapshot_can_still_be_loaded_to_look_at(store: SnapshotStore) -> None:
    """A reader that only refuses cannot answer "what is wrong with it?"."""
    store.write(snapshot_of(golden_vector_ir()))
    path = store.snapshot_path("1.0.0.0")
    path.write_text(path.read_text().replace("value: 10", "value: 99"))

    damaged = store.read("1.0.0.0", verify=False)

    assert not damaged.digest_matches()


def test_a_snapshot_under_the_wrong_file_name_is_a_coded_refusal(
    store: SnapshotStore,
) -> None:
    """A snapshot names itself; the file name and the document have to agree, or a lookup by
    version returns something that is not that version."""
    store.write(snapshot_of(golden_vector_ir()))
    misfiled = store.snapshots_dir / f"2.0.0.0{SNAPSHOT_SUFFIX}"
    misfiled.write_text(store.snapshot_path("1.0.0.0").read_text())

    with pytest.raises(StoreError) as caught:
        store.read("2.0.0.0")

    assert caught.value.reason is StoreErrorReason.VERSION_MISMATCH


def test_a_damaged_index_is_a_coded_refusal(store: SnapshotStore) -> None:
    store.write(snapshot_of(golden_vector_ir()))
    store.meta_path.write_text("store_version: '1.0'\ncurrent: 9.9.9.9\nhistory: []\n")

    with pytest.raises(StoreError) as caught:
        store.read_meta()

    assert caught.value.reason is StoreErrorReason.META_UNREADABLE


def test_nothing_is_repaired_on_the_way_past(store: SnapshotStore) -> None:
    """Corruption is reported, never edited away: the bytes on disk after a failed read are
    the bytes that were there before it."""
    store.write(snapshot_of(golden_vector_ir()))
    path = store.snapshot_path("1.0.0.0")
    damaged = path.read_text().replace("value: 10", "value: 99")
    path.write_text(damaged)

    with pytest.raises(StoreError):
        store.read("1.0.0.0")

    assert path.read_text() == damaged


def test_a_stored_ir_with_no_canonical_form_is_a_coded_refusal(store: SnapshotStore) -> None:
    """An IR that satisfies the §2 model but that IR-SPEC §6.1 step 5 refuses — here an
    integer outside the I-JSON exact range — has no digest to compare against, so the file is
    not a snapshot anything could have written."""
    store.write(snapshot_of(golden_vector_ir()))
    path = store.snapshot_path("1.0.0.0")
    path.write_text(path.read_text().replace("value: 10", f"value: {2**53}"))

    with pytest.raises(StoreError) as caught:
        store.read("1.0.0.0")

    assert caught.value.reason is StoreErrorReason.SNAPSHOT_UNREADABLE


def test_a_store_says_where_it_is(store: SnapshotStore) -> None:
    assert repr(store) == f"SnapshotStore({str(store.path)!r})"


# ── check() — the definition of "consistent" ─────────────────────────────────────────────


def test_a_healthy_store_checks_out_clean(store: SnapshotStore) -> None:
    store.write(snapshot_of(golden_vector_ir(), version="1.0.0.0"))
    store.write(snapshot_of(awkward_ir(), version="2.0.0.0"))

    report = store.check()

    assert report.ok
    assert report.problems == ()
    assert report.orphans == ()
    assert report.residue == ()


def test_a_store_directory_with_nothing_in_it_checks_out_clean(store: SnapshotStore) -> None:
    """The half-created store a killed ``gebra snapshot`` could leave: directories, no index,
    no snapshots. Nothing claims anything, so nothing is inconsistent."""
    store.path.mkdir(parents=True)

    report = store.check()

    assert report.ok
    assert report.orphans == ()


def test_check_reports_every_problem_rather_than_the_first(store: SnapshotStore) -> None:
    store.write(snapshot_of(golden_vector_ir(), version="1.0.0.0"))
    store.write(snapshot_of(awkward_ir(), version="2.0.0.0"))
    store.snapshot_path("1.0.0.0").unlink()
    store.snapshot_path("2.0.0.0").write_text("not: [a snapshot\n")

    report = store.check()

    assert not report.ok
    assert [problem.reason for problem in report.problems] == [
        StoreErrorReason.SNAPSHOT_MISSING,
        StoreErrorReason.SNAPSHOT_UNREADABLE,
    ]
    assert [problem.version for problem in report.problems] == ["1.0.0.0", "2.0.0.0"]


def test_check_catches_an_index_that_disagrees_with_the_snapshot_it_points_at(
    store: SnapshotStore,
) -> None:
    store.write(snapshot_of(golden_vector_ir()))
    store.meta_path.write_text(
        store.meta_path.read_text().replace(GOLDEN_VECTOR_DIGEST, "sha256:" + "0" * 64)
    )

    report = store.check()

    assert [problem.reason for problem in report.problems] == [StoreErrorReason.DIGEST_MISMATCH]


def test_check_reports_a_damaged_index_as_the_one_thing_wrong(store: SnapshotStore) -> None:
    store.write(snapshot_of(golden_vector_ir()))
    store.meta_path.write_text("store_version: '1.0'\ncurrent: 9.9.9.9\nhistory: []\n")

    report = store.check()

    assert [problem.reason for problem in report.problems] == [StoreErrorReason.META_UNREADABLE]


def test_leftover_temp_files_are_residue_rather_than_damage(store: SnapshotStore) -> None:
    """What a process killed outright leaves behind. A temp name is never the target of
    anything that reads, so a store carrying one still reads correctly."""
    store.write(snapshot_of(golden_vector_ir()))
    residue = store.snapshots_dir / ".1.0.0.0.yaml.xyz123.tmp"
    residue.write_text("half a doc")

    report = store.check()

    assert report.ok
    assert report.residue == (residue,)


# ── Acceptance 2 — an interrupted write leaves the store consistent ──────────────────────


def _fail_on_call(monkeypatch: pytest.MonkeyPatch, ordinal: int) -> None:
    """Make the ``ordinal``-th atomic write of the next ``write()`` die like a killed process."""
    calls = {"n": 0}

    def flaky(path: Any, text: str) -> None:
        calls["n"] += 1
        if calls["n"] == ordinal:
            raise OSError(5, "Input/output error")
        write_atomic(path, text)

    monkeypatch.setattr("gebra.store.store.write_atomic", flaky)


def test_an_interruption_before_the_snapshot_lands_changes_nothing(
    store: SnapshotStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    store.write(snapshot_of(golden_vector_ir(), version="1.0.0.0"))
    _fail_on_call(monkeypatch, 1)

    with pytest.raises(OSError):
        store.write(snapshot_of(awkward_ir(), version="2.0.0.0"))

    report = store.check()
    assert report.ok
    assert report.orphans == ()
    assert store.versions() == ("1.0.0.0",)
    assert not store.snapshot_path("2.0.0.0").exists()


def test_an_interruption_between_the_two_writes_leaves_an_orphan_not_a_broken_store(
    store: SnapshotStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The reason the two writes are ordered snapshot-first: the survivable outcome is a
    snapshot file no index row references, which every reader ignores. The reverse order
    would leave an index row pointing at a file that does not exist."""
    store.write(snapshot_of(golden_vector_ir(), version="1.0.0.0"))
    _fail_on_call(monkeypatch, 2)

    with pytest.raises(OSError):
        store.write(snapshot_of(awkward_ir(), version="2.0.0.0"))

    report = store.check()
    assert report.ok
    assert report.problems == ()
    assert report.orphans == (store.snapshot_path("2.0.0.0"),)
    assert store.versions() == ("1.0.0.0",)
    assert store.current() is not None
    assert store.current().version == "1.0.0.0"  # type: ignore[union-attr]


def test_re_running_the_interrupted_write_completes_it(
    store: SnapshotStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The repair is the retry — which is why :meth:`write` overwrites an orphan file while
    still refusing a version the index already holds."""
    store.write(snapshot_of(golden_vector_ir(), version="1.0.0.0"))
    _fail_on_call(monkeypatch, 2)
    with pytest.raises(OSError):
        store.write(snapshot_of(awkward_ir(), version="2.0.0.0"))
    monkeypatch.undo()

    store.write(snapshot_of(awkward_ir(), version="2.0.0.0"))

    report = store.check()
    assert report.ok
    assert report.orphans == ()
    assert store.versions() == ("1.0.0.0", "2.0.0.0")
    assert store.read("2.0.0.0").ir == awkward_ir()


def test_an_interrupted_first_ever_write_leaves_a_readable_empty_store(
    store: SnapshotStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fail_on_call(monkeypatch, 2)

    with pytest.raises(OSError):
        store.write(snapshot_of(golden_vector_ir()))

    report = store.check()
    assert report.ok
    assert store.versions() == ()
    assert store.current() is None
    assert report.orphans == (store.snapshot_path("1.0.0.0"),)


def test_an_interruption_never_leaves_a_half_written_document_readable(
    store: SnapshotStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The two halves of acceptance 2 composed: the per-file atomicity is ``os.replace``'s,
    the across-file one is the write order's, and what a reader sees after either kind of
    interruption is a whole document or none."""
    store.write(snapshot_of(golden_vector_ir(), version="1.0.0.0"))
    before = store.meta_path.read_bytes()
    _fail_on_call(monkeypatch, 2)

    with pytest.raises(OSError):
        store.write(snapshot_of(awkward_ir(), version="2.0.0.0"))

    assert store.meta_path.read_bytes() == before
    assert store.snapshot_path("2.0.0.0").read_text() == dump_snapshot(
        snapshot_of(awkward_ir(), version="2.0.0.0")
    )


# ── Acceptance 3 — the D-025 digest-collision test ───────────────────────────────────────


TERSE, VERBOSE = b"You are terse.", b"You are verbose."


def test_two_workflows_differing_only_in_prompt_text_differ_in_nothing_else() -> None:
    """The control: the two IRs used below are identical everywhere except the one slot, so a
    different digest can only have come through it."""
    terse, verbose = prompt_bearing_ir(TERSE), prompt_bearing_ir(VERBOSE)

    assert _annotations_without_digests(terse) == _annotations_without_digests(verbose)
    assert terse != verbose


def test_a_prompt_only_edit_moves_the_graph_version() -> None:
    """D-11 In-Scope 10 and IR-SPEC §6.6: "a prompt edit bumps ``graph_version`` exactly as a
    topology edit does" — because §6.4 puts ``prompt_digest`` inside the hash scope."""
    assert graph_version(prompt_bearing_ir(TERSE)) != graph_version(prompt_bearing_ir(VERBOSE))


def test_a_config_only_edit_moves_the_graph_version() -> None:
    assert graph_version(prompt_bearing_ir(TERSE, config=b"temperature=0")) != graph_version(
        prompt_bearing_ir(TERSE, config=b"temperature=1")
    )


def test_without_the_digest_slots_the_same_two_workflows_collide() -> None:
    """The gap D-025 closes, shown rather than asserted: node bodies are opaque to the IR, so
    with the §3.6 slots empty these two versions *are* the same document — same canonical
    bytes, same digest, and a store that could not tell them apart."""
    assert graph_version(bodiless_ir()) == graph_version(bodiless_ir())
    assert _annotations_without_digests(prompt_bearing_ir(TERSE)) == _annotations_without_digests(
        bodiless_ir()
    )


def test_a_prompt_edit_lands_as_a_distinct_snapshot(store: SnapshotStore) -> None:
    """The card's acceptance, end to end: two versions, two files, two index rows, two
    digests — and each reads back as the workflow it was."""
    terse = snapshot_of(prompt_bearing_ir(TERSE), version="1.0.0.0")
    verbose = snapshot_of(prompt_bearing_ir(VERBOSE), version="1.0.1.0")

    store.write(terse)
    store.write(verbose)

    assert terse.graph_version != verbose.graph_version
    assert (
        store.snapshot_path("1.0.0.0").read_bytes() != store.snapshot_path("1.0.1.0").read_bytes()
    )
    assert store.read("1.0.0.0") == terse
    assert store.read("1.0.1.0") == verbose
    digests = {record.graph_version for record in store.read_meta().history}
    assert len(digests) == 2
    assert store.check().ok


def test_the_prompt_body_itself_never_reaches_the_store(store: SnapshotStore) -> None:
    """Layered hashing (DEC-10): "bodies never enter the IR; only fingerprints do". A
    snapshot is safe to commit — it carries the digest and not the prompt."""
    store.write(snapshot_of(prompt_bearing_ir(TERSE)))

    written = store.snapshot_path("1.0.0.0").read_bytes()

    assert TERSE not in written
    assert b"prompt_digest: sha256:" in written


def test_the_envelope_is_outside_the_hash_scope(store: SnapshotStore) -> None:
    """IR-SPEC §6.4, holding by construction rather than by rule: the digest is computed from
    the ``ir`` member, so no provenance field can reach it."""
    here = snapshot_of(golden_vector_ir(), version="1.0.0.0")
    elsewhere = snapshot_of(
        golden_vector_ir(),
        version="9.9.9.9",
        source="somewhere-else",
        extracted_at="2027-01-01T00:00:00Z",
        sidecar_path="/other/gebra.toml",
    )

    assert here.graph_version == elsewhere.graph_version == GOLDEN_VECTOR_DIGEST
    assert here.extracted_from != elsewhere.extracted_from


# ── WA-07: the store reaches no substrate and no network ─────────────────────────────────


_TRIPWIRE = """\
import socket, sys, tempfile
attempts = []


class _TripSocket(socket.socket):
    def __new__(cls, *a, **k):
        attempts.append("socket")
        print("WA07-TRIP", file=sys.stderr)
        raise AssertionError("a socket was created by the store")


def _trip_dns(*a, **k):
    attempts.append("getaddrinfo")
    print("WA07-TRIP", file=sys.stderr)
    raise AssertionError("a name was resolved by the store")


socket.socket = _TripSocket
socket.getaddrinfo = _trip_dns

from gebra.store import SnapshotStore
from tests.store.hand_built import ALL_IRS, snapshot_of

with tempfile.TemporaryDirectory() as room:
    store = SnapshotStore.for_project(room)
    for index, (name, build) in enumerate(sorted(ALL_IRS.items())):
        snapshot = snapshot_of(build(), version="1.0.0.%d" % index)
        store.write(snapshot)
        assert store.read(snapshot.version) == snapshot, name
    assert store.check().ok
"""

_REPORT = """
print([m for m in sys.modules
       if m.split(".")[0] in {"langgraph", "langchain", "langchain_core", "networkx"}]
      + attempts)
"""


def _run_guarded(probe: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", _TRIPWIRE + probe + _REPORT],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_writing_and_reading_the_whole_store_reaches_no_substrate_and_no_socket() -> None:
    """WA-07 for this card's path. The store takes an IR *model*, so there is no user object
    in reach to invoke; what is checkable is the rest of the invariant — that the whole
    write-and-read cycle imports no substrate and opens no connection."""
    completed = _run_guarded()

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "[]", completed.stdout
    assert "WA07-TRIP" not in completed.stderr, completed.stderr


def test_the_guard_trips_when_something_does_reach_the_substrate() -> None:
    """The armed negative control: a green tripwire is only evidence if it can go red."""
    completed = _run_guarded("import langchain_core\nsocket.getaddrinfo('localhost', 80)\n")

    assert completed.returncode != 0
    assert "WA07-TRIP" in completed.stderr
