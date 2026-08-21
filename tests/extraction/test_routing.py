"""INTROSPECTION-SPEC §6 — the ``send``/``conditional`` classification and its two neighbours.

Card EX-03. Three rules meet on every routing declaration and each has its own section below:

* **the kind**, from the declaration's declared return-type hint and from nothing else (§6's
  classification rule, and §1's "never via body inspection");
* **the targets**, which the kind does not supply — a declaration with none is the ``dynamic``
  form (DEC-28), and a classified declaration with some is emitted over exactly those;
* **the codomain**, when a ``Literal`` hint declares one distinct from ``path_map``, which ir 1.0
  has no slot for and §6 sends to provenance.

The fourth section is WA-07's, and it is the card's second acceptance box: the hazard §1 rule 3
names — ``get_type_hints()`` evaluating string and forward-reference annotations — with its
tripwire, its armed controls, and the one residue the rule licenses stated rather than hidden.

The classification claims are quantified over
:data:`~tests.sample_workflows.sentinel_routing.HINT_CASES`, which is §6's own sentence as a
table, so a form the spec names cannot be missing from the suite without the table showing it.
"""

from __future__ import annotations

import subprocess
import sys
import types
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from gebra.extraction import extract
from gebra.extraction.builder import _router_hint
from gebra.extraction.routing import RouterHint, declared_return_hint
from gebra.ir.models import ConditionalEdge, DynamicEdge, Edge, SendEdge
from tests.extraction.test_builder import constructs
from tests.sample_workflows import sentinel_graph as sg
from tests.sample_workflows import sentinel_routing as sr
from tests.sample_workflows import sentinel_routing_futures as futures

REPO_ROOT = Path(__file__).resolve().parents[2]


def edges_of(envelope: Any, kind: type[Edge]) -> list[Any]:
    """Every edge of one kind, in emission order."""
    return [edge for edge in envelope.ir.edges if isinstance(edge, kind)]


# ── §6's classification rule, row by row ─────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("label", "declaration", "kind", "codomain"),
    sr.HINT_CASES,
    ids=[row[0] for row in sr.HINT_CASES],
)
def test_every_declared_hint_form_classifies_as_the_spec_says(
    label: str, declaration: Callable[..., object], kind: str, codomain: tuple[str, ...]
) -> None:
    """§6's classification sentence, one row per form it names.

    ``send`` **iff** the hint names ``Send`` — "bare ``Send``, ``list[Send]``/``Sequence[Send]``,
    or a ``Union``/``Command`` form admitting one" — and every other form, "a ``Literal[...]``
    label hint, a plain ``str`` hint, … or no hint at all", is ``conditional``. The codomain
    column rides the same read, because it comes off the same hint.

    Two rows are worth naming: ``Command[Literal[...]]`` classifies **conditional**, since it
    names no ``Send``; and a hint of ``None`` is *declared* — it is a hint that licenses nothing,
    which is a different fact from having none, even though §6 gives the two the same kind.
    """
    hint = declared_return_hint(declaration)

    assert hint.kind == kind, label
    assert hint.codomain == codomain, label
    assert hint.declared is (label != "no hint"), label


def test_the_hint_table_covers_every_form_the_spec_names() -> None:
    """The parametrization above is only as wide as the table, so the table needs a floor.

    Both poles, separately: a table that drifted to all-``send`` or all-``conditional`` rows
    would keep every assertion above green while covering half the rule.
    """
    kinds = [kind for _, _, kind, _ in sr.HINT_CASES]

    assert kinds.count("send") >= 7
    assert kinds.count("conditional") >= 7
    assert len({label for label, *_ in sr.HINT_CASES}) == len(sr.HINT_CASES)


def test_the_classification_reads_a_declaration_and_never_a_body() -> None:
    """§6: "read via ``typing.get_type_hints()`` …, never via body inspection".

    The strongest form of the claim available without a subprocess: every callable in the table
    records itself in a module-level ledger *before* raising, so a read that reached a body shows
    up even if something swallowed the exception. The ledgers must be empty after the whole
    table has been classified — twice over, since a second pass would also catch a read that
    memoized a body's answer.
    """
    sr.TRIPPED.clear()
    futures.TRIPPED.clear()

    for _ in range(2):
        for _label, declaration, _kind, _codomain in sr.HINT_CASES:
            declared_return_hint(declaration)

    assert sr.TRIPPED == []
    # The one exception is licensed and is the subject of its own test below: an annotation
    # *expression* runs when it is evaluated (§1 rule 3), and two rows in the table are exactly
    # that. Nothing else may appear here.
    assert set(futures.TRIPPED) <= {"annotation-expression-raised", "annotation-expression-ran"}


