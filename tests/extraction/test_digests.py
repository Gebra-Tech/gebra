"""INTROSPECTION-SPEC §7.4 — ``prompt_digest`` / ``config_digest`` (ratified — DEC-15).

Four things are under test, in this order:

1. **The rules, cell by cell.** (d)'s twelve coercion rows, (b)'s eight template rows and (c)'s
   member rules each have a case in ``tests/sample_workflows/sentinel_digests.py`` that declares
   *its own expected projection* — the JSON, the exact digest-input bytes, the form C — so a
   rule that changed fails the case that states it rather than moving a golden nobody can read.
   Coverage is an equality against the vocabulary, not a count of tests.
2. **The carriers**, per (a): which node gets which slot, on both paths that have a bound object
   to read, including the wrapper case where the model sits under a binding — and, per the
   DEC-21 amendment EX-16 implements, the ``model.bind(tools=…)`` case together with the bound
   the amendment keeps: a ``RunnableBinding`` subclass outside the enumeration stays declined.
3. **EX-07's three acceptance claims** — determinism across runs, a prompt-only edit moving
   ``graph_version``, and bodies never reaching the IR — each of which now quantifies over the
   tool-bound workflow too, since it joined ``sentinel_digests.WORKFLOWS``.
4. **The WA-07 tripwire** for this path, with an armed control per raiser.

Every model, template, config value, mapping key and set member the fixtures use raises if the
digest path touches it in a way §7.4 rules out, and records itself first, so a trip swallowed
by a narrow ``except`` is still visible.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from langchain_core.prompts import ChatPromptTemplate, PromptTemplate
from langchain_core.runnables.base import RunnableBinding

import gebra
from gebra.extraction import ExtractionEnvelope, ExtractionWarningCode, to_json
from gebra.extraction.digests import (
    UNREPRESENTABLE,
    NodeDigests,
    PromptGap,
    coerce,
    config_form,
    digests_for,
    prompt_form,
)
from gebra.ir.canonical import canonical_bytes, canonical_foreign_bytes, render_digest
from tests import substrate
from tests.sample_workflows import sentinel_digests as sd

REPO_ROOT = Path(__file__).resolve().parents[2]

#: The slot grammar IR-SPEC §3.6 fixes for both digests.
DIGEST = re.compile(r"^sha256:[a-f0-9]{64}$")


# ── (d) — the coercion table ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize("name", sorted(sd.COERCION_CASES))
def test_every_coercion_case_matches_its_declared_projection(name: str) -> None:
    """K is the twelve-row table of §7.4 (d), and each row states its own answer.

    The expectation is written in the fixture, not computed here, so the assertion is against
    the ruling rather than against the implementation's opinion of it.
    """
    case = sd.COERCION_CASES[name]

    assert coerce(case.build()) == case.expected


def test_the_coercion_table_covers_every_rule_of_the_ruling() -> None:
    """All twelve rows, checked as a set equality so a rule cannot lose its case quietly."""
    covered = {case.rule for case in sd.COERCION_CASES.values()}

    assert covered == set(range(1, 13))


@pytest.mark.parametrize("name", sorted(sd.COERCION_CASES))
def test_every_coercion_result_is_json_the_shipped_pipeline_carries(name: str) -> None:
    """K is *total* into the §3.6 pipeline — which is the whole reason it pre-resolves.

    "The pre-pass must pre-resolve exactly the values the pipeline refuses, so extraction stays
    total" (PD-014 finding 5). So every row's output must serialize through the shipped
    foreign-object pipeline without raising: a NaN, an out-of-range integer, a lone surrogate or
    a non-string key reaching it would be a :class:`CanonicalizationError` out of
    ``gebra.extract()``, which §2 puts only at the object boundary.
    """
    case = sd.COERCION_CASES[name]

    assert canonical_foreign_bytes(coerce(case.build()))


def test_a_marker_carries_a_class_identity_and_never_a_rendering() -> None:
    """(d) rule 12's whole point: the class, never ``repr`` — no address ever reaches a digest.

    The fixture's ``__repr__``/``__str__``/``__format__``/``__getattr__`` all raise, so this
    passing at all is the claim; the assertion is that what came back names the *type* and
    holds nothing else.
    """
    marker = coerce(sd.ArmedClient())

    assert marker == {UNREPRESENTABLE: "tests:ArmedClient"}
    assert "0x" not in canonical_foreign_bytes(marker).decode()


def test_a_class_identity_is_read_and_never_rendered() -> None:
    """The route (d) rule 12 takes to a class name must not run the metaclass's ``__repr__``.

    Found by this path's tripwire rather than by review: :func:`gebra.naming.type_identity`
    spelled its fallback ``getattr(cls, "__qualname__", repr(cls))``, and Python evaluates a
    ``getattr`` default **eagerly** — so ``repr(cls)`` ran on every type this package named,
    digest input included, executing whatever ``__repr__`` a metaclass supplied. That is the
    hazard :mod:`gebra.extraction.state` records in the same words for the same reason. The
    fallback is now a constant, and this is the control.
    """
    marker = coerce(sd.ArmedMetaValue())

    assert marker == {UNREPRESENTABLE: "tests:ArmedMetaValue"}
    assert sd.TRIPPED == []


def test_a_class_identity_does_not_go_through_the_metaclass_at_all() -> None:
    """Not merely "no rendering": the metaclass never sees the read.

    ``cls.__qualname__`` and ``cls.__module__`` route through the metaclass's
    ``__getattribute__``, which is user code answering a **digest-bearing** value. The unbound
    ``type`` descriptors are what the interpreter itself uses, so the probe below — which
    records every watched name it is asked for — records nothing.
    """
    marker = coerce(sd.NameProbedValue())

    assert marker == {UNREPRESENTABLE: "tests:NameProbedValue"}
    assert sd.TRIPPED == []
    # The probe is live: read the same names the ordinary way and it records all three.
    assert (sd.NameProbedValue.__qualname__, sd.NameProbedValue.__module__) != ("", "")
    assert sd.TRIPPED == [
        "NameProbeMeta.__getattribute__:__qualname__",
        "NameProbeMeta.__getattribute__:__module__",
    ]
    sd.TRIPPED.clear()


def test_a_class_whose_module_is_not_a_string_is_named_by_its_qualname_alone() -> None:
    """The one half of a class identity a class can genuinely answer with a non-string.

    A rendering would have been the obvious fallback, and a rendering is what must not happen:
    the identity carries the qualname and an empty package rather than whatever was put there.
    """
    assert coerce(sd.OddlyModuledValue()) == {UNREPRESENTABLE: ":OddlyModuledValue"}


def test_two_equal_sets_coerce_to_one_array_whatever_order_they_were_built_in() -> None:
    """(d) rule 11 is what keeps a hash-seeded iteration order out of a digest.

    Building the same set from two different insertion orders is the in-process half; the
    cross-process half is
    :func:`test_the_digests_are_identical_across_processes_with_different_hash_seeds`.
    """
    forwards = coerce({"alpha", "beta", "gamma", "delta"})
    backwards = coerce({"delta", "gamma", "beta", "alpha"})

    assert forwards == backwards == ["alpha", "beta", "delta", "gamma"]


def test_a_secret_is_recognised_by_type_and_never_read() -> None:
    """(c)'s exclusion is by value type — the fixture's ``get_secret_value`` raises."""
    assert coerce(sd.ArmedSecret("sk-live")) == {UNREPRESENTABLE: "secret"}


# ── (b) — the prompt byte source ─────────────────────────────────────────────────────────


@pytest.mark.parametrize("name", sorted(sd.PROMPT_CASES))
def test_every_prompt_case_digests_the_bytes_the_ruling_names(name: str) -> None:
    """(b), row by row: the digest input is declared per case, byte for byte.

    Declaring the *input* rather than the digest is what makes these readable: a reviewer
    checks ``b'[{"role":"system","template":"You are {role}."}]'`` against §7.4 (b) directly,
    where a hex string would only say that something did not change.
    """
    case = sd.PROMPT_CASES[name]
    form = prompt_form(case.build())

    if case.digest_input is None:
        assert isinstance(form, PromptGap)
        assert (form.identity, dict(form.where)) == (case.offender, dict(case.where))
    else:
        assert form == case.digest_input


@pytest.mark.parametrize("name", sorted(sd.PROMPT_CASES))
def test_a_digesting_case_renders_the_slot_grammar_over_its_declared_bytes(name: str) -> None:
    """The slot value is §6.1 steps 7–8 over exactly those bytes, and nothing else."""
    case = sd.PROMPT_CASES[name]
    digests = digests_for("n", case.build())

    if case.digest_input is None:
        assert digests.prompt is None
    else:
        assert digests.prompt == render_digest(case.digest_input)
        assert DIGEST.match(digests.prompt)


def test_the_prompt_table_covers_every_row_of_the_closed_vocabulary() -> None:
    """(b) closes the vocabulary, so the coverage claim is an equality in three directions."""
    assert set(sd.PROMPT_ROWS) == set(sd.PROMPT_CASES)
    assert set(sd.PROMPT_ROWS.values()) == sd.PROMPT_VOCABULARY


@pytest.mark.parametrize(
    "name",
    sorted(name for name, case in sd.PROMPT_CASES.items() if case.digest_input is None),
)
def test_an_unrecognised_template_is_absent_and_warned_rather_than_partial(name: str) -> None:
    """(b) rule 4: absent for that node, never a partial digest, and one §8 record.

    The record carries what §8's row for the §7.4 case names — the construct kind, the location,
    why it is unmappable, whether the IR is partial there, and the offender's class identity
    (with the item index where there is one).
    """
    case = sd.PROMPT_CASES[name]
    digests = digests_for("n", case.build())

    assert digests.prompt is None
    assert len(digests.warnings) == 1
    warning = digests.warnings[0]
    assert warning.code is ExtractionWarningCode.UNSUPPORTED_CONSTRUCT
    assert warning.node == "n"
    assert warning.detail["construct"] == "prompt-template-not-carried"
    assert warning.detail["ir_partial"] is True
    assert warning.detail["location"] == {"node": "n", "offender": case.offender, **case.where}


def test_the_string_branch_is_byte_exact_and_unnormalized() -> None:
    """The frozen IR-SPEC §3.6 sentence, made checkable: the digest is SHA-256 of the template.

    ``sha256("hello")`` is a value a reviewer can look up, which is the point of picking it.
    """
    digests = digests_for("n", PromptTemplate.from_template("hello"))

    assert digests.prompt == (
        "sha256:2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
    )


def test_the_two_normalizations_the_ruling_declines_both_move_the_digest() -> None:
    """ "No trimming, no normalization, no NFC" — checked as three distinct digests.

    An extractor that trimmed, or that NFC-normalized the way §6.3 does for identifier-role
    strings, would collapse two of these onto one.
    """
    plain = digests_for("n", PromptTemplate.from_template("café")).prompt
    padded = digests_for("n", PromptTemplate.from_template("  café ")).prompt
    decomposed = digests_for("n", PromptTemplate.from_template("café")).prompt

    assert len({plain, padded, decomposed}) == 3


def test_the_documented_insensitivities_are_insensitive() -> None:
    """(b)'s stated limits, asserted rather than left as prose.

    ``template_format``, ``input_variables`` and ``partial_variables`` are not digested, so two
    templates differing only in those share a ``prompt_digest``. Honest, documented limits of a
    "did the prompt text change?" fingerprint — and a test is what keeps them documented.
    """
    plain = PromptTemplate(template="Hi {name}", input_variables=["name"])
    partialled = PromptTemplate(
        template="Hi {name}", input_variables=[], partial_variables={"name": "Ada"}
    )
    mustache = PromptTemplate(template="Hi {name}", input_variables=[], template_format="mustache")

    assert digests_for("n", plain).prompt == digests_for("n", partialled).prompt
    assert digests_for("n", plain).prompt == digests_for("n", mustache).prompt
    assert plain.input_variables != mustache.input_variables


def test_authored_message_order_is_semantic() -> None:
    """M is an array in authored order — §6.2's array sorts do not reach it."""
    forwards = ChatPromptTemplate.from_messages([("system", "a"), ("human", "b")])
    backwards = ChatPromptTemplate.from_messages([("human", "b"), ("system", "a")])

    assert digests_for("n", forwards).prompt != digests_for("n", backwards).prompt


