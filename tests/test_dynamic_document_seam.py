"""The ir-1.1 seam across every consumer — snapshot, freshness, diff, gate, drawing — all lifted.

A ``dynamic`` edge (ratified — DEC-28, 2026-08-09) declares a router whose target set is not
statically known. The story of this file, in four cards:

* **SD-12** (2026-08-21) found that the recorder accepted such a document into an empty store,
  that every later changed re-snapshot then raised out of the topology-diff graph, that the
  freshness check raised the same undocumented error, and that the ``gebra_freshness`` gate
  leaked the traceback — and made every surface *decline* the document coherently, at the
  mouth, in one wording (PD-044 D11's posture), ruling on an interim basis that a store already
  holding one errors with guidance and is never migrated.
* **VAL-14** (2026-09-04) made the wedge five read the document, and left the four declines in
  place on a reason that was not a validator's to rule: what a headless edge looks like in the
  diff's ``nx`` representation was unruled.
* **SD-13** ruled it — **PD-059**: the edge is carried on its source vertex and reported with no
  target, so two documents differing only in one never diff as unchanged — and lifted the four
  declines together, leaving one: the display emitter, on the drawing question PD-059 D8
  deliberately left to the CLI track.
* **CLI-11** ruled that one — **PD-060**: the same source-carried representation on the page, a
  ``[Dn]`` marker on the source and a rendered dispatch note, so nothing is dropped and no head
  is invented. This file is now the claim that the surfaces *agree the other way*, with no
  exception: the recorder records, extends and compares a 1.1 document; the freshness check
  answers all three states over one; the gate renders a stale 1.1 store as stale; the emitter
  draws it; and nothing is migrated because nothing needs to be.

**WA-07.** Every document here is built with the IR model constructors, and the inner pytest
session's marked function *returns* a ``WorkflowIR``, so it takes
:func:`gebra.pytest_plugin.resolve_ir`'s fixture-only branch and no extraction runs on that path.
The tests that reach a live object are
:func:`test_snapshot_records_a_live_map_reduce_workflow` — because ``snapshot()`` is defined as
``record()`` over an extraction and there is no other way to state it — and
:func:`test_verify_reaches_a_verdict_over_the_live_map_reduce_workflow`, which extracts the same
builder once and hands the *document* to ``verify()``; ``_nothing_was_executed`` below says exactly
what its ledger covers and what it does not. No extraction path is added — the entry points called
here are the shipped ones, and the guarded children that speak for them are
``tests/snapshot/test_travel_booking.py`` (the ``snapshot()`` → ``extract()`` → store path) and
``tests/extraction/test_routing.py`` (this builder, extracted in a fresh interpreter with the
network taken away and ``StateGraph.compile`` replaced by a raiser).
"""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

