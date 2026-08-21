"""The INTROSPECTION-SPEC §4 compiled-level extraction path, and its WA-07 tripwire.

The suite is organized by the four things §4 says: the compiled-level surfaces (§4.1), the
authority ruling's builder-primary half (§4.3 rule 1), the cross-check and its disagreement
rule (§4.2 / §4.3 rules 2–3), and the builderless downgrade (§4.3 rule 4).

Two claims run through all of them. The **IR never moves** — DEC-06's whole content is that
the compiled level adds facts and never rewrites the builder's, so the parity tests compare
the compiled reading against the same builder extracted on its own, byte for byte, and the
divergence tests do it again on a graph whose two levels genuinely disagree. And **nothing is
invoked**: every node, router and Pregel step in ``tests/sample_workflows/sentinel_compiled.py``
raises if called, and the two user-authored channel classes there record before they act, so a
guarded read that a ``try`` block swallowed still shows up in ``TRIPPED``.
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from gebra.extraction import (
    CompiledSurfaces,
    CrossCheck,
    ExtractionEnvelope,
    ExtractionError,
    ExtractionErrorReason,
    ExtractionWarning,
    ExtractionWarningCode,
    ObjectFamily,
    classify,
    extract,
    extract_compiled,
    to_data,
)
from gebra.extraction.compiled import CROSS_CHECK_XRAY
from gebra.ir.canonical import graph_version
from gebra.ir.models import (
    Annotations,
    Checkpointer,
    ConditionalEdge,
    DynamicEdge,
    Interrupts,
    Runtime,
)
from tests import substrate
from tests.sample_workflows import sentinel_compiled as sc
from tests.sample_workflows import sentinel_graph as sg
from tests.sample_workflows import sentinel_routing as sr

REPO_ROOT = str(Path(__file__).resolve().parents[2])


def _every_fixture() -> list[Any]:
    """Every §4 fixture name, with the ones this substrate cannot build marked skipped.

    The parametrizations below quantify over the fixture table, and two of its shapes need
    builder APIs that arrived in langgraph 1.2.0 — so on the two frozen VERSION-COMPAT §3
    cells below that minor, the table is shorter (EX-17 / PD-038 Finding 2). Reading the
    names off ``EXTRACTABLE_COMPILED`` alone would make those cases *disappear* on those cells,
    which is exactly the kind of silent narrowing a matrix exists to catch. The union is used
    instead, and the missing ones carry a skip whose reason names the API and its minor.
    """
    return [
        pytest.param(name, marks=[pytest.mark.skip(reason=sc.UNAVAILABLE_COMPILED[name])])
        if name in sc.UNAVAILABLE_COMPILED
        else pytest.param(name)
        for name in sorted({*sc.EXTRACTABLE_COMPILED, *sc.UNAVAILABLE_COMPILED})
    ]


@pytest.fixture(autouse=True)
def _clear_tripped() -> Iterator[None]:
    """Every test starts with an empty sentinel log and asserts nothing was recorded.

    The blanket assertion is what makes the never-invokes claim cover the *whole file* rather
    than only the guarded subprocess at the bottom: a read that reached a fixture's channel
    fails the test that reached it, named, instead of surviving to a summary.
    """
    sc.TRIPPED.clear()
    yield
    assert [call for call in sc.TRIPPED if not call.startswith("ValueType")] == [], sc.TRIPPED


def _warnings_of(
    envelope: ExtractionEnvelope, code: ExtractionWarningCode
) -> tuple[ExtractionWarning, ...]:
    return envelope.warnings_of(code)


# ── narrowing readers ────────────────────────────────────────────────────────────────────
#
# Each asserts the presence it reads past, so a slot that silently went absent fails the test
# that meant to look at it rather than an attribute access three lines later. They are the
# reason the assertions below stay one line each.


def _runtime(envelope: ExtractionEnvelope) -> Runtime:
    runtime = envelope.ir.runtime
    assert runtime is not None, "a compiled extraction always carries a runtime block (§4.1)"
    return runtime


def _interrupts(envelope: ExtractionEnvelope) -> Interrupts:
    interrupts = _runtime(envelope).interrupts
    assert interrupts is not None
    return interrupts


def _checkpointer(envelope: ExtractionEnvelope) -> Checkpointer:
    checkpointer = _runtime(envelope).checkpointer
    assert checkpointer is not None
    return checkpointer


def _surfaces(envelope: ExtractionEnvelope) -> CompiledSurfaces:
    surfaces = envelope.extracted_from.compiled
    assert surfaces is not None, "a §4 extraction always records its compiled-level surfaces"
    return surfaces


def _cross_check(envelope: ExtractionEnvelope) -> CrossCheck:
    check = _surfaces(envelope).cross_check
    assert check is not None
    return check


def _annotations(envelope: ExtractionEnvelope, node_id: str) -> Annotations:
    (node,) = [candidate for candidate in envelope.ir.nodes if candidate.id == node_id]
    assert node.annotations is not None
    return node.annotations


def _pairs(envelope: ExtractionEnvelope) -> set[tuple[str, str]]:
    """The IR's plain ``(from, to)`` incidences — ``conditional``/``dynamic`` carry no ``to``."""
    return {
        (edge.from_, edge.to)
        for edge in envelope.ir.edges
        if not isinstance(edge, (ConditionalEdge, DynamicEdge))
    }


# ── §4.1 — the compiled-level surfaces ───────────────────────────────────────────────────


def test_interrupt_gates_land_on_the_runtime_slots() -> None:
    """§4.1: ``interrupt_before_nodes`` → ``runtime.interrupts.before``, and likewise after."""
    envelope = extract(sc.build_gated_graph())

    assert _interrupts(envelope).before == ("act_step",)
    assert _interrupts(envelope).after == ("plan_step",)


def test_the_all_sentinel_is_expanded_to_the_full_node_list() -> None:
    """§4.1: the ``All`` sentinel "MUST be expanded to the full extracted node-id list".

    Expanded rather than carried, and the difference is not cosmetic: ``"*"`` is not a node id
    under the §5 grammar, so passing it through would put a string in ``runtime.interrupts``
    that names nothing — and the expansion is a static, Full-knowable one, which is why §4.1
    requires it rather than permitting it.
    """
    envelope = extract(sc.build_all_gates_graph())

    assert _interrupts(envelope).before == tuple(sorted(node.id for node in envelope.ir.nodes))
    assert _interrupts(envelope).after is None


def test_an_empty_gate_list_emits_no_member_and_no_gates_emits_no_object() -> None:
    """§4.1's two omission rules, which IR-SPEC §6.3 is the reason for.

    An empty optional array is omit-normalized before canonicalization, so ``before: []`` and
    member absence share one canonical form — emitting the empty array would be writing a form
    the digest erases, and two extractors that disagreed about it would still agree about the
    digest while comparing unequal as models.
    """
    partial = extract(sc.build_empty_gates_graph())
    assert _interrupts(partial).before is None
    assert _interrupts(partial).after == ("act_step",)

    assert _runtime(extract(sc.build_ungated_graph())).interrupts is None


@pytest.mark.parametrize(
    ("factory", "present"),
    [(sc.build_gated_graph, True), (sc.build_ungated_graph, False)],
    ids=["attached", "absent"],
)
def test_checkpointer_presence_is_emitted_either_way(factory: Any, present: bool) -> None:
    """§4.1: "a known fact either way at compiled level, so both values are emitted".

    The `false` value is the load-bearing one. IR-SPEC §3.7 gives ``present`` no default so
    omit-normalization can never strip it, which is what makes ``{present: false}`` — "there is
    no checkpointer" — a different document from the slot's absence, which is what a
    builder-level extraction says ("unknown, never guessed").
    """
    assert _checkpointer(extract(factory())).present is present


def test_the_builder_level_carries_no_runtime_block_at_all() -> None:
    """The §7.1 asymmetry, checked as the pair it is rather than on one side.

    "Full at compiled level; absent (never guessed) at builder level" is a statement about two
    extractions of one graph, so both are run here: the uncompiled builder has no ``runtime``
    and the compiled object has one, and that is the *only* difference between them.
    """
    builder = sg.build_sentinel_graph()
    from_builder = extract(builder)
    from_compiled = extract(builder.compile())

    assert from_builder.ir.runtime is None
    assert from_compiled.ir.runtime is not None
    assert to_data(from_builder)["ir"] == {
        key: value for key, value in to_data(from_compiled)["ir"].items() if key != "runtime"
    }


@pytest.mark.skipif(not substrate.HAS_NODE_DEFAULTS, reason=substrate.NODE_DEFAULTS_REASON)
def test_a_folded_default_reaches_the_ir_and_its_resolution_reaches_provenance() -> None:
    """§4.1's folded ``set_node_defaults``, both halves.

    ``compile()`` writes the graph-level default into the builder's own node spec, so the
    *value* arrives through §3 like an authored one — that is why the IR below carries a
    ``retry_policy`` on the node that declared none. What has no ir 1.0 slot is which node
    inherited it, and §4.1 puts exactly that in provenance.
    """
    envelope = extract(sc.build_folded_defaults_graph())

    inherited = _annotations(envelope, "plan_step").retry_policy
    declared = _annotations(envelope, "act_step").retry_policy
    assert inherited is not None and inherited.max_attempts == 5
    assert declared is not None and declared.max_attempts == 2

    folded = _surfaces(envelope).folded_defaults
    assert [(entry.node, entry.member) for entry in folded] == [("plan_step", "retry_policy")]


