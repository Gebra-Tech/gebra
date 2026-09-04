"""The snapshot-freshness engine — three states, one comparison, and no writes.

The gate half of SD-07's second acceptance box (a pytest session going red on a changed agent)
is ``tests/audit/test_freshness_gate.py``'s; this file is the engine underneath it, stated over
hand-built IR models so that every case — including the ones a live agent cannot easily be made
to produce, like a store whose current label is not a V.S.F.E label — is reachable (WA-07: no
extractor, no substrate, nothing to invoke).

The comparison the engine makes is deliberately the recorder's: the working IR's digest against
:meth:`~gebra.store.store.SnapshotStore.current`, which is what :func:`gebra.snapshot.snapshot`
compares before deciding whether to write. That the two really do agree is asserted where the
recorder is in reach — ``tests/audit/test_travel_booking.py``, over live extractions — because
a check that disagreed with the recorder would be a CI failure with no remedy. What this file
states about it is the half that needs no extractor: the comparison is against ``current``, and
``current`` is not required to be the store's newest row.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from gebra.audit import Freshness, FreshnessOutcome, freshness
from gebra.diff import workflow_diff
from gebra.ir.canonical import graph_version
from gebra.store import Snapshot, SnapshotStore, StoreError, dump_meta
from gebra.versioning import Component
from tests.lineage.stores import STAGES, evolved_labels, evolved_store, provenance
from tests.versioning.workflows import NODES, with_repeated_node_id, workflow

if TYPE_CHECKING:
    from gebra.ir import WorkflowIR

#: The repository root, for the guarded child at the bottom of this file.
REPO_ROOT = Path(__file__).resolve().parents[2]


def _store_with(root: Path, ir: WorkflowIR, *, version: str = "1.0.0.0") -> SnapshotStore:
    """A one-version store holding ``ir`` — the ordinary "already snapshotted" starting point."""
    store = SnapshotStore.for_project(root)
    store.write(
        Snapshot.of(
            ir,
            version=version,
            extracted_from=provenance("tests.audit.test_freshness", "2026-08-12T09:00:00Z"),
        )
    )
    return store


# ── The three states ─────────────────────────────────────────────────────────────────────


def test_a_store_holding_this_definition_is_fresh(tmp_path: Path) -> None:
    ir = workflow()
    store = _store_with(tmp_path, ir)

    outcome = freshness(ir, store=store)

    assert outcome.state is Freshness.FRESH
    assert outcome.fresh
    assert outcome.version == "1.0.0.0"
    assert outcome.graph_version == graph_version(ir) == outcome.snapshot_graph_version
    assert outcome.diff is None
    assert outcome.moved == ()
    assert outcome.store == store.path


def test_a_definition_that_moved_since_the_snapshot_is_stale(tmp_path: Path) -> None:
    """The case the CI check exists for: the agent changed and nobody re-snapshotted.

    The diff rides the outcome so a message can say *which* counters moved without the caller
    reading the store a second time — here S and F, an added node wired in, which is the
    first step of the shared evolution fixture.
    """
    before, after = STAGES[0].build(), STAGES[1].build()
    store = _store_with(tmp_path, before)

    outcome = freshness(after, store=store)

    assert outcome.state is Freshness.STALE
    assert not outcome.fresh
    assert outcome.snapshot_graph_version == graph_version(before)
    assert outcome.graph_version == graph_version(after)
    assert outcome.diff is not None
    assert outcome.moved == (Component.S, Component.F)
    assert outcome.diff.topology.nodes.added == ("audit",)


def test_a_store_that_holds_nothing_is_not_stale(tmp_path: Path) -> None:
    """Three states rather than two: nothing changed, nothing was ever recorded, and telling a
    first-time user their definition had drifted would be false."""
    store = SnapshotStore.for_project(tmp_path)

    outcome = freshness(workflow(), store=store)

    assert outcome.state is Freshness.UNSNAPSHOTTED
    assert not outcome.fresh
    assert outcome.version is None
    assert outcome.snapshot_graph_version is None
    assert outcome.diff is None
    assert "no snapshot" in outcome.summary()


def test_a_store_directory_that_does_not_exist_reads_as_an_empty_one(tmp_path: Path) -> None:
    store = SnapshotStore(tmp_path / "nowhere" / ".gebra")

    assert freshness(workflow(), store=store).state is Freshness.UNSNAPSHOTTED
    assert not store.path.exists()


# ── The comparison is the recorder's ─────────────────────────────────────────────────────


def test_the_comparison_is_against_current_not_the_newest_row(tmp_path: Path) -> None:
    """SD-01's ruling leaves ``current`` free of "must be the last row", and the recorder
    compares against ``current``. So does this — stated by a store whose pointer is deliberately
    not its newest version, where the two readings give different answers.

    (That the check and the recorder agree on a *live* agent is
    ``tests/audit/test_travel_booking.py``'s, where the recorder is in reach.)
    """
    labels = evolved_labels()
    store = evolved_store(tmp_path / "evolved")
    repointed = store.read_meta().model_copy(update={"current": labels[0]})
    store.meta_path.write_text(dump_meta(repointed), encoding="utf-8")

    assert store.read_meta().current == labels[0]
    assert freshness(STAGES[0].build(), store=store).fresh
    assert not freshness(STAGES[-1].build(), store=store).fresh


def test_a_current_label_outside_the_vsfe_grammar_still_checks(tmp_path: Path) -> None:
    """PD-012 makes the label a file name and SD-01's floor is path safety, not the grammar, so
    a store can hold ``draft``. Freshness never parses a label — it compares digests — so such a
    store answers normally rather than raising, which a check that bumped would not."""
    store = _store_with(tmp_path, STAGES[0].build(), version="draft")
    assert store.read_meta().current == "draft"

    fresh = freshness(STAGES[0].build(), store=store)
    stale = freshness(STAGES[1].build(), store=store)

    assert fresh.fresh
    assert fresh.version == "draft"
    assert stale.state is Freshness.STALE
    assert stale.moved == (Component.S, Component.F)


# ── Refusals ─────────────────────────────────────────────────────────────────────────────


def test_a_document_repeating_a_node_id_is_refused_before_the_store_is_read(
    tmp_path: Path,
) -> None:
    """IR-SPEC §2.1 (DEC-22): such a document has no identity to anchor on, so it is refused on
    the same terms and in the same order :func:`gebra.snapshot.snapshot` refuses it — before the
    store is looked at, so an empty store does not answer ``unsnapshotted`` for it.

    The model refuses one at validation since card IR-07, so nothing *loaded* reaches here;
    the document is built past validation with ``model_copy`` to reach this floor, which is
    the only way left to hold it."""
    duplicated = with_repeated_node_id(workflow(), NODES[0].id)
    store = SnapshotStore.for_project(tmp_path)

    with pytest.raises(ValueError, match="unique"):
        freshness(duplicated, store=store)


def test_a_damaged_store_is_a_fault_and_not_a_freshness_verdict(tmp_path: Path) -> None:
    """Reading a corrupt store as "stale" would ask a user to re-snapshot their way out of a
    damaged file. The store's own coded refusal comes through instead."""
    store = _store_with(tmp_path, workflow())
    store.meta_path.write_text("current: [not, a, label]\n", encoding="utf-8")

    with pytest.raises(StoreError) as caught:
        freshness(workflow(), store=store)

    assert caught.value.reason.value == "meta-unreadable"


def test_the_check_writes_nothing(tmp_path: Path) -> None:
    """A freshness check that recorded the snapshot it was missing would be a gate that always
    passes, and the artifact it wrote would be one nobody reviewed."""
    store = _store_with(tmp_path, STAGES[0].build())
    before = {path: path.read_bytes() for path in sorted(store.path.rglob("*")) if path.is_file()}

    freshness(STAGES[1].build(), store=store)
    freshness(STAGES[0].build(), store=store)
    freshness(STAGES[2].build(), store=SnapshotStore.for_project(tmp_path / "empty"))

    after = {path: path.read_bytes() for path in sorted(store.path.rglob("*")) if path.is_file()}
    assert after == before
    assert not (tmp_path / "empty").exists()


# ── The outcome value itself ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        pytest.param(
            {"state": Freshness.UNSNAPSHOTTED, "version": "1.0.0.0"},
            "names the current snapshot",
            id="a-label-for-an-empty-store",
        ),
        pytest.param(
            {"state": Freshness.FRESH, "version": "1.0.0.0"},
            "iff there is one",
            id="a-label-with-no-digest",
        ),
        pytest.param(
            {"state": Freshness.FRESH, "version": "1.0.0.0", "snapshot_graph_version": "sha256:b"},
            "two digests are one digest",
            id="fresh-with-two-digests",
        ),
        pytest.param(
            {"state": Freshness.STALE, "version": "1.0.0.0", "snapshot_graph_version": "sha256:a"},
            "exactly when the definition and the snapshot differ",
            id="stale-without-a-diff",
        ),
    ],
)
def test_an_outcome_cannot_say_more_than_its_state_supports(
    kwargs: dict[str, object], message: str
) -> None:
    """The invariants are enforced at the value, so no caller can build an answer no check
    could have observed."""
    with pytest.raises(ValueError, match=message):
        FreshnessOutcome(graph_version="sha256:a", store=Path("/tmp/.gebra"), **kwargs)  # type: ignore[arg-type]