# ── the kind, as emitted edges ───────────────────────────────────────────────────────────


def test_a_send_hinted_router_emits_one_send_edge_per_declared_target() -> None:
    """§6: "emit one ``{from, to, kind: send}`` edge per declared target".

    One router per ``Send``-licensing form, each declaring ``act_step``: one send edge each, no
    conditional edge, and the branch name on each so that ``(from, condition)`` still identifies
    the group (§3's rule for a ``.branches``-derived edge, which §6's kind refinement does not
    touch). The expected ``condition`` set is derived from the router list the fixture was built
    from, so a form added there has to appear here too.
    """
    envelope = extract(sr.build_send_forms_graph())
    sends = edges_of(envelope, SendEdge)

    assert edges_of(envelope, ConditionalEdge) == []
    assert {(edge.from_, edge.to) for edge in sends} == {("plan_step", "act_step")}
    assert sorted(edge.condition or "" for edge in sends) == sorted(
        router.__name__ for router in sr.SEND_ROUTERS
    )
    assert constructs(envelope) == []
    assert envelope.ir.ir_version == "1.0"


def test_every_other_hint_form_stays_a_conditional_edge_over_its_declared_targets() -> None:
    """§6's conservative pole, as edges: five routers, five ``conditional`` edges, one target.

    ``route_literal`` is the row that shows the second static source doing its work — it declares
    no ``path_map`` at all, and the substrate reads the ``Literal`` hint into ``BranchSpec.ends``,
    so the target set is declared without an argument at the call site.
    """
    envelope = extract(sr.build_conditional_forms_graph())
    conditionals = edges_of(envelope, ConditionalEdge)

    assert edges_of(envelope, SendEdge) == []
    assert edges_of(envelope, DynamicEdge) == []
    assert len(conditionals) == 5
    assert {tuple(sorted(edge.path_map.items())) for edge in conditionals} == {
        (("act_step", "act_step"),)
    }
    assert constructs(envelope) == []


def test_a_node_hinted_send_classifies_its_declared_destinations() -> None:
    """The other §6 surface: ``StateNodeSpec.ends`` from ``destinations=``, classified by the
    node function's own hint.

    This is the case EX-02 emitted uniformly as ``conditional`` "because EX-02 reads no hints",
    and the refinement lands here as well as on ``BranchSpec``. No ``BranchSpec`` means no branch
    name, so the edge carries no ``condition`` — inventing one would put a string this build made
    up inside ``graph_version``.
    """
    envelope = extract(sr.build_node_destinations_send_graph())
    (send,) = edges_of(envelope, SendEdge)

    assert (send.from_, send.to, send.condition) == ("plan_step", "act_step", None)
    assert edges_of(envelope, ConditionalEdge) == []


def test_the_command_literal_idiom_stays_conditional() -> None:
    """``Command[Literal[...]]`` on a node declares targets and names no ``Send``.

    The mainstream Command-routing surface (PD-018 D4), and the one a hint-reading build could
    plausibly get wrong in the other direction: the hint is *read*, it declares the targets the
    substrate put in ``StateNodeSpec.ends``, and it classifies ``conditional`` because §6's
    licensing condition is naming ``Send`` rather than being a ``Command`` form.
    """
    envelope = extract(sg.build_destinations_graph())

    assert edges_of(envelope, SendEdge) == []
    assert {
        label
        for edge in edges_of(envelope, ConditionalEdge)
        for label in edge.path_map  # every group's labels
    } >= {"act_step"}


@pytest.mark.parametrize(
    "factory",
    [sr.build_dynamic_send_hinted_graph, sr.build_dynamic_command_router_graph],
    ids=["send-hinted", "command-hinted"],
)
def test_a_router_with_no_declared_targets_is_a_dynamic_edge(
    factory: Callable[[], StateGraph[sg.SentinelState]],
) -> None:
    """§6: "Classification licenses the kind only — emitting ``send`` edges additionally
    requires declared targets".

    Both fixtures carry a hint and neither declares a target, and the hint's *kind* is exactly
    what must not decide the outcome here: a ``Send``-hinted router with no ``path_map`` is §6's
    canonical map-reduce, and a ``Command[Literal[...]]``-hinted **router** declares nothing
    either (that form fills ``ends`` on the node surface only). Both are ``dynamic``, both stamp
    ``1.1``, and neither invents a target.
    """
    envelope = extract(factory())
    (dynamic,) = edges_of(envelope, DynamicEdge)

    assert edges_of(envelope, SendEdge) == []
    assert edges_of(envelope, ConditionalEdge) == []
    assert dynamic.from_ == "plan_step"
    assert dynamic.condition is not None
    assert envelope.ir.ir_version == "1.1"
    assert constructs(envelope) == ["router-without-declared-targets"]


