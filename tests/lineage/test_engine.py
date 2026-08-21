"""The card's first acceptance criterion, plus the windowing and totality it rests on.

**Box 1 — "lineage over a multi-version store returns complete ordered history with
digests".** ``tests/lineage/stores.py`` builds that store: one workflow through five versions,
each label derived by :func:`~gebra.diff.workflow_diff` rather than written down. The tests
below hold the listing to *complete* (every row the store holds, and the totals say so even
when a window does not show them), *ordered* (the store's own append order, oldest first) and
*with digests* — checked against the digest of the stage's IR, not against the listing's own
output.

Three further claims live here because a listing that lacked any of them would not be one:

* **it opens one file.** ``lineage()`` reads ``meta.yaml`` and never a snapshot, which is
  observable by deleting every snapshot file and still getting a complete history;
* **a window never lies about the whole.** ``total``, ``omitted_before``, ``omitted_after``
  and every absolute ``index`` ride along, a page's first row still reports its true
  predecessor, and a :class:`~gebra.lineage.models.Lineage` that does not add up cannot be
  constructed;
* **it is total over what the store accepts.** The store's floor on a label is path-safety,
  not SD-02's grammar, and nothing forbids a history that counts down or repeats a digest.
  ``awkward_store`` holds all three and still lists.

The second acceptance criterion — stable, golden-testable output — is
``tests/lineage/test_document.py``.

Everything is hand-built IR models (WA-07): no extractor, no substrate, nothing to invoke.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from gebra.diff import WorkflowDiff
from gebra.ir.canonical import graph_version
from gebra.lineage import (
    Lineage,
    LineageEntry,
    LineageError,
    LineageErrorReason,
    LineageStep,
    compare,
    lineage,
)
from gebra.store import META_FILENAME, SnapshotStore, StoreError, StoreErrorReason
from gebra.versioning import Component, Version
from tests.lineage.stores import LANDED, STAGES, awkward_store, evolved_labels, evolved_store

REPO_ROOT = Path(__file__).resolve().parents[2]

S, F, E = Component.S, Component.F, Component.E


@pytest.fixture
def evolved(tmp_path: Path) -> SnapshotStore:
    """The five-version store the card's first criterion is about."""
    return evolved_store(tmp_path)


@pytest.fixture
def awkward(tmp_path: Path) -> SnapshotStore:
    """A history the engines would not write and the store does not forbid."""
    return awkward_store(tmp_path)


# ── Box 1: complete, ordered, with digests ───────────────────────────────────────────────


def test_lineage_lists_every_version_the_store_holds_oldest_first(evolved: SnapshotStore) -> None:
    history = lineage(evolved)

    assert history.versions == evolved_labels()
    assert history.versions == evolved.versions()  # the store's own order, not a re-sort
    assert history.total == len(STAGES) == 5
    assert not history.truncated
    assert [entry.index for entry in history] == [0, 1, 2, 3, 4]


def test_every_row_carries_the_digest_of_the_workflow_it_stores(evolved: SnapshotStore) -> None:
    """ "With digests", checked against the content rather than against the listing itself."""
    for entry, stage in zip(lineage(evolved), STAGES, strict=True):
        assert entry.graph_version == graph_version(stage.build())


def test_every_row_carries_when_it_landed_and_which_one_is_current(
    evolved: SnapshotStore,
) -> None:
    history = lineage(evolved)

    assert tuple(entry.created_at for entry in history) == LANDED
    assert [entry.is_current for entry in history] == [False, False, False, False, True]
    assert history.current == evolved_labels()[-1]
    assert history.current_entry is history.newest


def test_the_oldest_version_has_no_step_and_every_other_one_does(evolved: SnapshotStore) -> None:
    """``step is None`` means exactly one thing: nothing precedes this version."""
    entries = lineage(evolved).entries

    assert entries[0].step is None
    assert all(entry.step is not None for entry in entries[1:])
    assert [entry.step.previous for entry in entries[1:] if entry.step] == list(
        evolved_labels()[:-1]
    )