def test_a_graph_with_no_defaults_records_no_folding() -> None:
    """The converse, so the record above is a discriminator rather than a constant."""
    assert _surfaces(extract(sc.build_ungated_graph())).folded_defaults == ()


def test_a_discovered_subgraph_is_its_parent_node_and_the_document_is_complete() -> None:
    """§4.1, ratified as DEC-19: the parent node only, and that document is *conforming*.

    "ir 1.0 carries a discovered subgraph as its parent node only: child nodes, child edges,
    and the child's own ``entry``/``finish``/Σ are NOT emitted; the discovered-parent set is
    recorded in the provenance envelope, which is the conforming disclosure — such a document
    is complete, carries no warning for the unexpansion, and reaches the §8 strict-mode bar."

    So the last assertion is the load-bearing one, and it is the one that changed when the
    ruling landed: a subgraph-bearing workflow emits **no** ``unsupported-construct``, because
    an IR that is complete must not say it is partial. Child expansion is the named first 1.x
    feature; §4.1 forbids improvising any of it here.
    """
    envelope = extract(sc.build_subgraph_parent())

    assert _surfaces(envelope).subgraphs == ("legs",)
    assert [node.id for node in envelope.ir.nodes] == [
        "legs",
        "plan_step",
        "summarize_step",
    ]
    assert not any("/" in node.id for node in envelope.ir.nodes)
    assert _warnings_of(envelope, ExtractionWarningCode.UNSUPPORTED_CONSTRUCT) == ()


def test_a_subgraph_bearing_workflow_reaches_the_strict_mode_bar() -> None:
    """The consequence DEC-19 rules on, stated as the property §8 defines it by.

    §8 makes "a warning-free extraction" part of the strict-mode bar. Under the ruling an
    unexpanded subgraph is not a defect, so a workflow that contains one must be able to be
    warning-free — otherwise every such workflow would sit permanently outside strict mode for
    using a construct the substrate supports and ir 1.0 deliberately summarises.

    The one thing this graph *does* warn about is unrelated and expected: its nodes carry no
    declared contract, so the D-011 defaults apply and say so. That is the §4 annotation floor,
    not a statement about the subgraph.
    """
    envelope = extract(sc.build_subgraph_parent())

    codes = {warning.code for warning in envelope.warnings}
    assert codes <= {ExtractionWarningCode.CONTRACT_DEFAULTED}
    assert all(
        warning.detail.get("ir_partial") is not True
        for warning in envelope.warnings
        if warning.detail
    )


@pytest.mark.skipif(
    not substrate.HAS_NODE_ERROR_HANDLER, reason=substrate.NODE_ERROR_HANDLER_REASON
)
def test_the_error_handler_map_lands_in_provenance() -> None:
    """§4.1: ``node_error_handler_map`` "still lands in provenance only — no ir 1.0 slot"."""
    envelope = extract(sc.build_error_handler_graph())

    handlers = _surfaces(envelope).error_handlers
    assert list(handlers) == ["plan_step"]
    assert handlers["plan_step"].startswith("__error_handler__")


def test_a_builder_level_extraction_records_no_compiled_surfaces() -> None:
    """The provenance carrier is absent where there is no compiled level to read."""
    assert extract(sg.build_sentinel_graph()).extracted_from.compiled is None


@pytest.mark.parametrize(
    ("gates", "construct"),
    [
        ("not-a-sentinel", "interrupt-gates-unrecognized"),
        (17, "interrupt-gates-unrecognized"),
        ([object()], "interrupt-gate-unrepresentable"),
        ([""], "interrupt-gate-unrepresentable"),
    ],
    ids=["stray-string", "not-iterable", "not-a-name", "empty-name"],
)
def test_an_unmappable_gate_list_is_warned_rather_than_raised(
    gates: object, construct: str
) -> None:
    """A compiled attribute holding a value with no ir 1.0 form is §8's ``unsupported-construct``.

    The substrate types the member ``All | Sequence[str]`` and ``compile()`` refuses a gate
    naming an unknown node, so none of these is reachable through the public API — they are
    what a hand-built or a future Pregel could carry, and §2 is emphatic that a *supported*
    object with an unmappable construct is warned inside the IR, never raised.
    """
    compiled = sc.build_ungated_graph()
    compiled.interrupt_before_nodes = gates  # type: ignore[assignment]

    envelope = extract(compiled)

    warnings = _warnings_of(envelope, ExtractionWarningCode.UNSUPPORTED_CONSTRUCT)
    assert [warning.detail["construct"] for warning in warnings] == [construct]
    assert _runtime(envelope).interrupts is None


# ── §4.3 rule 1 — builder-authoritative when available ───────────────────────────────────


def test_the_compiled_family_is_registered_and_routes_through_the_backreference() -> None:
    """§2 row 1 / §4.3 rule 1: the compiled object takes §4, whose topology is §3's."""
    compiled = sg.build_sentinel_graph().compile()
    dispatch = classify(compiled)

    assert dispatch.family is ObjectFamily.COMPILED
    assert dispatch.builder is compiled.builder
    assert extract(compiled).extracted_from.family is ObjectFamily.COMPILED


def test_the_provenance_names_the_compiled_object_not_its_builder() -> None:
    """``extracted_from.source`` is the object handed to ``extract()`` (IR-SPEC §4.1)."""
    envelope = extract(sg.build_sentinel_graph().compile())

    assert envelope.extracted_from.source == "langgraph:CompiledStateGraph"


@pytest.mark.parametrize("name", _every_fixture())
def test_every_compiled_fixture_extracts_to_a_digestible_ir(name: str) -> None:
    """Extraction is total over these shapes, and every result has a ``graph_version``.

    Digesting is the half that makes "spec-shaped" checkable rather than asserted: a document
    canonicalization refuses is one ``extract()`` must not emit, so a gate id, a state key or
    a path_map label that reached the IR in the wrong form fails here.
    """
    envelope = extract(sc.EXTRACTABLE_COMPILED[name]())

    assert envelope.ir.nodes
    assert envelope.graph_version().startswith("sha256:")
    assert envelope.extracted_from.family is ObjectFamily.COMPILED


@pytest.mark.parametrize("name", sorted(sc.REFUSED_COMPILED))
def test_a_compiled_object_with_no_usable_drawing_is_refused_at_the_boundary(name: str) -> None:
    """§2's error posture on the §4 family: refuse at the boundary, never a partial IR."""
    with pytest.raises(ExtractionError) as raised:
        extract(sc.REFUSED_COMPILED[name]())

    assert raised.value.reason in {
        ExtractionErrorReason.NO_EXTRACTABLE_SURFACE,
        ExtractionErrorReason.EMPTY_NODE_SET,
    }
    assert raised.value.family is ObjectFamily.COMPILED


def test_extracting_before_and_after_compile_yields_one_topology_and_one_state() -> None:
    """Rule 1 as the property it is: compiling adds ``runtime`` and changes nothing else.

    Checked at the digest, not only at the model. The two documents differ by exactly one
    slot, so stripping it must reproduce the builder's own ``graph_version`` string — which is
    what "the builder-derived IR stays unchanged" has to mean for a hash-scoped IR.
    """
    builder = sg.build_sentinel_graph()
    before = extract(builder)
    after = extract(builder.compile())

    assert graph_version(after.ir.model_copy(update={"runtime": None})) == before.graph_version()
    # …and the two levels are nonetheless different *documents*: `runtime` is in hash scope
    # (IR-SPEC §6.4), and a compiled extraction always carries one because checkpointer
    # presence is a known fact there and an unknown at builder level (§4.1, §7.1). Asserted
    # rather than left implied, because it is the fact a snapshot consumer has to plan around.
    assert after.graph_version() != before.graph_version()


@pytest.mark.skipif(not substrate.HAS_NODE_DEFAULTS, reason=substrate.NODE_DEFAULTS_REASON)
def test_a_graph_level_retry_default_reaches_the_ir_from_the_moment_it_is_compiled() -> None:
    """The one before/after difference that is the substrate's rather than this build's.

    ``compile()`` writes ``set_node_defaults`` into the builder's own node specs, in place, so
    a node that declared no ``retry_policy`` has one afterwards — at *either* extraction level,
    because there is only one builder object. Extraction never compiles anything (§1 rule 2),
    so this is a fact about the object it was handed, and the honest thing is to record which
    nodes got theirs that way rather than to hide the change.
    """
    compiled = sc.build_folded_defaults_graph()
    from_builder = extract(compiled.builder)

    assert _annotations(extract(compiled), "plan_step").retry_policy is not None
    inherited = [node for node in from_builder.ir.nodes if node.id == "plan_step"]
    assert inherited[0].annotations is not None
    assert inherited[0].annotations.retry_policy is not None


def test_a_direct_call_without_a_sidecar_reading_still_extracts() -> None:
    """``extract_compiled`` is callable outside the entry point, as ``extract_builder`` is."""
    envelope = extract_compiled(classify(sg.build_sentinel_graph().compile()))

    assert envelope.extracted_from.sidecar is None
    assert envelope.ir.runtime is not None


# ── §4.2 / §4.3 rules 2–3 — the cross-check and the disagreement rule ────────────────────


