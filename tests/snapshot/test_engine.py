"""The snapshot engine — the idempotency policy, the label it assigns, and how it refuses.

Card SD-03's two reserved decisions are what this file pins:

* **the re-snapshot policy** — a call compares the working IR's ``graph_version`` against the
  store's *current* snapshot, and either writes nothing or writes the label the diff engine's
  bump class lands on. Both acceptance boxes are stated over the live travel-booking agent in
  ``tests/snapshot/test_travel_booking.py``; here they are stated over constructed IR pairs,
  where "which component moved" is the fixture rather than an observation about a graph;
* **the API surface** — two entry points, one outcome value, one error type with coded
  reasons, and store faults that arrive as the store's own :class:`StoreError`.

Every row of the policy table is asserted **twice**: against the expected V.S.F.E label, and
against :func:`~gebra.versioning.classify.changed_components` over the same pair — the version
engine's independent answer to the same question. A label this engine assigns and a component
set that engine computes cannot drift apart without a red test.

Nothing here reaches a live workflow object; the IR is hand-built (WA-07). The strong form of
the never-invokes claim — the whole ``extract`` → store path under a guarded interpreter — is
the travel-booking file's.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError as PydanticValidationError

from gebra.diff import WorkflowDiff, workflow_diff
from gebra.ir import DynamicEdgeUnsupportedError
from gebra.ir.canonical import graph_version
from gebra.ir.models import DynamicEdge, Node, WorkflowIR
from gebra.lineage import lineage
from gebra.snapshot import (
    SnapshotAction,
    SnapshotError,
    SnapshotErrorReason,
    SnapshotOutcome,
    record,
    record_document,
)
from gebra.snapshot import engine as engine_module
from gebra.store import ExtractedFrom, Snapshot, SnapshotStore, StoreError, StoreErrorReason
from gebra.verify import verify
from gebra.versioning import Component, changed_components
from tests.snapshot.envelopes import (
    envelope_of,
    with_escalated_effect,
    with_extra_node,
    with_extra_state_key,
    with_retyped_state_key,
)
from tests.store.hand_built import golden_vector_ir, prompt_bearing_ir

#: One fixed instant, so every fixture in this file is a function of its arguments and the
#: only test that reads a clock is the one about reading the clock.
MOMENT = dt.datetime(2026, 8, 12, 9, 0, 0, tzinfo=dt.timezone.utc)


@pytest.fixture
def store(tmp_path: Path) -> SnapshotStore:
    """An empty store in its own directory — not created until the first write."""
    return SnapshotStore.for_project(tmp_path)


def stored(store: SnapshotStore, ir: WorkflowIR, **kwargs: Any) -> SnapshotOutcome:
    """Record ``ir`` at :data:`MOMENT`, so nothing in a fixture depends on when it ran."""
    kwargs.setdefault("extracted_at", MOMENT)
    return record(envelope_of(ir), store=store, **kwargs)


# ── The variants, and the premise that they are what they say ────────────────────────────

#: One deliberate edit apiece, with the component set the edit moves and the label it lands
#: on from ``1.0.0.0``. The vocabulary is ``tests/diff/test_workflow.py``'s: a wired node is
#: S+F (a vertex and a contract), an effect escalation is F, a Σ edit is E.
VARIANTS: tuple[tuple[str, Any, frozenset[Component], str], ...] = (
    ("node added and wired", with_extra_node, frozenset({Component.S, Component.F}), "1.1.1.0"),
    ("effect class escalated", with_escalated_effect, frozenset({Component.F}), "1.0.1.0"),
    ("optional state key added", with_extra_state_key, frozenset({Component.E}), "1.0.0.1"),
    ("state key retyped", with_retyped_state_key, frozenset({Component.E}), "1.0.0.1"),
)


@pytest.mark.parametrize(("label", "build", "expected", "version"), VARIANTS)
def test_every_variant_is_a_valid_document_that_differs_from_the_base(
    label: str, build: Any, expected: frozenset[Component], version: str
) -> None:
    """The fixtures are built with ``model_copy``, which skips validation — so validate them.

    ``model_copy(update=…)`` is the one route around a pydantic model's validators, and a
    variant that quietly stopped being a legal ``WorkflowIR`` would make every row below a
    statement about a document the engine would never see. Each one is therefore re-validated
    through the model, and asserted to differ from the base at all — a no-op edit would make
    its row pass for the wrong reason.
    """
    variant = build()
    assert WorkflowIR.model_validate(variant.model_dump(by_alias=True)) == variant
    assert graph_version(variant) != graph_version(golden_vector_ir())
    assert changed_components(golden_vector_ir(), variant) == expected, label
    assert version  # the expected label rides the same row, checked in the policy test below


# ── Acceptance box 1 — the idempotency policy ────────────────────────────────────────────


def test_the_first_snapshot_of_an_empty_store_is_the_initial_version(
    store: SnapshotStore,
) -> None:
    """An empty store has nothing to bump from, so the first version is chosen, not derived.

    ``1.0.0.0`` is :meth:`Version.initial`'s answer, and the outcome says explicitly that
    nothing preceded it: no previous label, no diff, an empty bump class. A first snapshot
    reporting some component as "moved" would be claiming a comparison it never made.
    """
    outcome = stored(store, golden_vector_ir())

    assert outcome.action is SnapshotAction.RECORDED
    assert outcome.recorded and outcome.first
    assert outcome.version == "1.0.0.0"
    assert outcome.previous is None
    assert outcome.diff is None
    assert outcome.bump_class == frozenset()
    assert outcome.path == store.snapshot_path("1.0.0.0")
    assert outcome.path.is_file()
    assert store.versions() == ("1.0.0.0",)
    assert store.read_meta().current == "1.0.0.0"


def test_snapshotting_the_unchanged_definition_twice_writes_nothing(
    store: SnapshotStore,
) -> None:
    """**Acceptance box 1**, at its strongest reading: a no-op *and* the same version.

    The card allows either ("a no-op/same-version"); the policy is both, and both are
    asserted here on the bytes rather than on the return value alone — the snapshot file and
    ``meta.yaml`` are byte-identical afterwards, the history gained no row, and no second file
    appeared anywhere in the store. A policy that wrote an identical file back would satisfy
    "same version" while still touching the store on every call.
    """
    first = stored(store, golden_vector_ir())
    before = {path: path.read_bytes() for path in sorted(store.path.rglob("*")) if path.is_file()}

    second = stored(store, golden_vector_ir())

    assert second.action is SnapshotAction.UNCHANGED
    assert not second.recorded
    assert second.version == first.version == "1.0.0.0"
    assert second.previous == "1.0.0.0"
    assert second.bump_class == frozenset()
    assert second.path == first.path
    assert {
        path: path.read_bytes() for path in sorted(store.path.rglob("*")) if path.is_file()
    } == (before)
    assert store.versions() == ("1.0.0.0",)


def test_an_unchanged_call_carries_the_comparison_it_made(store: SnapshotStore) -> None:
    """ "Nothing moved" is a claim, so the outcome carries the diff that says so.

    ``identical`` here is the digest-level statement — both sides canonicalize to one byte
    string — and that is what makes the no-op sound: two IRs with the same ``graph_version``
    have the same canonical form (IR-SPEC §6), so "the workflow did not change" and "the
    digest did not move" are one question rather than two that happen to agree.
    """
    stored(store, golden_vector_ir())
    outcome = stored(store, golden_vector_ir())

    assert outcome.diff is not None
    assert outcome.diff.identical
    assert not outcome.diff.has_changes
    assert outcome.diff.before.graph_version == outcome.diff.after.graph_version
    assert outcome.diff.before.version == "1.0.0.0"


def test_new_provenance_alone_is_not_a_change(store: SnapshotStore) -> None:
    """A different source, a different timestamp, a different sidecar — still no new version.

    This is the envelope/hash-scope boundary (IR-SPEC §6.4) reaching the policy: everything
    the second call says about *how* the IR was obtained differs from the first, and none of
    it is content. A policy keyed on anything but the digest would record a second version
    here, and the store would carry two labels for one workflow.
    """
    stored(store, golden_vector_ir(), source="a:one")
    outcome = record(
        envelope_of(golden_vector_ir(), source="b:two", sidecar="/elsewhere/gebra.toml"),
        store=store,
        extracted_at=MOMENT + dt.timedelta(days=30),
    )

    assert outcome.action is SnapshotAction.UNCHANGED
    assert store.versions() == ("1.0.0.0",)
    assert store.read("1.0.0.0").extracted_from.source == "a:one"


# ── The label a change gets ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize(("label", "build", "expected", "version"), VARIANTS)
def test_a_changed_definition_gets_the_label_its_bump_class_lands_on(
    store: SnapshotStore, label: str, build: Any, expected: frozenset[Component], version: str
) -> None:
    """The policy table: one edit, the counters it moves, and the label that produces.

    Asserted three ways — the label, the outcome's own reported bump class, and
    :func:`changed_components` over the same pair, which is the version engine answering
    without going through the diff. Nothing resets: an F change from ``1.0.0.0`` lands on
    ``1.0.1.0`` and leaves S and E reading what they read (D-11 In-Scope 2's "and/or").
    """
    stored(store, golden_vector_ir())
    outcome = stored(store, build())

    assert outcome.recorded, label
    assert outcome.version == version
    assert outcome.previous == "1.0.0.0"
    assert outcome.bump_class == expected
    assert changed_components(golden_vector_ir(), build()) == expected
    assert store.versions() == ("1.0.0.0", version)
    assert store.read(version).graph_version == graph_version(build())


def test_bumps_accumulate_across_a_sequence(store: SnapshotStore) -> None:
    """Each label is derived from the store's *current* one, so the counters keep counting.

    Four versions, each compared against the one before it rather than against the first: the
    third step moves S and F *back* (the node the second step added is gone again) and E
    forward, and every one of those is a change that counts. Nothing resets — the S counter
    still reads 2 at the end, which is how many topology changes this store has seen — and
    each label is strictly above the one before it, since any non-empty bump moves the version
    forward. That last part is a property of a store this engine filled from empty, not of
    every store: the policy bumps from ``current``, which SD-01's index does not require to be
    the newest row, so a store whose pointer was moved backwards by hand can mint a label
    below its own maximum.
    """
    stored(store, golden_vector_ir())
    assert stored(store, with_extra_node()).version == "1.1.1.0"
    assert stored(store, with_extra_state_key()).version == "1.2.2.1"
    assert stored(store, with_escalated_effect()).version == "1.2.3.2"

    assert store.versions() == ("1.0.0.0", "1.1.1.0", "1.2.2.1", "1.2.3.2")
    assert store.check().ok
    assert [entry.version for entry in lineage(store).entries] == list(store.versions())


def test_a_prompt_body_change_is_a_change(store: SnapshotStore) -> None:
    """Decision D-025 reaching the policy: a prompt-only edit is a new version.

    The opaque-body gap is closed inside the hash scope (IR-SPEC §6.4 puts the per-node
    ``prompt_digest`` in it), so an engine that compares digests inherits the closure without
    knowing anything about prompts. The two snapshots differ in exactly one node's digest —
    and the prompt bytes themselves are in neither file.
    """
    stored(store, prompt_bearing_ir(b"answer briefly"))
    outcome = stored(store, prompt_bearing_ir(b"answer at length"))

    assert outcome.recorded
    assert outcome.bump_class == frozenset({Component.F})
    assert outcome.version == "1.0.1.0"
    assert b"answer at length" not in outcome.path.read_bytes()


def test_reverting_records_a_new_version_carrying_the_old_digest(store: SnapshotStore) -> None:
    """The policy compares against ``current``, not against the whole history.

    Reverting an edit is a change *relative to where the store points*, so it records a new
    version — the history is a log of what happened, and re-pointing at the old label would
    lose the fact that the workflow went there and came back. Two versions then carry one
    digest, which is a shape the store and the version-history engine both already model.
    """
    stored(store, golden_vector_ir())
    stored(store, with_extra_node())
    outcome = stored(store, golden_vector_ir())

    assert outcome.recorded
    assert outcome.version == "1.2.2.0"
    assert outcome.graph_version == graph_version(golden_vector_ir())
    assert store.read("1.0.0.0").graph_version == store.read("1.2.2.0").graph_version
    assert store.check().ok


def test_an_unchanged_definition_against_an_unparseable_current_label_still_no_ops(
    store: SnapshotStore,
) -> None:
    """A label the V.S.F.E grammar refuses blocks a *bump*, never the no-op — and that
    asymmetry is deliberate.

    The store's own check on a label is a path-safety floor and is deliberately wider than
    the grammar (SD-01's ruling), so a store can hold ``draft``. Answering "nothing moved"
    needs no arithmetic and so needs no grammar; deriving a next label does, and that is the
    refusal the next test pins.
    """
    store.write(_hand_written(golden_vector_ir(), "draft"))

    outcome = stored(store, golden_vector_ir())

    assert outcome.action is SnapshotAction.UNCHANGED
    assert outcome.version == "draft"
    assert store.versions() == ("draft",)


# ── Refusals ─────────────────────────────────────────────────────────────────────────────


def test_a_change_against_an_unparseable_current_label_is_refused(store: SnapshotStore) -> None:
    """Coded, and it does not invent a numbering beside the one the store is using."""
    store.write(_hand_written(golden_vector_ir(), "draft"))

    with pytest.raises(SnapshotError) as caught:
        stored(store, with_extra_node())

    assert caught.value.reason is SnapshotErrorReason.UNVERSIONABLE_CURRENT
    assert "draft" in str(caught.value)
    assert store.versions() == ("draft",)


def test_a_document_repeating_a_node_id_is_never_stored(store: SnapshotStore) -> None:
    """IR-SPEC §2.1 (ratified DEC-22), enforced on **every** path — the empty store included.

    "Node ``id``s MUST be unique within a document … loaders MUST reject it." The model
    rejects it since card IR-07, so nothing *loaded* gets this far; the floor that catches a
    model built past validation is :func:`~gebra.diff.topology.resolve_subject`'s — and a
    first snapshot has nothing to diff against, so it would otherwise walk straight past it.
    This engine therefore resolves the document before it looks at the store, on the first
    write and on every later one.

    Two reasons that matters here specifically, both about what a stored digest means. Such a
    document has no well-defined canonical form (§6.2's ``nodes[]`` sort key ties, so authored
    order reaches the digest, which §6.4 excludes — PD-032's finding, ratified as DEC-22), so
    the label would be content-addressed to nothing in particular. And every *later* call on
    that store would be refused when it tried to diff against it, which is a store that reads
    fine and can never be added to.
    """
    base = golden_vector_ir()
    twice = base.model_copy(update={"nodes": (*base.nodes, base.nodes[0])})

    with pytest.raises(ValueError, match="unique"):
        stored(store, twice)
    assert not store.exists

    # And on a store that already holds a version, where the refusal is the diff engine's own.
    stored(store, base)
    with pytest.raises(ValueError, match="unique"):
        stored(store, twice)
    assert store.versions() == ("1.0.0.0",)


def test_a_run_report_that_forbids_recording_is_applied(store: SnapshotStore) -> None:
    """PROPERTY-CATALOG-SPEC §0.2, applied rather than re-derived: a FATAL records nothing.

    The report is a real ``verify()`` run over the same IR — an unreachable node, which is
    P-01's condition (i) — so the field being read is the one the validators produced. The
    engine reads ``gate.snapshot_eligible`` and nothing else; what counts as FATAL is the
    property catalog's question and stays there.
    """
    base = golden_vector_ir()
    unreachable = base.model_copy(update={"nodes": (*base.nodes, Node(id="orphan"))})
    report = verify(unreachable)
    assert report.gate.counts.fatal > 0 and not report.gate.snapshot_eligible

    with pytest.raises(SnapshotError) as caught:
        record(envelope_of(unreachable), store=store, extracted_at=MOMENT, eligibility=report)

    assert caught.value.reason is SnapshotErrorReason.NOT_SNAPSHOT_ELIGIBLE
    assert not store.exists


def test_an_eligible_run_report_records(store: SnapshotStore) -> None:
    """The control for the refusal above: a clean run passed in changes nothing else.

    Without this the refusal test would also pass on an engine that refused every report it
    was handed.
    """
    report = verify(golden_vector_ir())
    assert report.gate.snapshot_eligible

    outcome = record(
        envelope_of(golden_vector_ir()), store=store, extracted_at=MOMENT, eligibility=report
    )

    assert outcome.recorded
    assert store.versions() == ("1.0.0.0",)


def test_a_run_report_about_some_other_ir_cannot_authorize_a_write(store: SnapshotStore) -> None:
    """``docs/specs/CLI-SPEC.md`` §4.2's "one resolution, one IR", made true by construction.

    §4.2 requires the eligibility run and the write to share one resolution, so that "the
    digest the store records is the digest the gate saw". A caller that verified one workflow
    and recorded another would satisfy every check the engine could make on the report alone —
    so the report's own subject digest, which :func:`~gebra.verify.verify` computes rather than
    accepts, is compared against the one being stored. Nothing is written.
    """
    clean = verify(golden_vector_ir())
    assert clean.gate.snapshot_eligible

    with pytest.raises(SnapshotError) as caught:
        record(envelope_of(with_extra_node()), store=store, extracted_at=MOMENT, eligibility=clean)

    assert caught.value.reason is SnapshotErrorReason.ELIGIBILITY_MISMATCH
    assert not store.exists


def test_a_moved_digest_that_selects_no_component_is_refused(
    store: SnapshotStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The engine's stated premise, failing loudly instead of writing a wrong label.

    ``workflow_diff``'s bump class is empty exactly when the two sides are identical, over
    every document the diff engine accepts — that is SD-05's completeness property, and it is
    what makes "a digest that moved always moves a counter" true. The premise is a *property
    of another engine*, so this test breaks it on purpose: with the diff stubbed to report no
    movement, the label would come back equal to the current one and the store would be asked
    to hold two contents under one label. The engine refuses instead, and names why.
    """
    stored(store, golden_vector_ir())

    def _blind(before: WorkflowIR | Snapshot, after: WorkflowIR | Snapshot) -> WorkflowDiff:
        del after
        return workflow_diff(before, before)

    monkeypatch.setattr(engine_module, "workflow_diff", _blind)

    with pytest.raises(SnapshotError) as caught:
        stored(store, with_extra_node())

    assert caught.value.reason is SnapshotErrorReason.NO_VERSION_MOVEMENT
    assert store.versions() == ("1.0.0.0",)


def test_a_damaged_current_snapshot_arrives_as_the_store_s_own_error(
    store: SnapshotStore,
) -> None:
    """Store faults are propagated, not re-wrapped: one fault, one vocabulary.

    A snapshot file edited under its digest is the one content corruption the store can
    detect (IR-SPEC §6.1 step 9), and it is the store's finding — coded, naming its own file.
    Translating it into a snapshot-engine reason would give a caller two codes to learn for
    one condition.
    """
    stored(store, golden_vector_ir())
    path = store.snapshot_path("1.0.0.0")
    path.write_text(path.read_text(encoding="utf-8").replace("plan", "planx"), encoding="utf-8")

    with pytest.raises(StoreError) as caught:
        stored(store, golden_vector_ir())

    assert caught.value.reason is StoreErrorReason.DIGEST_MISMATCH
    # Not a `SnapshotError` — and the two types are provably disjoint, since neither inherits
    # the other and their constructors disagree, so this is `type(...) is` rather than an
    # `isinstance` mypy would (rightly) call unreachable.
    assert type(caught.value) is StoreError


# ── The provenance bridge ────────────────────────────────────────────────────────────────


def test_the_source_defaults_to_what_extraction_knows(store: SnapshotStore) -> None:
    """Absent a better reference, the stored ``source`` is extraction's own — the type.

    ``gebra.extract()`` takes a live object rather than a file, so what it knows about the
    source is that object's type identity. It is an honest default and a thin one, which is
    why the caller can name something better.
    """
    stored(store, golden_vector_ir())

    assert store.read("1.0.0.0").extracted_from.source == "langgraph:StateGraph"


def test_the_caller_can_name_the_reference_it_used(store: SnapshotStore) -> None:
    """``docs/specs/CLI-SPEC.md`` §2.1 reads this member back as a snapshot subject's source.

    A report over a stored version says where the subject came from by quoting the snapshot's
    ``extracted_from.source``; for a run that named ``travel_booking:build_agent``, that
    reference is the useful answer and ``langgraph:StateGraph`` is not.
    """
    stored(store, golden_vector_ir(), source="travel_booking:build_agent")

    assert store.read("1.0.0.0").extracted_from.source == "travel_booking:build_agent"


def test_the_sidecar_path_crosses_over_including_its_absence(store: SnapshotStore) -> None:
    """ANNOTATION-API-SPEC §2's requirement, carried under PD-012's member name.

    §2 requires the envelope's ``extracted_from`` to record the sidecar used *or its absence*
    "so digest divergence is diagnosable" — sidecar-filled annotations sit inside the hash
    scope. Both halves are pinned: a path crosses over, and an absence crosses over as
    ``None`` rather than as an empty string, which the store model refuses outright.
    """
    stored(store, golden_vector_ir(), source="a:one")
    assert store.read("1.0.0.0").extracted_from.sidecar_path is None

    other = SnapshotStore.for_project(store.path.parent / "second")
    record(
        envelope_of(golden_vector_ir(), sidecar="/proj/gebra.toml"),
        store=other,
        extracted_at=MOMENT,
    )
    assert other.read("1.0.0.0").extracted_from.sidecar_path == "/proj/gebra.toml"


def test_the_extractor_version_is_carried_not_re_read(store: SnapshotStore) -> None:
    """What made the IR is what the envelope says made it, not what is installed now.

    An engine that read ``gebra.__version__`` here would relabel a snapshot of an IR produced
    by another build — which is exactly the case the field exists to make diagnosable.
    """
    record(
        envelope_of(golden_vector_ir(), extractor_version="0.0.0.dev-elsewhere"),
        store=store,
        extracted_at=MOMENT,
    )

    assert store.read("1.0.0.0").extracted_from.extractor_version == "0.0.0.dev-elsewhere"


def test_the_timestamp_is_injectable_and_lands_in_utc(store: SnapshotStore) -> None:
    """The one clock in the path, and the seam that takes it out of the path.

    An aware instant in another zone is converted rather than reinterpreted (the store's one
    spelling is UTC at second precision), and the history row defaults to the snapshot's own
    ``extracted_at`` — the store reads no clock of its own, so the two agree by construction.
    """
    tehran = dt.timezone(dt.timedelta(hours=3, minutes=30))
    stored(
        store, golden_vector_ir(), extracted_at=dt.datetime(2026, 8, 12, 12, 30, 0, tzinfo=tehran)
    )

    assert store.read("1.0.0.0").extracted_from.extracted_at == "2026-08-12T09:00:00Z"
    assert store.read_meta().history[0].created_at == "2026-08-12T09:00:00Z"


def test_without_an_explicit_instant_the_engine_reads_the_clock(store: SnapshotStore) -> None:
    """The default is now, and it is the only place in the path that asks.

    Bounded rather than pinned: the recorded instant sits between two readings taken around
    the call, at the store's own second precision. That is as much as a clock-reading default
    can honestly be asserted to be.
    """
    before = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    record(envelope_of(golden_vector_ir()), store=store)
    after = dt.datetime.now(dt.timezone.utc)

    recorded = store.read("1.0.0.0").extracted_from.extracted_at
    assert before.strftime("%Y-%m-%dT%H:%M:%SZ") <= recorded
    assert recorded <= after.strftime("%Y-%m-%dT%H:%M:%SZ")


def test_one_envelope_and_one_instant_reach_two_stores_as_one_file(tmp_path: Path) -> None:
    """The store's determinism claim, extended to the whole path this card wires.

    PD-012 finding 6 reads "two independent writes of the same IR are byte-identical" as a
    property of the *emitter given identical input*, and left the question of what an
    unchanged re-snapshot does to this card. Here both halves meet: pin the one input the
    engine adds — the instant — and two stores that never saw each other hold the same bytes.
    """
    first = SnapshotStore.for_project(tmp_path / "a")
    second = SnapshotStore.for_project(tmp_path / "b")
    envelope = envelope_of(golden_vector_ir())

    left = record(envelope, store=first, extracted_at=MOMENT)
    right = record(envelope, store=second, extracted_at=MOMENT)

    assert left.version == right.version
    assert left.path.read_bytes() == right.path.read_bytes()
    assert first.meta_path.read_bytes() == second.meta_path.read_bytes()


# ── The outcome value ────────────────────────────────────────────────────────────────────


def test_the_outcome_is_frozen_and_compares_by_value() -> None:
    """Two calls that did the same thing to the same store are one value."""
    outcome = SnapshotOutcome(
        action=SnapshotAction.RECORDED,
        version="1.0.0.0",
        graph_version=graph_version(golden_vector_ir()),
        path=Path("/store/.gebra/snapshots/1.0.0.0.yaml"),
    )
    twin = SnapshotOutcome(
        action=SnapshotAction.RECORDED,
        version="1.0.0.0",
        graph_version=graph_version(golden_vector_ir()),
        path=Path("/store/.gebra/snapshots/1.0.0.0.yaml"),
    )

    assert outcome == twin
    with pytest.raises(AttributeError):
        outcome.version = "1.0.0.1"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        pytest.param(
            {"action": SnapshotAction.UNCHANGED, "previous": "1.0.0.1"},
            "they are one version",
            id="unchanged-naming-a-different-previous",
        ),
        pytest.param(
            {"action": SnapshotAction.UNCHANGED, "previous": "1.0.0.0"},
            "what makes the claim checkable",
            id="unchanged-without-the-comparison",
        ),
        pytest.param(
            {"action": SnapshotAction.RECORDED, "previous": "0.9.0.0"},
            "the diff it moved by",
            id="recorded-over-a-previous-without-a-diff",
        ),
    ],
)
def test_an_outcome_cannot_say_what_the_engine_would_never_say(
    kwargs: dict[str, Any], expected: str
) -> None:
    """The invariants are enforced at the value, so a hand-built outcome is refused too.

    A consumer branches on ``recorded`` and then reads ``previous``, ``bump_class`` and
    ``diff``; an outcome whose parts disagree would send it somewhere the engine never went.
    """
    with pytest.raises(ValueError, match=expected):
        SnapshotOutcome(
            version="1.0.0.0",
            graph_version=graph_version(golden_vector_ir()),
            path=Path("/store/.gebra/snapshots/1.0.0.0.yaml"),
            **kwargs,
        )


def test_a_first_snapshot_carrying_a_diff_is_refused() -> None:
    """The fourth invariant: there is nothing a first version could have been compared to."""
    with pytest.raises(ValueError, match="nothing it"):
        SnapshotOutcome(
            action=SnapshotAction.RECORDED,
            version="1.0.0.0",
            graph_version=graph_version(golden_vector_ir()),
            path=Path("/store/.gebra/snapshots/1.0.0.0.yaml"),
            diff=workflow_diff(golden_vector_ir(), with_extra_node()),
        )


def test_no_outcome_member_is_named_for_a_safe_or_breaking_verdict() -> None:
    """WA-06 / SOW §8: this engine reports what was recorded, never what a change means.

    P-12 ``evolution-safety`` is deferred out of Phase 0 (PD-006 R4), and the diff an outcome
    carries says so in the field where a classification would go. The member names are swept
    here so that a later addition cannot introduce a verdict slot quietly; the diff's own
    output is swept in ``tests/diff/test_workflow.py``.
    """
    import gebra.snapshot as package

    verdict_words = ("safe", "unsafe", "breaking", "compatible", "benign", "harmless")
    members = set(SnapshotOutcome.__dataclass_fields__) | set(package.__all__)
    assert not [name for name in members if any(word in name.lower() for word in verdict_words)]

    outcome = workflow_diff(golden_vector_ir(), with_extra_node())
    assert outcome.evolution_safety.status == "deferred-to-phase-1"


def _hand_written(ir: WorkflowIR, version: str) -> Snapshot:
    """A snapshot built outside the engine, for the labels the engine would never assign."""
    return Snapshot.of(
        ir,
        version=version,
        extracted_from=ExtractedFrom(
            source="hand:written",
            extractor_version="0.0.1.dev0",
            extracted_at="2026-08-12T09:00:00Z",
        ),
    )


# ── The document entry point (CLI-05) ────────────────────────────────────────────────────


def test_a_document_records_under_the_same_policy(store: SnapshotStore) -> None:
    """`record_document` is the same recorder at a third mouth, not a second policy.

    A document seeds the store at the chosen initial label, an envelope recording bumps from
    it, and a later document recording bumps from *that* — one `current`-anchored policy
    whichever entry point a call came through, which is what keeps CLI-SPEC §4.2's
    "label assignment and re-snapshot policy are SD-03's" one sentence about one thing.
    """
    seeded = record_document(
        golden_vector_ir(), store=store, source="build/base.ir.yaml", extracted_at=MOMENT
    )
    assert seeded.recorded and seeded.first
    assert seeded.version == "1.0.0.0"

    via_envelope = stored(store, with_extra_node())
    assert via_envelope.recorded and via_envelope.previous == "1.0.0.0"

    grown = record_document(
        with_extra_state_key(), store=store, source="build/next.ir.yaml", extracted_at=MOMENT
    )
    assert grown.recorded and grown.previous == via_envelope.version
    assert grown.bump_class == changed_components(with_extra_node(), with_extra_state_key())


def test_a_document_recording_states_document_provenance(store: SnapshotStore) -> None:
    """The four `extracted_from` members, filled with the facts a document recording has.

    The source is the caller's reference verbatim; the producer version is this build's —
    the build that read, validated and canonically re-emitted the document — never a value
    invented for an extraction that did not happen; the sidecar member is an honest absence,
    because no extraction consulted one; and the instant is the injectable one.
    """
    import gebra

    record_document(
        golden_vector_ir(), store=store, source="build/agent.ir.yaml", extracted_at=MOMENT
    )

    provenance = store.read("1.0.0.0").extracted_from
    assert provenance.source == "build/agent.ir.yaml"
    assert provenance.extractor_version == gebra.__version__
    assert provenance.sidecar_path is None
    assert provenance.extracted_at == "2026-08-12T09:00:00Z"


def test_an_unchanged_document_recording_writes_nothing_and_reads_no_clock(
    store: SnapshotStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The idempotency policy holds at this mouth too, clock-freedom included.

    The second call gets no instant and the module clock is armed to fail, so the no-op
    branch is shown never to build provenance at all — the same "no clock is read" the
    envelope entry point states.
    """
    record_document(
        golden_vector_ir(), store=store, source="build/agent.ir.yaml", extracted_at=MOMENT
    )
    before = {path: path.read_bytes() for path in store.path.rglob("*") if path.is_file()}

    def _no_clock() -> dt.datetime:
        raise AssertionError("an unchanged document recording read the clock")

    monkeypatch.setattr(engine_module, "_now", _no_clock)
    again = record_document(golden_vector_ir(), store=store, source="elsewhere/agent.ir.yaml")

    assert not again.recorded and again.version == "1.0.0.0"
    assert again.diff is not None and again.diff.identical
    assert {path: path.read_bytes() for path in store.path.rglob("*") if path.is_file()} == before


def test_a_document_recording_applies_the_recording_rule(store: SnapshotStore) -> None:
    """PROPERTY-CATALOG-SPEC §0.2 reaches the document mouth unchanged.

    The report is a real ``verify()`` run over the same IR, exactly as the envelope-side
    test states it; the refusal and the store's untouched state are the same claim.
    """
    base = golden_vector_ir()
    unreachable = base.model_copy(update={"nodes": (*base.nodes, Node(id="orphan"))})
    report = verify(unreachable)
    assert not report.gate.snapshot_eligible

    with pytest.raises(SnapshotError) as caught:
        record_document(
            unreachable,
            store=store,
            source="build/agent.ir.yaml",
            extracted_at=MOMENT,
            eligibility=report,
        )

    assert caught.value.reason is SnapshotErrorReason.NOT_SNAPSHOT_ELIGIBLE
    assert not store.exists


def test_an_empty_document_source_is_refused(store: SnapshotStore) -> None:
    """The store model's own floor holds: a source has to say something (PD-012)."""
    with pytest.raises(PydanticValidationError):
        record_document(golden_vector_ir(), store=store, source="", extracted_at=MOMENT)
    assert not store.exists


def test_a_dynamic_document_is_declined_at_the_document_mouth(store: SnapshotStore) -> None:
    """The DEC-28 decline covers the third entry point on the same terms as the other two."""
    dynamic = WorkflowIR(
        ir_version="1.1",
        entry="plan",
        finish="collect",
        nodes=(Node(id="plan"), Node(id="collect")),
        edges=(DynamicEdge(kind="dynamic", **{"from": "plan"}, condition="route"),),
    )

    with pytest.raises(DynamicEdgeUnsupportedError):
        record_document(dynamic, store=store, source="build/dynamic.ir.yaml", extracted_at=MOMENT)
    assert not store.exists