# ── (c) — the config surface ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize("name", sorted(sd.CONFIG_CASES))
def test_every_config_case_projects_the_form_the_ruling_names(name: str) -> None:
    """(c), member rule by member rule: provider identity, params, and the bound overlay.

    Each case declares only the members it is *about*; the base-model fields every
    ``BaseChatModel`` carries are declared once in ``BASE_PARAMS``, so a row reads as the rule
    it exercises.
    """
    case = sd.CONFIG_CASES[name]
    model, bindings = case.build()

    form = config_form(model, bindings)

    if case.degraded:
        assert form is None
        return
    expected: dict[str, Any] = {
        "provider": "tests:ArmedChatModel",
        "params": {**sd.BASE_PARAMS, **case.params},
    }
    if case.bound is not None:
        expected["bound"] = case.bound
    assert form == expected


@pytest.mark.parametrize("name", sorted(sd.CONFIG_CASES))
def test_every_config_case_renders_the_slot_grammar_over_its_form(name: str) -> None:
    """The slot value is §3.6's foreign pipeline over C, then §6.1 steps 7–8."""
    case = sd.CONFIG_CASES[name]
    model, bindings = case.build()

    digests = digests_for("n", model, bindings=bindings)

    if case.degraded:
        assert digests.config is None
        return
    form = config_form(model, bindings)
    assert digests.config == render_digest(canonical_foreign_bytes(form))
    assert DIGEST.match(digests.config)