import gebra.ir as gebra_ir
from gebra.audit import Freshness, freshness
from gebra.diff import EdgeChanged, EdgeRef, topology_graph, workflow_diff
from gebra.display import render_mermaid
from gebra.extraction import extract
from gebra.extraction.base import ObjectFamily
from gebra.extraction.envelope import ExtractedFrom as ExtractionProvenance
from gebra.extraction.envelope import ExtractionEnvelope
from gebra.ir.models import DynamicEdge, Edge, Node, NormalEdge, WorkflowIR
from gebra.lineage import compare
from gebra.pytest_plugin import FRESHNESS_MARKER, check_freshness
from gebra.snapshot import SnapshotAction, SnapshotError, SnapshotErrorReason, record, snapshot
from gebra.store import ExtractedFrom, Snapshot, SnapshotStore
from gebra.verify import PropertyReport, WellFormednessWitness, verify
from gebra.verify.graph import build_graph_model
from gebra.versioning import Component
from tests.sample_workflows import sentinel_graph as sg
from tests.sample_workflows import sentinel_routing as sr
from tests.store.hand_built import golden_vector_ir
from tests.versioning.workflows import restamped

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

    What the two ledgers cover, precisely. ``route_send_list`` — the router that makes this
    document ir 1.1 — records into ``sentinel_routing.TRIPPED`` before raising, so an invocation
    of it is visible here even if something on the extraction path swallowed the exception. The
    two *node* bodies come from ``sentinel_graph.raiser`` and record too, into
    ``sentinel_graph.TRIPPED`` — ``SentinelExecutedError.__init__`` appends before the raise —
    so that ledger is cleared and asserted beside the first (corrected at VAL-14's never-invokes
    pre-review). The guarded child that holds the same builder in a fresh interpreter, with the
    network taken away and ``StateGraph.compile`` replaced by a raiser, is
    ``tests/extraction/test_routing.py``'s run over ``ROUTING_BUILDERS``.
    """
    del sr.TRIPPED[:]
    del sg.TRIPPED[:]
    yield
    assert sr.TRIPPED == []
    assert sg.TRIPPED == []


#: One fixed instant, so every fixture here is a function of its arguments.
MOMENT = dt.datetime(2026, 8, 21, 9, 0, 0, tzinfo=dt.timezone.utc)

#: The repository root, injected into the generated inner test file so it can import this
#: module's builder regardless of ``pytester``'s tmp cwd.
REPO_ROOT = Path(__file__).resolve().parents[1]

#: Where the decline helper is allowed to be named at all: the module that defines it and the
#: package `__init__` that re-exports it. Everywhere else under ``src/`` is the grep CLI-11's
#: acceptance box asks for, widened from SD-13's four modules to the whole library.
_DECLINE_HOME = ("src/gebra/ir/models.py", "src/gebra/ir/__init__.py")


def dynamic_ir(*, extra_node: bool = False, condition: str | None = "route_legs") -> WorkflowIR:
    """A map-reduce document: ``plan`` routes dynamically, the workers converge on ``collect``.

    ``extra_node`` adds one wired node, which moves the digest without changing the edge kind;
    ``condition`` is the router's declared expression, the one member of a ``dynamic`` edge that
    can move while the edge persists.
    """
    nodes = [Node(id="plan"), Node(id="book_leg"), Node(id="collect")]
    edges: list[Edge] = [
        DynamicEdge(kind="dynamic", **{"from": "plan"}, condition=condition),
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


def declared_ir() -> WorkflowIR:
    """The same workflow with the router's targets declared — the 1.0 twin, one edge apart."""
    return WorkflowIR(
        ir_version="1.0",
        entry="plan",
        finish="collect",
        state={"legs": "list[str]"},
        nodes=(Node(id="plan"), Node(id="book_leg"), Node(id="collect")),
        edges=(
            NormalEdge(kind="normal", **{"from": "plan"}, to="book_leg"),
            NormalEdge(kind="normal", **{"from": "book_leg"}, to="collect"),
        ),
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
    """A store whose current snapshot is an ir 1.1 document, written through the store directly.

    This is the state SD-12 ruled on — a store a pre-SD-12 build, a hand-written file or a
    direct :meth:`~gebra.store.store.SnapshotStore.write` left behind — and the state the
    recorder now reaches on its own (below). Written through the store rather than the recorder
    here so the two routes are checked against each other.
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


def _dynamic_ref(condition: str | None = "route_legs") -> EdgeRef:
    return EdgeRef("dynamic", "plan", None, condition=condition)


# ── The recorder: a 1.1 document records, extends and compares ────────────────────────────


def test_record_records_a_dynamic_document_into_an_empty_store(tmp_path: Path) -> None:
    """SD-12's observation 1, the other way round: the empty store is where the recorder used
    to *accept* the document by accident and then decline it on purpose; it now records it as
    the document it is, and reads it back equal."""
    store = SnapshotStore.for_project(tmp_path)

    outcome = record(envelope_of(dynamic_ir()), store=store, source="probe", extracted_at=MOMENT)

    assert outcome.action is SnapshotAction.RECORDED
    assert outcome.version == "1.0.0.0"
    assert outcome.diff is None
    assert store.read("1.0.0.0").ir == dynamic_ir()
    assert store.read("1.0.0.0").ir.ir_version == "1.1"
    assert store.check().ok


def test_snapshot_records_a_live_map_reduce_workflow(tmp_path: Path) -> None:
    """The story as a user meets it: ``gebra.snapshot()`` over a bare-``Send`` router.

    ``gebra.extract()`` emits ``kind: dynamic`` for a router whose target set is not statically
    known (INTROSPECTION-SPEC §6, DEC-28) and stamps the document ``"1.1"``; ``snapshot()`` is
    ``record()`` over exactly that envelope, and it records. Every body in the builder raises if
    it is called; the router records itself first, which is the half ``_nothing_was_executed``
    (above) can see. Extraction reads the builder and never runs it (WA-07).
    """
    store = SnapshotStore.for_project(tmp_path)

    outcome = snapshot(sr.build_dynamic_send_hinted_graph(), store=store, extracted_at=MOMENT)

    assert outcome.action is SnapshotAction.RECORDED
    stored = store.read(outcome.version).ir
    assert stored.ir_version == "1.1"
    assert any(isinstance(edge, DynamicEdge) for edge in stored.edges)


def test_a_store_already_holding_a_dynamic_snapshot_extends_under_a_derived_label(
    tmp_path: Path,
) -> None:
    """SD-12's observation 2, lifted: the store that used to be wedged extends. The label is the
    diff's — a node added (S and F, identity being both) and an edge added (S) — and the diff
    the outcome carries leaves the persisting ``dynamic`` edge out of every delta, as it leaves
    every other unchanged edge out."""
    store = store_holding_a_dynamic_snapshot(tmp_path)

    outcome = record(
        envelope_of(dynamic_ir(extra_node=True)), store=store, source="probe", extracted_at=MOMENT
    )

    assert outcome.action is SnapshotAction.RECORDED
    assert outcome.version == "1.1.1.0"
    assert outcome.previous == "1.0.0.0"
    assert outcome.diff is not None
    assert outcome.diff.bump_class == frozenset({Component.S, Component.F})
    assert outcome.diff.topology.nodes.added == ("audit",)
    assert outcome.diff.topology.edges.added == (EdgeRef("normal", "collect", "audit"),)
    assert outcome.diff.topology.edges.removed == ()
    assert store.versions() == ("1.0.0.0", "1.1.1.0")


def test_a_dynamic_edge_that_leaves_is_a_removed_edge_and_an_s_move(tmp_path: Path) -> None:
    """Declaring the router's targets is what moves an edge out of the ``dynamic`` class (the
    extraction tutorial's own sentence), and the recorder labels that as the S move it is: the
    headless edge is reported *removed* with no target, the declared edge added, and the stamp
    goes back to ``"1.0"`` with the construct that required it — never as unchanged."""
    store = store_holding_a_dynamic_snapshot(tmp_path)

    outcome = record(envelope_of(declared_ir()), store=store, source="probe", extracted_at=MOMENT)

    assert outcome.action is SnapshotAction.RECORDED
    assert outcome.version == "1.1.0.0"
    assert outcome.diff is not None
    assert outcome.diff.bump_class == frozenset({Component.S})
    assert outcome.diff.topology.edges.removed == (_dynamic_ref(),)
    assert outcome.diff.topology.edges.added == (EdgeRef("normal", "plan", "book_leg"),)
    assert store.read("1.1.0.0").ir.ir_version == "1.0"


def test_a_stamp_only_difference_gets_one_answer_on_every_surface(tmp_path: Path) -> None:
    """The one hash-scope member with no V.S.F.E component is the stamp (IR-SPEC §8 — a format
    migration is not a workflow migration), and over-stamping is admitted (DEC-34): a working
    definition that is the current snapshot's content stamped ``"1.1"`` moves the digest and
    no counter. PD-059 D7b as ratified gives that pair one answer everywhere: the recorder
    refuses it naming the stamp and writes nothing; the diff names it (``stamp_only``, both
    stamps on the anchors) and is neither identical nor a change; the freshness check answers
    ``restamped`` with the remedy the recorder honours — never ``stale``."""
    store = SnapshotStore.for_project(tmp_path)
    record(envelope_of(golden_vector_ir()), store=store, source="probe", extracted_at=MOMENT)
    over_stamped = restamped(golden_vector_ir(), "1.1")
    before = store.meta_path.read_bytes()

    with pytest.raises(SnapshotError) as caught:
        record(envelope_of(over_stamped), store=store, source="probe", extracted_at=MOMENT)
    diff = workflow_diff(store.read("1.0.0.0"), over_stamped)
    outcome = freshness(over_stamped, store=store)

    assert caught.value.reason is SnapshotErrorReason.NO_VERSION_MOVEMENT
    assert "ir_version stamp" in str(caught.value)
    assert "format migration" in str(caught.value)
    assert "defect" not in str(caught.value)
    assert store.versions() == ("1.0.0.0",)
    assert store.meta_path.read_bytes() == before
    assert diff.stamp_only and not diff.identical and not diff.has_changes
    assert (diff.before.ir_version, diff.after.ir_version) == ("1.0", "1.1")
    assert outcome.state is Freshness.RESTAMPED and not outcome.fresh
    assert outcome.stamps == ("1.0", "1.1")
    assert "re-stamp the working definition to ir_version 1.0" in outcome.summary()


def test_nothing_is_migrated_because_nothing_needs_to_be(tmp_path: Path) -> None:
    """SD-12's interim ruling — error with guidance, never migrate — revisited as the card asked.

    There is still nothing to migrate *to*: the stored document is valid ir 1.1, its digest is
    what it is, and the store is append-only. What changed is that the store no longer has to
    refuse: it extends and compares against the snapshot as it stands. So the ruled behaviour
    is that the bytes never move **and** every route forward is open — pinned by reading the
    snapshot and the index back byte-for-byte after an extension, a freshness check and a
    stored-pair comparison have all run against it.
    """
    store = store_holding_a_dynamic_snapshot(tmp_path)
    before = store.snapshot_path("1.0.0.0").read_bytes()

    record(
        envelope_of(dynamic_ir(extra_node=True)), store=store, source="probe", extracted_at=MOMENT
    )
    outcome = freshness(dynamic_ir(extra_node=True), store=store)
    compared = compare(store, "1.0.0.0", "1.1.1.0")

    assert outcome.state is Freshness.FRESH
    assert compared.bump_class == frozenset({Component.S, Component.F})
    assert (compared.before.version, compared.after.version) == ("1.0.0.0", "1.1.1.0")
    assert store.snapshot_path("1.0.0.0").read_bytes() == before
    assert store.read("1.0.0.0").ir == dynamic_ir()
    assert store.check().ok


# ── The freshness check: all three states, over a 1.1 document ────────────────────────────


def test_freshness_answers_all_three_states_for_a_dynamic_document(tmp_path: Path) -> None:
    """SD-12's observation 3, lifted, and its coherence half: each state names a next step the
    recorder will now take — ``unsnapshotted`` and ``stale`` both say "record it", and the
    recorder records exactly this document."""
    store = SnapshotStore.for_project(tmp_path)

    assert freshness(dynamic_ir(), store=store).state is Freshness.UNSNAPSHOTTED
    record(envelope_of(dynamic_ir()), store=store, source="probe", extracted_at=MOMENT)
    assert freshness(dynamic_ir(), store=store).state is Freshness.FRESH
    stale = freshness(dynamic_ir(extra_node=True), store=store)

    assert stale.state is Freshness.STALE
    assert stale.diff is not None
    assert stale.moved == (Component.S, Component.F)


def test_a_dynamic_edge_alone_moves_the_freshness_answer(tmp_path: Path) -> None:
    """The acceptance sentence, on the check's own surface: two documents differing only in the
    router's declared expression are a stale pair, and the diff the outcome carries reports the
    persisting headless edge with its moved guard — both targets ``None``, never rewired."""
    store = store_holding_a_dynamic_snapshot(tmp_path)

    outcome = freshness(dynamic_ir(condition="route_legs_v2"), store=store)

    assert outcome.state is Freshness.STALE
    assert outcome.diff is not None
    assert outcome.diff.bump_class == frozenset({Component.S})
    assert outcome.diff.topology.edges.changed == (
        EdgeChanged(
            kind="dynamic",
            source="plan",
            label=None,
            target_before=None,
            target_after=None,
            condition_before="route_legs",
            condition_after="route_legs_v2",
        ),
    )
    (change,) = outcome.diff.topology.edges.changed
    assert change.condition_changed and not change.rewired


def test_the_check_documents_what_it_raises_and_it_is_no_longer_the_decline() -> None:
    """Both ``Raises`` sections name what a caller can still meet — the two model floors as
    ``ValueError`` — and neither names the class the decline used to raise (SD-12's box 2,
    kept true the other way round)."""
    for entry_point in (freshness, check_freshness, record, snapshot):
        doc = entry_point.__doc__ or ""
        raises = doc[doc.index("Raises:") :]
        assert "DynamicEdgeUnsupportedError" not in raises, entry_point.__name__
        assert "ValueError" in raises, entry_point.__name__


# ── The pytest gate: a stale 1.1 store is stale, a fresh one is fresh ──────────────────────


# The session is in-process, so this file's import of `tests.…` binds the *same* module object
# — and the same `sr.TRIPPED` list — as the parent. The path insert is conditional for the same
# reason: an unconditional one would leave a duplicate entry in the parent's own `sys.path`.
_INNER = """
import sys
if {root!r} not in sys.path:
    sys.path.insert(0, {root!r})
import pytest
from tests.test_dynamic_document_seam import dynamic_ir

@pytest.mark.{marker}(name="legs", store={store!r})
def test_snapshot_is_current():
    return dynamic_ir(extra_node={extra_node!r})
"""


def _inner(store: Path, *, extra_node: bool) -> str:
    return _INNER.format(
        root=str(REPO_ROOT), marker=FRESHNESS_MARKER, store=store.as_posix(), extra_node=extra_node
    )


def test_the_freshness_gate_reports_a_stale_dynamic_store_as_stale(
    pytester: pytest.Pytester,
) -> None:
    """SD-12's observation 4, lifted: the gate used to render "the freshness check could not be
    made" for a 1.1 store (and before SD-12, a raw traceback). It now renders the designed stale
    message, with the moved counters, and still no traceback."""
    store = store_holding_a_dynamic_snapshot(Path(pytester.path))
    pytester.makepyfile(_inner(store.path, extra_node=True))

    result = pytester.runpytest()

    result.assert_outcomes(failed=1)
    printed = result.stdout.str()
    result.stdout.fnmatch_lines(
        ["*gebra · legs · snapshot freshness*", "*changed and was not re-snapshotted*"]
    )
    assert "Traceback (most recent call last)" not in printed
    assert "DynamicEdgeUnsupportedError" not in printed
    assert "the freshness check could not be made" not in printed


def test_the_freshness_gate_passes_a_fresh_dynamic_store(pytester: pytest.Pytester) -> None:
    store = store_holding_a_dynamic_snapshot(Path(pytester.path))
    pytester.makepyfile(_inner(store.path, extra_node=False))

    result = pytester.runpytest()

    result.assert_outcomes(passed=1)


# ── The one decline that remains, and the four that do not ────────────────────────────────


def test_every_consumer_reads_the_document_and_the_last_decline_is_lifted(
    tmp_path: Path,
) -> None:
    """The fifth decline, lifted at CLI-11 (PD-060). PD-059 D8 kept the drawing question apart
    from the diff's because they share a fact and not an audience: a diff descriptor can say
    "no target" in so many words, a Mermaid arrow cannot. PD-060 answers it in the drawing's
    own vocabulary — the headless edge is carried on its source, as a marker and a rendered
    dispatch note — so this list has no exception left."""
    document = dynamic_ir()
    store = SnapshotStore.for_project(tmp_path)
    reads: tuple[Callable[[], object], ...] = (
        lambda: topology_graph(document),
        lambda: workflow_diff(document, dynamic_ir(extra_node=True)),
        lambda: record(envelope_of(document), store=store, source="probe", extracted_at=MOMENT),
        lambda: freshness(document, store=store),
        lambda: build_graph_model(document),
        lambda: verify(document),
        lambda: render_mermaid(document),
    )
    for read in reads:
        read()  # none of these raises any more

    drawing = render_mermaid(document)
    assert '  n_plan["plan [D1]"]' in drawing
    assert "dynamic dispatch - plan: 1 dynamic router, targets not statically known" in drawing
    arrows = [line for line in drawing.split("\n") if "-->" in line or "-.->" in line]
    assert arrows == ["  START --> n_plan", "  n_collect --> END", "  n_book_5fleg --> n_collect"]


def test_refuse_dynamic_edges_has_no_caller_left_anywhere_in_the_library() -> None:
    """Acceptance box 2 as a machine check, widened by CLI-11: the decline's helper and its
    error are not named anywhere under ``src/`` outside the module that defines them — not
    called, not caught, not imported. They stay on the frozen ``gebra.ir`` export surface
    (PD-060: an export removal is IR-MODELS-FREEZE §4's matter, DEC-routed), so the names are
    still there and still tested; what has no caller is the *decline*."""
    pattern = re.compile(r"refuse_dynamic_edges|DynamicEdgeUnsupportedError")
    home = {REPO_ROOT / relative for relative in _DECLINE_HOME}
    for source in sorted((REPO_ROOT / "src").rglob("*.py")):
        if source in home:
            continue
        assert pattern.search(source.read_text(encoding="utf-8")) is None, source
    assert {"refuse_dynamic_edges", "DynamicEdgeUnsupportedError"} <= set(gebra_ir.__all__)


def test_the_kept_declines_message_names_what_reads_the_document_now() -> None:
    """The helper stays for consumers outside this package, so its message is the thing that
    goes stale if a future card re-introduces a decline — pinned here rather than left to
    rot (the ir-contract pre-review's observation 8). It names every ruling that took a
    consumer off the list, and claims no caller of its own."""
    with pytest.raises(gebra_ir.DynamicEdgeUnsupportedError) as caught:
        gebra_ir.refuse_dynamic_edges(dynamic_ir().edges, consumer="a 1.0-vocabulary reader")

    message = str(caught.value)
    assert "a 1.0-vocabulary reader" in message
    assert "has no semantics for the `dynamic` edge kind" in message
    for ruling in ("DEC-28", "PD-059", "PD-060", "DIAGRAM-STYLE-GUIDE §3.3"):
        assert ruling in message, ruling
    assert "gebra display" in message and "never an invented head" in message
    assert "unruled" not in message, "the drawing question is ruled; the message must not say so"


def test_an_under_stamped_model_built_past_validation_is_refused_by_every_surface(
    tmp_path: Path,
) -> None:
    """The floor DEC-34 §3 named — the construct declines — is replaced, not dropped: a model
    stamped below the minor its edges require (reachable only through ``model_copy``, the
    loader refusing it) is refused by the recorder, the check and the diff alike, as a
    ``ValueError`` the CLI and the gate already report as a refusal, and nothing is written.

    **The display emitter is deliberately not in this loop** (ir-contract pre-review, note 2).
    The floor is a *loader* rule — IR-SPEC §2.5 note 7 as DEC-34 keyed it, and §8's MUST binds
    emitters of IR, not renderers of it — and SD-13 put the guard on the surfaces that anchor a
    digest or write a durable artifact. `render_mermaid` does neither: it draws the document it
    is handed, stamp and all, and the shape is unreachable through any loader since IR-08.
    """
    lowered = dynamic_ir().model_copy(update={"ir_version": "1.0"})
    store = SnapshotStore.for_project(tmp_path)

    for call in (
        lambda: record(envelope_of(lowered), store=store, source="probe", extracted_at=MOMENT),
        lambda: freshness(lowered, store=store),
        lambda: workflow_diff(lowered, dynamic_ir()),
    ):
        with pytest.raises(ValueError, match="below the lowest minor"):
            call()
    assert store.current() is None
    assert not store.meta_path.exists()


# ── The validators, unchanged since VAL-14 ────────────────────────────────────────────────


def test_the_shared_validator_graph_model_reads_the_same_document(tmp_path: Path) -> None:
    """VAL-14 landed §0.3's convention in the shared model — no member for the edge, ``plan``
    recorded as a participating source — and ``verify()`` reaches a verdict; the store now
    records the very same document, so the two halves of the seam answer alike."""
    document = dynamic_ir()

    model = build_graph_model(document)
    report = verify(document)
    recorded = record(envelope_of(document), store=SnapshotStore.for_project(tmp_path), source="p")

    assert model.dynamic_sources == frozenset({"plan"})
    assert report.error is None
    assert report.subject is not None and report.subject.ir_version == "1.1"
    assert recorded.action is SnapshotAction.RECORDED


def test_verify_reaches_a_verdict_over_the_live_map_reduce_workflow() -> None:
    """The story as a user meets it after VAL-14: extract a bare-``Send`` router, verify it.

    ``gebra.extract()`` emits ``kind: dynamic`` for ``plan_step``'s router and stamps the document
    ``"1.1"`` (INTROSPECTION-SPEC §6; IR-SPEC §8); ``verify()`` then answers — no
    ``ir-validation`` refusal — with ``act_step`` surfaced as dynamic-dependent rather than
    flagged unreachable, which is the false FATAL DEC-28 clause 1 forbids. Extraction reads the
    builder and never runs it; the router records itself in the ledger if anything invokes it,
    and ``_nothing_was_executed`` checks that ledger after this test as after every other.
    """
    envelope = extract(sr.build_dynamic_send_hinted_graph())
    assert envelope.ir.ir_version == "1.1"

    report = verify(envelope.ir)

    assert report.error is None
    assert report.gate.exit_code == 0
    assert report.subject is not None and report.subject.ir_version == "1.1"
    p01 = report.outcome_for("graph-well-formed")
    assert isinstance(p01, PropertyReport) and isinstance(p01.witness, WellFormednessWitness)
    assert p01.witness.dynamic_dependent == ("act_step",)


# ── The control: no ir 1.0 document is touched ────────────────────────────────────────────


def test_no_ir_1_0_document_is_affected(tmp_path: Path) -> None:
    """The golden vector records, re-records as UNCHANGED, and reads fresh — the whole 1.0 path
    through both surfaces this card touched, in one test, so "nothing else moved" is observed
    here rather than only inferred from the suites that did not change."""
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