def test_the_dynamic_form_stays_inside_hash_scope() -> None:
    """DEC-18 D4's second fence, checked rather than reviewed: the router is not omitted.

    Edge omission "deletes the router from hash scope and turns a warning into a P-01 FATAL
    false positive", so the ``dynamic`` edge has to be *in* the digest. Two graphs identical
    except for the router's presence must therefore differ in ``graph_version``, and the same
    graph twice must not.
    """
    with_router = extract(sr.build_dynamic_send_hinted_graph()).graph_version()
    again = extract(sr.build_dynamic_send_hinted_graph()).graph_version()
    without: StateGraph[sg.SentinelState] = StateGraph(sg.SentinelState)
    without.add_node("plan_step", sg.raiser("plan_step"))
    without.add_node("act_step", sg.raiser("act_step"))
    without.add_edge(START, "plan_step")
    without.add_edge("act_step", END)

    assert with_router == again
    assert with_router != extract(without).graph_version()


def test_a_send_template_carries_a_target_once_however_many_labels_named_it() -> None:
    """A send template is a template: two labels naming one node declare one edge.

    And the label that is not its own target has nowhere to ride on ``kind: send``, so it is
    reported rather than dropped quietly — one warning for the declaration, naming the labels.
    """
    envelope = extract(sr.build_relabelled_send_graph())
    (send,) = edges_of(envelope, SendEdge)
    (warning,) = [
        w for w in envelope.warnings if w.detail.get("construct") == "send-template-labels-dropped"
    ]

    assert (send.from_, send.to) == ("plan_step", "act_step")
    assert warning.detail["location"]["labels"] == ("leg",)
    assert warning.detail["ir_partial"] is True


def test_a_send_template_naming_end_drops_it_rather_than_writing_a_reference() -> None:
    """``to`` is a node id: the ``"END"`` literal is blessed for ``path_map`` values only.

    Writing ``to: "END"`` would make every downstream reader resolve a node named ``END`` — and
    P-01's graph model does exactly that (it special-cases the literal inside ``path_map`` and
    nowhere else), so the reference would become an ``edge-target-undefined`` FATAL on a workflow
    whose author declared nothing wrong. The declaration is dropped with its own warning, and the
    surviving target is still emitted.
    """
    envelope = extract(sr.build_send_to_end_graph())
    (send,) = edges_of(envelope, SendEdge)

    assert (send.from_, send.to) == ("plan_step", "act_step")
    assert constructs(envelope) == ["send-template-targets-end"]
    # And the dropped declaration did not become an END incidence by another route: `finish`
    # holds the node the plain `(act_step, END)` edge wired and not the router's source, so the
    # (m3) label half of the DEC-18 finish rule stayed out of it.
    assert envelope.ir.finish == "act_step"


@pytest.mark.parametrize(
    "factory",
    [sr.build_async_send_router_graph, sr.build_lambda_send_router_graph],
    ids=["async", "RunnableLambda"],
)
def test_the_hint_is_found_through_the_wrappers_the_substrate_adds(
    factory: Callable[[], StateGraph[sg.SentinelState]],
) -> None:
    """The declared hint is never on the object the substrate hands over.

    A router arrives as a ``RunnableCallable`` whose own ``__annotations__`` is empty, and for an
    ``async def`` its ``func`` is empty too — the callable is in ``afunc``, while a *sync*
    router's ``afunc`` holds a ``run_in_executor`` partial that must never be read as the
    declaration. Both are the ANNOTATION §6 wrapper walk's job, which is why this path reuses it
    rather than reaching for ``.func``.
    """
    envelope = extract(factory())
    (send,) = edges_of(envelope, SendEdge)

    assert (send.from_, send.to) == ("plan_step", "act_step")


# ── the codomain, where ir 1.0 has no slot ───────────────────────────────────────────────