def test_the_model_construct_edge_degrades_rather_than_raising() -> None:
    """(e)'s recorded implementer edge, and the only way ``config_digest`` is not Full.

    "``getattr`` on a ``model_fields`` name absent from an instance's ``__dict__`` — possible
    only via ``model_construct()`` — degrades to the absent-digest + ``unsupported-construct``
    path rather than raising."
    """
    partial = sd.NeedyChatModel.model_construct(temperature=0.5)

    digests = digests_for("mdl", partial)

    assert digests.config is None
    assert [w.detail["construct"] for w in digests.warnings] == ["model-field-unreadable"]
    assert digests.warnings[0].detail["location"] == {
        "node": "mdl",
        "offender": "tests:NeedyChatModel",
    }
    assert digests.warnings[0].detail["ir_partial"] is True


def test_the_prescribed_field_read_can_reach_a_shadowing_property() -> None:
    """A **recorded residue** of §7.4 (c)'s own recipe, stated rather than denied (PD-029).

    (c) prescribes ``type(m).model_fields`` + ``getattr(m, name)`` and asserts in the same
    breath that "no property, method, or ``repr`` read ever runs on the model object". The
    second sentence is not guaranteed by the first: pydantic strips a field-shadowing class
    attribute only from the class being built, so a ``@property`` on a **base** plus the
    annotation on the subclass leaves a live data descriptor above the instance dict — and a
    data descriptor resolves first. What the digest then carries is what the property returned.

    This build does the read (c) prescribes and does not improvise a shield around it; the
    inaccuracy is in the spec sentence, and the WA-03 write-up is filed. The assertion below is
    what makes the residue *counted* rather than described.
    """
    model = sd.build_shadowing_model()
    sd.RESIDUE.clear()

    form = config_form(model)

    assert form is not None
    params = form["params"]
    assert isinstance(params, dict)
    assert params["shadowed"] == "from-the-property"
    assert sd.RESIDUE == ["_ShadowingBase.shadowed"]
    sd.RESIDUE.clear()


def test_the_prescribed_field_read_can_reach_a_subclass_getattr() -> None:
    """The second half of the same residue, on the path (e) covers for a stock model.

    ``BaseModel.__getattr__`` raising ``AttributeError`` is what makes the ``model_construct``
    degrade sound — and a subclass ``__getattr__`` overrides it, so the degrade never fires and
    a computed value reaches the digest instead. Same disposition as above (PD-029).
    """
    partial = sd.ReachingChatModel.model_construct(temperature=0.5)
    sd.RESIDUE.clear()

    form = config_form(partial)

    assert form is not None  # the (e) degrade did NOT fire — that is the residue
    params = form["params"]
    assert isinstance(params, dict)
    assert params["model_name"] == "from-getattr"
    assert sd.RESIDUE == ["ReachingChatModel.model_name"]
    sd.RESIDUE.clear()


def test_the_prompt_side_has_no_such_residue() -> None:
    """The asymmetry that makes the residue above the model side's alone.

    Every attribute the prompt branch reads sits behind an **exact-type** gate, so those objects
    are always stock langchain classes: an unrecognised template or item is decided from
    ``type()`` and never read at all. The fixtures whose every member raises are the control —
    they take (b)'s fallback without tripping.
    """
    assert isinstance(prompt_form(sd.ArmedTemplate(input_variables=[])), PromptGap)
    assert digests_for("n", sd.ArmedMessageItem()) == NodeDigests()
    assert sd.TRIPPED == []


def test_a_whole_model_is_full_and_warns_about_nothing() -> None:
    """The converse of the edge above — (c)'s "Full on every discovered model node"."""
    digests = digests_for("mdl", sd.NeedyChatModel(model_name="pinned"))

    assert DIGEST.match(digests.config or "")
    assert digests.warnings == ()


def test_the_config_digest_carries_the_substrate_version() -> None:
    """A consequence a reader of a digest has to know, stated as a test rather than buried.

    From langchain-core 1.4.7 ``BaseChatModel`` fills its ``metadata`` field with the running
    langchain-core version at construction. That field is a ``model_fields`` member with a
    non-``None`` value, so (c) digests it — and a langchain-core upgrade therefore moves
    ``config_digest``, and with it ``graph_version``, with no user edit behind it. §7.4 (e)
    names exactly this ("a substrate minor release adding a model field with a non-``None``
    default moves ``config_digest``; the A1 pin plus the VERSION-COMPAT drift probes are the
    detection surface"), so this is the ruled behaviour rather than a defect — but it is not
    guessable from the slot's name, and a silent change to it should fail a suite rather than a
    user's diff.

    **Both sides of that release are tested, because the matrix runs both** (EX-17 /
    PD-038 Finding 2). Below 1.4.7 the field's default is ``None``, and the assertion is
    then the *other* half of the same rule: the member is still declared on the model, and (c)
    omits it because its value is ``None`` — not because the projection stopped looking. Which
    is why the ``model_fields`` assertion below is unconditional and only the value differs:
    the digest moving across a substrate release is the ruled behaviour, and a projection that
    silently stopped reading the field would fail here on every cell.
    """
    import langchain_core

    model = sd.ArmedChatModel()
    form = config_form(model)

    assert form is not None
    params = form["params"]
    assert isinstance(params, dict)
    assert "metadata" in type(model).model_fields
    filled = {"lc_versions": {"langchain-core": langchain_core.__version__}}
    if substrate.CORE_FILLS_LC_VERSIONS_METADATA:
        assert params["metadata"] == filled
    else:
        assert model.metadata is None
        assert "metadata" not in params


def test_a_run_config_wrapper_never_moves_the_digest() -> None:
    """(c) excludes ``RunnableConfig`` content: ``with_config`` is observability, not config.

    ``with_config`` produces a stock ``RunnableBinding`` whose ``kwargs`` are empty and whose
    ``config`` carries the tags — so the overlay is empty, ``"bound"`` is absent, and the model
    digests exactly as it does bare.
    """
    model = sd.ArmedChatModel(temperature=0.3)
    wrapper = model.with_config(tags=["prod"], metadata={"team": "x"})

    bare = digests_for("n", model).config
    wrapped = digests_for("n", model, bindings=(wrapper,)).config

    assert bare == wrapped


# ── (a) — the carriers, end to end ───────────────────────────────────────────────────────


def digests_of(envelope: ExtractionEnvelope) -> dict[str, tuple[str | None, str | None]]:
    """Node id → its two digest slots, for reading a carrier claim off an extraction."""
    return {
        node.id: (
            None if node.annotations is None else node.annotations.prompt_digest,
            None if node.annotations is None else node.annotations.config_digest,
        )
        for node in envelope.ir.nodes
    }


def test_a_chain_puts_each_digest_on_the_node_whose_own_object_carries_it() -> None:
    """(a) on the §5 path: one carrier each, and no aggregation onto a parent.

    ``prompt | model`` stitches to two nodes and each carries exactly the slot its own bound
    object licenses — which is also the negative claim, since neither node carries both.
    """
    envelope = gebra.extract(sd.build_chain())

    slots = digests_of(envelope)
    assert set(slots) == {"%seq[0]", "%seq[1]"}
    assert slots["%seq[0]"][0] is not None and slots["%seq[0]"][1] is None
    assert slots["%seq[1]"][0] is None and slots["%seq[1]"][1] is not None