def test_two_readings_that_agree_record_a_cross_check_and_warn_about_nothing() -> None:
    """The mainstream case: a declared ``path_map`` router draws exactly as it was declared.

    This is the test that decides whether the cross-check is usable at all. §8 makes a
    warning-free extraction part of the strict-mode bar, so a comparison that fired on an
    ordinary workflow would put every workflow outside it — the absence of a divergence here
    is the claim, and the recorded ``performed`` is what stops that absence from being vacuous.
    """
    envelope = extract(sc.build_agreeing_graph())

    check = _cross_check(envelope)
    assert check.performed is True
    assert check.declined is None
    assert _warnings_of(envelope, ExtractionWarningCode.BUILDER_COMPILED_DIVERGENCE) == ()


def test_a_seeded_divergence_is_warned_and_the_builder_ir_is_unchanged() -> None:
    """§4.3 rule 3, both halves, on a graph whose two levels genuinely disagree.

    The builder gained an edge and a node after the object was compiled, so the drawing is a
    reading of the old topology. Rule 3: "builder wins for topology intent … any topology
    divergence leaves the builder-derived IR unchanged and MUST emit the
    ``builder-compiled-divergence`` warning recording both readings". So the added edge is in
    the IR, the drawing's absence of it is in the warning, and the IR is byte-identical to
    what §3 alone produces from the same builder.
    """
    compiled = sc.build_seeded_divergence()

    envelope = extract(compiled)
    (warning,) = _warnings_of(envelope, ExtractionWarningCode.BUILDER_COMPILED_DIVERGENCE)

    assert ("plan_step", "summarize_step") in _pairs(envelope)
    assert warning.detail["delta"]["edges_only_in_builder"] == (("plan_step", "summarize_step"),)
    assert warning.detail["delta"]["nodes_only_in_builder"] == ("summarize_step",)
    assert warning.detail["xray"] is CROSS_CHECK_XRAY
    assert "plan_step" in warning.detail["builder"]["nodes"]

    from_builder_alone = extract(compiled.builder)
    assert graph_version(envelope.ir.model_copy(update={"runtime": None})) == (
        from_builder_alone.graph_version()
    )


def test_the_divergence_warning_never_moves_the_digest() -> None:
    """Warnings ride the envelope, outside hash scope (§8; IR-SPEC §6.4) — checked, not assumed.

    The same builder is extracted twice, once through the level that warns and once through
    the one that cannot, and the two digests agree once ``runtime`` is set aside.
    """
    compiled = sc.build_natural_divergence()
    warned = extract(compiled)
    quiet = extract(compiled.builder)

    assert _warnings_of(warned, ExtractionWarningCode.BUILDER_COMPILED_DIVERGENCE)
    assert _warnings_of(quiet, ExtractionWarningCode.BUILDER_COMPILED_DIVERGENCE) == ()
    assert graph_version(warned.ir.model_copy(update={"runtime": None})) == quiet.graph_version()


def test_the_implicit_edge_a_drawing_invents_is_reported_as_the_compiled_side_s() -> None:
    """§4.2's own warning made observable: the drawing terminates where nothing declared it.

    A router-only graph declares no END wiring, so §3 reads ``finish: []`` (DEC-18's
    warning-scoped form) while the Pregel loop's drawing ends at the node it runs out of work
    on. The delta names the *compiled* side as the extra, which is the direction §4.3 rule 3
    requires — the builder is not missing anything, the drawing added something.
    """
    envelope = extract(sc.build_natural_divergence())
    (warning,) = _warnings_of(envelope, ExtractionWarningCode.BUILDER_COMPILED_DIVERGENCE)

    assert warning.detail["delta"] == {"finish_only_in_compiled": ("act_step",)}
    assert envelope.ir.finish == ()


def test_an_xray_expanded_subgraph_is_not_reported_as_a_divergence() -> None:
    """§4.3 rule 2's "modulo … implicit-edge heuristics", applied to the one xray performs.

    ``xray=True`` draws *inside* the subgraph the builder reading holds as a single node, so
    the raw edge sets cannot match. Folding a drawn ``parent:child`` id to its top-level node
    (§4.2: "drawn ``:``-prefixed ids map to ledger path segments") is what puts the readings at
    one granularity; without it every workflow with a subgraph would warn, permanently.
    """
    envelope = extract(sc.build_subgraph_parent())

    assert _cross_check(envelope).performed is True
    assert _warnings_of(envelope, ExtractionWarningCode.BUILDER_COMPILED_DIVERGENCE) == ()


def test_a_top_level_self_loop_still_diverges_when_the_drawing_lacks_it() -> None:
    """The folding rule excludes expansion artifacts, not genuine self-loops.

    An edge is dropped from the comparison only when at least one endpoint *was* expanded, so
    a real ``n → n`` edge — which a retry or a poll loop is — is still compared. Seeded on the
    builder after compilation so the drawing is known not to carry it.
    """
    compiled = sc.build_ungated_graph()
    compiled.builder.edges.add(("plan_step", "plan_step"))

    envelope = extract(compiled)
    (warning,) = _warnings_of(envelope, ExtractionWarningCode.BUILDER_COMPILED_DIVERGENCE)

    assert warning.detail["delta"]["edges_only_in_builder"] == (("plan_step", "plan_step"),)


@pytest.mark.parametrize(
    ("factory", "level"),
    [
        (sc.build_armed_channel_graph, "the compiled graph"),
        (sc.build_armed_channel_subgraph_parent, "the subgraph at 'legs'"),
    ],
    ids=["root", "subgraph"],
)
def test_the_cross_check_declines_where_running_it_would_execute_user_code(
    factory: Any, level: str
) -> None:
    """§4.3 rule 2 is a SHOULD; §1 rule 1 is a MUST. The SHOULD stands down.

    ``get_graph()`` runs the Pregel loop symbolically and asks each channel whether it has a
    value — ``channel.get()``. For a LangGraph channel that is library code; the fixture here
    binds a user-authored one whose ``get()`` records and then raises, so a cross-check that
    ran anyway would fail this test twice over: once on the recorded call and once on the
    exception. Nothing is lost but a diagnostic, and the decline is recorded so the missing
    warning is never read as "the readings agreed".

    The subgraph case is not redundant: ``xray`` draws every discovered subgraph with the same
    loop, so a precondition checked only at the root would not be one.
    """
    envelope = extract(factory())

    check = _cross_check(envelope)
    assert check.performed is False
    assert check.declined is not None
    assert level in check.declined
    assert "tests:ArmedChannel" in check.declined
    assert sc.TRIPPED == ["ValueType"] * len(sc.TRIPPED)
    assert _warnings_of(envelope, ExtractionWarningCode.BUILDER_COMPILED_DIVERGENCE) == ()


def test_the_decline_is_about_the_channel_class_not_about_what_its_body_does() -> None:
    """The precondition cannot be "decline only the dangerous ones" — that needs running them.

    ``RecordingChannel`` extends a stock channel and would have answered every question the
    drawing asked, harmlessly. It is declined anyway, because the only way to learn that is to
    execute it, and §1 rule 1 is what forbids finding out. The recorded log staying empty is
    the proof that the decline happened before any call, not after one.
    """
    envelope = extract(sc.build_recording_channel_graph())

    check = _cross_check(envelope)
    assert check.performed is False
    assert check.declined is not None
    assert "tests:RecordingChannel" in check.declined
    assert sc.TRIPPED == ["ValueType"] * len(sc.TRIPPED)


def test_the_declined_cross_check_costs_the_diagnostic_and_nothing_else() -> None:
    """A declined cross-check still yields the whole IR, the runtime block and the digest."""
    envelope = extract(sc.build_armed_channel_graph())

    assert [node.id for node in envelope.ir.nodes] == ["plan_step"]
    assert _checkpointer(envelope).present is False
    assert envelope.graph_version().startswith("sha256:")


def test_the_cross_check_declines_on_a_document_with_a_dynamic_router() -> None:
    """§4.3 rule 2 is a SHOULD, and on this document the drawn reading is a different graph.

    §4.2 already grades ``get_graph()`` "heuristic for dynamic branches"; what is *measured* here
    is how far that reaches. At the pinned substrate a graph whose router declares no targets
    draws exactly two edges — ``__start__ → router`` and ``router → __end__`` — and drops **every
    declared edge beyond the router**, including the plain ``(act_step, END)`` this fixture wires.
    Comparing against that would report the drawing's own limit as a topology divergence on every
    map-reduce workflow, permanently and for no diagnostic gain, so the comparison is declined and
    ``CrossCheck.declined`` records why. The IR, the runtime block and the digest are unaffected —
    the same cost a declined cross-check has always had.
    """
    compiled = sr.build_dynamic_send_hinted_graph().compile()
    drawn = compiled.get_graph(xray=True)
    envelope = extract(compiled)

    assert {(edge.source, edge.target) for edge in drawn.edges} == {
        ("__start__", "plan_step"),
        ("plan_step", "__end__"),
    }
    check = _cross_check(envelope)
    assert check.performed is False
    assert check.declined is not None
    assert "no static target set (plan_step)" in check.declined
    assert envelope.warnings_of(ExtractionWarningCode.BUILDER_COMPILED_DIVERGENCE) == ()
    assert envelope.ir.ir_version == "1.1"
    assert envelope.graph_version().startswith("sha256:")


def test_the_cross_check_still_runs_where_no_router_is_dynamic() -> None:
    """The decline is a test on the builder reading's own dynamic sources and nothing else."""
    envelope = extract(sr.build_send_forms_graph().compile())

    assert _cross_check(envelope).performed is True