def test_every_pair_reports_the_bump_class_its_two_labels_record(evolved: SnapshotStore) -> None:
    """The per-pair bump classes the card asks for, on the five-version store.

    The expected column is the evolution's own shape: an audit node added and wired moves
    topology and a contract, an effect-class escalation moves a contract, a new optional Σ key
    moves the state schema, and widening the finish wiring moves topology.
    """
    expected = [(S, F), (F,), (E,), (S,)]

    steps = [entry.step for entry in lineage(evolved).entries[1:]]

    assert [step.bump_class for step in steps if step] == expected
    assert all(step.decreased == () for step in steps if step)
    assert all(step.content_changed for step in steps if step)
    assert all(step.forward and step.comparable for step in steps if step)


def test_the_labels_agree_with_the_diff_engine_on_every_pair(evolved: SnapshotStore) -> None:
    """The label-derived step and the content-derived one are two answers to two questions —
    on a store whose labels *were* derived from the content, they have to coincide, and that
    is the check that keeps this fixture honest."""
    for entry in lineage(evolved).entries[1:]:
        assert entry.step is not None
        content = compare(evolved, entry.step.previous, entry.version)
        assert frozenset(entry.step.bump_class or ()) == content.bump_class
        assert content.has_changes is entry.step.content_changed


def test_a_store_that_was_never_written_lists_as_an_empty_lineage(tmp_path: Path) -> None:
    history = lineage(SnapshotStore.for_project(tmp_path))

    assert history == Lineage()
    assert (history.total, len(history), history.current) == (0, 0, None)
    assert (history.oldest, history.newest, history.current_entry) == (None, None, None)


def test_an_initialized_but_empty_store_lists_as_an_empty_lineage(tmp_path: Path) -> None:
    store = SnapshotStore.for_project(tmp_path)
    store.initialize()

    assert lineage(store) == Lineage()


# ── One read: a listing never opens a snapshot ───────────────────────────────────────────


def test_a_listing_opens_no_snapshot_file(evolved: SnapshotStore) -> None:
    """The claim is a filesystem one, so it is observable by removing what it must not read.

    With every snapshot file gone the store is *not* healthy — ``check()`` says so — and the
    listing is still complete, because everything a listing reports is in the index."""
    for path in evolved.snapshots_dir.iterdir():
        path.unlink()

    history = lineage(evolved)

    assert history.versions == evolved_labels()
    assert all(entry.graph_version.startswith("sha256:") for entry in history)
    assert not evolved.check().ok  # what a listing deliberately does not check for you


def test_what_a_listing_reports_is_what_the_index_records(evolved: SnapshotStore) -> None:
    """A snapshot edited out from under its index row does not change the listing — detecting
    that is ``check()``'s job, and a listing that silently re-derived the digest would be
    reporting on data it had also just recomputed."""
    newest = evolved.snapshot_path(evolved_labels()[-1])
    newest.write_text(newest.read_text(encoding="utf-8").replace("audit", "auditor"), "utf-8")

    assert lineage(evolved).newest == LineageEntry(
        index=4,
        version="1.2.2.1",
        graph_version=graph_version(STAGES[-1].build()),
        created_at=LANDED[-1],
        is_current=True,
        step=LineageStep(previous="1.1.2.1", content_changed=True, bump_class=(S,), decreased=()),
    )
    assert [problem.reason for problem in evolved.check().problems] == [
        StoreErrorReason.DIGEST_MISMATCH
    ]


# ── Ordering and pagination ──────────────────────────────────────────────────────────────


def test_since_and_until_are_inclusive_version_anchors(evolved: SnapshotStore) -> None:
    labels = evolved_labels()

    assert lineage(evolved, since=labels[1]).versions == labels[1:]
    assert lineage(evolved, until=labels[2]).versions == labels[:3]
    assert lineage(evolved, since=labels[1], until=labels[3]).versions == labels[1:4]
    assert lineage(evolved, since=labels[2], until=labels[2]).versions == (labels[2],)