def test_a_binding_wrapper_carries_nothing_and_its_model_child_carries_the_config() -> None:
    """(a)'s wrapper rule, under the token naming DEC-20 ratified.

    ``prompt | RunnableBinding(RunnableBinding(model))`` emits the wrapper as its own node and
    the model as the ``%bind[0]`` child below it. The **wrapper** node is what (a) means by
    "binding-wrapper nodes carry neither digest" — under PD-025 D1 a bind frame contributes no
    segment, so ``%bind[…]`` names the object *inside* the binding, which is the model.
    """
    envelope = gebra.extract(sd.build_bound_chain())

    slots = digests_of(envelope)
    assert set(slots) == {"%seq[0]", "%seq[1]", "%seq[1]/%bind[0]", "%seq[1]/%bind[0]/%bind[0]"}
    assert slots["%seq[0]"][0] is not None
    assert slots["%seq[1]"] == (None, None)
    assert slots["%seq[1]/%bind[0]"] == (None, None)
    assert slots["%seq[1]/%bind[0]/%bind[0]"][1] is not None


def test_the_enclosing_bindings_reach_the_model_digest_outermost_first() -> None:
    """The overlay a wrapped model digests is the one an invocation would pass it.

    Both bindings set ``seed``; the outer one wins, so the wrapped model's digest equals the
    one computed with that merged overlay and differs from the bare model's.
    """
    envelope = gebra.extract(sd.build_bound_chain())
    carrier = "%seq[1]/%bind[0]/%bind[0]"

    wrapped = digests_of(envelope)[carrier][1]
    bare = digests_for("n", sd.ArmedChatModel(temperature=0.2)).config
    merged = digests_for(
        "n",
        sd.ArmedChatModel(temperature=0.2),
        bindings=(_binding({"seed": 2}), _binding({"stop": ["x"], "seed": 1})),
    ).config

    assert wrapped == merged
    assert wrapped != bare


def _binding(kwargs: dict[str, Any]) -> Any:
    """A stock ``RunnableBinding`` around a throwaway model, for an overlay-only comparison."""
    from langchain_core.runnables.base import RunnableBinding
    from langchain_core.runnables.passthrough import RunnablePassthrough

    return RunnableBinding(bound=RunnablePassthrough(), kwargs=kwargs)


def test_a_builder_node_bound_to_a_template_or_a_model_is_a_carrier() -> None:
    """(a) applied through §3's row purpose (iii), on both template branches and the model."""
    envelope = gebra.extract(sd.build_builder())

    slots = digests_of(envelope)
    assert set(slots) == {"prompt", "string_prompt", "model"}
    assert slots["prompt"][0] is not None and slots["prompt"][1] is None
    assert slots["string_prompt"][0] is not None
    assert slots["model"] == (None, slots["model"][1])
    assert slots["model"][1] is not None


def test_the_compiled_level_reports_the_same_carriers_as_its_builder() -> None:
    """§4 is builder-primary, so the digests come across unchanged — the §7.1 asymmetry is
    ``runtime``, and nothing here."""
    builder = sd.build_builder()

    from_builder = digests_of(gebra.extract(builder))
    from_compiled = digests_of(gebra.extract(builder.compile()))

    assert from_builder == from_compiled


def test_a_composite_that_merely_contains_a_template_carries_nothing() -> None:
    """ "Digests are never aggregated onto parents" (a), checked on the shape that would.

    A ``StateGraph`` node bound to ``prompt | model`` has a template *reachable* from its
    runnable, and it carries no digest: (a) quantifies over the node's **own** bound object, and
    §5 discovery inside a node is not wired at this level, so there is no child node to carry
    one either. The absence is the honest reading rather than a shortfall — inventing an
    aggregate digest for the parent would fingerprint something the author never wrote.
    """
    from typing import TypedDict

    from langgraph.graph import END, START, StateGraph

    class State(TypedDict):
        q: str

    graph: Any = StateGraph(State)
    graph.add_node("composite", sd.build_chain())
    graph.add_edge(START, "composite")
    graph.add_edge("composite", END)

    assert digests_of(gebra.extract(graph)) == {"composite": (None, None)}


def test_a_model_behind_a_stock_binding_is_discovered_under_it() -> None:
    """The positive control, and the one that runs on every cell of the matrix.

    A ``RunnableBinding`` of exactly that class is what §5's stitching admits, so it is
    descended into: the binding's own node carries neither digest — §7.4 (a)'s "binding-wrapper
    nodes carry neither" — and the model underneath gets a node of its own with the
    ``config_digest``. Constructed directly rather than through ``bind()`` so that this case
    stays about the stock class itself whatever a given langchain-core's ``bind()`` answers with;
    the test below is the ``bind()`` shape.
    """
    model = sd.ArmedChatModel(temperature=0.2)
    binding: RunnableBinding[Any, Any] = RunnableBinding(bound=model, kwargs={"stop": ["x"]})
    chain = ChatPromptTemplate.from_messages([("system", "s")]) | binding

    envelope = gebra.extract(chain)

    slots = digests_of(envelope)
    assert slots["%seq[0]"][0] is not None
    assert slots["%seq[1]"] == (None, None)
    assert slots["%seq[1]/%bind[0]"][1] is not None
    assert "lcel-composition-not-stock" not in [
        warning.detail.get("construct")
        for warning in envelope.warnings
        if warning.code is ExtractionWarningCode.UNSUPPORTED_CONSTRUCT
    ]


def test_a_model_behind_a_non_stock_binding_is_not_discovered_and_says_so() -> None:
    """The bound on the DEC-21 admission — EX-16's second acceptance, with the fixture armed.

    §7.4 (a) as amended admits an *enumerated* set of stock langchain-core subclasses by exact
    type. Everything else stays where DEC-20/PD-025 put it: a ``RunnableBinding`` subclass can
    answer ``bound`` or ``kwargs`` with code of its own, so it is kept opaque, the model gets no
    node of its own, and no ``config_digest`` is emitted for it. The decline is not silent — the
    ``lcel-composition-not-stock`` record names the unread composition — and it is not merely
    asserted either: :class:`~tests.sample_workflows.sentinel_digests.NonStockBinding` records
    and raises if anything reads its ``kwargs``, so an empty ``TRIPPED`` is the read that did not
    happen rather than an absent member with several possible causes.

    The fixture declares its subclass rather than reaching for ``model.bind(...)``, which is now
    admitted on every cell of the frozen matrix and so can no longer express this shape at all.
    """
    model = sd.ArmedChatModel(temperature=0.2)
    binding = sd.NonStockBinding(bound=model, kwargs={"stop": ["x"]})
    chain = ChatPromptTemplate.from_messages([("system", "s")]) | binding

    envelope = gebra.extract(chain)

    slots = digests_of(envelope)
    assert slots["%seq[0]"][0] is not None
    assert slots["%seq[1]"] == (None, None)
    assert set(slots) == {"%seq[0]", "%seq[1]"}
    assert "lcel-composition-not-stock" in [
        warning.detail.get("construct")
        for warning in envelope.warnings
        if warning.code is ExtractionWarningCode.UNSUPPORTED_CONSTRUCT
    ]
    assert sd.TRIPPED == []