def test_a_stale_outcome_whose_two_digests_agree_is_refused() -> None:
    """The one invariant the parametrized table cannot state, because it needs a diff to reach:
    "stale" *means* the two digests differ, and an outcome saying otherwise would make a CI
    failure out of a store that already holds the definition."""
    identical = workflow_diff(workflow(), workflow())

    with pytest.raises(ValueError, match="two digests differ"):
        FreshnessOutcome(
            state=Freshness.STALE,
            graph_version="sha256:a",
            store=Path("/tmp/.gebra"),
            version="1.0.0.0",
            snapshot_graph_version="sha256:a",
            diff=identical,
        )


def test_a_digest_too_short_to_elide_is_printed_whole() -> None:
    """The elision is a courtesy, not a format: anything that is not a long ``<algorithm>:<hex>``
    is passed through rather than mangled into something that looks truncated but is not."""
    outcome = FreshnessOutcome(
        state=Freshness.UNSNAPSHOTTED, graph_version="sha256:abcd", store=Path("/tmp/.gebra")
    )

    assert "sha256:abcd" in outcome.summary()
    assert "…" not in outcome.summary()


def test_the_summary_says_what_moved_and_what_to_do_about_it(tmp_path: Path) -> None:
    store = _store_with(tmp_path, STAGES[0].build())

    summary = freshness(STAGES[1].build(), store=store).summary()

    assert "changed and was not re-snapshotted" in summary
    assert str(store.path) in summary
    assert "1.0.0.0" in summary
    assert "moved" in summary and "S, F" in summary
    assert "gebra.snapshot.snapshot(workflow, store=store)" in summary