def test_limit_keeps_the_most_recent_rows(evolved: SnapshotStore) -> None:
    """``git log -n`` semantics: a log grows at one end, so truncation drops the other."""
    labels = evolved_labels()

    assert lineage(evolved, limit=2).versions == labels[-2:]
    assert lineage(evolved, limit=len(labels)).versions == labels
    assert lineage(evolved, limit=99).versions == labels
    assert lineage(evolved, limit=0).versions == ()


def test_limit_counts_within_the_window_the_anchors_select(evolved: SnapshotStore) -> None:
    labels = evolved_labels()

    assert lineage(evolved, until=labels[3], limit=2).versions == labels[2:4]
    assert lineage(evolved, since=labels[1], limit=99).versions == labels[1:]


def test_a_window_accounts_for_the_whole_history(evolved: SnapshotStore) -> None:
    window = lineage(evolved, since=evolved_labels()[1], until=evolved_labels()[3], limit=2)

    assert window.versions == evolved_labels()[2:4]
    assert (window.total, window.omitted_before, window.omitted_after) == (5, 2, 1)
    assert window.omitted_before + len(window) + window.omitted_after == window.total
    assert [entry.index for entry in window] == [2, 3]
    assert window.truncated


def test_an_empty_window_still_accounts_for_the_whole_history(evolved: SnapshotStore) -> None:
    window = lineage(evolved, limit=0)

    assert (len(window), window.total) == (0, 5)
    assert (window.omitted_before, window.omitted_after) == (5, 0)
    assert window.truncated


def test_a_windows_first_row_reports_its_predecessor_in_the_store(evolved: SnapshotStore) -> None:
    """A page's first row is not a store's first row, and its step says so — the bump class of
    a pair is a fact about the store, not about which rows a caller asked to see."""
    first = lineage(evolved, limit=2).oldest

    assert first is not None and first.step is not None
    assert first.step.previous == evolved_labels()[2]
    assert first.step == lineage(evolved).entries[3].step


def test_the_current_pointer_can_sit_outside_a_window(evolved: SnapshotStore) -> None:
    window = lineage(evolved, limit=2)
    earlier = lineage(evolved, until=evolved_labels()[0])

    assert window.current_entry is not None and window.current_entry.is_current
    assert earlier.current == evolved_labels()[-1]  # still reported…
    assert earlier.current_entry is None  # …and honestly absent from the page
    assert all(not entry.is_current for entry in earlier)


def test_the_order_is_the_stores_own_and_a_reversal_is_the_callers(evolved: SnapshotStore) -> None:
    """There is one order and no option for another: a newest-first display is
    ``reversed(...)`` where display decisions live (D-11 In-Scope 3 → brief D-12)."""
    history = lineage(evolved)

    assert [entry.version for entry in reversed(history.entries)] == list(evolved_labels()[::-1])
    assert not any("order" in name or "reverse" in name for name in dir(history))


# ── Refusals ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("anchor", ["since", "until"])
def test_an_anchor_the_store_does_not_hold_is_a_coded_refusal(
    evolved: SnapshotStore, anchor: str
) -> None:
    anchors: dict[str, str] = {anchor: "9.9.9.9"}

    with pytest.raises(LineageError) as caught:
        lineage(evolved, since=anchors.get("since"), until=anchors.get("until"))

    assert caught.value.reason is LineageErrorReason.UNKNOWN_VERSION
    assert caught.value.value == "9.9.9.9"
    assert anchor in str(caught.value)


def test_an_anchor_on_an_empty_store_says_the_store_is_empty(tmp_path: Path) -> None:
    with pytest.raises(LineageError) as caught:
        lineage(SnapshotStore.for_project(tmp_path), since="1.0.0.0")

    assert caught.value.reason is LineageErrorReason.UNKNOWN_VERSION
    assert "the store is empty" in str(caught.value)


def test_a_window_that_cannot_contain_a_row_is_a_coded_refusal(evolved: SnapshotStore) -> None:
    labels = evolved_labels()

    with pytest.raises(LineageError) as caught:
        lineage(evolved, since=labels[3], until=labels[1])

    assert caught.value.reason is LineageErrorReason.INVALID_WINDOW
    assert caught.value.value == f"{labels[3]}..{labels[1]}"