# ── EX-16 — the stock binding-wrapper admission (§7.4 (a) as amended by DEC-21) ───────────


def test_a_tool_bound_model_carries_a_config_digest_with_the_tool_overlay() -> None:
    """EX-16's first acceptance: ``prompt | model.bind(tools=…)`` has a ``config_digest``.

    The ruled shape end to end. ``bind()`` answers with ``_ChatModelBinding`` at the pin and with
    the stock ``RunnableBinding`` below core 1.4.0; §7.4 (a) as amended by DEC-21 admits both by
    exact type, so this test states one node set and one set of slots and every cell of the
    frozen VERSION-COMPAT §3 matrix must produce them — which is also the EX-17 handoff
    closing, since before the admission the two ends of the matrix disagreed about whether the
    model was a node at all.

    The overlay is checked for its content rather than only for its presence: the projected form
    is compared against the tool schema as authored, so a build that admitted the wrapper but
    dropped its ``kwargs`` would fail here.
    """
    chain = sd.build_tool_bound_chain()

    envelope = gebra.extract(chain)

    slots = digests_of(envelope)
    assert set(slots) == {"%seq[0]", "%seq[1]", "%seq[1]/%bind[0]"}
    assert slots["%seq[0]"][0] is not None
    assert slots["%seq[1]"] == (None, None)
    assert DIGEST.match(slots["%seq[1]/%bind[0]"][1] or "")
    assert [
        warning.detail.get("construct")
        for warning in envelope.warnings
        if warning.code is ExtractionWarningCode.UNSUPPORTED_CONSTRUCT
    ] == []

    model, bindings = sd.bound_with_tools([sd.TOOL_SCHEMA], temperature=0.2, seed=7)
    form = config_form(model, bindings)
    assert form is not None
    assert form["bound"] == {"tools": [sd.TOOL_SCHEMA]}
    assert render_digest(canonical_foreign_bytes(form)) == slots["%seq[1]/%bind[0]"][1]


def test_a_bare_tool_bound_model_puts_the_digest_on_the_id_the_wrapper_used_to_hold() -> None:
    """The degenerate family-3 root, where the admission does not *add* a node — it moves one.

    Handed a bare ``model.bind(tools=…)``, the pre-admission build named the wrapper itself
    ``%bind[0]`` (the §2 degenerate case names an unexpandable frame by the kind it derives
    from) and carried no digest. Now the frame expands and ``%bind[0]`` is the **model**, which
    carries the ``config_digest``. So for this shape the node id set is unchanged and a digest
    appears on an id that already existed — still inside DEC-21's ruled movement, but not the
    "gains a node" story the composed shape tells, which is why it has its own vector.
    """
    model, (binding,) = sd.bound_with_tools([sd.TOOL_SCHEMA])

    envelope = gebra.extract(binding)

    slots = digests_of(envelope)
    assert set(slots) == {"%bind[0]"}
    assert slots["%bind[0]"][0] is None
    assert DIGEST.match(slots["%bind[0]"][1] or "")
    assert slots["%bind[0]"][1] == digests_for("%bind[0]", model, bindings=(binding,)).config
    assert sd.TRIPPED == []


def test_a_tool_set_edit_moves_the_graph_version() -> None:
    """The other half of EX-16's first acceptance, as a discriminator rather than a coincidence.

    Three extractions: the same tool set twice, then an edited one. The first pair pins that the
    digest is a function of the tools' *values* — a projection that varied per call would pass a
    two-extraction test — and the third says the edit reaches ``graph_version``. Both edits a
    caller can make are covered: a member inside a tool's schema, and the size of the tool set.
    """
    before = gebra.extract(sd.build_tool_bound_chain())
    again = gebra.extract(sd.build_tool_bound_chain())
    edited = gebra.extract(sd.build_tool_bound_chain(tools=[sd.EDITED_TOOL_SCHEMA]))
    widened = gebra.extract(
        sd.build_tool_bound_chain(tools=[sd.TOOL_SCHEMA, sd.EDITED_TOOL_SCHEMA])
    )

    assert before.graph_version() == again.graph_version()
    assert before.graph_version() != edited.graph_version()
    assert before.graph_version() != widened.graph_version()
    assert edited.graph_version() != widened.graph_version()


def test_the_tool_edit_reaches_the_version_through_the_config_digest_and_nothing_else() -> None:
    """Localized, the way the prompt-edit claim is: exactly one slot on one node moved.

    A tool-set edit that had also moved the topology, a contract or the model's own parameters
    would move ``graph_version`` too, so the discriminating assertion is that the two IRs are
    byte-identical under canonicalization once the model node's ``config_digest`` is cleared.
    """
    before = gebra.extract(sd.build_tool_bound_chain())
    after = gebra.extract(sd.build_tool_bound_chain(tools=[sd.EDITED_TOOL_SCHEMA]))

    moved = {
        node_id
        for node_id in digests_of(before)
        if digests_of(before)[node_id] != digests_of(after)[node_id]
    }
    assert moved == {"%seq[1]/%bind[0]"}

    assert canonical_bytes(_without_config(before.ir)) == canonical_bytes(_without_config(after.ir))


def _without_config(ir: Any) -> Any:
    """``ir`` with every ``config_digest`` cleared — for isolating what a tool edit moved."""
    return ir.model_copy(
        update={
            "nodes": tuple(
                node
                if node.annotations is None
                else node.model_copy(
                    update={
                        "annotations": node.annotations.model_copy(update={"config_digest": None})
                    }
                )
                for node in ir.nodes
            )
        }
    )


def test_a_tool_passed_as_an_object_is_named_by_its_class_and_not_by_its_body() -> None:
    """A limit of the tool fingerprint, stated as a test rather than as a caveat (PD-043).

    (d)'s coercion K is total and closed: a ``BaseTool`` is not JSON data, so rule 12 answers
    with its class identity. The consequence is worth knowing before relying on the slot —
    binding two *different* ``StructuredTool``s produces the same overlay, so that edit does not
    move ``config_digest``, while the mainstream ``bind(tools=[<schema dict>])`` shape digests in
    full (the test above). Changing this means projecting a tool's own surface, which is a
    §7.4 (b)-shaped vocabulary extension and therefore a future DEC, never an extractor's
    improvisation — so what is asserted here is exactly what the ratified rules produce.
    """
    alpha_model, alpha_binding = sd.bound_with_tools([sd.armed_tool("alpha")])
    beta_model, beta_binding = sd.bound_with_tools([sd.armed_tool("beta")])

    alpha = config_form(alpha_model, alpha_binding)
    beta = config_form(beta_model, beta_binding)
    assert alpha is not None and beta is not None
    assert alpha["bound"] == {"tools": [{UNREPRESENTABLE: "langchain_core:StructuredTool"}]}
    assert alpha == beta

    schemas = config_form(*sd.bound_with_tools([sd.TOOL_SCHEMA]))
    assert schemas is not None
    assert schemas != alpha
    assert sd.TRIPPED == []