def test_the_summary_elides_the_digests_it_prints(tmp_path: Path) -> None:
    """A message a person reads is not the place to compare 64 hex digits; the whole digest is
    on the outcome."""
    ir = STAGES[0].build()
    store = _store_with(tmp_path, ir)

    summary = freshness(ir, store=store).summary()

    assert graph_version(ir) not in summary
    assert graph_version(ir)[: len("sha256:") + 16] in summary
    assert "…" in summary


def test_no_freshness_output_makes_a_safe_or_breaking_claim(tmp_path: Path) -> None:
    """P-12 ``evolution-safety`` is deferred (SOW §8; PD-006 R4). A freshness check reports that
    content moved and which counters moved with it, and stops — so no verdict vocabulary appears
    in any of the three summaries, and no member of the outcome is named for one."""
    store = _store_with(tmp_path, STAGES[0].build())
    empty = SnapshotStore.for_project(tmp_path / "empty")
    summaries = [
        freshness(STAGES[0].build(), store=store).summary(),
        freshness(STAGES[1].build(), store=store).summary(),
        freshness(STAGES[0].build(), store=empty).summary(),
    ]

    verdicts = ("safe", "unsafe", "breaking", "compatible", "backward", "benign", "additive")
    for summary in summaries:
        for verdict in verdicts:
            assert verdict not in summary.lower(), summary
    assert not {field for field in FreshnessOutcome.__dataclass_fields__} & set(verdicts)

    stale = freshness(STAGES[1].build(), store=store)
    assert stale.diff is not None
    assert stale.diff.evolution_safety.status == "deferred-to-phase-1"


# ── WA-07: the whole package reaches no substrate and no network ─────────────────────────