def test_a_literal_codomain_beside_a_path_map_lands_in_provenance_only() -> None:
    """§6's codomain-capture rule, both halves.

    "Extraction MUST still read that hint … and record it in provenance as … router-codomain
    evidence, **never merged into ``path_map``**." So the edge is unchanged — one label, the one
    the author declared — and the wider codomain the return hint declares is beside the IR, where
    it cannot reach ``graph_version``.
    """
    envelope = extract(sr.build_codomain_distinct_graph())
    (conditional,) = edges_of(envelope, ConditionalEdge)
    (codomain,) = envelope.extracted_from.router_codomains

    assert conditional.path_map == {"go": "act_step"}
    assert codomain.node == "plan_step"
    assert codomain.condition == "route_literal_wider"
    assert codomain.labels == ("act_step", "plan_step")
    assert codomain.path_map_labels == ("go",)
    # "never merged into `path_map`", checked on the label the codomain adds: `plan_step` is a
    # declared node of this graph, so it *could* have been merged in as a label or a target
    # without anything else looking wrong. It is neither.
    assert "plan_step" not in conditional.path_map
    assert "plan_step" not in conditional.path_map.values()


def test_a_codomain_the_path_map_already_states_is_not_recorded_twice() -> None:
    """The record is for a codomain *distinct* from ``path_map``, which is §7.3 item 5's case.

    Where the two agree the hint is already in the IR — the substrate itself fills ``ends`` from
    a ``Literal`` hint when no ``path_map`` was declared — so a record would restate the edge and
    every ``Literal``-hinted router in every workflow would carry one.
    """
    envelope = extract(sr.build_conditional_forms_graph())

    assert envelope.extracted_from.router_codomains == ()


def test_the_codomain_record_never_moves_the_digest() -> None:
    """The envelope is outside hash scope (IR-SPEC §6.4), and this record is in the envelope.

    Held by construction rather than by inspection: the same graph with and without the wider
    return hint differs in ``path_map`` nowhere, so if the codomain reached the IR the two
    digests would differ.
    """
    wider = extract(sr.build_codomain_distinct_graph())
    narrow: StateGraph[sg.SentinelState] = StateGraph(sg.SentinelState)
    narrow.add_node("plan_step", sg.raiser("plan_step"))
    narrow.add_node("act_step", sg.raiser("act_step"))
    narrow.add_edge(START, "plan_step")
    narrow.add_edge("act_step", END)
    narrow.add_conditional_edges("plan_step", sr.route_literal_wider, {"go": "act_step"})

    assert wider.extracted_from.router_codomains != ()
    assert wider.graph_version() == extract(narrow).graph_version()


# ── WA-07: the annotation-evaluation hazard §1 rule 3 names ──────────────────────────────


def test_a_string_annotation_is_read_by_evaluating_it_and_nothing_else_runs() -> None:
    """The branch that must evaluate: two resolvable string hints, read correctly, nothing run.

    Under ``from __future__ import annotations`` the raw annotation is the string
    ``"list[Send]"``, so not evaluating it would mean not reading the declaration at all. Both
    routers classify from their evaluated hints and neither body is reached.
    """
    sr.TRIPPED.clear()
    futures.TRIPPED.clear()

    envelope = extract(sr.build_stringly_annotated_graph())

    assert len(edges_of(envelope, SendEdge)) == 1
    assert len(edges_of(envelope, ConditionalEdge)) == 1
    assert (sr.TRIPPED, futures.TRIPPED) == ([], [])
    assert constructs(envelope) == []


def test_an_unevaluable_hint_degrades_to_no_hint_rather_than_aborting() -> None:
    """§1 rule 3: "degrade any evaluation failure to an unknown hint (never abort, never execute
    repair logic)".

    The one shape a real builder can hold — ``add_node``'s schema inference evaluates the hint,
    gets a ``NameError``, and keeps the node — so this is the degradation running end to end
    rather than at a seam. The edge is still emitted over the declared targets, at the
    conservative kind, and the fact that a declared hint went unread is *reported*: no hint and
    an unreadable hint are different facts, and only the second is about this graph.
    """
    envelope = extract(sr.build_unevaluable_node_hint_graph())
    (conditional,) = edges_of(envelope, ConditionalEdge)
    (warning,) = [
        w for w in envelope.warnings if w.detail.get("construct") == "router-hint-unevaluable"
    ]

    assert conditional.path_map == {"act_step": "act_step"}
    assert edges_of(envelope, SendEdge) == []
    assert "NameError" in warning.detail["why"]
    assert "NoSuchNameAnywhere" in warning.detail["why"]
    assert warning.node == "plan_step"