def test_a_node_that_carries_neither_gets_no_digest_members() -> None:
    """The negative: :func:`digests_for` answers empty for everything that is not a carrier."""
    for subject in ("a string", 7, None, PromptTemplate, sd.ArmedClient()):
        assert digests_for("n", subject) == NodeDigests()


# ── acceptance 1 — determinism across runs and platforms ─────────────────────────────────


def test_re_extracting_an_unchanged_workflow_gives_the_same_digests() -> None:
    """The same object twice, and a freshly built equal one — both must agree.

    The second half is the one with content: it says the digest is a function of the source
    objects' *values*, not of a particular object's lifetime, which is (e)'s "two conforming
    extractors given equal source objects MUST produce string-equal digests".
    """
    for name, build in sorted(sd.WORKFLOWS.items()):
        subject = build()
        once, twice = gebra.extract(subject), gebra.extract(subject)
        fresh = gebra.extract(build())

        assert digests_of(once) == digests_of(twice) == digests_of(fresh), name
        assert once.graph_version() == twice.graph_version() == fresh.graph_version(), name


#: Re-extracts every workflow fixture and reports the digests and the ``graph_version``. Run in
#: child interpreters under different hash seeds, where the point is that they agree.
_DIGEST_REPORT = """
import gebra
from tests.sample_workflows import sentinel_digests as sd

for name, build in sorted(sd.WORKFLOWS.items()):
    envelope = gebra.extract(build())
    slots = tuple(
        (
            node.id,
            None if node.annotations is None else node.annotations.prompt_digest,
            None if node.annotations is None else node.annotations.config_digest,
        )
        for node in envelope.ir.nodes
    )
    print(name, slots, envelope.graph_version())

assert sd.TRIPPED == [], sd.TRIPPED
"""


def test_the_digests_are_identical_across_processes_with_different_hash_seeds() -> None:
    """The determinism acceptance, checked where it can actually fail.

    "Deterministic across runs and platforms" is not observable in one interpreter for the
    parts that would break it: a ``set``-valued parameter iterates in ``PYTHONHASHSEED`` order,
    a mapping's insertion order is not, and ``id()``-derived text would differ per process. Four
    child interpreters under four seeds re-extract every fixture and must print the same bytes.

    Platform independence is not simulable here, so what is checked instead is the property it
    rests on: every rule in §7.4 is a function of values and classes only, and the two
    process-varying inputs — hash order and object addresses — are the ones these seeds move.
    """
    outputs = {
        seed: subprocess.run(
            [sys.executable, "-c", _DIGEST_REPORT],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
            env={**os.environ, "PYTHONHASHSEED": seed},
        )
        for seed in ("0", "1", "777", "12345")
    }

    for seed, result in outputs.items():
        assert result.returncode == 0, (seed, result.stderr)
    reports = {result.stdout for result in outputs.values()}
    assert len(reports) == 1, outputs
    assert "sha256:" in next(iter(reports))


def test_a_hash_seeded_container_does_not_reach_the_digest() -> None:
    """The specific mechanism the seeds above would expose, isolated.

    A model whose parameter is a ``frozenset`` of strings: iteration order varies per process,
    the digest must not.
    """
    one = sd.ArmedChatModel(flavours=frozenset({"a", "b", "c"}))
    other = sd.ArmedChatModel(flavours=frozenset({"c", "b", "a"}))

    assert digests_for("n", one).config == digests_for("n", other).config


# ── acceptance 2 — a prompt-only edit moves graph_version ─────────────────────────────────


@pytest.mark.parametrize(
    "build",
    [sd.build_chain, sd.build_bound_chain, sd.build_tool_bound_chain, sd.build_builder],
)
def test_a_prompt_only_edit_changes_the_graph_version(build: Any) -> None:
    """EX-07's second acceptance, on every path that has a prompt carrier.

    The two workflows differ in the prompt text and in nothing else — same topology, same
    model, same parameters — so a different ``graph_version`` can only have come through
    ``prompt_digest``, which IR-SPEC §6.4 puts in hash scope. Re-running each build twice with
    the *same* text is the converse, and it is what makes this a discriminator rather than a
    coincidence: without it a digest that varied per call would pass.
    """
    before = gebra.extract(build("You are a careful assistant."))
    again = gebra.extract(build("You are a careful assistant."))
    after = gebra.extract(build("You are a *very* careful assistant."))

    assert before.graph_version() == again.graph_version()
    assert before.graph_version() != after.graph_version()


def test_the_prompt_edit_reaches_the_version_through_the_digest_and_nothing_else() -> None:
    """The same claim, localized: only the carrier node's ``prompt_digest`` moved.

    A topology or contract change would also move ``graph_version``, so the discriminating
    assertion is that the two IRs are identical once the digest is set aside.
    """
    before = gebra.extract(sd.build_chain("one"))
    after = gebra.extract(sd.build_chain("two"))

    changed = {
        node_id
        for node_id in digests_of(before)
        if digests_of(before)[node_id] != digests_of(after)[node_id]
    }
    assert changed == {"%seq[0]"}

    stripped_before = before.ir.model_copy(
        update={"nodes": tuple(_without_digests(node) for node in before.ir.nodes)}
    )
    stripped_after = after.ir.model_copy(
        update={"nodes": tuple(_without_digests(node) for node in after.ir.nodes)}
    )
    assert canonical_bytes(stripped_before) == canonical_bytes(stripped_after)


def _without_digests(node: Any) -> Any:
    """``node`` with both digest slots cleared — for isolating what a prompt edit moved."""
    if node.annotations is None:
        return node
    return node.model_copy(
        update={"annotations": node.annotations.model_copy(update={"prompt_digest": None})}
    )


def test_a_config_only_edit_changes_the_graph_version_too() -> None:
    """The companion claim for the other slot, which the card's objective names alongside it."""
    from langchain_core.runnables.base import RunnableSequence

    template = ChatPromptTemplate.from_messages([("system", "s")])
    cool: Any = RunnableSequence(template, sd.ArmedChatModel(temperature=0.0))
    warm: Any = RunnableSequence(template, sd.ArmedChatModel(temperature=0.9))

    assert gebra.extract(cool).graph_version() != gebra.extract(warm).graph_version()


# ── acceptance 3 — bodies never embedded ─────────────────────────────────────────────────

#: Text that appears in a fixture prompt or config and must never appear in an IR or envelope.
#:
#: A bound tool's own text is on this list for the same reason a prompt's is: after the DEC-21
#: admission a tool schema reaches the ``"bound"`` overlay, and a tool description is authored
#: content that the IR must fingerprint rather than carry.
_BODIES: tuple[str, ...] = (
    "You are a careful assistant.",
    "careful",
    "sk-live",
    "END",
    "Fetch the itinerary legs for a booking reference.",
    "lookup_itinerary",
)