_TRIPWIRE = """\
import socket, sys
attempts = []


class _TripSocket(socket.socket):
    def __new__(cls, *a, **k):
        attempts.append("socket")
        print("WA07-TRIP", file=sys.stderr)
        raise AssertionError("a socket was created by the audit engine")


def _trip_dns(*a, **k):
    attempts.append("getaddrinfo")
    print("WA07-TRIP", file=sys.stderr)
    raise AssertionError("a name was resolved by the audit engine")


socket.socket = _TripSocket
socket.getaddrinfo = _trip_dns

import tempfile
from pathlib import Path

from gebra.audit import Freshness, export_store, freshness, read_export, snapshot_report
from tests.lineage.stores import STAGES, awkward_store, evolved_labels, evolved_store

with tempfile.TemporaryDirectory() as root:
    labels = evolved_labels()
    store = evolved_store(Path(root) / "evolved")
    awkward = awkward_store(Path(root) / "awkward")

    # The export, over every version of both stores, written and read back.
    for target in (store, awkward):
        for outcome in export_store(target):
            document = read_export(target, outcome.version)
            assert document.subject is not None
            assert document.subject.input_mode == "snapshot"
            assert document.subject.version == outcome.version
    assert snapshot_report(store.read(labels[0])).report_format

    # The freshness check, on all three of its answers.
    assert freshness(STAGES[0].build(), store=store).state is Freshness.STALE
    assert freshness(STAGES[-1].build(), store=store).fresh
    empty = Path(root) / "empty"
    assert freshness(STAGES[0].build(), store=type(store)(empty)).state is Freshness.UNSNAPSHOTTED

assert "networkx" in sys.modules  # in reach through gebra.diff, exactly as that package states
"""

_REPORT = """
print([m for m in sys.modules
       if m.split(".")[0] in {"langgraph", "langchain", "langchain_core"}]
      + attempts)
"""


def _run_guarded(probe: str = "") -> subprocess.CompletedProcess[str]:
    # `PYTHONOPTIMIZE` is pinned off because the child states its whole claim in `assert`
    # statements, and an inherited `-O` would delete them while leaving the run green.
    return subprocess.run(
        [sys.executable, "-c", _TRIPWIRE + probe + _REPORT],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "PYTHONOPTIMIZE": "0"},
    )


def test_exporting_and_checking_freshness_reach_no_substrate_and_no_socket() -> None:
    """WA-07 for this card's engine paths, in the strong form the package's own shape allows.

    :mod:`gebra.audit` takes IR models rather than live workflows — the extraction leg is the
    pytest plugin's, which has its own tripwires — so unlike :mod:`gebra.snapshot` this package
    can be held to the *import* claim as well as the invocation one: exporting two whole stores
    and asking all three freshness questions imports no langgraph, no langchain and no
    langchain-core, and opens no connection. networkx is deliberately not on the refusal list
    and the child asserts it *is* imported: the diff a stale outcome carries goes through
    :mod:`gebra.diff`, whose graph representation brief D-11 mandates.
    """
    completed = _run_guarded()

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "[]", completed.stdout
    assert "WA07-TRIP" not in completed.stderr, completed.stderr


@pytest.mark.parametrize(
    ("probe", "expected"),
    [
        ("socket.socket()\n", "a socket was created by the audit engine"),
        ("socket.getaddrinfo('example.invalid', 443)\n", "a name was resolved by the audit engine"),
    ],
)
def test_the_guarded_run_is_armed(probe: str, expected: str) -> None:
    """The armed negative controls for the network half — one per raiser, not one per half.

    A green tripwire is only evidence if it can go red, and "it can go red" has to be true of
    each raiser separately: a table that fired only ``getaddrinfo`` would leave the socket
    constructor untested, and a refactor that stopped installing it would keep this file green.
    Matched on each raiser's full message so a control cannot drift onto the other one.
    """
    completed = _run_guarded(probe)

    assert completed.returncode != 0
    assert "WA07-TRIP" in completed.stderr
    assert expected in completed.stderr


def test_the_guard_trips_when_something_does_reach_the_substrate() -> None:
    """The armed negative control for the ``sys.modules`` half, which no socket probe can arm:
    a substrate import opens no connection, so only the sweep in the trailing report catches
    it, and its green reading is ``stdout == "[]"``."""
    completed = _run_guarded("import langchain_core\n")

    assert completed.returncode == 0, completed.stderr
    assert "WA07-TRIP" not in completed.stderr
    assert completed.stdout.strip() != "[]"
    assert "langchain_core" in completed.stdout