@pytest.mark.parametrize(
    ("declaration", "expected"),
    [
        (futures.route_unresolvable, "NameError"),
        (futures.route_armed_annotation, "SentinelExecutedError"),
    ],
    ids=["unresolvable", "raising-expression"],
)
def test_every_way_a_hint_can_fail_to_read_degrades_the_same_way(
    declaration: Callable[..., object], expected: str
) -> None:
    """Two failure modes, one outcome — and the second is the hazard, not merely a bug.

    An unresolvable forward reference raises ``NameError``; an annotation expression that runs
    and fails raises whatever it likes. Both leave the router at ``conditional`` with the reason
    carried out, and neither escapes. The pinned substrate refuses to *attach* either of these
    (``add_conditional_edges`` evaluates the same annotations while building the graph and lets
    the exception through), so this is defence in depth — which is worth having, because "the
    substrate happens to check first" is not a property gebra controls.
    """
    hint = declared_return_hint(declaration)

    assert hint.declared is True
    assert hint.names_send is False
    assert hint.kind == "conditional"
    assert hint.degraded is not None
    assert expected in hint.degraded


def test_the_substrate_itself_refuses_a_router_whose_annotation_raises() -> None:
    """The framing fact for the test above, asserted rather than asserted-in-prose.

    LangGraph evaluates a router's annotations through ``BranchSpec.from_path``'s schema
    inference, so a ``StateGraph`` carrying an annotation expression that raises cannot be built
    in the first place. This is what bounds the residue below: at this substrate the expressions
    extraction can meet are the ones that already ran once, successfully, at build time.
    """
    builder: StateGraph[sg.SentinelState] = StateGraph(sg.SentinelState)
    builder.add_node("plan_step", sg.raiser("plan_step"))
    builder.add_edge(START, "plan_step")

    with pytest.raises(sg.SentinelExecutedError):
        builder.add_conditional_edges("plan_step", futures.route_armed_annotation, ["plan_step"])


def test_an_annotation_expression_runs_when_it_is_evaluated_and_that_is_the_ruled_residue() -> None:
    """§1 rule 3 in terms: "arbitrary annotation expressions run at extraction time".

    Stated as a passing test rather than left in a docstring, because it is the one thing on this
    path that *does* execute code the author wrote — and pretending otherwise is exactly what
    WA-07's tripwires exist to prevent. What is bounded is which code: the expression inside the
    annotation, evaluated in its own module's namespace, on a callable a routing declaration
    named. The router **body** is not reached, which is the claim §6 actually makes, and the
    ledger below is what separates the two.

    The residue is licensed and not gratuitous: §6 names ``get_type_hints()`` as the mechanism,
    and the alternative — writing an evaluator that admits only a "safe" subset of annotation
    expressions — would be improvising semantics for a read the spec already specifies.
    """
    sr.TRIPPED.clear()
    futures.TRIPPED.clear()
    graph = sr.build_arming_annotation_graph()  # the substrate evaluates it once, here
    futures.TRIPPED.clear()

    envelope = extract(graph)
    (send,) = edges_of(envelope, SendEdge)

    assert (send.from_, send.to) == ("plan_step", "act_step")
    assert futures.TRIPPED == ["annotation-expression-ran"]
    assert "route_arming_hint" not in futures.TRIPPED
    assert sr.TRIPPED == []


def test_reading_a_return_hint_evaluates_that_callables_other_annotations_too() -> None:
    """The evaluation's width, recorded rather than discovered later.

    ``typing.get_type_hints()`` has no per-member form, so asking it for a ``return`` hint
    evaluates the callable's parameter annotations as well — annotations this path never reads.
    That is a consequence of using §6's named mechanism, and narrowing it would mean
    hand-evaluating one annotation, which is an evaluator this card is not licensed to write. The
    exposure is bounded twice over: only string-annotated callables reach the evaluation at all
    (a resolved annotation object is read as it is), and only routing declarations are asked.
    """
    hint = declared_return_hint(futures.route_send_stringly)

    assert hint.names_send is True
    assert "state" in futures.route_send_stringly.__annotations__
    assert isinstance(futures.route_send_stringly.__annotations__["state"], str)


def test_a_resolved_annotation_is_read_without_evaluating_anything() -> None:
    """The narrowing that keeps the hazard off the common path.

    A module without the future import has real type objects in ``__annotations__``; they were
    evaluated at import time, and re-evaluating them would buy nothing and cost the parameter
    annotations. Checked by taking away the callable's globals: with no module namespace at all,
    ``get_type_hints`` could not resolve a string — and the hint still reads.
    """
    import types

    stripped = types.FunctionType(
        sr.route_send_list.__code__,
        {},  # no globals: an evaluation would have nothing to resolve against
        "route_send_list",
        sr.route_send_list.__defaults__,
        sr.route_send_list.__closure__,
    )
    stripped.__annotations__ = dict(sr.route_send_list.__annotations__)

    assert declared_return_hint(stripped).kind == "send"