@pytest.mark.parametrize("name", sorted(sd.WORKFLOWS))
def test_no_prompt_or_config_body_reaches_the_ir(name: str) -> None:
    """EX-07's third acceptance: only fingerprints cross into the document.

    Quantified over the canonical bytes — which is what ``graph_version`` digests and what a
    snapshot store persists — **and** over the serialized envelope, since a body smuggled into
    a warning's ``detail`` would be just as published. The prompt text, a bound stop token and
    the secret's own value are all searched for verbatim.
    """
    envelope = gebra.extract(sd.WORKFLOWS[name]())

    document = canonical_bytes(envelope.ir).decode()
    published = to_json(envelope)
    for body in _BODIES:
        assert body not in document, (name, body)
        assert body not in published, (name, body)


@pytest.mark.parametrize("name", sorted(sd.WORKFLOWS))
def test_the_only_digest_shaped_content_is_the_two_slots(name: str) -> None:
    """The positive half: what *did* cross is a digest string in a digest slot.

    Together with the test above this is the "bodies never embedded" claim in both directions —
    nothing of the body is there, and what is there is the fingerprint the slot is specified to
    hold.
    """
    envelope = gebra.extract(sd.WORKFLOWS[name]())

    carried = [
        value
        for node in envelope.ir.nodes
        if node.annotations is not None
        for value in (node.annotations.prompt_digest, node.annotations.config_digest)
        if value is not None
    ]
    assert carried
    for value in carried:
        assert DIGEST.match(value), value


def test_a_warning_names_a_class_and_never_a_body() -> None:
    """The §8 record for an undigestable template carries an identity, not the template.

    An implementation that put the offending object in the message — the obvious way to make a
    warning helpful — would publish exactly what the slot exists not to publish.
    """
    text = "SECRET-PROMPT-TEXT"
    template = PromptTemplate(template=text, input_variables=[])
    unreadable = sd.PROMPT_CASES["armed-template"].build()

    for subject in (template, unreadable):
        digests = digests_for("n", subject)
        published = json.dumps([w.model_dump(mode="json") for w in digests.warnings])
        assert text not in published


# ── WA-07 — the tripwire for the path this card lands ────────────────────────────────────

#: The guarded child. Network primitives raise from the first line, socket *construction* is
#: only counted until the imports are done (the bounded-import phase the sibling paths explain),
#: and then every surface §7.4 promises not to touch is taken away: the ``Runnable`` execution
#: entry points, ``get_graph``, ``StateGraph.compile``, and — the one this path is really about
#: — ``builtins.repr``, which is what every rejected byte source reached and what would put a
#: memory address inside a digest. The fixtures arm the rest from their own side: a model's
#: properties, a config value's ``__repr__``/``__getattr__``, a mapping key's ``__str__`` and a
#: set member's ordering dunders all record and raise.
_TRIPWIRE = """
import socket, sys, builtins

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
        raise AssertionError("a socket was created on the digest path")


socket.socket = _CountSocket
socket.getaddrinfo = _record("getaddrinfo")
socket.gethostbyname = _record("gethostbyname")
socket.create_connection = _record("create_connection")

import gebra
from gebra.extraction.digests import coerce, config_form, digests_for, prompt_form
from langgraph.graph.state import StateGraph
from tests.sample_workflows import sentinel_digests as sd

# Build every fixture while the substrate is still whole — constructing a template or a model
# is the substrate's own work, not extraction's.
workflows = {name: build() for name, build in sd.WORKFLOWS.items()}
coercions = {name: case.build() for name, case in sd.COERCION_CASES.items()}
prompts = {name: case.build() for name, case in sd.PROMPT_CASES.items()}
configs = {name: case.build() for name, case in sd.CONFIG_CASES.items()}

assert attempts == [], attempts
socket.socket = _TripSocket
StateGraph.compile = _record("StateGraph.compile")

# `repr` is armed with **one** allow-list entry rather than outright, and the exception is
# named rather than assumed: IR-SPEC §6.1 step 6's ES number formatting takes CPython's
# shortest round-tripping digits from `repr` of an exact `float` (`gebra.ir.canonical.
# _format_double`), which is a builtin on a builtin and carries no address. Every other
# `repr` call site on this path is a defect — it is what PD-014 finding 3 rejected three
# candidate byte sources for — so this converts "no repr of a source object" from a claim
# about the code into a counted one about the run.
_stock_repr = builtins.repr


def _guarded_repr(value):
    if type(value) is float:
        return _stock_repr(value)
    attempts.append("repr"); print("WA07-TRIP", file=sys.stderr)
    raise AssertionError("repr was reached")


builtins.repr = _guarded_repr

# Arming `Runnable.invoke` alone would prove nothing: `BasePromptTemplate`, `BaseChatModel` and
# `RunnableBindingBase` all *override* it, so the base-class raiser is shadowed on exactly the
# two object families this path introduces. The arm list therefore walks the whole MRO of every
# fixture the path touches — the workflows, the templates, the models and the bindings around
# them — which is the standard `test_lcel.py` sets, for the same reason.
subjects = [*workflows.values(), *prompts.values()]
for pair in configs.values():
    subjects.append(pair[0])
    subjects.extend(pair[1])

armed = []
for runnable in subjects:
    for cls in type(runnable).__mro__:
        for method in (
            "invoke",
            "ainvoke",
            "stream",
            "astream",
            "batch",
            "abatch",
            "transform",
            "atransform",
            # The DEC-21-admitted class's *own* methods are `stream_events`/`astream_events` —
            # execution entry points that no base-class raiser shadows, so admitting the class
            # without arming them would leave its own surface uncovered.
            "stream_events",
            "astream_events",
            "get_graph",
        ):
            if method in vars(cls) and not getattr(vars(cls)[method], "_wa07", False):
                raiser = _record(cls.__name__ + "." + method)
                raiser._wa07 = True
                setattr(cls, method, raiser)
                armed.append(cls.__name__ + "." + method)
for expected in (
    "Runnable.get_graph",
    "BasePromptTemplate.invoke",
    "BaseChatModel.invoke",
    "RunnableBindingBase.invoke",
):
    assert expected in armed, (expected, armed)

# The DEC-21 admission is exercised under the guard rather than only outside it, and by an
# *enumerated* class where the substrate has one — the stock `RunnableBinding` was already
# admitted before this card, so requiring only "some admitted class" would leave the amendment's
# own surface unexercised here. `is` throughout: `in` would run the metaclass's `__eq__`.
from gebra.extraction.stock import ADMITTED_BINDING_CLASSES, STOCK_BINDING_SUBCLASSES

required = STOCK_BINDING_SUBCLASSES or ADMITTED_BINDING_CLASSES
assert any(
    any(type(binding) is wanted for wanted in required)
    for pair in configs.values()
    for binding in pair[1]
), "no admitted binding wrapper reached the guarded child"

counts = [0, 0, 0, 0]
for name, value in coercions.items():
    coerce(value); counts[0] += 1
for name, template in prompts.items():
    prompt_form(template); digests_for("n", template); counts[1] += 1
for name, pair in configs.items():
    config_form(pair[0], pair[1]); digests_for("n", pair[0], bindings=pair[1]); counts[2] += 1
for name, runnable in workflows.items():
    envelope = gebra.extract(runnable)
    envelope.graph_version()          # canonicalize and digest, still under the guard
    counts[3] += 1

assert counts == [%d, %d, %d, %d], counts
assert sd.TRIPPED == [], sd.TRIPPED
"""