def test_a_negative_limit_is_a_coded_refusal(evolved: SnapshotStore) -> None:
    with pytest.raises(LineageError) as caught:
        lineage(evolved, limit=-1)

    assert caught.value.reason is LineageErrorReason.NEGATIVE_LIMIT
    assert caught.value.value == "-1"


def test_a_bad_query_is_not_a_damaged_store(evolved: SnapshotStore) -> None:
    """Two different faults keep two different types: nothing is wrong with a store whose
    history simply does not hold the version a caller named."""
    with pytest.raises(LineageError) as caught:
        lineage(evolved, since="9.9.9.9")

    assert not issubclass(LineageError, StoreError)
    assert isinstance(caught.value, ValueError)
    assert evolved.check().ok


def test_a_damaged_index_stays_the_stores_own_refusal(evolved: SnapshotStore) -> None:
    (evolved.path / META_FILENAME).write_text("current: [not, an, index]\n", encoding="utf-8")

    with pytest.raises(StoreError) as caught:
        lineage(evolved)

    assert caught.value.reason is StoreErrorReason.META_UNREADABLE


# ── Total over what the store accepts ────────────────────────────────────────────────────


def test_a_label_that_is_not_a_version_still_lists(awkward: SnapshotStore) -> None:
    """PD-012 makes the label a file name; SD-02's grammar is narrower and the store neither
    imposes nor parses it. A listing that raised here could not list a legal store."""
    history = lineage(awkward)

    assert history.versions == ("1.2.0.0", "1.1.0.0", "draft", "2.0.0.0", "3.0.0.0")
    unparsed = [entry for entry in history if entry.step and not entry.step.comparable]
    assert [entry.version for entry in unparsed] == ["draft", "2.0.0.0"]
    for entry in unparsed:
        assert entry.step is not None
        assert entry.step.bump_class is None and entry.step.decreased is None
        assert entry.step.forward is None


def test_a_step_that_counts_down_is_reported_as_one(awkward: SnapshotStore) -> None:
    """Reporting only what rose would show a backwards step as an empty bump class —
    indistinguishable from a version that changed nothing."""
    step = lineage(awkward).entries[1].step

    assert step is not None
    assert step.bump_class == ()
    assert step.decreased == (S,)
    assert step.comparable and step.forward is False


def test_two_versions_holding_one_content_report_an_unchanged_digest(
    awkward: SnapshotStore,
) -> None:
    entries = lineage(awkward).entries

    assert entries[1].graph_version == entries[2].graph_version
    assert entries[2].step is not None and not entries[2].step.content_changed
    assert entries[3].step is not None and entries[3].step.content_changed


def test_the_labels_and_the_content_can_disagree_and_both_are_reported(
    awkward: SnapshotStore,
) -> None:
    """The two questions the module docstring separates, on the store where they part ways."""
    step = lineage(awkward).entries[1].step
    content = compare(awkward, "1.2.0.0", "1.1.0.0")

    assert step is not None
    assert step.bump_class == ()  # the labels record no bump — S went down
    assert content.bump_class == frozenset({S})  # the content moved all the same
    assert step.content_changed is content.has_changes is True


def test_a_v_step_is_reported_and_is_not_a_disagreement_with_the_content(
    awkward: SnapshotStore,
) -> None:
    """The one component the two answers cannot be compared over.

    A label step ranges over all four components, because a caller may write ``3.0.0.0`` after
    ``2.0.0.0`` and a version history that dropped the V would be hiding a version change. A
    content diff never reports V — the frozen package defines S, F and E and says nothing about
    what V counts (``Component.derived()``), so no diff can produce one. The two therefore
    agree only over the derived three, which is the comparison this suite makes everywhere."""
    step = lineage(awkward).entries[4].step
    content = compare(awkward, "2.0.0.0", "3.0.0.0")

    assert step is not None
    assert step.bump_class == (Component.V,) and step.forward
    assert Component.V not in Component.derived()
    assert Component.V not in content.bump_class
    # Over the derived three the two do differ on this pair — and that difference is about S,
    # never about the V, which no content diff could have reported either way.
    assert frozenset(step.bump_class) & frozenset(Component.derived()) == frozenset()
    assert content.bump_class == frozenset({S})