def test_a_get_graph_that_raises_declines_rather_than_failing_the_extraction() -> None:
    """The drawing is a foreign 250-step symbolic execution; it may cost a diagnostic only."""
    compiled = sc.build_ungated_graph()

    def _boom(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("the drawing blew up")

    compiled.get_graph = _boom  # type: ignore[method-assign]

    envelope = extract(compiled)

    check = _cross_check(envelope)
    assert check.performed is False
    assert check.declined is not None
    assert "did not return a readable drawing" in check.declined
    assert envelope.ir.nodes


def test_the_armed_channel_is_armed() -> None:
    """A tripwire nobody trips proves nothing: the channel really does raise when asked."""
    channel = sc.ArmedChannel(str)

    with pytest.raises(sc.ChannelSentinelError):
        channel.get()
    with pytest.raises(sc.ChannelSentinelError):
        channel.update(["x"])
    assert sc.TRIPPED == ["ArmedChannel.get", "ArmedChannel.update"]
    sc.TRIPPED.clear()


# ── §4.3 rule 4 — the builderless downgrade ──────────────────────────────────────────────


def test_a_builderless_pregel_is_warned_exactly_once() -> None:
    """§8: ``compiled-only-extraction`` is "emitted once per extraction"."""
    envelope = extract(sc.build_gated_pregel())

    assert len(_warnings_of(envelope, ExtractionWarningCode.COMPILED_ONLY_EXTRACTION)) == 1


def test_the_downgrade_warning_carries_what_its_registry_row_names() -> None:
    """§8's "what it carries" column: object type, extraction level, the blanket downgrade."""
    envelope = extract(sc.build_gated_pregel())
    (warning,) = _warnings_of(envelope, ExtractionWarningCode.COMPILED_ONLY_EXTRACTION)

    assert warning.detail["object_type"] == "langgraph:Pregel"
    assert warning.detail["extraction_level"] == "compiled"
    assert "knowability class" in warning.detail["downgrade"]
    assert warning.node is None


def test_the_downgrade_extracts_a_topology_and_leaves_state_absent() -> None:
    """What rule 4 licenses and what it does not.

    Topology comes from the one surface §2 names for this family, one knowability class down.
    Σ has no compiled-level source at all — §3's ``state`` row reads a ``StateGraph``'s schemas
    and input schema, and a raw Pregel declares which of its channels are state nowhere — so
    ``state`` is absent, which is §0's Runtime-only discipline rather than a guess dressed as
    a downgrade.
    """
    envelope = extract(sc.build_gated_pregel())

    assert [node.id for node in envelope.ir.nodes] == ["pregel_step"]
    assert envelope.ir.entry == "pregel_step"
    assert envelope.ir.state is None


def test_the_compiled_level_slots_are_not_downgraded() -> None:
    """§7.1 rates ``interrupts``/``checkpointer`` Full "at the compiled level only".

    A builderless Pregel *is* that level, so rule 4's one-class downgrade — which is scoped to
    "every §3-derived field" — does not reach them and they are carried in full.
    """
    envelope = extract(sc.build_gated_pregel())

    assert _interrupts(envelope).before == ("pregel_step",)
    assert _checkpointer(envelope).present is True


def test_the_downgrade_defaults_every_contract_and_says_so() -> None:
    """The contract half of the downgrade, read back through ANNOTATION §5's own lookup.

    §3's decorator and tool-carried tiers are reached through ``StateNodeSpec.runnable``, which
    this family has no counterpart for that any spec names, so those tiers withdraw and the
    D-011 defaults apply — §7.1's "Declared-trusted; D-011 default → Inferred-warned" is
    literally one class down, which is why this is the rule applied rather than a second
    decision. Checked through ``slot_grade`` because §5 makes that the normative question.
    """
    from gebra.extraction import SlotGrade

    envelope = extract(sc.build_gated_pregel())

    assert envelope.slot_grade("pregel_step", "effect") is SlotGrade.DEFAULTED
    assert envelope.slot_grade("pregel_step", "idempotent") is SlotGrade.DECLARED
    assert _warnings_of(envelope, ExtractionWarningCode.CONTRACT_DEFAULTED)


def test_a_sidecar_still_wins_its_slots_on_the_downgraded_path(tmp_path: Path) -> None:
    """The ``gebra.toml`` tier is a §2 surface, not a §3-derived field, so it is not downgraded.

    Dropping a declaration an author wrote in a file would be a silent loss of exactly the kind
    §8's taxonomy exists to make impossible — and there would be no warning for it, because no
    §8 row says "the extractor ignored your sidecar".
    """
    sidecar = tmp_path / "gebra.toml"
    sidecar.write_text(
        'schema = "gebra-sidecar-v1"\n[nodes.pregel_step]\neffects = ["network"]\n',
        encoding="utf-8",
    )

    envelope = extract(sc.build_gated_pregel(), sidecar=sidecar)

    assert _annotations(envelope, "pregel_step").effect == ("network",)
    assert envelope.extracted_from.sidecar == str(sidecar)


def test_a_drawn_router_row_becomes_a_conditional_edge_with_its_declared_label() -> None:
    """A drawn conditional edge's ``data`` is the ``path_map`` label the declaration carried.

    Read from the drawing rather than invented: an unlabelled row falls to the identity map
    ``{target: target}``, which is the substrate's own conversion for a list-valued
    ``path_map`` and the convention §3's ``ends`` row already reads across. No ``condition`` is
    emitted — that slot is "the declared branch name" and a drawing carries none, so inventing
    one would put a string this build made up inside ``graph_version``.
    """
    compiled = sc.build_agreeing_graph()
    stripped = compiled.copy()
    del stripped.builder

    envelope = extract(stripped)

    (conditional,) = [edge for edge in envelope.ir.edges if isinstance(edge, ConditionalEdge)]
    assert conditional.from_ == "plan_step"
    assert conditional.path_map == {"act": "act_step", "done": "summarize_step"}
    assert conditional.condition is None


# ── §2's family is the protocol, so a third-party Pregel is in scope by definition ───────
#
# §2 defines ``is_pregel(x)`` as ``isinstance(x, PregelProtocol)``. LangGraph's own objects
# cannot produce most of the shapes below — a drawing whose edge targets a reserved sentinel,
# a node name with no representable id, a subgraph getter that raises — so a build that only
# ever met LangGraph objects would carry these guards untested and would discover them on the
# first third-party implementation instead.


def _drawn(nodes: Any, edges: Any, **attributes: Any) -> Any:
    """A real builderless ``Pregel`` answering with an authored drawing (see the note above)."""
    return sc.drawn_pregel(sc.Drawing(nodes, edges), **attributes)


@pytest.mark.parametrize(
    ("nodes", "edges", "constructs"),
    [
        (
            {"__start__": None, "n1": None, "__end__": None},
            [sc.DrawnEdge("__start__", "__end__")],
            ["start-to-end-edge", "missing-start-wiring", "missing-finish-wiring"],
        ),
        (
            {"__start__": None, "n1": None, "": None},
            [sc.DrawnEdge("__start__", "n1"), sc.DrawnEdge("n1", "__end__")],
            ["drawn-node-unrepresentable"],
        ),
        (
            {"__start__": None, "n1": None},
            [sc.DrawnEdge("__start__", "n1"), sc.DrawnEdge("n1", "__start__")],
            ["reserved-drawn-target", "missing-finish-wiring"],
        ),
        (
            {"__start__": None, "n1": None},
            [sc.DrawnEdge("__start__", ""), sc.DrawnEdge("n1", "")],
            [
                "drawn-node-unrepresentable",
                "drawn-node-unrepresentable",
                "missing-start-wiring",
                "missing-finish-wiring",
            ],
        ),
    ],
    ids=["start-to-end", "unnameable-node", "edge-into-start", "unnameable-reference"],
)
def test_a_drawing_this_ir_cannot_carry_is_warned_never_raised(
    nodes: Any, edges: Any, constructs: list[str]
) -> None:
    """§2: a *supported* object with unmappable constructs extracts with warnings.

    Each drawing here holds one shape ir 1.0 has no form for — a START→END incidence, a node
    whose name has no representable id, an edge into the reserved START — and each is reported
    with the §8 code kept for exactly that, with the IR honestly partial at the location.
    """
    envelope = extract(_drawn(nodes, edges))

    warnings = _warnings_of(envelope, ExtractionWarningCode.UNSUPPORTED_CONSTRUCT)
    assert [warning.detail["construct"] for warning in warnings] == constructs
    assert all(warning.detail["ir_partial"] for warning in warnings)


def test_a_labelled_drawn_row_into_end_becomes_an_end_path_map_label() -> None:
    """The (m3) END incidence, read off a drawing rather than off a ``BranchSpec``.

    A labelled conditional row into ``__end__`` is a ``path_map`` entry valued ``"END"`` — the
    forced spelling DEC-18 recorded, because ``"__end__"`` is a reserved segment the IR never
    emits. And because it *is* an END incidence, the missing-finish warning does not fire: that
    is DEC-18's scoping, applied to this surface as well as to the builder's.
    """
    envelope = extract(
        _drawn(
            {"__start__": None, "n1": None, "__end__": None},
            [
                sc.DrawnEdge("__start__", "n1"),
                sc.DrawnEdge("n1", "__end__", data="done", conditional=True),
            ],
        )
    )

    (conditional,) = [edge for edge in envelope.ir.edges if isinstance(edge, ConditionalEdge)]
    assert conditional.path_map == {"done": "END"}
    assert envelope.ir.finish == ()
    assert _warnings_of(envelope, ExtractionWarningCode.UNSUPPORTED_CONSTRUCT) == ()


def test_two_entry_members_collapse_to_the_list_form() -> None:
    """IR-SPEC §6.3: ``entry`` is a scalar iff the wired set is a singleton, a list otherwise."""
    envelope = extract(
        _drawn(
            {"__start__": None, "n1": None, "n2": None, "__end__": None},
            [
                sc.DrawnEdge("__start__", "n1"),
                sc.DrawnEdge("__start__", "n2"),
                sc.DrawnEdge("n1", "__end__"),
            ],
        )
    )

    assert envelope.ir.entry == ("n1", "n2")
    assert envelope.ir.finish == "n1"


@pytest.mark.parametrize(
    ("nodes", "edges"),
    [
        ("not a mapping", ()),
        ({"__start__": None, "n1": None}, "not iterable"),
        ({"__start__": None, "n1": None, 7: None}, [object(), sc.DrawnEdge("__start__", "n1")]),
    ],
    ids=["nodes-not-a-mapping", "edges-not-iterable", "members-of-the-wrong-shape"],
)
def test_a_drawing_of_the_wrong_shape_degrades_rather_than_crashing(nodes: Any, edges: Any) -> None:
    """The drawing is a foreign object; reading it is defensive, never trusting.

    Each of these either yields an IR with what could be read or reaches §2's boundary refusal
    — never a ``TypeError`` out of ``extract()``, which is the one outcome §2 does not admit.
    """
    try:
        envelope = extract(_drawn(nodes, edges))
    except ExtractionError as error:
        assert error.family is ObjectFamily.COMPILED
        return
    assert envelope.ir.nodes


def _raiser(*args: Any, **kwargs: Any) -> Any:
    raise RuntimeError("subgraph discovery blew up")


@pytest.mark.parametrize(
    "getter",
    [
        None,
        _raiser,
        lambda *a, **k: "not a sequence of pairs",
        lambda *a, **k: [("legs",), (7, None)],
        lambda *a, **k: [("", None)],
    ],
    ids=["no-getter", "getter-raises", "not-pairs", "wrong-members", "unnameable-parent"],
)
def test_unreadable_subgraph_discovery_costs_provenance_and_nothing_else(getter: Any) -> None:
    """§4.1's discovery is provenance with no ir 1.0 slot, so it may never fail an extraction."""
    workflow = _drawn(
        {"__start__": None, "n1": None, "__end__": None},
        [sc.DrawnEdge("__start__", "n1"), sc.DrawnEdge("n1", "__end__")],
    )
    workflow.get_subgraphs = getter

    envelope = extract(workflow)

    assert _surfaces(envelope).subgraphs == ()
    assert [node.id for node in envelope.ir.nodes] == ["n1"]


@pytest.mark.parametrize(
    ("handlers", "recorded"),
    [
        ("not a mapping", {}),
        ({"n1": 7, 7: "n1"}, {}),
        ({"": "handler", "n1": ""}, {}),
        ({"n1": "handler"}, {"n1": "handler"}),
    ],
    ids=["not-a-mapping", "wrong-member-types", "unnameable-members", "readable"],
)
def test_the_error_handler_map_is_read_defensively(handlers: Any, recorded: Any) -> None:
    """Same posture as discovery: a provenance-only fact never costs an extraction."""
    workflow = _drawn(
        {"__start__": None, "n1": None, "__end__": None},
        [sc.DrawnEdge("__start__", "n1"), sc.DrawnEdge("n1", "__end__")],
        node_error_handler_map=handlers,
    )

    assert _surfaces(extract(workflow)).error_handlers == recorded


def test_a_compiled_object_with_no_readable_channels_declines_the_cross_check() -> None:
    """The never-invokes precondition is conservative in the safe direction.

    A compiled object whose channel mapping cannot be read is not "no user channels" — it is
    "unknown", and running a symbolic execution to find out is exactly what the precondition
    exists to avoid.
    """
    compiled = sc.build_ungated_graph()
    compiled.channels = "not a mapping"  # type: ignore[assignment]

    check = _cross_check(extract(compiled))

    assert check.performed is False
    assert check.declined is not None
    assert "no readable channel mapping" in check.declined


def test_a_subgraph_entry_of_the_wrong_shape_is_skipped_by_the_precondition_scan() -> None:
    """The scan reads ``(name, graph)`` pairs; anything else contributes no level to check."""
    compiled = _paired(*_AGREEING_DRAWING)
    compiled.get_subgraphs = lambda *args, **kwargs: [("legs",), "not a pair"]

    assert _cross_check(extract(compiled)).performed is True


def test_a_subgraph_getter_that_raises_declines_the_cross_check() -> None:
    """The scan cannot see below, so it must not assume there is nothing there."""
    compiled = sc.build_subgraph_parent()

    def _boom(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("discovery blew up")

    compiled.get_subgraphs = _boom  # type: ignore[method-assign]

    check = _cross_check(extract(compiled))

    assert check.performed is False
    assert check.declined is not None
    assert "could not be read" in check.declined


def test_a_builder_with_no_defaults_member_records_no_folding() -> None:
    """``_node_defaults`` is a private member no memo pins; losing it costs a diagnostic only.

    Unskipped on every matrix cell, because the shape it pins — a builder with no
    ``_node_defaults`` member — is reached from two directions: by deleting it where
    ``set_node_defaults`` exists, and natively on the two frozen cells below langgraph 1.2.0,
    where the member was never there. Gating this one on the API would have skipped it exactly
    where its subject is the *default* state (EX-17 / PD-038 Finding 2), so the fixture
    follows the substrate and the member is removed only if it is present.
    """
    compiled = (
        sc.build_folded_defaults_graph()
        if substrate.HAS_NODE_DEFAULTS
        else sc.build_ungated_graph()
    )
    if hasattr(compiled.builder, "_node_defaults"):
        # The member arrived with `set_node_defaults` in langgraph 1.2.0, so on the two frozen
        # matrix cells below it there is no attribute for `mypy` to resolve — the ignore is
        # load-bearing there and unnecessary on 1.2+, which `unused-ignore` reconciles.
        del compiled.builder._node_defaults  # type: ignore[attr-defined, unused-ignore]
    assert not hasattr(compiled.builder, "_node_defaults")

    assert _surfaces(extract(compiled)).folded_defaults == ()
    assert extract(compiled).ir.nodes


#: The drawing a plain two-node builder would produce, authored rather than derived — so the
#: cross-check can be exercised against a *known* compiled reading and the "modulo" rules can
#: be checked one at a time. §2 admits the shape in terms: row 1 is "any Pregel exposing
#: ``.builder``", which a third-party implementation reaches by protocol registration.
_AGREEING_DRAWING = (
    {"__start__": None, "plan_step": None, "act_step": None, "__end__": None},
    [
        sc.DrawnEdge("__start__", "plan_step"),
        sc.DrawnEdge("plan_step", "act_step"),
        sc.DrawnEdge("act_step", "__end__"),
    ],
)


def _paired(nodes: Any, edges: Any) -> Any:
    """A real compiled two-node graph answering with an authored drawing."""
    return sc.drawn_compiled(sc.Drawing(nodes, edges))


def test_a_compiled_object_with_no_subgraph_getter_still_cross_checks() -> None:
    """The scan covers what it can reach; an object with no getter has nothing below it."""
    compiled = _paired(*_AGREEING_DRAWING)
    compiled.get_subgraphs = None

    envelope = extract(compiled)

    assert _cross_check(envelope).performed is True
    assert _surfaces(envelope).subgraphs == ()
    assert _warnings_of(envelope, ExtractionWarningCode.BUILDER_COMPILED_DIVERGENCE) == ()


def test_a_compiled_object_with_no_callable_drawing_declines() -> None:
    """``get_graph`` is the cross-check's only surface; without one there is nothing to derive."""
    compiled = sc.build_ungated_graph()
    compiled.get_graph = None  # type: ignore[assignment]

    check = _cross_check(extract(compiled))

    assert check.performed is False
    assert check.declined is not None


def test_a_start_to_end_incidence_is_dropped_from_both_readings() -> None:
    """A sentinel-to-sentinel edge has no ir 1.0 carrier, so neither reading may carry one.

    §3 already drops it with a warning; the cross-check has to drop it too, or the drawing
    would look like it declared an incidence the IR deliberately does not — and the drawing
    below is authored precisely because LangGraph's own never draws one.
    """
    envelope = extract(
        _paired(
            _AGREEING_DRAWING[0],
            [*_AGREEING_DRAWING[1], sc.DrawnEdge("__start__", "__end__")],
        )
    )

    assert _cross_check(envelope).performed is True
    assert _warnings_of(envelope, ExtractionWarningCode.BUILDER_COMPILED_DIVERGENCE) == ()


def test_a_drawn_sentinel_incidence_on_an_unnameable_node_is_not_a_reading() -> None:
    """A drawn id with no §5 form contributes to neither reading, on either side.

    It cannot: ``entry``/``finish`` name node ids, and there is no id here. So the two extra
    edges below change nothing — the readings still agree — which is the honest outcome for a
    reference the grammar admits no spelling for.
    """
    envelope = extract(
        _paired(
            _AGREEING_DRAWING[0],
            [
                *_AGREEING_DRAWING[1],
                sc.DrawnEdge("__start__", ""),
                sc.DrawnEdge("", "__end__"),
            ],
        )
    )

    assert _cross_check(envelope).performed is True
    assert _warnings_of(envelope, ExtractionWarningCode.BUILDER_COMPILED_DIVERGENCE) == ()


@pytest.mark.parametrize(
    ("nodes", "edges"),
    [
        ("not a mapping", ()),
        ({"__start__": None, "plan_step": None}, 17),
        ({"__start__": None, "plan_step": None}, [object()]),
    ],
    ids=["nodes-not-a-mapping", "edges-not-iterable", "edge-of-the-wrong-shape"],
)
def test_a_cross_check_drawing_of_the_wrong_shape_diverges_rather_than_crashing(
    nodes: Any, edges: Any
) -> None:
    """Reading the drawing is defensive on the cross-check side too.

    A drawing that carries nothing readable reads as an *empty* compiled topology, which is a
    divergence — the honest report, since the two readings genuinely do not agree — and never a
    ``TypeError`` out of ``extract()``. The builder reading is untouched either way, which is
    rule 3 holding even when the compiled level is unreadable.
    """
    envelope = extract(_paired(nodes, edges))

    assert _cross_check(envelope).performed is True
    assert _warnings_of(envelope, ExtractionWarningCode.BUILDER_COMPILED_DIVERGENCE)
    assert [node.id for node in envelope.ir.nodes] == ["act_step", "plan_step"]


def test_a_drawn_edge_from_an_unnameable_node_into_end_is_warned() -> None:
    """The finish side of the reference check, which the entry side does not reach for it."""
    envelope = extract(
        _drawn(
            {"__start__": None, "n1": None, "__end__": None},
            [
                sc.DrawnEdge("__start__", "n1"),
                sc.DrawnEdge("n1", "__end__"),
                sc.DrawnEdge("", "__end__"),
            ],
        )
    )

    warnings = _warnings_of(envelope, ExtractionWarningCode.UNSUPPORTED_CONSTRUCT)
    assert [warning.detail["construct"] for warning in warnings] == ["drawn-node-unrepresentable"]
    assert envelope.ir.finish == "n1"


def test_a_drawing_whose_edges_are_not_iterable_reads_as_no_edges() -> None:
    """A ``str`` is iterable and an ``int`` is not; the guard is about the latter."""
    envelope = extract(_drawn({"__start__": None, "n1": None}, 17))

    assert [node.id for node in envelope.ir.nodes] == ["n1"]
    assert envelope.ir.edges == ()
    assert envelope.ir.entry == ()


def test_a_send_edge_is_label_expanded_into_the_builder_reading() -> None:
    """The cross-check's builder side covers all three edge kinds, including ``send``.

    No §3 path emits a ``send`` edge yet — §6's classification is EX-03's card — so this is
    checked against a hand-authored IR rather than through ``extract()``. The alternative is a
    branch that first runs the day EX-03 lands, on a workflow nobody is looking at.
    """
    from gebra.extraction.compiled import _builder_topology
    from gebra.ir.models import WorkflowIR
    from gebra.ir.serialization import load_json

    ir = load_json(
        WorkflowIR,
        """
        {"ir_version": "1.0", "entry": "plan", "finish": "book_leg",
         "nodes": [{"id": "plan"}, {"id": "book_leg"}],
         "edges": [{"kind": "send", "from": "plan", "to": "book_leg"}]}
        """,
    )

    assert _builder_topology(ir).edges == frozenset({("plan", "book_leg")})


def test_the_downgraded_path_records_no_cross_check() -> None:
    """There is no builder reading to compare against, so the record is absent, not false."""
    envelope = extract(sc.build_gated_pregel())

    assert _surfaces(envelope).cross_check is None


def test_the_compiled_only_path_refuses_rather_than_drawing_a_foreign_object() -> None:
    """§4.3 rule 4's only surface is gated, and the gate runs *before* the call.

    ``get_graph()`` on an arbitrary ``PregelProtocol`` implementation is arbitrary code —
    LangGraph's own ``RemoteGraph`` answers it with an HTTP request — and §1 rule 1 forbids
    opening a connection outright. §2 already has the branch this lands in: a Pregel-protocol
    object with no ``.builder`` and no *usable* ``get_graph()`` is refused at the boundary, and
    a getter that cannot be called without violating a MUST is not a usable one.

    The socket-opening fixture is what makes "before the call" checked rather than asserted: it
    records into ``TRIPPED`` on its first line, so a gate that ran too late would leave a mark
    even though the extraction still refused.
    """
    with pytest.raises(ExtractionError) as raised:
        extract(sc.SocketOpeningPregel(None))

    assert raised.value.reason is ExtractionErrorReason.NO_EXTRACTABLE_SURFACE
    assert sc.TRIPPED == []


@pytest.mark.parametrize(
    ("name", "route"),
    [
        ("armed-channel", "channel class"),
        ("armed-checkpointer", "checkpointer"),
        ("armed-cache-policy", "cache key function"),
        ("armed-mapper-pregel", "write mapper"),
        ("armed-root-pregel", "constructor"),
        ("recording-channel-pregel", "channel class"),
        ("socket-opening-pregel", "network"),
        ("third-party-protocol-pregel", "protocol implementation"),
    ],
)
def test_every_route_a_drawing_could_reach_user_code_by_is_gated(name: str, route: str) -> None:
    """One armed fixture per route, so the gate is a checked claim rather than a described one.

    §1 rule 3 says ``get_graph()`` "stays within never-invokes (no user code runs)"; on
    langgraph 1.2.10 a drawing reaches a channel's ``get()``, a checkpointer's
    ``get_next_version()``, a node's cache ``key_func``, a ``ChannelWrite`` entry's ``mapper``, a
    ``__root__`` channel's ``ValueType()`` **called as a constructor**, and — for a non-``Pregel``
    protocol object — whatever that object's getter does, network included. Each fixture below
    arms one of those and records before it acts, so a gate that stopped covering a route shows
    up here as a recorded call rather than as a quiet regression.

    Which side of the gate a hazard lands on depends on what the call was for: a builder-primary
    object still extracts (the cross-check is a SHOULD and simply declines), a builderless one is
    refused (the drawing is the only surface it has).
    """
    factory = {**sc.EXTRACTABLE_COMPILED, **sc.REFUSED_COMPILED}[name]

    try:
        envelope = extract(factory())
    except ExtractionError as error:
        assert error.reason is ExtractionErrorReason.NO_EXTRACTABLE_SURFACE
        assert route in str(error) or "not a `langgraph.pregel.Pregel`" in str(error)
    else:
        check = _cross_check(envelope)
        assert check.performed is False
        assert check.declined is not None
    assert [call for call in sc.TRIPPED if not call.startswith("ValueType")] == [], sc.TRIPPED


@pytest.mark.parametrize(
    ("attribute", "value", "fragment"),
    [
        ("channels", "not a mapping", "no readable channel mapping"),
        ("channels", {"__root__": sc.LastValue(str)}, "calls as a constructor"),
        ("nodes", "not a mapping", "no readable node mapping"),
    ],
    ids=["unreadable-channels", "root-channel", "unreadable-nodes"],
)
def test_every_unreadable_or_hazardous_surface_declines_the_cross_check(
    attribute: str, value: Any, fragment: str
) -> None:
    """The gate is conservative in the safe direction on every surface it reads.

    A surface it cannot read is a hazard, not the absence of one — the alternative is finding
    out by running the drawing, which is the thing the gate exists to avoid. The ``__root__``
    row is the sharpest: ``draw_graph`` reads that channel's ``ValueType`` **and calls the
    result**, which is §1 rule 4's first named hazard rather than merely a body.
    """
    compiled = sc.build_ungated_graph()
    setattr(compiled, attribute, value)

    check = _cross_check(extract(compiled))

    assert check.performed is False
    assert check.declined is not None
    assert fragment in check.declined


def test_an_armed_root_value_type_is_never_constructed_builder_primary() -> None:
    """Route 5, genuinely armed on the cross-check side: the constructor must never run.

    The ``__root__`` row of ``test_every_unreadable_or_hazardous_surface_declines_the_cross_check``
    binds a *stock* ``LastValue`` and shows the gate declines; this binds one whose ``ValueType``
    records and **raises from its constructor**, so "the drawing never calls it" stops being a
    reading of the gate's message and becomes a checked fact. ``draw_graph`` would evaluate
    ``specs["__root__"].ValueType()`` (``pregel/_draw.py``); the gate stands in front of it, so
    ``ArmedRootValueType.__init__`` never runs and :data:`sc.TRIPPED` stays empty.
    """
    compiled = sc.build_ungated_graph()
    # `channels` is invariant in its value type, so a `dict[str, LastValue[...]]` needs the
    # ignore on the cells where mypy resolves the attribute strictly; `unused-ignore` reconciles
    # the cells where it does not, the same pattern the folded-defaults fixtures use.
    compiled.channels = {  # type: ignore[assignment, unused-ignore]
        "__root__": sc.LastValue(sc.ArmedRootValueType)
    }

    check = _cross_check(extract(compiled))

    assert check.performed is False
    assert check.declined is not None
    assert "calls as a constructor" in check.declined
    assert sc.TRIPPED == []  # the autouse fixture also asserts this; stated here for the reader


def test_the_armed_root_value_type_is_armed() -> None:
    """A tripwire nobody trips proves nothing: constructing the value type really does raise."""
    with pytest.raises(sc.ChannelSentinelError):
        sc.ArmedRootValueType()
    assert sc.TRIPPED == ["ArmedRootValueType.__init__"]
    sc.TRIPPED.clear()


def test_a_builder_whose_node_keys_do_not_order_records_no_folding() -> None:
    """Provenance never fails an extraction, including on a mapping that will not sort.

    Read off the reader directly rather than through ``extract()``: a non-string node name is
    refused by the §3 path long before this runs, so the only way to reach the guard is to hand
    it the foreign builder §2 admits but LangGraph never produces.
    """
    from gebra.extraction.compiled import _folded_defaults

    class Defaults:
        retry_policy = object()
        cache_policy = None
        timeout = None

    class ForeignBuilder:
        _node_defaults = Defaults()
        nodes = {"plan_step": object(), 7: object()}  # noqa: RUF012

    assert _folded_defaults(ForeignBuilder()) == ()
    assert _folded_defaults(object()) == ()


def test_a_drawing_that_is_not_returned_at_all_is_a_boundary_refusal() -> None:
    """The gate passed and the call still yielded nothing — §2's "no usable surface"."""
    workflow = sc.build_gated_pregel()
    workflow.get_graph = lambda *args, **kwargs: None  # type: ignore[method-assign,assignment]

    with pytest.raises(ExtractionError) as raised:
        extract(workflow)

    assert raised.value.reason is ExtractionErrorReason.NO_EXTRACTABLE_SURFACE
    assert "did not return a readable drawing" in str(raised.value)


def test_a_compiled_object_with_no_checkpointer_attribute_leaves_the_slot_absent() -> None:
    """ "Full at compiled level" presumes the level knows; an unreadable surface does not.

    ``present: false`` is a claim in hash scope, so it is made only where the attribute answers.
    No LangGraph object reaches this, but §2 defines the family by the Pregel *protocol*.
    """
    from gebra.extraction.compiled import _checkpointer as read_checkpointer

    class Surfaceless:
        """A Pregel-protocol shape that answers nothing about a checkpointer."""

    assert read_checkpointer(Surfaceless()) is None
    assert read_checkpointer(sc.build_ungated_graph()) == Checkpointer(present=False)


def test_a_node_with_no_readable_writers_is_not_a_hazard() -> None:
    """The per-node scan reads two members and treats an unreadable one as nothing to run."""
    from gebra.extraction.compiled import _node_hazard

    class Node:
        cache_policy = None
        writers = 17  # not iterable at all — a `str` would be

    assert _node_hazard(Node()) is None


def test_a_value_whose_type_answers_oddly_is_treated_as_foreign() -> None:
    """The safe direction, checked: an unreadable provenance answers "not LangGraph's"."""
    from gebra.extraction.compiled import _from_substrate

    class Odd:
        __module__ = 7  # type: ignore[assignment]

    assert _from_substrate(Odd()) is False
    assert _from_substrate(sc.LastValue(str)) is True


def test_a_stock_pregel_is_drawn_and_only_langgraphs_own_code_runs() -> None:
    """What the gate lets through, stated as what it is rather than as "nothing runs".

    A drawing of a stock ``Pregel`` still executes LangGraph's own ``ChannelWrite.invoke`` and
    asks LangGraph's own channels for their values — library code, on library objects. What it
    does not touch is the workflow: the Pregel node below raises if it is called, and it is not.
    """
    envelope = extract(sc.build_gated_pregel())

    assert [node.id for node in envelope.ir.nodes] == ["pregel_step"]
    assert sc.TRIPPED == []


def test_the_recording_channel_is_the_only_thing_that_records() -> None:
    """The control for the test above: the Pregel step itself raises if it is ever called."""
    with pytest.raises(sg.SentinelExecutedError):
        sc.pregel_step("anything")


# ── the taxonomy, held to its registry rows ──────────────────────────────────────────────


@pytest.mark.parametrize("name", _every_fixture())
def test_every_warning_this_path_emits_is_in_the_closed_vocabulary(name: str) -> None:
    """§8's vocabulary is closed: a construct is reported with one of the codes or not at all."""
    envelope = extract(sc.EXTRACTABLE_COMPILED[name]())

    for warning in envelope.warnings:
        assert isinstance(warning.code, ExtractionWarningCode)
        assert warning.message


@pytest.mark.parametrize("name", _every_fixture())
def test_every_envelope_this_path_produces_round_trips(name: str) -> None:
    """An envelope that could not be serialized could not be reported (§8)."""
    data = to_data(extract(sc.EXTRACTABLE_COMPILED[name]()))

    assert data["extracted_from"]["family"] == "compiled"
    assert isinstance(data["warnings"], list)


def test_the_fixture_table_covers_the_four_things_section_4_says() -> None:
    """The parametrized claims above are only as wide as this table, so it needs a floor.

    The floor is on the *union* — what the suite claims to cover — while the second assertion
    holds the version gate to the only two shapes it is allowed to remove. A third name
    appearing in ``UNAVAILABLE_COMPILED`` is a widening of the gate and fails here rather than
    thinning the matrix quietly.
    """
    named = {*sc.EXTRACTABLE_COMPILED, *sc.UNAVAILABLE_COMPILED}

    # The union is the same size on every matrix cell — each version-conditional shape lands in
    # one table or the other — so the floor is the current count rather than the loose one it
    # replaced, and a fixture that went missing on some cell fails here instead of thinning the
    # parametrizations quietly.
    assert len(named) >= 18
    assert len(sc.REFUSED_COMPILED) >= 2
    assert named & set(sc.REFUSED_COMPILED) == set()
    assert set(sc.EXTRACTABLE_COMPILED) & set(sc.UNAVAILABLE_COMPILED) == set()
    assert set(sc.UNAVAILABLE_COMPILED) <= {"folded-defaults", "error-handler"}


def test_the_version_gate_removes_a_fixture_only_where_its_api_is_missing() -> None:
    """The gate is a fact about the substrate, not a switch a green run can be bought with.

    Both directions: a shape whose API is present must be buildable and armed, and a shape
    whose API is absent must be named with a reason rather than dropped. This is the assertion
    that stops ``UNAVAILABLE_COMPILED`` from becoming somewhere to put an inconvenient fixture.
    """
    expected = {}
    if not substrate.HAS_NODE_DEFAULTS:
        expected["folded-defaults"] = substrate.NODE_DEFAULTS_REASON
    if not substrate.HAS_NODE_ERROR_HANDLER:
        expected["error-handler"] = substrate.NODE_ERROR_HANDLER_REASON

    assert sc.UNAVAILABLE_COMPILED == expected
    for name in ("folded-defaults", "error-handler"):
        assert (name in sc.EXTRACTABLE_COMPILED) is (name not in sc.UNAVAILABLE_COMPILED)


# ── WA-07 — the tripwire for the path this card lands ────────────────────────────────────

#: The guarded child. Network primitives raise from the first line and socket construction is
#: only counted until the imports are done — the same bounded-import phase ``test_dispatch``
#: explains. Then ``StateGraph.compile`` is taken away and every §4 shape is extracted: the
#: fixtures are compiled *before* the guard goes up, because compiling is the fixture's step
#: and §1 rule 2 is precisely that it is never extraction's.
#:
#: Unlike the §3 path, this one also arms ``Runnable.invoke`` — but it cannot arm it *outright*,
#: because a drawing of a stock ``Pregel`` runs LangGraph's own ``ChannelWrite.invoke`` (route 4,
#: ``pregel/_draw.py``). So the guard allow-lists ``ChannelWrite`` and **counts** those calls,
#: turning EX-05's *stated* residue ("the drawing runs LangGraph's own ``ChannelWrite.invoke``")
#: into a counted one — a non-empty count is the proof the allow-list was exercised — while every
#: other ``invoke`` trips. And the child asserts ``langgraph.pregel.remote`` never entered
#: ``sys.modules``: route 6 is the ``RemoteGraph`` network call, and its module is the thing a
#: build that reached for it would have imported (directly on point for DEC-19 route 6).
_TRIPWIRE = """
import socket, sys

attempts = []
built = []


def _record(name):
    def _seen(*a, **k):
        attempts.append(name); print("WA07-TRIP", file=sys.stderr)
        raise AssertionError(name + " was reached")
    return _seen


class _CountSocket(socket.socket):
    def __new__(cls, *a, **k):
        built.append(a)
        return super().__new__(cls, *a, **k)


class _TripSocket(socket.socket):
    def __new__(cls, *a, **k):
        attempts.append("socket"); print("WA07-TRIP", file=sys.stderr)
        raise AssertionError("a socket was created on the compiled extraction path")


socket.socket = _CountSocket
socket.getaddrinfo = _record("getaddrinfo")
socket.gethostbyname = _record("gethostbyname")
socket.create_connection = _record("create_connection")

import gebra
from gebra.extraction import ExtractionError
from langchain_core.runnables.base import Runnable
from langgraph.graph.state import StateGraph
from langgraph.pregel._write import ChannelWrite
from tests.sample_workflows import sentinel_compiled as sc

# Compile every fixture while compile() still exists. Compiling is the fixture's own step;
# what §1 rule 2 forbids is extraction ever taking it, which the raiser below checks.
extractable = {name: factory() for name, factory in sc.EXTRACTABLE_COMPILED.items()}
refused = {name: factory() for name, factory in sc.REFUSED_COMPILED.items()}
sc.TRIPPED.clear()

assert attempts == [], attempts
socket.socket = _TripSocket
StateGraph.compile = _record("StateGraph.compile")

# Arm `Runnable.invoke`, allow-listing (and counting) LangGraph's own `ChannelWrite`. The class
# that actually defines `invoke` in ChannelWrite's MRO is patched — deriving it from the MRO
# rather than importing a private path keeps this correct across the frozen matrix minors — and
# the base `Runnable.invoke` is armed as a backstop for any runnable whose invoke is not that one.
channelwrite_invokes = []
_invoke_owner = next(cls for cls in ChannelWrite.__mro__ if "invoke" in vars(cls))
_real_invoke = _invoke_owner.invoke


def _guarded_invoke(self, *a, **k):
    if isinstance(self, ChannelWrite):
        channelwrite_invokes.append(type(self).__name__)
        return _real_invoke(self, *a, **k)
    attempts.append("invoke:" + type(self).__name__); print("WA07-TRIP", file=sys.stderr)
    raise AssertionError("Runnable.invoke reached a non-ChannelWrite: " + type(self).__name__)


def _trip_invoke(self, *a, **k):
    attempts.append("invoke:" + type(self).__name__); print("WA07-TRIP", file=sys.stderr)
    raise AssertionError("Runnable.invoke reached: " + type(self).__name__)


_invoke_owner.invoke = _guarded_invoke
Runnable.invoke = _trip_invoke

extracted = 0
for name, workflow in extractable.items():
    envelope = gebra.extract(workflow)
    assert envelope.ir.nodes, name
    envelope.graph_version()          # canonicalize and digest, still under the guard
    extracted += 1

boundary = 0
for name, workflow in refused.items():
    try:
        gebra.extract(workflow)
    except ExtractionError:
        boundary += 1

assert (extracted, boundary) == (%d, %d), (extracted, boundary)
# The drawing of a stock Pregel runs LangGraph's own ChannelWrite.invoke — the one invoke this
# path licenses. A non-empty count is the proof the allow-list was exercised (else the guard
# above would have proven nothing); every other invoke would have tripped `attempts`.
assert channelwrite_invokes, "no ChannelWrite.invoke ran — the drawing never reached route 4"
# Route 6 (RemoteGraph's network call) is the one route with a module of its own; a build that
# reached for it would have imported it, so its absence from sys.modules is route 6's tripwire.
assert "langgraph.pregel.remote" not in sys.modules, [m for m in sys.modules if "remote" in m]
# The armed channels never answered anything but the licensed ValueType read: `get`/`update`
# would have raised, and this record is what catches one an `except` block swallowed.
assert [call for call in sc.TRIPPED if not call.startswith("ValueType")] == [], sc.TRIPPED
"""

_REPORT = "print(attempts)\n"


def _run_guarded(probe: str = "") -> subprocess.CompletedProcess[str]:
    body = _TRIPWIRE % (len(sc.EXTRACTABLE_COMPILED), len(sc.REFUSED_COMPILED))
    return subprocess.run(
        [sys.executable, "-c", body + probe + _REPORT],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_compiled_extraction_invokes_nothing_and_compiles_nothing() -> None:
    """The WA-07 claim for the §4 path, in a fresh interpreter.

    Seven claims at once. Every node, router and Pregel step in every fixture raises if it is
    called, so an extraction that touched one fails the run. ``StateGraph.compile`` is replaced
    by a raiser before the first extraction, so §1 rule 2 is checked rather than reviewed — and
    it matters more here than on the §3 path, because the §4 path holds live compiled objects
    and could recompile one to re-read a surface. ``Runnable.invoke`` is armed with an allow-list
    for LangGraph's own ``ChannelWrite`` (route 4, which a stock drawing legitimately runs), and
    the child asserts that allow-list was **exercised** (a non-empty count) so the arming is not
    vacuous while every other invoke would have tripped. ``langgraph.pregel.remote`` is asserted
    absent from ``sys.modules`` — route 6's ``RemoteGraph`` is the one route with a module of its
    own, so a build that reached for it would have imported it. Nothing resolves a name or opens
    a connection at any point, imports included, and nothing constructs a socket while extracting.
    And the two user-authored channels record before they act, so the child asserts the record
    rather than only its own exit status: the cross-check's never-invokes precondition is what
    keeps that record empty, and a precondition that quietly stopped working would show up here as
    a recorded ``ArmedChannel.get`` even though the extraction still succeeded.

    The counts come from the fixture tables, so a shape added there joins this claim with it.
    """
    result = _run_guarded()

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "[]", result.stdout
    assert "WA07-TRIP" not in result.stderr, result.stderr


@pytest.mark.parametrize(
    ("probe", "expected"),
    [
        ("sc.build_ungated_graph().builder.compile()\n", "StateGraph.compile was reached"),
        ("socket.socket()\n", "a socket was created"),
        ("socket.getaddrinfo('example.invalid', 80)\n", "getaddrinfo was reached"),
        ("socket.gethostbyname('example.invalid')\n", "gethostbyname was reached"),
        ("socket.create_connection(('example.invalid', 80))\n", "create_connection was reached"),
    ],
    ids=["compile", "socket", "getaddrinfo", "gethostbyname", "create_connection"],
)
def test_each_raiser_is_armed(probe: str, expected: str) -> None:
    """A tripwire nobody trips proves nothing — so every raiser gets its own control.

    The controls run *after* the child's own assertions, so each one proves the raiser was live
    at the end of the very run that made the claim.
    """
    result = _run_guarded(probe)

    assert result.returncode != 0
    assert expected in result.stderr


def test_the_guarded_child_notices_a_channel_that_answered() -> None:
    """The record assertion in the child is armed too, not decorative.

    Without this control, ``TRIPPED`` could quietly stop being appended to and the child's
    final assertion would pass over an empty list forever.
    """
    result = _run_guarded("sc.ArmedChannel(str).get()\n")

    assert result.returncode != 0
    assert "ChannelSentinelError" in result.stderr


def test_the_invoke_guard_notices_a_non_channelwrite_invoke() -> None:
    """The ``Runnable.invoke`` guard is armed too: a non-``ChannelWrite`` invoke trips it.

    The allow-list is the delicate part — arming ``invoke`` while letting ``ChannelWrite``
    through could silently degrade into letting *everything* through. This probe calls
    ``.invoke`` on an ordinary node runnable (a ``RunnableCallable``, not a ``ChannelWrite``), so
    the ``isinstance`` branch that trips is the one exercised — proving the guard still refuses
    what it must at the end of the very run that counted the legitimate calls.
    """
    result = _run_guarded('extractable["ungated"].builder.nodes["plan_step"].runnable.invoke({})\n')

    assert result.returncode != 0
    assert "reached a non-ChannelWrite" in result.stderr


def test_the_compiled_fixtures_are_armed() -> None:
    """Every node function and router in the §4 fixtures raises ``SentinelExecutedError``.

    All of them, not a sample: an unarmed fixture is a hole exactly where the claim above is
    strongest, since that is the graph whose extraction would then prove nothing.

    The exact exception matters. An earlier form of this test caught ``Exception`` and dropped
    it, keeping only a ``>= 20`` floor — so a fixture that stopped raising ``SentinelExecutedError``
    and started raising, say, ``TypeError`` still counted as "not a sentinel" and the arming
    silently rotted. Here every *callable* body must raise ``SentinelExecutedError`` and nothing
    else; the only non-callable is a nested ``CompiledStateGraph`` bound as a subgraph node (its
    ``.func`` is the compiled graph, which is not called here), and it is skipped explicitly
    rather than swallowed. A body that raised any other exception now fails the run.
    """
    state: sg.SentinelState = {"query": "q", "plan": "p", "answer": "a"}
    checked = 0
    skipped_subgraphs = 0

    for factory in sc.EXTRACTABLE_COMPILED.values():
        workflow = factory()
        builder = getattr(workflow, "builder", None)
        if builder is None:
            continue  # a builderless Pregel — its node bodies are armed via `pregel_step` below
        callables: list[Any] = [spec.runnable for spec in builder.nodes.values()]
        callables += [
            spec.path for branches in builder.branches.values() for spec in branches.values()
        ]
        for runnable in callables:
            function = getattr(runnable, "func", runnable)
            if not callable(function):
                # A nested compiled graph bound as a subgraph node: not a sentinel body, and the
                # only non-callable this walk meets. Counted so the floor below cannot hide one
                # that went missing.
                skipped_subgraphs += 1
                continue
            with pytest.raises(sg.SentinelExecutedError):
                function(state)
            checked += 1

    # The builderless `gated-pregel` node body is armed on its own — it is not reached by the
    # builder walk above, so its arming is asserted directly rather than counted in `checked`.
    with pytest.raises(sg.SentinelExecutedError):
        sc.pregel_step("anything")

    # Holds on every frozen matrix cell: the two 1.2-era shapes contribute four callables, so the
    # floor sits below the reduced count rather than the full one.
    assert checked >= 30, checked
    assert skipped_subgraphs >= 2, skipped_subgraphs