def test_a_hint_object_that_answers_by_raising_degrades_rather_than_escaping() -> None:
    """§1 rule 3's degradation covers the whole read, not only the evaluation step.

    A type expression is an arbitrary object and reading its shape means reading ``__origin__``
    and ``__args__``; an object that raises on those is not a shape gebra can classify, and it
    must not become an exception out of ``gebra.extract()``.
    """

    # A plain object never triggers the reads: `typing.get_origin`/`get_args` gate on
    # isinstance against alias classes, so the original plain-`Hostile` fixture passed
    # VACUOUSLY (WA-07 pre-review F3, 2026-08-10) — zero property reads, the except path
    # never fired. A `types.GenericAlias` subclass IS admitted by that gate, so its
    # raising `__args__` genuinely reaches the walk, and the assertion below requires the
    # degradation to have actually fired.
    class Hostile(types.GenericAlias):
        """A genuine alias subclass that raises from the members the walk reads."""

        @property
        def __args__(self) -> object:  # type: ignore[override]
            raise RuntimeError("__args__ was read")

    def router(state: object) -> None:
        raise AssertionError

    router.__annotations__ = {"return": Hostile(list, (int,))}

    hint = declared_return_hint(router)

    assert hint.kind == "conditional"
    assert hint.declared is True
    assert hint.degraded is not None  # the fence fired — this test can no longer pass vacuously
    assert "__args__ was read" in hint.degraded


def test_a_send_router_declaring_only_end_emits_no_edges() -> None:
    """Pin of the total-carrier-loss disposition (PD-044 D15, ratified 2026-08-10).

    A send-classified router declaring ONLY `END` targets has every target dropped by D4
    (`send-template-targets-end`) — and the group is then NOT emitted at all: zero edges,
    never a `dynamic` edge (which would claim "targets unknown" when targets were declared),
    `ir_version` unaffected. Edge-omission-shaped, ruled acceptable because the substrate
    itself rejects `Send(END, ...)` at runtime — the shape is genuinely defective and the
    downstream P-01 dead-end FATAL is truthful. This pin makes the disposition drift-loud.
    """
    from gebra.extraction import extract

    # Module-level names only in the annotations: the substrate evaluates them at graph
    # build (D6's own substrate-evaluation fact), and a nested def sees module globals.
    def router(state: sg.SentinelState) -> Send:
        sr._trip("router body")
        raise AssertionError

    def worker(state: sg.SentinelState) -> dict[str, object]:
        sr._trip("worker body")
        raise AssertionError

    builder = StateGraph(sg.SentinelState)
    builder.add_node("worker", worker)
    builder.set_entry_point("worker")
    builder.set_finish_point("worker")
    builder.add_conditional_edges("worker", router, [END])

    env = extract(builder)
    assert env.ir.edges == ()  # total carrier loss: no send edge, no dynamic edge
    assert env.ir.ir_version == "1.0"  # a defective shape never flips the version
    assert any(
        "send-template-targets-end" in str(w) for w in (env.warnings or ())
    )  # the D4 warning fires per declaration


def test_a_send_hinted_node_with_no_declared_targets_stays_a_plain_node() -> None:
    """Pin of the empty-`ends` reading (IR-spec pre-review F1, 2026-08-10).

    `add_node("worker", fn)` where `fn` is Send/Command-hinted but declares NO targets (no
    `destinations=`, no `Command[Literal]`) never reaches the routing classification: it
    extracts as a plain node — no edge, no `dynamic` form, no §8 dynamic-dispatch warning.
    Whether §6's Command-node clause instead requires the dynamic fallback is routed to the
    PD-044 ratification (latitude record) — this pin exists so the behavior cannot drift
    while that question is open. Direction is conservative: no claim is invented.
    """
    from langgraph.graph import StateGraph

    from gebra.extraction import extract
    from tests.sample_workflows.sentinel_graph import SentinelState
    from tests.sample_workflows.sentinel_routing import _trip

    def worker(state: SentinelState) -> list[Send]:
        _trip("worker body")
        raise AssertionError

    builder = StateGraph(SentinelState)
    builder.add_node("worker", worker)
    builder.set_entry_point("worker")
    builder.set_finish_point("worker")

    env = extract(builder)
    assert [n.id for n in env.ir.nodes] == ["worker"]
    assert env.ir.edges == ()  # no dynamic edge, no send edge
    assert env.ir.ir_version == "1.0"  # minimal stamping: no dynamic construct present
    assert not any(
        "unsupported-construct" in str(getattr(w, "code", "")) and "dynamic" in str(w)
        for w in (env.warnings or ())
    )


