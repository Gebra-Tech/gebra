"""The ir-1.1 seam across the snapshot, freshness and pytest-gate surfaces — SD-12.

A ``dynamic`` edge (ratified — DEC-28, 2026-08-09) declares a router whose target set is not
statically known, and every consumer written against the ir 1.0 ``kind`` vocabulary **declines**
such a document rather than dropping the edge (PD-044 D11). The shared validator graph model and
the topology-diff graph did so from the start. The three surfaces built on top of the diff did
not, and the 2026-08-12 post-landing review found the seam that left:

1. :func:`gebra.snapshot.record` **accepted** a dynamic document into an empty store — the one
   place there is no earlier version to diff against, and so the one place the decline was never
   reached — violating the engine's own stored-snapshot-must-be-diffable premise;
2. every later *changed* re-snapshot of that store then raised
   :class:`~gebra.ir.DynamicEdgeUnsupportedError` out of the topology-diff graph, a class absent
   from :func:`~gebra.snapshot.record`'s documented ``Raises`` — a store nothing could move
   forward, refused in words about a graph the caller never asked for;
3. :func:`gebra.audit.freshness` raised the same undocumented error on a stale dynamic pair;
4. ``@pytest.mark.gebra_freshness`` printed the raw traceback through the plugin's own frames,
   because the hook caught only ``GebraTargetError`` and ``ValueError`` and the decline is a
   ``NotImplementedError`` subclass.

Fail-closed throughout — nothing wrong was ever reported as right — but incoherent, undocumented
and untested. One test per observation below, plus the coherence claims that make them a seam
rather than four bugs: one wording across every surface, nothing migrated, and no ir 1.0
document touched.

**WA-07.** Every document here is built with the IR model constructors, and the inner pytest
session's marked function *returns* a ``WorkflowIR``, so it takes
:func:`gebra.pytest_plugin.resolve_ir`'s fixture-only branch and no extraction runs on that path.
The one test that does reach a live object is
:func:`test_snapshot_declines_a_live_map_reduce_workflow`, because ``snapshot()`` is defined as
``record()`` over an extraction and there is no other way to state it; ``_nothing_was_executed``
below says exactly what its ledger covers and what it does not. No extraction path is added — the
entry points called here are the shipped ones, and the guarded children that speak for them are
``tests/snapshot/test_travel_booking.py`` (the ``snapshot()`` → ``extract()`` → store path) and
``tests/extraction/test_routing.py`` (this builder, extracted in a fresh interpreter with the
network taken away and ``StateGraph.compile`` replaced by a raiser).
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from gebra.audit import Freshness, freshness
from gebra.diff.graph import topology_graph
from gebra.extraction.base import ObjectFamily
from gebra.extraction.envelope import ExtractedFrom as ExtractionProvenance
from gebra.extraction.envelope import ExtractionEnvelope
from gebra.ir import DynamicEdgeUnsupportedError
from gebra.ir.models import DynamicEdge, Edge, Node, NormalEdge, WorkflowIR
from gebra.pytest_plugin import FRESHNESS_MARKER, check_freshness
from gebra.snapshot import SnapshotAction, record, snapshot
from gebra.store import ExtractedFrom, Snapshot, SnapshotStore
from gebra.verify.graph import build_graph_model
from tests.sample_workflows import sentinel_routing as sr
from tests.store.hand_built import golden_vector_ir

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

pytest_plugins = ["pytester"]


@pytest.fixture(autouse=True)
def _nothing_was_executed() -> Iterator[None]:
    """The one live builder here is read, never run — asserted after every test.

    Cleared on entry rather than asserted empty, which is the idiom
    ``tests/extraction/test_contracts.py`` uses and the only one that works on **this** ledger:
    ``sentinel_routing.TRIPPED`` is module-global and is *deliberately* filled by
    ``tests/extraction/test_routing.py``'s arming test, which fires every one of those callables
    to prove the guard is live. Asserting it empty on entry would have been a claim about
    collection order rather than about this file. Every ``pytester`` session here is in-process,
    so this is the same list object throughout and an escape inside one would be visible.

    What the ledger covers, precisely: ``route_send_list`` — the router that makes this
    document ir 1.1 — records before raising, so an invocation of it is visible here even if
    something on the extraction path swallowed the exception. The two *node* bodies come from
    ``sentinel_graph.raiser`` and raise a ``RuntimeError`` subclass without recording, so an
    invocation of those is caught by the exception propagating, not by this list; the guarded
    child that holds that half for this exact builder is
    ``tests/extraction/test_routing.py``'s fresh-interpreter run over ``ROUTING_BUILDERS``.
    """
    del sr.TRIPPED[:]
    yield
    assert sr.TRIPPED == []


#: One fixed instant, so every fixture here is a function of its arguments.
MOMENT = dt.datetime(2026, 8, 21, 9, 0, 0, tzinfo=dt.timezone.utc)

#: The repository root, injected into the generated inner test file so it can import this
#: module's builder regardless of ``pytester``'s tmp cwd.
REPO_ROOT = Path(__file__).resolve().parents[1]


def dynamic_ir(*, extra_node: bool = False) -> WorkflowIR:
    """A map-reduce document: ``plan`` routes dynamically, the workers converge on ``collect``.

    ``extra_node`` adds one wired node, which moves the digest without changing the edge kind —
    the "the workflow changed" half of observations 2 and 3.
    """
    nodes = [Node(id="plan"), Node(id="book_leg"), Node(id="collect")]
    edges: list[Edge] = [
        DynamicEdge(kind="dynamic", **{"from": "plan"}, condition="route_legs"),
        NormalEdge(kind="normal", **{"from": "book_leg"}, to="collect"),
    ]
    if extra_node:
        nodes.append(Node(id="audit"))
        edges.append(NormalEdge(kind="normal", **{"from": "collect"}, to="audit"))
    return WorkflowIR(
        ir_version="1.1",
        entry="plan",
        finish="collect",
        state={"legs": "list[str]"},
        nodes=tuple(nodes),
        edges=tuple(edges),
    )


def envelope_of(ir: WorkflowIR) -> ExtractionEnvelope:
    """What ``gebra.extract()`` would have returned for ``ir`` — built, never extracted."""
    return ExtractionEnvelope(
        ir=ir,
        extracted_from=ExtractionProvenance(
            source="langgraph:StateGraph",
            family=ObjectFamily.BUILDER,
            extractor_version="0.0.1.dev0",
        ),
    )


def store_holding_a_dynamic_snapshot(root: Path) -> SnapshotStore:
    """A store whose current snapshot is an ir 1.1 document — what a pre-fix build left behind.

    Written through :meth:`~gebra.store.store.SnapshotStore.write` rather than through
    :func:`~gebra.snapshot.record`, which now declines: the store has no edge-kind opinion of
    its own (it stores documents, it does not diff them), so this is the only way left to reach
    the state the review found — and it is the state a pre-fix store is already in.
    """
    store = SnapshotStore.for_project(root)
    store.write(
        Snapshot.of(
            dynamic_ir(),
            version="1.0.0.0",
            extracted_from=ExtractedFrom(
                source="tests.test_dynamic_document_seam",
                extractor_version="0.0.1.dev0",
                extracted_at="2026-08-21T09:00:00Z",
            ),
        )
    )
    return store


# ── Observation 1: record() accepted a dynamic document into an empty store ───────────────


def test_record_declines_a_dynamic_document_into_an_empty_store(tmp_path: Path) -> None:
    """The empty store is where the decline was missing, because it is where no diff runs.

    :func:`~gebra.snapshot.record` derives a label by diffing against the store's current
    snapshot; with no current snapshot the label is :meth:`Version.initial` and the diff engine
    — the one consumer that already declined — is never reached. So the document landed, and
    every path out of that store was closed behind it. The refusal now happens at the mouth.
    """
    store = SnapshotStore.for_project(tmp_path)

    with pytest.raises(DynamicEdgeUnsupportedError) as caught:
        record(envelope_of(dynamic_ir()), store=store, source="probe", extracted_at=MOMENT)

    message = str(caught.value)
    assert "the snapshot recorder" in message
    assert "edges[0]" in message
    assert "DEC-28" in message
    # Nothing was written: no index, no snapshot file, no directory holding half a store.
    assert store.current() is None
    assert not store.snapshot_path("1.0.0.0").exists()
    assert not store.meta_path.exists()


def test_snapshot_declines_a_live_map_reduce_workflow(tmp_path: Path) -> None:
    """The story as a user meets it: ``gebra.snapshot()`` over a bare-``Send`` router.

    The hand-built documents above state the rule; this states that the rule is reachable from
    the entry point that produces such a document in the first place — ``gebra.extract()`` emits
    ``kind: dynamic`` for a router whose target set is not statically known (INTROSPECTION-SPEC
    §6, DEC-28), and ``snapshot()`` is ``record()`` over exactly that envelope.

    Every body in the builder raises if it is called; the router records itself first, which is
    the half ``_nothing_was_executed`` (above) can see. Note the ordering this test does *not*
    claim to change: ``snapshot()`` extracts and *then* refuses, so the decline is what stops the
    document being stored, never what stops it being read (WA-07).
    """
    store = SnapshotStore.for_project(tmp_path)

    with pytest.raises(DynamicEdgeUnsupportedError) as caught:
        snapshot(sr.build_dynamic_send_hinted_graph(), store=store, extracted_at=MOMENT)

    assert "the snapshot recorder" in str(caught.value)
    assert store.current() is None


def test_record_documents_the_decline_it_makes(tmp_path: Path) -> None:
    """The class is in ``record()``'s and ``snapshot()``'s ``Raises``, which is where a caller
    who has to handle it looks — the half of the observation that was a documentation defect."""
    for entry_point in (record, snapshot):
        doc = entry_point.__doc__ or ""
        assert "Raises:" in doc
        raises = doc[doc.index("Raises:") :]
        assert "DynamicEdgeUnsupportedError" in raises, entry_point.__name__


# ── Observation 2: the wedged store ───────────────────────────────────────────────────────


def test_a_store_already_holding_a_dynamic_snapshot_declines_at_the_mouth(
    tmp_path: Path,
) -> None:
    """The wedge, from the other side: a store that already holds one says so itself.

    Before this card the message named "the topology-diff graph" — a component the caller never
    asked for, reached three frames below ``record``. It now names the recorder and the snapshot
    it read, so the two remedies stay distinguishable: change the definition you are recording,
    or reckon with what the store holds (which is nobody's to change — see below).
    """
    store = store_holding_a_dynamic_snapshot(tmp_path)

    with pytest.raises(DynamicEdgeUnsupportedError) as caught:
        record(envelope_of(golden_vector_ir()), store=store, source="probe", extracted_at=MOMENT)

    message = str(caught.value)
    assert "the snapshot recorder, reading the store's current snapshot" in message
    assert "the topology-diff graph" not in message


def test_nothing_is_migrated_and_the_stored_snapshot_is_left_alone(tmp_path: Path) -> None:
    """The ruling on this card's one reserved decision: **error with guidance, never migrate.**

    There is nothing to migrate *to*. Rewriting the document without its ``dynamic`` edge would
    delete a declared router from hash scope — the silent drop DEC-28 clause 1 forbids in terms
    — and would move a digest under a V.S.F.E label that already names other content, which
    PD-012 makes a file name. So the bytes are left exactly as they are and stay readable; what
    the store cannot do until the 1.1 semantics land is extend or compare against them.
    """
    store = store_holding_a_dynamic_snapshot(tmp_path)
    before = store.snapshot_path("1.0.0.0").read_bytes()
    meta_before = store.meta_path.read_bytes()

    for call in (
        lambda: record(envelope_of(dynamic_ir(extra_node=True)), store=store, source="probe"),
        lambda: record(envelope_of(golden_vector_ir()), store=store, source="probe"),
        lambda: freshness(golden_vector_ir(), store=store),
    ):
        with pytest.raises(DynamicEdgeUnsupportedError):
            call()

    assert store.snapshot_path("1.0.0.0").read_bytes() == before
    assert store.meta_path.read_bytes() == meta_before
    assert store.read("1.0.0.0").ir == dynamic_ir()
    assert store.check().ok


# ── Observation 3: freshness() on a stale dynamic pair ────────────────────────────────────


def test_freshness_declines_a_dynamic_working_definition_whatever_the_store_holds(
    tmp_path: Path,
) -> None:
    """All three states are declined, not only the stale one — the coherence half.

    Each of the three outcomes names a next step: ``unsnapshotted`` and ``stale`` both say
    "record it", and :func:`~gebra.snapshot.record` now declines exactly this document. An
    ``unsnapshotted`` verdict here would send a reader to a call that refuses them.
    """
    empty = SnapshotStore.for_project(tmp_path / "empty")
    populated = SnapshotStore.for_project(tmp_path / "populated")
    record(envelope_of(golden_vector_ir()), store=populated, source="probe", extracted_at=MOMENT)

    for store in (empty, populated):
        with pytest.raises(DynamicEdgeUnsupportedError) as caught:
            freshness(dynamic_ir(), store=store)
        assert "the freshness check" in str(caught.value)


def test_freshness_declines_a_stale_dynamic_pair(tmp_path: Path) -> None:
    """The observation as the review made it: a store holding one, and a changed definition."""
    store = store_holding_a_dynamic_snapshot(tmp_path)

    with pytest.raises(DynamicEdgeUnsupportedError) as caught:
        freshness(dynamic_ir(extra_node=True), store=store)

    assert "the freshness check" in str(caught.value)


def test_freshness_documents_the_decline_it_makes() -> None:
    """As ``record()``'s: the class is named in the ``Raises`` a caller reads."""
    doc = freshness.__doc__ or ""
    assert "Raises:" in doc
    assert "DynamicEdgeUnsupportedError" in doc[doc.index("Raises:") :]


def test_check_freshness_documents_the_decline_it_propagates() -> None:
    """The plugin's programmatic half re-raises it, so its own ``Raises`` names it too."""
    doc = check_freshness.__doc__ or ""
    assert "Raises:" in doc
    assert "DynamicEdgeUnsupportedError" in doc[doc.index("Raises:") :]


# ── Observation 4: the pytest gate leaked the raw traceback ───────────────────────────────


# The session is in-process, so this file's import of `tests.…` binds the *same* module object
# — and the same `sr.TRIPPED` list — as the parent. The path insert is conditional for the same
# reason: an unconditional one would leave a duplicate entry in the parent's own `sys.path`.
_INNER = f"""
import sys
if {str(REPO_ROOT)!r} not in sys.path:
    sys.path.insert(0, {str(REPO_ROOT)!r})
import pytest
from tests.test_dynamic_document_seam import dynamic_ir

@pytest.mark.{FRESHNESS_MARKER}(name="legs", store="{{store}}")
def test_snapshot_is_current():
    return dynamic_ir(extra_node=True)
"""


def test_the_freshness_gate_renders_the_designed_message(pytester: pytest.Pytester) -> None:
    """A red item is the gate working; a *traceback* is the gate leaking.

    ``pytest.fail(..., pytrace=False)`` is what every other refusal on this marker renders with,
    and the hook reached none of them for this one: the decline is a ``NotImplementedError``
    subclass and the two ``except`` clauses named ``GebraTargetError`` and ``ValueError``. So a
    user met ``refuse_dynamic_edges``' own frame, the plugin's hook frame, and the exception
    class — instead of a sentence saying no check was made.
    """
    store = store_holding_a_dynamic_snapshot(Path(pytester.path))
    pytester.makepyfile(_INNER.format(store=store.path.as_posix()))

    result = pytester.runpytest()

    result.assert_outcomes(failed=1)
    printed = result.stdout.str()
    result.stdout.fnmatch_lines(
        ["*gebra · snapshot freshness*", "*the freshness check could not be made*"]
    )
    # The leak, named by its three parts: pytest's traceback header, the frames it walks, and
    # the exception class it lands on. `pytrace=False` shows none of them.
    assert "Traceback (most recent call last)" not in printed
    assert "refuse_dynamic_edges" not in printed
    assert "DynamicEdgeUnsupportedError" not in printed
    # And it is not reported as a freshness answer either way.
    assert "changed and was not re-snapshotted" not in printed
    assert "the store holds no snapshot" not in printed


# ── The seam: one wording, and no ir 1.0 document touched ─────────────────────────────────


def test_every_surface_declines_the_same_document_with_one_wording(tmp_path: Path) -> None:
    """Four consumers, one exception class, one explanation — that is what makes this a seam.

    The two that already declined (PD-044 D11) fix the wording; the two this card adds join it
    rather than inventing their own, so a reader who meets the decline in a CI log recognizes it
    in a traceback and in the API docs. ``snapshot()`` is the same decline one call up, stated
    over a live object in :func:`test_snapshot_declines_a_live_map_reduce_workflow`.
    """
    document = dynamic_ir()
    store = SnapshotStore.for_project(tmp_path)
    calls: tuple[Callable[[], object], ...] = (
        lambda: topology_graph(document),
        lambda: build_graph_model(document),
        lambda: record(envelope_of(document), store=store, source="probe"),
        lambda: freshness(document, store=store),
    )

    for call in calls:
        with pytest.raises(DynamicEdgeUnsupportedError) as caught:
            call()
        message = str(caught.value)
        assert "has no semantics for the `dynamic` edge kind" in message
        assert "DEC-28" in message
        assert "paired validator regression card" in message


def test_no_ir_1_0_document_is_affected(tmp_path: Path) -> None:
    """The control. The guard is a test on edge kinds and nothing else.

    The golden vector records, re-records as UNCHANGED, and reads fresh — the whole 1.0 path
    through both surfaces this card touched, in one test, so "nothing else moved" is observed
    here rather than only inferred from the suites that did not change.
    """
    store = SnapshotStore.for_project(tmp_path)

    first = record(
        envelope_of(golden_vector_ir()), store=store, source="probe", extracted_at=MOMENT
    )
    again = record(
        envelope_of(golden_vector_ir()), store=store, source="probe", extracted_at=MOMENT
    )

    assert first.action is SnapshotAction.RECORDED
    assert first.version == "1.0.0.0"
    assert again.action is SnapshotAction.UNCHANGED
    assert freshness(golden_vector_ir(), store=store).state is Freshness.FRESH
