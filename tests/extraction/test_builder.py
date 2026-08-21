"""Builder (``StateGraph``) extraction, and the never-invokes tripwire for that path.

Normative authority: INTROSPECTION-SPEC §3 (the per-attribute mapping table), §2 (the
degenerate-input rule, scoped by DEC-18), §8 (the warnings taxonomy), IR-SPEC §4.2/§6.3
(what ``entry``/``finish`` mean and which representation is canonical), under §1's
never-invokes discipline.

Every builder these tests read is armed: each node function and router raises
``SentinelExecutedError`` if it is called, so "extraction never invokes" is checked by the
fixtures themselves on every test in the file, not only in the guarded subprocess at the
bottom.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy
from pydantic import ValidationError

from gebra.annotations.contract import NodeContract
from gebra.extraction import (
    ExtractionError,
    ExtractionErrorReason,
    ExtractionWarningCode,
    ObjectFamily,
    SlotGrade,
    extract,
)
from gebra.extraction import builder as builder_module
from gebra.ir.canonical import graph_version
from gebra.ir.models import (
    Annotations,
    ConditionalEdge,
    DynamicEdge,
    NormalEdge,
    SendEdge,
    StateField,
)
from gebra.ir.models import RetryPolicy as IRRetryPolicy
from tests.sample_workflows import sentinel_graph as sg

REPO_ROOT = Path(__file__).resolve().parents[2]


#: The half of the §8 taxonomy the ANNOTATION surface owns — §4's three registry rows plus
#: the two DEC-08 contract codes. Since EX-11 wired §3's precedence chain into this path,
#: every node resolves a contract, so a node with no declaration of any kind carries the
#: D-011 ``contract-defaulted`` record. That half is
#: ``tests/extraction/test_contracts.py``'s subject; the §3 topology and state claims below
#: are quantified over its complement, so "warns for this and nothing else" still means
#: exactly what it did.
ANNOTATION_CODES = frozenset(
    {
        ExtractionWarningCode.CONTRACT_INFERRED,
        ExtractionWarningCode.CONTRACT_DEFAULTED,
        ExtractionWarningCode.ANNOTATION_CONFLICT,
        ExtractionWarningCode.ANNOTATION_UNKNOWN_NODE,
        ExtractionWarningCode.ANNOTATION_INVALID,
    }
)


def topology(envelope: Any) -> tuple[Any, ...]:
    """The warnings this file is about: everything outside the annotation half."""
    return tuple(warning for warning in envelope.warnings if warning.code not in ANNOTATION_CODES)


def constructs(envelope: Any) -> list[str]:
    """The ``construct`` key of each topology warning, in emission order."""
    return [warning.detail.get("construct", warning.code.value) for warning in topology(envelope)]


# ── The card's first acceptance box: the sentinel graph extracts to the right IR ─────────


def test_the_sentinel_graph_extracts_to_its_ir() -> None:
    """The whole §3 mapping over one graph, asserted as a value rather than field by field.

    Everything the builder declares is here and nothing else is: three nodes, the one plain
    edge, the router as a ``conditional`` edge carrying its declared branch
    name and ``path_map``, the two sentinel wirings as scalars because each wired set is a
    singleton (IR-SPEC §6.3), and the three state keys of ``SentinelState``. Every key
    carries ``optional: true`` because this builder declares no narrower input schema, so
    each of them *is* a graph input (§3's state row; the projection itself is
    ``tests/extraction/test_state.py``'s). ``runtime`` stays absent: both sub-slots are
    compiled-level surfaces §3 records as absent at builder level rather than guessing.

    ``annotations`` is the one part of this value that is not §3's: since EX-11 landed the
    ANNOTATION §3 chain, every node resolves a contract, and these three declare nothing on
    any surface — so each carries the decision D-011 conservative default for a body with no
    write evidence, ``pure: true``, together with its ``contract-defaulted`` record. The
    resolution itself is ``tests/extraction/test_contracts.py``'s subject; what belongs here
    is that the §3 rows and the §3-of-the-other-spec chain compose into one IR.
    """
    envelope = extract(sg.SENTINEL_GRAPH)
    ir = envelope.ir

    assert ir.ir_version == "1.0"
    assert ir.entry == "plan_step"
    assert ir.finish == "summarize_step"
    assert [node.id for node in ir.nodes] == ["act_step", "plan_step", "summarize_step"]
    assert all(node.annotations == Annotations(pure=True) for node in ir.nodes)
    assert ir.state == {
        "query": StateField(type="str", optional=True),
        "plan": StateField(type="str", optional=True),
        "answer": StateField(type="str", optional=True),
    }
    assert ir.runtime is None
    assert ir.edges == (
        NormalEdge(kind="normal", **{"from": "act_step"}, to="summarize_step"),
        ConditionalEdge(
            kind="conditional",
            **{"from": "plan_step"},
            condition="route_after_plan",
            path_map={"act": "act_step", "done": "summarize_step"},
        ),
    )
    assert topology(envelope) == ()
    assert envelope.extracted_from.family is ObjectFamily.BUILDER
    assert envelope.extracted_from.source == "langgraph:StateGraph"


def test_extraction_is_a_value_and_repeats_exactly() -> None:
    """Two extractions of one unchanged builder are equal, as models and as digests.

    Not a truism: ``builder.edges`` and ``builder.waiting_edges`` are ``set``s, whose
    iteration order varies with the process's string-hash seed, so the path sorts everything
    it emits. A regression here would be invisible in canonical form — which sorts again —
    and would only show up as goldens that fail on some runs.
    """
    first = extract(sg.build_sentinel_graph())
    second = extract(sg.build_sentinel_graph())

    assert first == second
    assert first.graph_version() == second.graph_version() == graph_version(first.ir)


# ── entry / finish, and the DEC-18 scoping of the missing-wiring warning ─────────────────


def test_a_router_terminated_graph_extracts_finish_empty_and_warning_free() -> None:
    """The DEC-18 D2 ruling, and the reason SD-5 was filed.

    This graph is well-formed and idiomatic: END is reachable, declared through (m3)
    ``path_map`` labels rather than any ``(x, END)`` edge. So ``finish`` is empty — there is
    no (m2) member to name — and **nothing is warned**, because nothing about the graph is
    undeclared. Before DEC-18 scoped the trigger, every conditionally-terminated workflow
    would have carried a missing-wiring warning and so failed the strict-mode bar for a
    defect it does not have.
    """
    envelope = extract(sg.build_router_terminated_graph())

    assert envelope.ir.finish == ()
    assert envelope.ir.entry == "plan_step"
    assert topology(envelope) == ()
    assert {
        label for edge in envelope.ir.edges for label in getattr(edge, "path_map", {}).values()
    } >= {"END"}


def test_an_unwired_builder_extracts_with_both_missing_wiring_warnings() -> None:
    """§2 degenerate-input rule: total over supported objects, warned rather than refused.

    Genuinely undeclared on both sides — no START edge, no conditional entry, no END
    incidence of either kind — which is exactly the case DEC-18 left the trigger firing for.
    """
    envelope = extract(sg.build_unwired_graph())

    assert envelope.ir.entry == ()
    assert envelope.ir.finish == ()
    assert constructs(envelope) == ["missing-start-wiring", "missing-finish-wiring"]
    assert all(
        warning.code is ExtractionWarningCode.UNSUPPORTED_CONSTRUCT
        for warning in topology(envelope)
    )


def test_a_declared_conditional_entry_derives_the_entry_from_its_path_map() -> None:
    """§3: "``branches[START]`` derives the entry: ``entry`` = the declared ``path_map`` targets"."""
    envelope = extract(sg.build_conditional_entry_graph(declared=True))

    assert envelope.ir.entry == ("act_step", "plan_step")
    assert topology(envelope) == ()
    # The START branch is carried by `entry`, never by an edge: START is not a node id, and
    # IR-SPEC §4.2 (m1) is what maps an entry member onto its sentinel incidence.
    assert all(edge.from_ != START for edge in envelope.ir.edges)


def test_a_dynamic_conditional_entry_extracts_entry_empty_with_its_own_warning() -> None:
    """§3: ``ends is None`` → ``entry: []`` plus the dynamic-dispatch warning, carrying the name.

    And *not* the missing-wiring warning: §2 says a conditional entry with no declared
    targets "carries §7.1's dynamic-dispatch warning instead, never this one". A START is
    declared here — what is unknowable is which node it reaches.
    """
    envelope = extract(sg.build_conditional_entry_graph(declared=False))

    assert envelope.ir.entry == ()
    assert constructs(envelope) == ["conditional-entry-without-path-map"]
    detail = envelope.warnings[0].detail
    assert detail["location"] == {"branch": "route_entry", "source": START}
    assert detail["ir_partial"] is True


def test_both_entry_sources_union() -> None:
    """§7.1 names two sources for ``entry``; a builder may declare through both at once."""
    builder: StateGraph[sg.SentinelState] = StateGraph(sg.SentinelState)
    builder.add_node("plan_step", sg.raiser("plan_step"))
    builder.add_node("act_step", sg.raiser("act_step"))
    builder.add_edge(START, "plan_step")
    builder.set_conditional_entry_point(sg.raiser("route_entry"), path_map={"b": "act_step"})
    builder.add_edge("plan_step", END)

    assert extract(builder).ir.entry == ("act_step", "plan_step")


def test_a_start_to_end_edge_is_dropped_with_a_warning() -> None:
    """A sentinel-to-sentinel incidence has no ir 1.0 carrier, so it is warned, not invented.

    ``entry``/``finish`` hold node ids, and neither sentinel is one — §5.1 reserves both
    spellings and says the IR never emits them. Dropping it silently would make the IR
    disagree with the builder without saying so; §8's ``unsupported-construct`` row exists
    for exactly "a supported object contains a construct extraction cannot map".
    """
    envelope = extract(sg.build_start_to_end_graph())

    assert constructs(envelope) == ["start-to-end-edge"]
    assert envelope.ir.entry == "plan_step"
    assert envelope.ir.finish == "plan_step"
    assert envelope.warnings[0].detail["location"] == {"edge": {"from": START, "to": END}}


def test_an_entry_label_targeting_end_is_dropped_with_a_warning() -> None:
    """The same unrepresentable incidence, reached through a conditional entry's path_map."""
    builder: StateGraph[sg.SentinelState] = StateGraph(sg.SentinelState)
    builder.add_node("plan_step", sg.raiser("plan_step"))
    builder.set_conditional_entry_point(
        sg.raiser("route_entry"), path_map={"skip": END, "go": "plan_step"}
    )
    builder.add_edge("plan_step", END)

    envelope = extract(builder)

    assert envelope.ir.entry == "plan_step"
    assert constructs(envelope) == ["reserved-entry-target"]


# ── edges: normal, waiting (the barrier), and the router group ───────────────────────────


def test_waiting_edges_flatten_to_normal_edges_with_one_warning_per_group() -> None:
    """§3: each source in the tuple yields one ``normal`` edge; the barrier itself is warned.

    ir 1.0 cannot express the all-of barrier (§7.3 item 3), so the warning is what keeps the
    P-04/P-09 conservatism visible instead of silently lost.
    """
    envelope = extract(sg.build_barrier_graph())

    assert {
        (edge.from_, edge.to) for edge in envelope.ir.edges if isinstance(edge, NormalEdge)
    } == {
        ("plan_step", "summarize_step"),
        ("act_step", "summarize_step"),
        ("plan_step", "review_step"),
        ("act_step", "review_step"),
    }
    barriers = envelope.warnings_of(ExtractionWarningCode.BARRIER_FLATTENED)
    assert len(barriers) == 2
    assert {barrier.detail["target"] for barrier in barriers} == {"review_step", "summarize_step"}
    assert all(barrier.detail["edges_expanded"] == 2 for barrier in barriers)
    assert all(barrier.detail["sources"] == ("plan_step", "act_step") for barrier in barriers)


def test_a_waiting_edge_to_end_contributes_finish_members() -> None:
    """END is a sentinel wherever it is reached from, so a barrier into it derives ``finish``."""
    builder: StateGraph[sg.SentinelState] = StateGraph(sg.SentinelState)
    builder.add_node("plan_step", sg.raiser("plan_step"))
    builder.add_node("act_step", sg.raiser("act_step"))
    builder.add_edge(START, "plan_step")
    builder.add_edge(START, "act_step")
    builder.add_edge(["plan_step", "act_step"], END)

    envelope = extract(builder)

    assert envelope.ir.finish == ("act_step", "plan_step")
    assert [edge for edge in envelope.ir.edges if isinstance(edge, NormalEdge)] == []


def test_a_router_becomes_one_conditional_edge_carrying_its_declared_name() -> None:
    """§3 row 9: ``condition`` is the declared branch name; the router body is never read."""
    envelope = extract(sg.build_router_terminated_graph())
    conditionals = [edge for edge in envelope.ir.edges if isinstance(edge, ConditionalEdge)]

    assert [(edge.from_, edge.condition) for edge in conditionals] == [
        ("act_step", "route_act"),
        ("plan_step", "route_plan"),
    ]
    assert conditionals[1].path_map == {"act": "act_step", "done": "END"}


def test_an_end_target_in_a_path_map_is_spelled_with_the_blessed_literal() -> None:
    """The forced reading recorded with DEC-18: ``"__end__"`` → ``"END"``.

    ``BranchSpec.ends`` carries the substrate's raw sentinel, while the ledger and IR-SPEC
    bless only ``"END"`` inside a ``path_map``; §3 states the mapping and not the
    translation. Passing the raw spelling through would name a reserved segment the IR never
    emits, so P-01 would report a target that does not exist — one direction is viable.
    """
    envelope = extract(sg.build_router_terminated_graph())
    labels = {
        target
        for edge in envelope.ir.edges
        if isinstance(edge, ConditionalEdge)
        for target in edge.path_map.values()
    }

    assert "END" in labels
    assert "__end__" not in labels


def test_two_routers_on_one_node_stay_two_edge_groups() -> None:
    """§3: branch names are unique per source, so ``(from, condition)`` identifies a group.

    Consumers "MUST NOT key on ``condition`` alone" — which only means anything if the two
    groups survive extraction as two edges.
    """
    builder: StateGraph[sg.SentinelState] = StateGraph(sg.SentinelState)
    builder.add_node("plan_step", sg.raiser("plan_step"))
    builder.add_node("act_step", sg.raiser("act_step"))
    builder.add_edge(START, "plan_step")
    builder.add_conditional_edges("plan_step", sg.raiser("route_one"), {"go": "act_step"})
    builder.add_conditional_edges("plan_step", sg.raiser("route_two"), {"stop": "act_step"})
    builder.add_edge("act_step", END)

    conditionals = [edge for edge in extract(builder).ir.edges if isinstance(edge, ConditionalEdge)]

    assert [(edge.from_, edge.condition) for edge in conditionals] == [
        ("plan_step", "route_one"),
        ("plan_step", "route_two"),
    ]


def test_declared_destinations_extract_as_conditional_edges() -> None:
    """§3 row 4 → §6: ``destinations=`` classifies ``conditional`` without a ``Send`` hint.

    §6 states it outright — "``destinations=`` without a ``Send`` hint … classifies as
    ``kind: conditional``" — and §3 adds "dict-valued ``ends`` supplies ``path_map``". This
    path reads no return-type hints, so it behaves as the no-hint case and emits the kind §6
    names for it.

    Refusing the member instead would refuse far more than ``destinations=``: the substrate
    fills the same ``ends`` from a ``Command[Literal[...]]`` **return annotation**, with no
    argument at the call site, so ``command_step`` below declares its routing without ever
    naming ``destinations``. That is the mainstream ``Command``-routing idiom, and §2 puts
    hard failure at the object boundary only.

    Two shapes, one rule. A dict-valued ``ends`` supplies its own labels; a tuple-valued one
    projects to the identity map, which is the substrate's own conversion for the equivalent
    list-valued ``path_map`` (``["n2"]`` becomes ``{"n2": "n2"}``) rather than a new
    convention. No ``condition`` is emitted: there is no ``BranchSpec`` here and so no
    declared branch name, and inventing one would put a string this build made up inside
    ``graph_version``.
    """
    envelope = extract(sg.build_destinations_graph())
    conditionals = {
        edge.from_: edge for edge in envelope.ir.edges if isinstance(edge, ConditionalEdge)
    }

    assert conditionals["plan_step"].path_map == {
        "act_step": "act_step",
        "review_step": "review_step",
    }
    assert conditionals["act_step"].path_map == {"review_step": "go review"}
    assert conditionals["command_step"].path_map == {"act_step": "act_step"}
    assert all(edge.condition is None for edge in conditionals.values())
    assert topology(envelope) == ()


def test_a_reserved_routing_target_is_dropped_with_a_warning() -> None:
    """A ``path_map`` label targeting START has no ir 1.0 carrier, so it is warned, not refused.

    The substrate accepts ``{"restart": START}`` on an uncompiled builder — it only rejects
    it at ``compile()``, which is never called. ir 1.0 gives START no incoming edges (§4.2
    (m5)) and never emits the reserved segment (§5.1), so the label is dropped and the rest
    of the group survives. Refusing would turn a dangling reference into a boundary error,
    which is the one thing this path says it leaves to P-01.
    """
    envelope = extract(sg.build_reserved_routing_target_graph())
    conditional = next(edge for edge in envelope.ir.edges if isinstance(edge, ConditionalEdge))

    assert conditional.path_map == {"go": "act_step"}
    assert constructs(envelope) == ["reserved-routing-target"]
    assert envelope.warnings[0].detail["location"]["label"] == "restart"


def test_a_group_whose_every_target_is_uncarriable_emits_no_edge() -> None:
    """The last label dropping must not leave an edge with an empty ``path_map`` behind.

    DEC-18 D4 ruled that shape out in terms — ``path_map`` *presence* is what tells the
    router-coverage property which mode to run in, so an empty map asserts "complete and
    empty" — so when every declared label turns out to be uncarriable the group is not
    emitted at all. Each dropped label still carries its own warning, so nothing goes silent.
    """
    builder: StateGraph[sg.SentinelState] = StateGraph(sg.SentinelState)
    builder.add_node("plan_step", sg.raiser("plan_step"), destinations=(START,))
    builder.add_edge(START, "plan_step")
    builder.add_conditional_edges("plan_step", sg.raiser("route_plan"), {"restart": START})
    builder.add_edge("plan_step", END)

    envelope = extract(builder)

    assert [edge for edge in envelope.ir.edges if isinstance(edge, ConditionalEdge)] == []
    assert constructs(envelope) == ["reserved-routing-target", "reserved-routing-target"]


def test_a_routing_label_is_nfc_normalized() -> None:
    """IR-SPEC §6.3 puts ``path_map`` labels in the NFC identifier role — so extraction emits NFC.

    Not a nicety: canonicalization *refuses* a non-NFC identifier rather than normalizing
    one, so emitting the authored bytes would produce an IR that §2 says must exist and that
    raises the moment anyone asks it for a ``graph_version``. The label below is authored as
    ``"cafe"`` + U+0301; it must come out as the single-codepoint form and must digest.
    """
    import unicodedata

    envelope = extract(sg.build_non_nfc_label_graph())
    conditional = next(edge for edge in envelope.ir.edges if isinstance(edge, ConditionalEdge))
    label = next(iter(conditional.path_map))

    assert unicodedata.is_normalized("NFC", label)
    assert label == unicodedata.normalize("NFC", "café")
    assert envelope.graph_version().startswith("sha256:")


def test_a_send_hinted_router_is_classified_send() -> None:
    """§6's classification, on the shape EX-02 left as the marker for it.

    This test is that marker, rewritten to state the ruling rather than the gap: a router
    declared ``-> list[Send]`` with ``path_map=["book_leg"]`` is the §6 worked example, and §6
    classifies it ``kind: send`` — "one ``{from, to, kind: send}`` edge per declared target".
    The conditional edge it used to extract to is *gone*, which is the half of the change a
    test that only looked for the new edge would have missed.

    Nothing about the fan-out's N is recorded, which is the other half of the worked example:
    the edge is the template, and P-09 treats the count as unbounded.
    """
    envelope = extract(sg.build_send_hinted_router_graph())
    sends = [edge for edge in envelope.ir.edges if isinstance(edge, SendEdge)]

    assert [edge for edge in envelope.ir.edges if isinstance(edge, ConditionalEdge)] == []
    assert len(sends) == 1
    assert (sends[0].from_, sends[0].to) == ("plan_step", "book_leg")
    assert sends[0].condition == "route_legs"
    assert constructs(envelope) == []


# ── nodes and node ids ──────────────────────────────────────────────────────────────────


def test_node_names_are_escaped_by_the_ledger_grammar() -> None:
    """§3 row 1: the only escaping a top-level name needs is ``/`` → ``%2F``, ``%`` → ``%25``.

    Both characters are legal in a substrate node name and both are structural in a node id,
    so the escape is what keeps ``node_id.split("/")`` correct with no context (§5.1). The
    references that point at these nodes are escaped by the same rule, so they still compare
    by byte equality.
    """
    envelope = extract(sg.build_escaped_names_graph())

    assert [node.id for node in envelope.ir.nodes] == ["act%25step", "plan%2Fstep"]
    assert envelope.ir.entry == "plan%2Fstep"
    assert envelope.ir.finish == "act%25step"
    assert {
        (edge.from_, edge.to) for edge in envelope.ir.edges if isinstance(edge, NormalEdge)
    } == {("plan%2Fstep", "act%25step")}


def test_the_sentinel_segments_are_never_emitted_as_nodes() -> None:
    """§5.1: ``__start__``/``__end__`` are reserved and extraction never emits them, per level."""
    ids = {
        node.id
        for envelope in map(extract, (f() for f in sg.EXTRACTABLE_BUILDERS.values()))
        for node in envelope.ir.nodes
    }

    assert not ids & {START, END}


def test_a_reference_to_an_undeclared_node_is_emitted_not_refused() -> None:
    """Whether a reference resolves is P-01's verdict, never ``extract()``'s.

    §2 puts well-formedness outside extraction in terms, and P-01 owns the
    ``edge-target-undefined`` family. Refusing here would move a verification verdict into
    the extractor and leave P-01 with nothing to report.
    """
    builder: StateGraph[sg.SentinelState] = StateGraph(sg.SentinelState)
    builder.add_node("plan_step", sg.raiser("plan_step"))
    builder.add_edge(START, "plan_step")
    builder.add_edge("plan_step", "ghost_step")
    builder.add_edge("plan_step", END)

    envelope = extract(builder)

    assert ("plan_step", "ghost_step") in {
        (edge.from_, edge.to) for edge in envelope.ir.edges if isinstance(edge, NormalEdge)
    }
    assert [node.id for node in envelope.ir.nodes] == ["plan_step"]


# ── retry_policy: the two DEC-18 D3 projection rules ─────────────────────────────────────


def test_declared_exception_types_project_to_opaque_name_strings() -> None:
    """§3: "``retry_on`` entries become opaque exception-name strings"; timing is dropped.

    The four timing members carry no verification content (IR-SPEC §3.2), so their absence
    is by design and needs no warning.
    """
    envelope = extract(sg.build_retry_graph())
    policies = {
        node.id: node.annotations.retry_policy
        for node in envelope.ir.nodes
        if node.annotations is not None
    }

    assert policies["declared_step"] is not None
    assert policies["declared_step"].max_attempts == 4
    assert policies["declared_step"].retry_on == ("ValueError", "KeyError")


def test_a_callable_retry_on_projects_empty_and_says_so(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """DEC-18 D3: ``retry_on: []`` means "declared policy, opaque trigger set", paired.

    The pairing is normative because the core-IR-only reading inverts the fact: the
    substrate's runtime reads a literal empty sequence as "retries on nothing", while the
    policy here retries on the library default set. The warning is what carries the
    difference, so this test asserts the pair, not the slot.
    """
    envelope = extract(sg.build_retry_graph())
    policies = {
        node.id: node.annotations.retry_policy
        for node in envelope.ir.nodes
        if node.annotations is not None
    }

    assert policies["defaulted_step"] is not None
    assert policies["defaulted_step"].max_attempts == 3
    assert policies["defaulted_step"].retry_on == ()

    paired = [
        warning
        for warning in envelope.warnings_for("defaulted_step")
        if warning.detail.get("construct") == "retry-on-opaque"
    ]
    assert len(paired) == 1
    assert "retries on nothing" in paired[0].detail["why"]
    assert capsys.readouterr().out == ""  # nothing printed: warnings ride the envelope


def test_a_retry_policy_sequence_projects_the_first_and_records_the_count() -> None:
    """DEC-18 D3: project the first policy (first-match semantics), warn with the count."""
    envelope = extract(sg.build_retry_graph())
    policies = {
        node.id: node.annotations.retry_policy
        for node in envelope.ir.nodes
        if node.annotations is not None
    }

    assert policies["sequenced_step"] is not None
    assert policies["sequenced_step"].max_attempts == 2
    assert policies["sequenced_step"].retry_on == ("TimeoutError",)

    flattened = [
        warning
        for warning in envelope.warnings_for("sequenced_step")
        if warning.detail.get("construct") == "retry-policy-sequence-flattened"
    ]
    assert len(flattened) == 1
    assert "2 retry policies" in flattened[0].detail["why"]


def test_a_single_retry_policy_is_not_read_as_a_sequence_of_its_fields() -> None:
    """The substrate's ``RetryPolicy`` is a ``NamedTuple``, so it *is* a ``Sequence``.

    Asking "is it a sequence" before "is it a policy" reads one policy as six fields and
    projects ``initial_interval``. The order of those two tests is what this pins.
    """
    builder: StateGraph[sg.SentinelState] = StateGraph(sg.SentinelState)
    builder.add_node(
        "plan_step",
        sg.raiser("plan_step"),
        retry_policy=RetryPolicy(max_attempts=9, retry_on=ValueError),
    )
    builder.add_edge(START, "plan_step")
    builder.add_edge("plan_step", END)

    envelope = extract(builder)
    annotations = envelope.ir.nodes[0].annotations

    assert annotations is not None
    assert annotations.retry_policy is not None
    assert annotations.retry_policy.max_attempts == 9
    assert topology(envelope) == ()


def test_an_empty_retry_policy_sequence_declares_nothing() -> None:
    """``retry_policy=[]`` attaches no policy, so no slot and — importantly — no warning.

    The flattening warning says "policies were dropped"; nothing was dropped here. Emitting
    it would put a workflow outside the strict-mode bar for a declaration its author did not
    make, which is the same over-firing DEC-18 scoped out of the missing-wiring trigger.
    """
    builder: StateGraph[sg.SentinelState] = StateGraph(sg.SentinelState)
    builder.add_node("plan_step", sg.raiser("plan_step"), retry_policy=[])
    builder.add_edge(START, "plan_step")
    builder.add_edge("plan_step", END)

    envelope = extract(builder)

    assert envelope.ir.nodes[0].annotations == Annotations(pure=True)
    assert topology(envelope) == ()


@pytest.mark.parametrize(
    ("retry_on", "expected", "warned"),
    [
        ((), (), []),
        ({ValueError}, (), ["retry-on-opaque"]),
        ([ValueError, sg.SentinelTrigger()], (), ["retry-on-opaque"]),
        ([ValueError, KeyError], ("ValueError", "KeyError"), []),
    ],
    ids=["empty-tuple", "set", "foreign-member", "all-types"],
)
def test_the_retry_on_pairing_rule_distinguishes_empty_from_opaque(
    retry_on: object,
    expected: tuple[str, ...],
    warned: list[str],
) -> None:
    """DEC-18 D3: an *unpaired* ``retry_on: []`` is the literal empty set; a paired one is opaque.

    That distinction is the whole point of making the pairing normative, so it has to survive
    every route to the empty projection. ``retry_on=()`` genuinely declares "retries on
    nothing" and must not be warned. A ``set``, and a sequence holding something that is not
    an exception type, are both unreadable and must be — and neither is coerced: the foreign
    member raises from ``__str__`` and ``__repr__``, so a projection that rendered it would
    fail here instead of putting a memory address inside ``graph_version``.

    A partly-recognizable sequence falls to the opaque form whole rather than projecting the
    members it *can* read: a partial list would claim the trigger set is exactly those.
    """
    builder: StateGraph[sg.SentinelState] = StateGraph(sg.SentinelState)
    builder.add_node(
        "plan_step",
        sg.raiser("plan_step"),
        retry_policy=RetryPolicy(max_attempts=3, retry_on=retry_on),  # type: ignore[arg-type]
    )
    builder.add_edge(START, "plan_step")
    builder.add_edge("plan_step", END)

    envelope = extract(builder)
    annotations = envelope.ir.nodes[0].annotations

    assert annotations is not None
    assert annotations.retry_policy is not None
    assert annotations.retry_policy.retry_on == expected
    assert constructs(envelope) == warned


@pytest.mark.parametrize("attached", [object(), ["not a policy"]], ids=["bare", "in-sequence"])
def test_an_unrecognized_retry_policy_is_warned_not_duck_typed(attached: object) -> None:
    """A slot value outside the substrate's own contract is warned, never read through.

    The substrate types the slot ``RetryPolicy | Sequence[RetryPolicy] | None``; anything
    else is out of contract. Reading ``max_attempts`` off it anyway would be a duck-typed
    call into a foreign object — the thing §1 rule 3's closed operation list exists to stop —
    and would crash extraction on an object §2 says must extract with warnings instead.
    """
    builder: StateGraph[sg.SentinelState] = StateGraph(sg.SentinelState)
    # The substrate's own signature refuses this, which is the point: the value is out of
    # its contract, and the question is what extraction does when one reaches it anyway.
    builder.add_node("plan_step", sg.raiser("plan_step"), retry_policy=attached)  # type: ignore[call-overload]
    builder.add_edge(START, "plan_step")
    builder.add_edge("plan_step", END)

    envelope = extract(builder)

    assert envelope.ir.nodes[0].annotations == Annotations(pure=True)
    assert constructs(envelope) == ["retry-policy-unrecognized"]


def test_a_node_with_no_retry_policy_carries_only_what_the_chain_resolved() -> None:
    """The two sources of ``annotations`` compose, and neither invents the other.

    ``retry_policy`` is §3's projection from the builder and ANNOTATION §1 puts it "out of
    annotation reach", so the two can never collide. A node with no policy carries whatever
    the §3 chain resolved and nothing else — here the D-011 default, since these fixtures
    declare no contract. Absence still round-trips as absence: a node with neither carries no
    ``annotations`` object at all, which is the test below.
    """
    envelope = extract(sg.build_retry_graph())
    plain = next(node for node in envelope.ir.nodes if node.id == "plain_step")

    assert plain.annotations == Annotations(pure=True)
    assert plain.annotations is not None
    assert plain.annotations.retry_policy is None


def test_a_node_with_neither_source_carries_no_annotations_object() -> None:
    """Absence round-trips as absence: an empty ``annotations`` would not omit-normalize away.

    Asserted against the assembler directly, because no builder can reach it any more: §4's
    D-011 defaults resolve *every* undeclared node to ``pure`` or to ``effect: [write]``, so a
    node whose contract is empty is now only produced by a path that discarded every slot it
    resolved (the carriability pass, ANNOTATION §3). The claim is worth keeping under test
    rather than deleting with its last live caller: canonical form **preserves** an empty
    object (IR-SPEC §6.3 omits ``null``, defaults and empty *arrays*), so ``annotations: {}``
    is the positive claim "this node declares nothing", which is a different document from a
    node that carries no contract at all.
    """
    from gebra.extraction.builder import _annotations
    from gebra.extraction.digests import NodeDigests

    policy = IRRetryPolicy(max_attempts=2, retry_on=())

    assert _annotations(None, None, None) is None
    assert _annotations(None, NodeContract(), None) is None
    assert _annotations(None, None, NodeDigests()) is None
    assert _annotations(policy, NodeContract(), None) == Annotations(retry_policy=policy)


# ── the object-boundary refusals ────────────────────────────────────────────────────────


def test_a_targetless_router_is_a_dynamic_edge() -> None:
    """§6's targetless form, in the shape DEC-28 ruled — replacing EX-02's interim refusal.

    Four claims, and each is one of the traps DEC-18 D4 named. The edge exists, so the router
    is not deleted from hash scope and P-01 has a source to see. It carries **no ``path_map``
    member at all**, so the "complete and empty" assertion an empty map would make is not
    representable rather than merely avoided — and the model refuses one, so a later edit cannot
    reintroduce it. The guard rides along as ``condition``, because a router's declared name is
    the one thing that *is* known about it. And the document says ``1.1``, which is the lowest
    minor that admits the kind (IR-SPEC §8's minimal stamping).
    """
    envelope = extract(sg.build_targetless_router_graph())
    (dynamic,) = [edge for edge in envelope.ir.edges if isinstance(edge, DynamicEdge)]

    assert envelope.ir.ir_version == "1.1"
    assert (dynamic.from_, dynamic.condition) == ("plan_step", "route_dynamically")
    assert not hasattr(dynamic, "path_map")
    with pytest.raises(ValidationError):
        DynamicEdge.model_validate(
            {"kind": "dynamic", "from": "plan_step", "path_map": {}}, by_alias=True
        )
    assert constructs(envelope) == ["router-without-declared-targets"]
    assert envelope.graph_version().startswith("sha256:")


def test_a_nonstring_routing_label_is_refused_rather_than_coerced() -> None:
    """Two reasons, and either alone would be enough.

    The substrate types a ``path_map`` key ``Hashable``; ir types it ``str``; the spec
    **specifies refusal** for the difference (INTROSPECTION-SPEC §6, ruled at DEC-32).
    Choosing ``str(label)`` here would fix a ``graph_version`` surface by improvisation.
    It would also *call* the label's ``__str__``, which §1's closed operation list does
    not admit — and the fixture's label raises from both ``__str__`` and ``__repr__``,
    so a coercion anywhere on this path fails the run rather than passing quietly. The
    refusal names the caller's fix: string labels.
    """
    with pytest.raises(ExtractionError) as caught:
        extract(sg.build_nonstring_label_graph())

    assert caught.value.reason is ExtractionErrorReason.CONSTRUCT_NOT_CARRIED
    assert "SentinelLabel" in str(caught.value)  # named by its type, never rendered
    assert "Use string labels" in str(caught.value)  # the workaround, stated (DEC-32)


def test_two_labels_sharing_one_nfc_form_are_refused_never_merged() -> None:
    """DEC-32 ruling 2: a label collision is an error, never a merge.

    ``café`` composed and decomposed are distinct Python strings the substrate holds side
    by side; after the IR's NFC normalization (IR-SPEC §6.3) they name one ``path_map``
    key. Before the ruling this path kept the last writer — a declared edge silently
    vanished from ``graph_version`` with no warning. The refusal is the fix, and the
    reason is its own code: the collision is a fact of the object (rename one label),
    not of the build, so ``CONSTRUCT_NOT_CARRIED`` would be the wrong claim.
    """
    with pytest.raises(ExtractionError) as caught:
        extract(sg.build_nfc_collision_label_graph())

    assert caught.value.reason is ExtractionErrorReason.LABEL_COLLISION
    assert "caf\u00e9" in str(caught.value)
    assert "rename one label" in str(caught.value)


def test_a_str_mixin_enum_label_carries_its_verbatim_value() -> None:
    """DEC-32's str-subclass clause, pinned against the accident chain that delivers it.

    A ``str``-mixin enum member IS a ``str``: it passes the label boundary as a string
    and the IR carries its verbatim **value** — never ``str(member)`` (whose render
    differs and here raises) and never ``.name``. This pins hash-scoped behaviour the
    build has shipped since EX-02; the spec now states it (INTROSPECTION-SPEC §6,
    DEC-32) rather than leaving it to the implementation's fast path.
    """
    ir = extract(sg.build_str_mixin_enum_label_graph()).ir

    routed = next(e for e in ir.edges if e.kind == "conditional")
    assert set(routed.path_map) == {"crimson"}  # the value; never "RED", never a render
    assert routed.path_map["crimson"] == "act_step"


def test_the_label_projection_returns_a_built_in_str_for_a_subclass() -> None:
    """The ``"".join((label,))`` spelling is load-bearing, pinned directly (EX-18).

    NFC's already-normal fast path returns a str-SUBCLASS object unchanged, and the
    label then becomes a dict key and a collision-set member — both of which would run
    a subclass ``__hash__``/``__eq__``. The join reads the buffer at C level and yields
    a built-in ``str``; if it regresses to the bare label, this test fails even though
    the model-level assertions above keep passing (the subclass here raises from every
    dunder the projection must not touch).
    """

    class Hostile(str):
        def __str__(self) -> str:
            raise AssertionError("__str__ ran")

        def __hash__(self) -> int:
            raise AssertionError("__hash__ ran")

        def __eq__(self, other: object) -> bool:
            raise AssertionError("__eq__ ran")

    projected = builder_module._path_map_label(
        Hostile("caf\u00e9"), workflow=object(), where="unit probe"
    )
    assert type(projected) is str
    assert projected == "caf\u00e9"


def test_a_node_named_with_the_empty_string_is_refused() -> None:
    """The substrate admits ``add_node("")``; no node-id grammar admits ``""`` (§5.1).

    Distinct from the two refusals above: those are facts about this build, and a later one
    lifts them. This one no build lifts — the fix is to name the node.
    """
    with pytest.raises(ExtractionError) as caught:
        extract(sg.build_unnamed_node_graph())

    assert caught.value.reason is ExtractionErrorReason.UNREPRESENTABLE_NODE_ID
    assert caught.value.object_type == "langgraph:StateGraph"


def test_an_empty_builder_is_still_refused_at_the_boundary() -> None:
    """The §2 exception survives the path landing: the refusal is the object's, not the build's."""
    empty: StateGraph[sg.SentinelState] = StateGraph(sg.SentinelState)

    with pytest.raises(ExtractionError) as caught:
        extract(empty)

    assert caught.value.reason is ExtractionErrorReason.EMPTY_NODE_SET


# ── the envelope's own obligations ──────────────────────────────────────────────────────


def test_warnings_ride_the_envelope_and_never_move_the_digest() -> None:
    """IR-SPEC §6.4: the envelope is outside hash scope, by construction rather than by rule.

    Two builders with the same topology and different warning sets must digest identically —
    the barrier graph's flattening warnings say something about the *builder*, not about the
    IR that came out of it.
    """
    warned = extract(sg.build_barrier_graph())
    plain: StateGraph[sg.SentinelState] = StateGraph(sg.SentinelState)
    for name in ("plan_step", "act_step", "summarize_step", "review_step"):
        plain.add_node(name, sg.raiser(name))
    plain.add_edge(START, "plan_step")
    plain.add_edge(START, "act_step")
    for source in ("plan_step", "act_step"):
        for target in ("summarize_step", "review_step"):
            plain.add_edge(source, target)
    plain.add_edge("summarize_step", END)
    plain.add_edge("review_step", END)

    assert warned.warnings != ()
    assert topology(extract(plain)) == ()
    assert warned.graph_version() == extract(plain).graph_version()


def test_every_warning_carries_the_four_facts_its_row_names() -> None:
    """§8's ``unsupported-construct`` row: construct kind, location, why, whether IR is partial.

    Asserted over every shape that warns rather than one of them, so a new emission site that
    forgets a key fails here instead of being discovered by a consumer.
    """
    seen = 0
    for factory in sg.EXTRACTABLE_BUILDERS.values():
        for warning in extract(factory()).warnings:
            if warning.code is not ExtractionWarningCode.UNSUPPORTED_CONSTRUCT:
                continue
            seen += 1
            assert set(warning.detail) == {"construct", "location", "why", "ir_partial"}
            assert isinstance(warning.detail["location"], dict)
            assert warning.detail["why"]
            assert isinstance(warning.detail["ir_partial"], bool)

    assert seen >= 5


def test_a_sidecar_entry_reaches_the_ir_and_moves_the_digest(tmp_path: Path) -> None:
    """The §2 lookup and the §3 chain now compose — and the digest is where you see it.

    This test has been the marker for the resolution card twice. EX-02 left it asserting that
    ``extracted_from.sidecar`` stayed ``None`` because no sidecar was ever opened; EX-09 made a
    file discoverable and left it asserting that the IR was byte-identical with and without
    one, because §3's chain did not exist. It exists now, so both halves flip: the entry fills
    the slots the higher tiers left open, and §2's own warning — "sidecar-filled annotations
    sit *inside* the ``graph_version`` hash scope" — becomes a demonstrable fact rather than a
    forward-looking note. The entry names one node, so the other two are untouched, which is
    what makes the digest move attributable.
    """
    sidecar = tmp_path / "gebra.toml"
    sidecar.write_bytes(
        b'schema = "gebra-sidecar-v1"\n[nodes.plan_step]\nreads = ["query"]\neffects = ["network"]\n'
    )

    with_sidecar = extract(sg.build_sentinel_graph(), sidecar=sidecar)
    without = extract(sg.build_sentinel_graph(), sidecar=tmp_path / "absent.toml")

    assert with_sidecar.extracted_from.sidecar == str(sidecar.resolve())
    assert with_sidecar.ir != without.ir
    assert with_sidecar.graph_version() != without.graph_version()

    resolved = {node.id: node.annotations for node in with_sidecar.ir.nodes}
    assert resolved["plan_step"] == Annotations(input=("query",), effect=("network",))
    assert resolved["act_step"] == Annotations(pure=True)
    # The declared slots are declared-grade; the slot no tier declared is not present at all,
    # because the sidecar closed `effect` and §4's D-011 pair withdraws when either half is
    # taken (a defaulted `pure` beside a declared `effect` is the contradiction §3's
    # resolved-contract pass exists to repair, so the tier never assembles it).
    assert with_sidecar.slot_grade("plan_step", "input") is SlotGrade.DECLARED
    assert with_sidecar.slot_grade("plan_step", "effect") is SlotGrade.DECLARED
    assert with_sidecar.slot_grade("act_step", "pure") is SlotGrade.DEFAULTED


def test_the_extracted_ir_is_what_a_validator_consumes() -> None:
    """Extractor out, validator in — the two lanes compose over a real builder.

    Worth asserting as one chain rather than trusting the model type: this is the first card
    where an IR that no fixture author wrote reaches a property validator, and the DEC-18 D2
    ruling is only correct if the empty ``finish`` it now produces is *verifiable*.

    It is, and the three verdicts are each the intended one. The router-terminated graph
    **passes** P-01 with ``finish: []``: END is reachable through the (m3) labels, so no sink
    is stranded — which is the executable form of the argument that a warning there would
    have been a false positive. The unwired builder **fails**, fatally, because nothing is
    reachable from START — extraction stayed total and handed the verdict to P-01, exactly
    where §2 puts it.
    """
    from gebra.verify import check_graph_well_formed

    passing = {
        name: check_graph_well_formed(extract(sg.EXTRACTABLE_BUILDERS[name]()).ir)
        for name in ("sentinel", "router_terminated", "barrier")
    }
    assert [report.result for report in passing.values()] == ["pass"] * 3

    unwired = check_graph_well_formed(extract(sg.build_unwired_graph()).ir)
    assert unwired.result == "fail"
    assert unwired.failure is not None
    reported = {unwired.failure.property_condition} | {
        co.property_condition for co in unwired.failure.co_failures or ()
    }
    assert "node-unreachable-from-start" in reported


def test_the_builder_family_is_wired_at_import() -> None:
    """``gebra.extract`` reaches this path without a test having to register it."""
    from gebra.extraction import extract_builder, extractor_for

    assert extractor_for(ObjectFamily.BUILDER) is extract_builder


# ── WA-07 — the tripwire for the path this card lands ────────────────────────────────────

#: The guarded child. Network primitives raise from the first line and socket construction is
#: only counted until the imports are done — the same bounded-import phase ``test_dispatch``
#: explains, for the same reason (extraction must import the substrate to read its classes).
#: Then ``StateGraph.compile`` is taken away and every §3 shape is extracted.
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
        raise AssertionError("a socket was created on the builder extraction path")


socket.socket = _CountSocket
socket.getaddrinfo = _record("getaddrinfo")
socket.gethostbyname = _record("gethostbyname")
socket.create_connection = _record("create_connection")

import gebra
from gebra.extraction import ExtractionError
from langgraph.graph.state import StateGraph
from tests.sample_workflows import sentinel_graph as sg

# Build every shape while compile() still exists — building is not compiling, and none of
# these factories calls a node, a router or compile().
extractable = {name: factory() for name, factory in sg.EXTRACTABLE_BUILDERS.items()}
refused = {name: factory() for name, factory in sg.REFUSED_BUILDERS.items()}

assert attempts == [], attempts
socket.socket = _TripSocket
StateGraph.compile = _record("StateGraph.compile")

extracted = 0
for name, builder in extractable.items():
    envelope = gebra.extract(builder)
    assert envelope.ir.nodes, name
    envelope.graph_version()          # canonicalize and digest, still under the guard
    extracted += 1

boundary = 0
for name, builder in refused.items():
    try:
        gebra.extract(builder)
    except ExtractionError:
        boundary += 1

assert (extracted, boundary) == (%d, %d), (extracted, boundary)
"""

_REPORT = "print(attempts)\n"


def _run_guarded(probe: str = "") -> subprocess.CompletedProcess[str]:
    body = _TRIPWIRE % (len(sg.EXTRACTABLE_BUILDERS), len(sg.REFUSED_BUILDERS))
    return subprocess.run(
        [sys.executable, "-c", body + probe + _REPORT],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_builder_extraction_invokes_nothing_and_compiles_nothing() -> None:
    """The WA-07 claim for the §3 path, in a fresh interpreter.

    Four claims at once, and the fixtures are what make them real rather than asserted: every
    node function and router in every builder below raises if it is called, so an extraction
    that touched one would fail the run; ``StateGraph.compile`` is replaced by a raiser before
    the first extraction, so §1 rule 2 ("MUST NOT execute ``StateGraph.compile()``") is
    checked rather than reviewed; nothing resolves a name or opens a connection at any point,
    imports included; and nothing so much as constructs a socket while extracting.

    The child asserts its own counts, so an extraction pass that silently stopped reaching the
    fixtures would fail here rather than pass with nothing to prove — and because the counts
    come from the fixture tables, a shape added to either table joins this claim with it.
    Canonicalization and the digest run inside the guard too: hashing walks the whole IR, and
    a value that reached out on ``__str__`` would be caught there rather than downstream.
    """
    result = _run_guarded()

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "[]", result.stdout
    assert "WA07-TRIP" not in result.stderr, result.stderr


@pytest.mark.parametrize(
    ("probe", "expected"),
    [
        ("sg.build_sentinel_graph().compile()\n", "StateGraph.compile was reached"),
        ("socket.socket()\n", "a socket was created"),
        ("socket.getaddrinfo('example.invalid', 80)\n", "getaddrinfo was reached"),
        ("socket.gethostbyname('example.invalid')\n", "gethostbyname was reached"),
        ("socket.create_connection(('example.invalid', 80))\n", "create_connection was reached"),
    ],
    ids=["compile", "socket", "getaddrinfo", "gethostbyname", "create_connection"],
)
def test_each_raiser_is_armed(probe: str, expected: str) -> None:
    """A tripwire nobody trips proves nothing — so every raiser gets its own control.

    All five, not just ``compile``: this child is an independent copy of the guard prologue,
    so a copy-paste slip that dropped one line would leave that raiser unarmed and the claim
    it carries silently vacuous, with everything still green. The controls run *after* the
    child's own assertions, so each one proves the raiser was live at the end of the very run
    that made the claim.

    ``compile`` is the one an extractor is most tempted to break — compiling would make
    several §3 surfaces easier to read — which is why §1 rule 2 names it explicitly.
    """
    result = _run_guarded(probe)

    assert result.returncode != 0
    assert expected in result.stderr


def test_the_tripwire_covers_the_shapes_this_path_handles() -> None:
    """The claim above is only as wide as the tables it quantifies over.

    The child's counts are derived from these tables, so both sides move together if a
    fixture is dropped — which means the tables themselves need a floor. Without one, the
    guarded run could shrink to a single builder and every assertion would still pass.
    """
    assert len(sg.EXTRACTABLE_BUILDERS) >= 13
    assert len(sg.REFUSED_BUILDERS) >= 2
    assert set(sg.EXTRACTABLE_BUILDERS) & set(sg.REFUSED_BUILDERS) == set()


def test_the_shape_fixtures_are_armed() -> None:
    """Every node function and router in the §3 shape fixtures raises when called.

    All of them, not a sample: an unarmed fixture is a hole exactly where the claim above is
    strongest, since that is the builder whose extraction would then prove nothing.
    """
    state: sg.SentinelState = {"query": "q", "plan": "p", "answer": "a"}
    checked = 0

    for factory in (*sg.EXTRACTABLE_BUILDERS.values(), *sg.REFUSED_BUILDERS.values()):
        builder = factory()
        callables: list[Any] = [spec.runnable for spec in builder.nodes.values()]
        callables += [
            spec.path for branches in builder.branches.values() for spec in branches.values()
        ]
        for runnable in callables:
            function = getattr(runnable, "func", runnable)
            with pytest.raises(sg.SentinelExecutedError):
                function(state)
            checked += 1

    assert checked >= 30