# ── The window invariants are enforced, not conventional ─────────────────────────────────


def test_a_window_that_under_reports_the_store_cannot_be_constructed() -> None:
    row = LineageEntry(
        index=0,
        version="1.0.0.0",
        graph_version="sha256:" + "0" * 64,
        created_at="2026-08-04T09:00:00Z",
    )

    with pytest.raises(ValueError, match="account for the whole history"):
        Lineage(entries=(row,), total=9)


def test_a_row_carrying_the_wrong_absolute_index_cannot_be_constructed() -> None:
    row = LineageEntry(
        index=7,
        version="1.0.0.0",
        graph_version="sha256:" + "0" * 64,
        created_at="2026-08-04T09:00:00Z",
    )

    with pytest.raises(ValueError, match="absolute place"):
        Lineage(entries=(row,), total=1)


# ── compare(): the content answer ────────────────────────────────────────────────────────


def test_comparing_two_stored_versions_returns_the_structural_diff(
    evolved: SnapshotStore,
) -> None:
    labels = evolved_labels()

    diff = compare(evolved, labels[0], labels[1])

    assert isinstance(diff, WorkflowDiff)
    assert (diff.before.version, diff.after.version) == (labels[0], labels[1])
    assert diff.topology.nodes.added == ("audit",)
    assert diff.bump_class == frozenset({S, F})


def test_comparing_across_the_whole_history_covers_every_step_it_spans(
    evolved: SnapshotStore,
) -> None:
    """A diff names domains, not a count of edits, so an end-to-end comparison selects exactly
    the union of the steps between — while the *labels* have counted each edit on the way."""
    labels = evolved_labels()
    steps = frozenset(
        component
        for entry in lineage(evolved).entries[1:]
        for component in (entry.step.bump_class or () if entry.step else ())
    )

    whole = compare(evolved, labels[0], labels[-1])

    assert whole.bump_class == steps == frozenset({S, F, E})
    assert str(whole.bump(Version.initial())) == "1.1.1.1"
    assert labels[-1] == "1.2.2.1"  # four recorded edits, three domains


def test_comparing_a_version_the_store_does_not_hold_is_the_stores_refusal(
    evolved: SnapshotStore,
) -> None:
    with pytest.raises(StoreError) as caught:
        compare(evolved, evolved_labels()[0], "9.9.9.9")

    assert caught.value.reason is StoreErrorReason.SNAPSHOT_MISSING


def test_a_comparison_grades_nothing(evolved: SnapshotStore) -> None:
    """P-12 ``evolution-safety`` is deferred (SOW §8; PD-006 R4). What comes back out of this
    package is the diff engine's own marker, in the slot a classification would occupy — the
    exhaustive no-safe/breaking-wording sweep is ``tests/diff/test_workflow.py``'s."""
    labels = evolved_labels()

    diff = compare(evolved, labels[0], labels[-1])

    assert diff.evolution_safety.status == "deferred-to-phase-1"
    assert diff.evolution_safety.property == "evolution-safety"


# ── The engine API brief D-11 In-Scope 3 owes brief D-12 ─────────────────────────────────


def test_the_public_shapes_stay_importable_from_the_package_root(evolved: SnapshotStore) -> None:
    import gebra.lineage as package

    for name in ("lineage", "compare", "Lineage", "LineageEntry", "LineageStep", "LineageError"):
        assert name in package.__all__ and hasattr(package, name)
    assert isinstance(lineage(evolved), Lineage)
    assert set(package.__all__) <= set(dir(package))


# ── WA-07: listing and comparing reach no substrate and no network ───────────────────────