_REPORT = "print(attempts)\nprint(sd.TRIPPED)\n"


def _run_guarded(probe: str = "") -> subprocess.CompletedProcess[str]:
    """The child, with an optional control probe appended after its own assertions."""
    body = _TRIPWIRE % (
        len(sd.COERCION_CASES),
        len(sd.PROMPT_CASES),
        len(sd.CONFIG_CASES),
        len(sd.WORKFLOWS),
    )
    return subprocess.run(
        [sys.executable, "-c", body + probe + _REPORT],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_digest_computation_invokes_nothing_and_renders_nothing() -> None:
    """The WA-07 claim for the §7.4 path, in a fresh interpreter.

    What makes it real rather than asserted is that the fixtures are armed from their own side:
    the model's ``_generate``, ``_llm_type``, ``_identifying_params``, ``lc_attributes`` and
    ``lc_secrets`` raise; the config value's ``__repr__``, ``__str__``, ``__format__`` and
    ``__getattr__`` raise; the mapping key's ``__str__`` raises; the set member's ordering
    dunders raise; the secret's ``get_secret_value`` raises; and every unrecognised template's
    members raise. Each records **before** raising, so the child asserts the fixture log empty
    as well as its own exit status.

    ``builtins.repr`` is armed on top of all that because it is the specific defect PD-014
    finding 3 rejected three candidate byte sources for: ``repr`` of a plumbing object embeds a
    ``0x…`` address, which is a run-dependent byte inside a digest and the exact thing this
    card's determinism acceptance forbids.

    The child asserts its own counts from the fixture tables, so a case added to any table joins
    this claim with it, and a pass that silently stopped reaching the fixtures fails here rather
    than passing with nothing to prove.
    """
    result = _run_guarded()

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().splitlines() == ["[]", "[]"], result.stdout
    assert "WA07-TRIP" not in result.stderr, result.stderr


@pytest.mark.parametrize(
    ("probe", "expected"),
    [
        ("repr(object())\n", "repr was reached"),
        ("workflows['chain'].invoke('x')\n", "RunnableSequence.invoke was reached"),
        ("prompts['string-template'].invoke({})\n", "BasePromptTemplate.invoke was reached"),
        ("configs['defaults'][0].invoke('x')\n", "BaseChatModel.invoke was reached"),
        (
            "configs['bound-overlay'][1][0].invoke('x')\n",
            "RunnableBindingBase.invoke was reached",
        ),
        ("workflows['chain'].get_graph()\n", "RunnableSequence.get_graph was reached"),
        ("StateGraph(dict).compile()\n", "StateGraph.compile was reached"),
        ("socket.socket()\n", "a socket was created"),
        ("socket.getaddrinfo('example.invalid', 80)\n", "getaddrinfo was reached"),
        ("socket.gethostbyname('example.invalid')\n", "gethostbyname was reached"),
        ("socket.create_connection(('example.invalid', 80))\n", "create_connection was reached"),
    ],
    ids=[
        "repr",
        "invoke",
        "template-invoke",
        "model-invoke",
        "binding-invoke",
        "get_graph",
        "compile",
        "socket",
        "getaddrinfo",
        "resolve",
        "connect",
    ],
)
def test_each_raiser_is_armed(probe: str, expected: str) -> None:
    """A tripwire nobody trips proves nothing — so every raiser gets its own control.

    The controls run *after* the child's own assertions, so each proves its raiser was live at
    the end of the very run that made the claim.
    """
    result = _run_guarded(probe)

    assert result.returncode != 0
    assert expected in result.stderr


@pytest.mark.parametrize(
    ("probe", "expected"),
    [
        ("sd.ArmedChatModel()._llm_type\n", "ArmedChatModel._llm_type"),
        ("sd.ArmedChatModel()._identifying_params\n", "ArmedChatModel._identifying_params"),
        ("sd.ArmedChatModel().lc_attributes\n", "ArmedChatModel.lc_attributes"),
        ("sd.ArmedChatModel().lc_secrets\n", "ArmedChatModel.lc_secrets"),
        ("sd.ArmedClient().anything\n", "ArmedClient.anything"),
        ("str(sd.ArmedKey())\n", "ArmedKey.__str__"),
        ("sorted([sd.ArmedMember('a'), sd.ArmedMember('b')])\n", "ArmedMember."),
        ("sd.ArmedSecret('x').get_secret_value()\n", "ArmedSecret.get_secret_value"),
        ("sd.ArmedTemplate(input_variables=[]).template\n", "ArmedTemplate.template"),
        ("sd.ArmedMessageItem().prompt\n", "ArmedMessageItem.prompt"),
        # `builtins.repr` is armed in the child, so the metaclass control calls its `__repr__`
        # directly — otherwise the guard's own raiser would fire first and prove nothing about
        # the fixture.
        ("type(sd.ArmedMetaValue).__repr__(sd.ArmedMetaValue)\n", "ArmedMeta.__repr__"),
        ("hash(sd.ArmedKey)\n", "ArmedMeta.__hash__"),
        ("sd.ArmedKey == int\n", "ArmedMeta.__eq__"),
        # EX-16's two: the overlay read the DEC-21 admission is bounded by, and a bound tool's
        # own body. Both are what makes `sd.TRIPPED == []` a claim rather than a dead fixture.
        (
            "configs['non-stock-binding-contributes-no-overlay'][1][0].kwargs\n",
            "NonStockBinding.kwargs",
        ),
        ("sd._armed_tool_body('anything')\n", "tool body"),
    ],
    ids=[
        "llm-type",
        "identifying-params",
        "lc-attributes",
        "lc-secrets",
        "value-getattr",
        "key-str",
        "member-order",
        "secret-value",
        "template-member",
        "message-item-member",
        "metaclass-repr",
        "metaclass-hash",
        "metaclass-eq",
        "non-stock-binding-kwargs",
        "tool-body",
    ],
)
def test_each_fixture_surface_is_armed(probe: str, expected: str) -> None:
    """The fixture-side raisers get controls too, for the same reason the guard's do.

    These are the ones that carry the specific §7.4 claims — that no property, method or
    rendering of a source object runs — so a fixture that quietly stopped raising would leave
    those claims vacuous while everything stayed green.
    """
    result = _run_guarded(f"try:\n    {probe.rstrip()}\nexcept BaseException:\n    pass\n")

    assert result.returncode == 0, result.stderr
    assert expected in result.stdout, result.stdout


def test_a_swallowed_trip_is_still_visible() -> None:
    """Recording before raising is what makes a ``try: … except: pass`` path visible.

    The assertion that matters is the *record*, not the exit status: a child that swallowed the
    exception exits 0 either way.
    """
    swallow = "\ntry:\n    socket.getaddrinfo('example.invalid', 80)\nexcept Exception:\n    pass\n"

    result = _run_guarded(swallow)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().splitlines() == ["['getaddrinfo']", "[]"], result.stdout