def test_a_branch_path_with_a_hostile_bool_is_never_truth_tested() -> None:
    """WA-07 pre-review F1 (2026-08-10): no truthiness test on a foreign routing object.

    `spec.path or spec.runnable` dispatched to a user `__bool__` during extraction — a
    §1-rule-3-unlicensed operation demonstrated live at the review. The fix reads both
    attributes with explicit None checks; this fixture arms `__bool__`/`__len__` to raise,
    so any reintroduction of a truthiness test goes red here rather than executing user
    code silently.
    """

    class ArmedPath:
        """A routing callable whose truthiness is a tripwire."""

        def __bool__(self) -> bool:
            raise AssertionError("extraction truth-tested a routing object (__bool__)")

        def __len__(self) -> int:
            raise AssertionError("extraction truth-tested a routing object (__len__)")

        def __call__(self, state: object) -> str:
            raise AssertionError("router body executed")

    ArmedPath.__call__.__annotations__ = {"state": object, "return": str}

    class _Spec:
        """The seam the truthiness bug lived in reads `path` then `runnable` — arm `path`."""

        path = ArmedPath()
        runnable = None

    from gebra.extraction.builder import _Reading

    reading = _Reading()
    # Through the SEAM (`_router_hint`), not `declared_return_hint` directly — the bug was
    # builder.py's `spec.path or spec.runnable`, so only a spec-shaped probe can go red on
    # reintroduction (pre-review R1, 2026-08-10).
    hint = _router_hint(_Spec(), reading, where="router 'armed' on node 'n'", node="n")

    assert hint.kind == "conditional"  # the seam completed without a single truth test


def test_the_seam_reports_a_degraded_hint_once_with_its_four_facts() -> None:
    """§8's row carries four facts, and the seam that emits it must carry all four.

    Tested at the seam because the graph-level fixture reaches it through ``add_node`` only: this
    is the same emission on the ``BranchSpec`` side, where the substrate makes the shape
    unbuildable, so the seam is the only place the router half can be exercised at all.
    """

    class _Spec:
        """The two members ``_router_hint`` reads, and nothing else."""

        path = futures.route_unresolvable

    from gebra.extraction.builder import _Reading

    reading = _Reading()
    hint = _router_hint(_Spec(), reading, where="router 'r' on node 'n'", node="n")
    (warning,) = reading.warnings

    assert hint.degraded is not None
    assert warning.detail["construct"] == "router-hint-unevaluable"
    assert warning.detail["ir_partial"] is True
    assert warning.detail["location"] == {"router": "router 'r' on node 'n'", "source": "n"}
    assert "NameError" in warning.detail["why"]


def test_an_undeclared_hint_is_not_warned_about() -> None:
    """The other side of the line: a router with no return annotation warns nothing.

    A declaration the author did not make is not a fact about their graph, and warning on it
    would fire on most routers in most workflows — the over-firing DEC-18 scoped out of the
    missing-wiring trigger, reached by another route.
    """
    envelope = extract(sr.build_conditional_forms_graph())

    assert declared_return_hint(sr.route_no_hint) == RouterHint()
    assert constructs(envelope) == []


# ── WA-07: the guarded child ─────────────────────────────────────────────────────────────

#: A fresh interpreter with the network taken away and ``StateGraph.compile`` replaced by a
#: raiser, extracting every §6 shape. The same shape as the §3 child in ``test_builder.py`` —
#: deliberately an independent copy, so a change to one cannot silently disarm the other.
_TRIPWIRE = """
import socket, sys

attempts = []


def _record(name):
    def _seen(*a, **k):
        attempts.append(name); print("WA07-TRIP", file=sys.stderr)
        raise AssertionError(name + " was reached")
    return _seen


class _TripSocket(socket.socket):
    def __new__(cls, *a, **k):
        attempts.append("socket"); print("WA07-TRIP", file=sys.stderr)
        raise AssertionError("a socket was created on the §6 classification path")


socket.getaddrinfo = _record("getaddrinfo")
socket.gethostbyname = _record("gethostbyname")
socket.create_connection = _record("create_connection")

import gebra
from langgraph.graph.state import StateGraph
from tests.sample_workflows import sentinel_routing as sr
from tests.sample_workflows import sentinel_routing_futures as futures

built = {name: factory() for name, factory in sr.ROUTING_BUILDERS.items()}

assert attempts == [], attempts
socket.socket = _TripSocket
StateGraph.compile = _record("StateGraph.compile")

extracted = 0
for name, builder in built.items():
    envelope = gebra.extract(builder)
    assert envelope.ir.edges, name
    envelope.graph_version()          # canonicalize and digest, still under the guard
    extracted += 1

assert extracted == %d, extracted
assert sr.TRIPPED == [], sr.TRIPPED
assert futures.TRIPPED == [], futures.TRIPPED
"""