_TRIPWIRE = """\
import socket, sys
attempts = []


class _TripSocket(socket.socket):
    def __new__(cls, *a, **k):
        attempts.append("socket")
        print("WA07-TRIP", file=sys.stderr)
        raise AssertionError("a socket was created by the lineage engine")


def _trip_dns(*a, **k):
    attempts.append("getaddrinfo")
    print("WA07-TRIP", file=sys.stderr)
    raise AssertionError("a name was resolved by the lineage engine")


socket.socket = _TripSocket
socket.getaddrinfo = _trip_dns

import tempfile
from pathlib import Path

from gebra.lineage import compare, dump_lineage, lineage, lineage_document
from tests.lineage.stores import awkward_store, evolved_labels, evolved_store

with tempfile.TemporaryDirectory() as root:
    labels = evolved_labels()
    store = evolved_store(Path(root) / "evolved")
    awkward = awkward_store(Path(root) / "awkward")

    history = lineage(store)
    assert history.versions == labels
    assert dump_lineage(lineage(store, since=labels[1], limit=2))
    assert lineage(store, limit=0).total == len(labels)
    assert lineage_document(history)["total"] == len(labels)   # the projection, called directly
    assert dump_lineage(lineage(awkward))

    # Every neighbouring pair of both stores, so no compare() arm sits outside the guard.
    for target in (store, awkward):
        for entry in lineage(target).entries[1:]:
            diff = compare(target, entry.step.previous, entry.version)
            assert diff.evolution_safety.status == "deferred-to-phase-1"

    # And the label/content agreement, on the store whose labels were content-derived.
    for entry in history.entries[1:]:
        diff = compare(store, entry.step.previous, entry.version)
        assert frozenset(entry.step.bump_class) == diff.bump_class
    assert compare(awkward, "1.1.0.0", "draft").identical

assert "networkx" in sys.modules  # in reach through gebra.diff, exactly as that package states
"""

_REPORT = """
print([m for m in sys.modules
       if m.split(".")[0] in {"langgraph", "langchain", "langchain_core"}]
      + attempts)
"""


def _run_guarded(probe: str = "") -> subprocess.CompletedProcess[str]:
    # ``PYTHONOPTIMIZE`` is pinned off because the child states half its claim in ``assert``
    # statements — the ``networkx`` reach among them — and an inherited ``-O`` would delete
    # them while leaving the run green.
    return subprocess.run(
        [sys.executable, "-c", _TRIPWIRE + probe + _REPORT],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "PYTHONOPTIMIZE": "0"},
    )


def test_listing_and_comparing_a_store_reaches_no_substrate_and_no_socket() -> None:
    """WA-07 for this card's paths. The engine's inputs are a store directory and IR models,
    so there is no user object in reach to invoke; what is checkable is the rest of the
    invariant — building, listing, windowing, dumping and comparing two whole stores imports
    no substrate and opens no connection. networkx is deliberately not on the refusal list and
    the child asserts it *is* imported: ``compare()`` goes through :mod:`gebra.diff`, whose
    graph representation brief D-11 mandates, so the allowance is stated rather than
    smuggled."""
    completed = _run_guarded()

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "[]", completed.stdout
    assert "WA07-TRIP" not in completed.stderr, completed.stderr


def test_the_guard_trips_when_something_does_reach_the_network() -> None:
    """The armed negative control for the socket half: a green tripwire is only evidence if it
    can go red."""
    completed = _run_guarded("socket.getaddrinfo('localhost', 80)\n")

    assert completed.returncode != 0
    assert "WA07-TRIP" in completed.stderr


def test_the_guard_trips_when_something_does_reach_the_substrate() -> None:
    """The armed negative control for the ``sys.modules`` half, which no socket probe can arm:
    a substrate import opens no connection, so only the sweep in ``_REPORT`` catches it, and
    its green reading is ``stdout == "[]"``."""
    completed = _run_guarded("import langchain_core\n")

    assert completed.returncode == 0, completed.stderr
    assert "WA07-TRIP" not in completed.stderr
    assert completed.stdout.strip() != "[]"
    assert "langchain_core" in completed.stdout