_REPORT = "print(attempts)\n"


def _run_guarded(probe: str = "") -> subprocess.CompletedProcess[str]:
    body = _TRIPWIRE % len(sr.ROUTING_BUILDERS)
    return subprocess.run(
        [sys.executable, "-c", body + probe + _REPORT],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_the_classification_path_invokes_nothing() -> None:
    """The card's WA-07 claim for the path it lands, in a fresh interpreter.

    Every router and node function in every §6 fixture records itself and raises if called; the
    child asserts both sentinel ledgers are empty at the end of its own run, so a read that
    reached a body fails here even if something on the path swallowed the exception. Nothing
    resolves a name or opens a connection, ``compile`` is taken away before the first extraction,
    and canonicalization runs inside the guard.

    The ``arming_annotation`` fixture is deliberately **not** in the table this quantifies over:
    its extraction is expected to run an annotation expression (§1 rule 3), so folding it in
    would force this claim to be weakened for every shape at once instead of stated plainly here
    and qualified in the one place it does not hold.
    """
    result = _run_guarded()

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "[]", result.stdout
    assert "WA07-TRIP" not in result.stderr, result.stderr


@pytest.mark.parametrize(
    ("probe", "expected"),
    [
        ("sr.build_send_forms_graph().compile()\n", "StateGraph.compile was reached"),
        ("socket.socket()\n", "a socket was created"),
        ("socket.getaddrinfo('example.invalid', 80)\n", "getaddrinfo was reached"),
        ("sr.route_send_list(None)\n", "'route_send_list' was invoked"),
        ("futures.route_send_stringly(None)\n", "'route_send_stringly' was invoked"),
    ],
    ids=["compile", "socket", "getaddrinfo", "router-body", "stringly-router-body"],
)
def test_each_raiser_is_armed(probe: str, expected: str) -> None:
    """A tripwire nobody trips proves nothing — so every raiser gets its own control.

    The last two are the ones this card adds and the ones that matter most here: they prove the
    fixture bodies were still live at the end of the very run that claimed nothing called them.
    """
    result = _run_guarded(probe)

    assert result.returncode != 0
    assert expected in result.stderr


def test_the_tripwire_covers_the_shapes_this_card_handles() -> None:
    """The claim above is only as wide as the table, and the table needs a floor and a shape.

    The floor stops the guarded run shrinking to one builder; the second assertion is what stops
    the table quietly losing the emission rules that have no ir carrier, which are exactly the
    ones a later edit is most likely to reach for.
    """
    assert len(sr.ROUTING_BUILDERS) >= 12
    assert {"dynamic_send_hinted", "relabelled_send", "send_to_end", "codomain_distinct"} <= set(
        sr.ROUTING_BUILDERS
    )
    assert set(sr.ROUTING_BUILDERS) & set(sr.ARMING_BUILDERS) == set()


def test_the_routing_fixtures_are_armed() -> None:
    """Every router and node function in the §6 fixtures raises when called.

    All of them, not a sample: an unarmed fixture is a hole exactly where the claim above is
    strongest, since that is the graph whose extraction would then prove nothing.
    """
    state: sg.SentinelState = {"query": "q", "plan": "p", "answer": "a"}
    checked = 0

    for factory in (*sr.ROUTING_BUILDERS.values(), *sr.ARMING_BUILDERS.values()):
        builder = factory()
        callables: list[Any] = [spec.runnable for spec in builder.nodes.values()]
        callables += [
            spec.path for branches in builder.branches.values() for spec in branches.values()
        ]
        for runnable in callables:
            function = getattr(runnable, "func", None) or getattr(runnable, "afunc", runnable)
            with pytest.raises(sg.SentinelExecutedError):
                result = function(state)
                if hasattr(result, "send"):  # an async router answers a coroutine
                    result.send(None)
            checked += 1

    assert checked >= 30
