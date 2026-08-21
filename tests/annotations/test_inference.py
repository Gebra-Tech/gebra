"""Shallow contract inference — ANNOTATION-API-SPEC §4 (ratified — DEC-08).

Four claims, each with its own section below:

* **The pattern table is closed, and each pattern is tested from both sides.**
  :data:`~tests.sample_workflows.sentinel_inference.INFERENCE_FIXTURES` states each node's
  whole outcome — the keys, *the pattern that licensed each one*, the applied D-011 default,
  and the blockers — and every fixture is checked against its own row.
  :data:`PATTERN_COVERAGE` is what makes "positive **and** negative" checkable per pattern
  rather than by counting tests: it names the fixtures on both sides of each of the five, and
  is asserted to cover the whole enum.
* **Inference never upgrades a claim.** The NEVER-SILENT-UPGRADE rule, asserted over every
  fixture and against a slot set written out from the specs rather than imported from the code.
* **Every inferred or defaulted slot carries its warning.** Asserted as a bijection over every
  fixture: each filled slot is named by exactly one finding, and each finding names only
  filled slots. The other half — that those findings read back as heuristic-grade through §5's
  own lookup — is ``tests/extraction/test_inference.py``.
* **Nothing is evaluated and nothing is invoked.** The source reader's own rules (a body it
  cannot read is the D-011 floor, never ``pure``), plus this path's WA-07 tripwire.

Nothing here imports langgraph or opens a socket.
"""

from __future__ import annotations

import ast
import functools
import os
import subprocess
import sys
import types
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

import pytest

from gebra.annotations import ANNOTATION_SLOTS, NodeContract, SlotGrade
from gebra.annotations.inference import (
    DEFAULT_EFFECT,
    INFERENCE_SLOTS,
    NEVER_INFERRED,
    Blocker,
    DefaultRule,
    InferenceFinding,
    Pattern,
    SourceCache,
    SourceRule,
    StateSchema,
    infer,
    infer_node,
    read_node_source,
)
from tests.sample_workflows import sentinel_inference as si
from tests.sample_workflows import sentinel_inference_futures as sif

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

REPO_ROOT = Path(__file__).resolve().parents[2]

#: The graph's state, as an extraction would supply it for the §4 exclusion.
SCHEMA: Final = StateSchema.of(*si.FULL_STATE_SCHEMAS)


def outcome(fixture: si.InferenceFixture) -> Any:
    """Run one fixture the way its row says it should be run."""
    return infer_node(fixture.node, state_schema=SCHEMA if fixture.schema else None)


def citations(inference: Any, slot: str) -> tuple[tuple[str, str], ...]:
    """One slot's inferred keys as the fixture table spells them: ``(key, pattern)`` pairs."""
    return tuple((key.key, key.pattern.value) for key in inference.keys.get(slot, ()))


# ── The closed pattern table ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize("name", sorted(si.INFERENCE_FIXTURES))
def test_every_fixture_reaches_its_declared_outcome(name: str) -> None:
    """Each row of the table is a §4 claim, asserted whole rather than field by field.

    Keys are compared **as sequences with their citations**, not as sets: §4 requires "one
    licensed-pattern citation per emitted key", so a build that found the right keys through
    the wrong pattern would be wrong in the way the warning is read, and would pass a set
    comparison.
    """
    fixture = si.INFERENCE_FIXTURES[name]

    inference = outcome(fixture)

    assert citations(inference, "input") == fixture.input
    assert citations(inference, "output") == fixture.output
    assert (inference.default.value if inference.default else None) == fixture.default
    assert inference.source.rule.value == fixture.source
    reported = [blocker.value for blocker in inference.blockers]
    assert [blocker for blocker in fixture.blockers if blocker not in reported] == []


@pytest.mark.parametrize("name", sorted(si.INFERENCE_FIXTURES))
def test_the_contract_carries_exactly_the_inferred_keys(name: str) -> None:
    """The carrier and the citations cannot disagree: the contract is built from them."""
    fixture = si.INFERENCE_FIXTURES[name]

    inference = outcome(fixture)

    assert inference.contract.input == (tuple(key for key, _ in fixture.input) or None)
    assert inference.contract.output == (tuple(key for key, _ in fixture.output) or None)


#: Which fixtures license each §4 pattern, and which look like it and do not.
#:
#: This is the card's "each closed pattern has positive + negative tests" acceptance in a form
#: a reader can check against the spec: the left column is quantified over the whole
#: :class:`Pattern` enum below, so a pattern with no fixtures on both sides fails the suite
#: rather than being absent from it.
PATTERN_COVERAGE: Final[dict[str, tuple[tuple[str, ...], tuple[str, ...]]]] = {
    "state-annotation-keys": (
        (
            "input_annotation_typed_dict",
            "input_annotation_inherited",
            "input_annotation_pydantic",
        ),
        (
            "input_annotation_full_state",
            "input_annotation_full_pydantic_state",
            "input_annotation_bare_dict",
            "input_annotation_string",
            "input_annotation_without_a_schema",
        ),
    ),
    "state-access": (
        ("input_subscript", "input_attribute", "input_in_a_comprehension"),
        (
            "input_computed_subscript",
            "input_method_call",
            "input_private_attribute",
            "input_inside_a_helper",
            "input_after_rebinding",
        ),
    ),
    "return-literal": (
        ("output_literal_dict", "multi_return_all_licensed", "multi_return_bare_returns"),
        (
            "output_dict_call",
            "output_spread",
            "output_computed_key",
            "output_from_a_helper",
            "multi_return_one_unlicensed",
        ),
    ),
    "return-annotation-keys": (
        ("output_annotation_typed_dict", "output_annotation_only", "shape_async"),
        (
            "output_annotation_full_state",
            "output_annotation_pydantic",
            "multi_return_annotation_abandoned",
        ),
    ),
    "command-update": (
        ("output_command_update",),
        (
            "output_command_built_elsewhere",
            "output_command_bound_to_a_name",
            "output_command_spread_keywords",
            "output_command_without_update",
        ),
    ),
}


def test_the_pattern_table_is_covered_from_both_sides() -> None:
    """Every pattern §4 licenses has fixtures that license it and fixtures that do not.

    Written against the enum rather than against a count, so adding a sixth pattern — which
    would be a spec change, since the table is closed — fails here until it is covered.
    """
    assert set(PATTERN_COVERAGE) == {pattern.value for pattern in Pattern}
    for positives, negatives in PATTERN_COVERAGE.values():
        assert positives and negatives


@pytest.mark.parametrize("pattern", sorted(PATTERN_COVERAGE))
def test_each_pattern_is_licensed_by_its_positive_fixtures(pattern: str) -> None:
    """The positive side: the named fixtures cite this pattern for at least one key."""
    for name in PATTERN_COVERAGE[pattern][0]:
        inference = outcome(si.INFERENCE_FIXTURES[name])
        cited = {key.pattern.value for keys in inference.keys.values() for key in keys}
        assert pattern in cited, name


@pytest.mark.parametrize("pattern", sorted(PATTERN_COVERAGE))
def test_each_pattern_is_refused_by_its_negative_fixtures(pattern: str) -> None:
    """The negative side: a shape that looks like the pattern licenses nothing under it.

    This is the half that makes "shallow" mean something. Every fixture here is a real thing
    people write — ``state.get("k")``, ``dict(**kwargs)``, ``def node(state: State)`` — and
    each of them stays *outside* the table.
    """
    for name in PATTERN_COVERAGE[pattern][1]:
        inference = outcome(si.INFERENCE_FIXTURES[name])
        cited = {key.pattern.value for keys in inference.keys.values() for key in keys}
        assert pattern not in cited, name


def test_the_pattern_table_is_asymmetric_about_pydantic() -> None:
    """§4's ``input`` row licenses "a ``TypedDict``/pydantic projection"; its ``output`` row
    licenses "a ``TypedDict`` return-type annotation". DEC-08 restates both in the same words.

    The table is closed — "anything not on it is not inferred" — so the same class read in the
    two positions gives two answers. It matters because output keys are a claim about *writes*:
    a pydantic return annotation read as a projection would put its field names in ``output``,
    inside the ``graph_version`` hash scope, over-reporting what the node writes.
    """
    on_the_parameter = outcome(si.INFERENCE_FIXTURES["input_annotation_pydantic"])
    on_the_return = outcome(si.INFERENCE_FIXTURES["output_annotation_pydantic"])

    assert citations(on_the_parameter, "input") == (("query", "state-annotation-keys"),)
    assert citations(on_the_return, "output") == ()
    assert Blocker.NOT_A_TYPED_DICT in on_the_return.blockers


def test_a_matched_output_pattern_is_write_evidence_even_with_no_keys_left() -> None:
    """§4's D-011 branch is a two-part test over the *patterns*: a node takes the ``pure``
    branch only when "no licensed output pattern matches **and** no assignment/mutation of the
    state parameter appears in the node body".

    Both halves of the pattern-(b) case are checked. A node that writes *only* by its return
    annotation is a writer even though its body shows nothing; and a node whose unlicensed
    return site abandoned the key set is still a writer, because the annotation matched. The
    alternative reading calls a node with a declared write ``pure: true``, which is the one
    direction D-011's "provably read-only" rules out.
    """
    annotation_only = outcome(si.INFERENCE_FIXTURES["output_annotation_only"])
    abandoned = outcome(si.INFERENCE_FIXTURES["multi_return_annotation_abandoned"])

    assert annotation_only.default is DefaultRule.WRITES_STATE
    assert annotation_only.contract.output == ("plan",)
    assert annotation_only.contract.pure is None

    assert abandoned.default is DefaultRule.WRITES_STATE
    assert abandoned.contract.output is None
    assert abandoned.contract.effect == DEFAULT_EFFECT
    assert abandoned.contract.pure is None


def test_no_fixture_is_called_pure_while_it_reports_a_write() -> None:
    """The contradiction the two-part test exists to prevent, quantified over the table."""
    contradictory = {
        name
        for name, fixture in si.INFERENCE_FIXTURES.items()
        if outcome(fixture).contract.pure is True and outcome(fixture).contract.output is not None
    }

    assert contradictory == set()


def test_a_projection_that_refuses_to_answer_does_not_stop_an_extraction() -> None:
    """``model_fields`` is a metaclass property, so a model answers it however it likes.

    Inference is the tier that guesses: a class that will not say what it declares is "no
    projection here" and the node falls to the D-011 floor — an exception out of `infer()`
    would make extraction total in name only.
    """
    inference = outcome(si.INFERENCE_FIXTURES["input_annotation_unreadable"])

    assert inference.contract.input is None
    assert Blocker.PROJECTION_UNREADABLE in inference.blockers
    assert inference.default is DefaultRule.WRITES_STATE


def test_the_full_state_exclusion_is_identity_and_not_shape() -> None:
    """§4 excludes "the graph's full state schema **itself**", which is an identity test.

    A projection that happens to declare every key the state has is still a projection: the
    author wrote it to say so. Only the graph's own schema object carries no information.
    """
    twin = si.State  # the same class, reached under another name — still excluded
    unrelated = si.Reads

    assert StateSchema.of(twin).is_full_state(si.State) is True
    assert StateSchema.of(unrelated).is_full_state(si.State) is False
    assert StateSchema.of().is_full_state(si.State) is False


def test_a_string_annotation_is_not_resolved_under_a_future_import() -> None:
    """PEP 563 leaves strings behind, and §4 forbids evaluating them.

    So the two annotation patterns withdraw and the body patterns carry the node — the whole
    outcome, not a partial one: the node still infers ``output`` from its literal return.
    """
    inference = infer_node(
        sif.annotated_under_future_import,
        state_schema=StateSchema.of(*sif.FULL_STATE_SCHEMAS),
    )

    assert citations(inference, "input") == (("query", "state-access"),)
    assert citations(inference, "output") == (("plan", "return-literal"),)
    assert Blocker.STRING_ANNOTATION in inference.blockers
    assert inference.default is DefaultRule.WRITES_STATE


# ── NEVER-SILENT-UPGRADE ─────────────────────────────────────────────────────────────────


def test_the_two_slot_sets_partition_the_annotatable_surface() -> None:
    """What inference may fill and what it may never fill, written out from the specs.

    Both sides are spelled here rather than derived from the code, so that a slot moving from
    one set to the other — which is what a silent upgrade *is* — fails this test.
    """
    inferable = {"input", "output", "effect", "pure"}
    never = {"idempotent", "deterministic", "variant", "compensation", "args_schema"}

    assert set(INFERENCE_SLOTS) == inferable
    assert set(NEVER_INFERRED) == never
    assert inferable | never == set(ANNOTATION_SLOTS)
    assert inferable & never == set()


@pytest.mark.parametrize("name", sorted(si.INFERENCE_FIXTURES))
def test_inference_never_yields_an_upgraded_slot(name: str) -> None:
    """§4's hard rule, over every fixture: "inference **never** yields ``idempotent``,
    ``deterministic``, ``variant``, or ``compensation``" — plus §1's ``args_schema``.

    Asserted against the contract rather than against the code path, because the claim is
    about what a consumer receives.
    """
    contract = outcome(si.INFERENCE_FIXTURES[name]).contract

    assert contract.idempotent is None
    assert contract.deterministic is None
    assert contract.variant is None
    assert contract.compensation is None
    assert contract.args_schema is None
    assert set(contract.declared_slots()) <= set(INFERENCE_SLOTS)


def test_no_fixture_in_the_whole_table_upgrades_anything() -> None:
    """The same claim once more, quantified over the table rather than per fixture.

    Per-fixture parametrization proves it for each row; this proves it for the *union*, which
    is what a reader of the acceptance box is being told.
    """
    upgraded = {
        name: slot
        for name, fixture in si.INFERENCE_FIXTURES.items()
        for slot in outcome(fixture).contract.declared_slots()
        if slot in NEVER_INFERRED
    }

    assert upgraded == {}


def test_the_defaults_are_the_only_way_effect_or_pure_is_filled() -> None:
    """``effect``/``pure`` come from the D-011 defaults and from no pattern.

    The two slots are not in §4's pattern table at all, so the only thing that may set them is
    the conservative default — which is what makes their ``contract-defaulted`` grade true.
    """
    for name, fixture in si.INFERENCE_FIXTURES.items():
        inference = outcome(fixture)
        if inference.default is None:
            assert inference.contract.effect is None, name
            assert inference.contract.pure is None, name
        elif inference.default is DefaultRule.NO_WRITE_EVIDENCE:
            assert inference.contract.pure is True, name
            assert inference.contract.effect is None, name
        else:
            assert inference.contract.effect == DEFAULT_EFFECT, name
            assert inference.contract.pure is None, name


# ── Every filled slot carries its finding ────────────────────────────────────────────────


@pytest.mark.parametrize("name", sorted(si.INFERENCE_FIXTURES))
def test_every_filled_slot_is_named_by_exactly_one_finding(name: str) -> None:
    """§4: "every inferred slot carries a ``contract-inferred`` warning", and its D-011 twin.

    A bijection in both directions: a slot with no finding would be a heuristic value §5's
    lookup reports as declared-grade, and a finding with no slot would be a warning about
    nothing.
    """
    inference = outcome(si.INFERENCE_FIXTURES[name])

    named = [slot for finding in inference.findings for slot in finding.slots]
    assert sorted(named) == sorted(inference.contract.declared_slots())
    assert len(named) == len(set(named))


@pytest.mark.parametrize("name", sorted(si.INFERENCE_FIXTURES))
def test_each_finding_carries_what_its_registry_row_names(name: str) -> None:
    """The §4 registry's "carries" column, per grade.

    ``contract-inferred``: "which slots were inferred; the licensing pattern … reminder that
    claims were not upgraded". ``contract-defaulted``: "the applied D-011 default; why no
    pattern applied; pointer to the declaration surfaces".
    """
    inference = outcome(si.INFERENCE_FIXTURES[name])

    for finding in inference.findings:
        if finding.grade is SlotGrade.INFERRED:
            patterns = finding.detail["patterns"]
            assert set(patterns) == set(finding.slots)
            for slot in finding.slots:
                assert set(patterns[slot]) == {key.key for key in inference.keys[slot]}
            assert finding.detail["claims_not_upgraded"] == list(NEVER_INFERRED)
        else:
            assert inference.default is not None
            assert finding.detail["rule"] == inference.default.value
            assert finding.detail["why"] == [blocker.value for blocker in inference.blockers]
            assert finding.detail["declaration_surfaces"] == ["decorator", "sidecar"]
            assert finding.detail["applied"] in ({"pure": True}, {"effect": ["write"]})
        assert finding.message.strip() == finding.message
        assert finding.detail["surface"] == "inference"


def test_a_finding_refuses_the_declared_grade() -> None:
    """§5's third grade is the *absence* of a finding, so it cannot be one."""
    with pytest.raises(ValueError, match="not one of the two grades"):
        InferenceFinding(grade=SlotGrade.DECLARED, slots=("input",), message="…")


def test_a_finding_refuses_to_name_no_slot() -> None:
    """§5's lookup is keyed by (node id, slot); a slotless record answers no question."""
    with pytest.raises(ValueError, match="names the slot"):
        InferenceFinding(grade=SlotGrade.INFERRED, slots=(), message="…")


# ── Inference fills what remains (§3's one sentence that lives here) ─────────────────────


def test_a_declared_slot_is_neither_filled_nor_warned() -> None:
    """§3: "Inference (lowest) … fills what remains".

    Both halves matter, and the second is the one that is easy to miss: a ``contract-inferred``
    warning naming a slot the decorator set would make §5's grade lookup call that slot
    heuristic-grade, which is a false statement about an author's declaration.
    """
    fixture = si.INFERENCE_FIXTURES["input_subscript"]

    inference = infer_node(fixture.node, state_schema=SCHEMA, declared=("input",))

    assert inference.contract.input is None
    assert inference.contract.output is not None
    assert all("input" not in finding.slots for finding in inference.findings)


def test_the_d011_default_stays_out_when_either_half_of_the_pair_is_declared() -> None:
    """``pure`` and ``effect`` are one statement in two slots (decision D-011 exclusivity).

    Filling one while the other is declared would assemble the cross-surface contradiction
    §3's resolved-contract pass exists to repair — from the tier that is meant to fill gaps.
    """
    writer = si.INFERENCE_FIXTURES["default_assignment"].node

    assert infer_node(writer, state_schema=SCHEMA).default is DefaultRule.WRITES_STATE
    assert infer_node(writer, state_schema=SCHEMA, declared=("pure",)).default is None
    assert infer_node(writer, state_schema=SCHEMA, declared=("effect",)).default is None


def test_a_fully_declared_contract_leaves_inference_with_nothing_to_say() -> None:
    """The degenerate case of the same rule: no value, and — equally — no warning."""
    fixture = si.INFERENCE_FIXTURES["input_subscript"]

    inference = infer_node(fixture.node, state_schema=SCHEMA, declared=INFERENCE_SLOTS)

    assert inference.contract == NodeContract()
    assert inference.findings == ()
    assert inference.default is None


def test_the_inference_reports_the_slots_it_filled() -> None:
    """The tier's own summary, in :data:`ANNOTATION_SLOTS` order — what §3's chain consumes."""
    filled = outcome(si.INFERENCE_FIXTURES["input_subscript"])
    empty = infer_node(si.reads_literal_subscripts, state_schema=SCHEMA, declared=INFERENCE_SLOTS)

    assert filled.inferred_slots() == ("input", "output", "effect")
    assert empty.inferred_slots() == ()


def test_an_empty_key_set_leaves_its_slot_unset() -> None:
    """Never ``output: []``.

    An empty array is a positive claim ("writes nothing") that no pattern made, and IR-SPEC
    §6.3 omits it from the canonical form — so it would be invisible in ``graph_version``
    while still blocking the D-011 floor at §3's chain. PD-019 (ii) decided the twin case for
    a sidecar whose every effect tag was rejected.
    """
    inference = outcome(si.INFERENCE_FIXTURES["output_empty_dict"])

    assert inference.contract.output is None
    assert "output" not in inference.keys
    assert inference.contract.pure is True


# ── The source reader ────────────────────────────────────────────────────────────────────


def compiled_elsewhere(filename: str) -> Callable[..., Any]:
    """A node whose code object names ``filename`` — how the reader's rules are reached."""
    namespace: dict[str, Any] = {}
    source = "def node(state):\n    return {'plan': state['query']}\n"
    exec(compile(source, filename, "exec"), namespace)  # noqa: S102 - the fixture is the point
    function: Callable[..., Any] = namespace["node"]
    return function


#: Every way :class:`SourceRule` says a body can fail to be read, with how to reach it. The
#: dict is asserted against the whole enum below, so a rule with no test fails the suite.
SOURCE_CASES: Final[dict[str, Callable[[Path], Any]]] = {
    "read": lambda _: si.reads_literal_subscripts,
    "not-a-python-function": lambda _: si.CallableNode(),
    "opaque": lambda _: None,  # reached through `opaque=True`, not through a callable
    "source-unavailable": lambda _: compiled_elsewhere("<string>"),
    "source-unparsable": lambda tmp: _unparsable(tmp),
    "definition-not-found": lambda tmp: _moved_definition(tmp),
    "definition-ambiguous": lambda tmp: _two_lambdas_on_one_line(tmp),
}


def _write(tmp: Path, name: str, text: str) -> Path:
    """One temporary module file."""
    path = tmp / name
    path.write_text(text, encoding="utf-8")
    return path


def _unparsable(tmp: Path) -> Any:
    """A node whose file exists and is not Python — edited since it was imported."""
    path = _write(tmp, "unparsable.py", "this is (not python\n")
    return compiled_elsewhere(str(path))


def _moved_definition(tmp: Path) -> Any:
    """A node whose file is Python but holds no matching definition at its line."""
    path = _write(tmp, "moved.py", "x = 1\n")
    return compiled_elsewhere(str(path))


def _two_lambdas_on_one_line(tmp: Path) -> Any:
    """Two ``lambda``\\ s with the same parameters on one line — nothing separates them."""
    path = _write(tmp, "twins.py", "pair = (lambda state: state['a'], lambda state: state['b'])\n")
    namespace: dict[str, Any] = {}
    exec(compile(path.read_text(encoding="utf-8"), str(path), "exec"), namespace)  # noqa: S102
    return namespace["pair"][0]


def test_every_source_rule_has_a_case() -> None:
    """Asserted against the whole enum, so an unreachable rule is a failure, not a gap."""
    assert set(SOURCE_CASES) == {rule.value for rule in SourceRule}


@pytest.mark.parametrize("rule", sorted(SOURCE_CASES))
def test_each_source_rule_is_reached_by_its_case(rule: str, tmp_path: Path) -> None:
    """Each way of not having a body is reported as itself rather than as a generic failure.

    The distinction is what the ``contract-defaulted`` row's "why no pattern applied" field
    carries, and the repairs differ: a node compiled from a string cannot be helped, while a
    node whose definition moved is a stale ``.pyc`` away from working.
    """
    if rule == "opaque":
        assert infer_node(si.reads_literal_subscripts, opaque=True).source.rule is SourceRule.OPAQUE
        return

    source = read_node_source(SOURCE_CASES[rule](tmp_path))

    assert source.rule.value == rule


def test_two_lambdas_on_one_line_are_separated_by_their_parameters(tmp_path: Path) -> None:
    """The positive control for the tie-break: ambiguity is refused, not guessed at.

    ``definition-ambiguous`` is only correct if the code *tried* — two lambdas that differ in
    their parameters are told apart, and only twins that differ in nothing are refused.
    """
    path = _write(
        tmp_path, "pair.py", "pair = (lambda alpha: alpha['a'], lambda beta: beta['b'])\n"
    )
    namespace: dict[str, Any] = {}
    exec(compile(path.read_text(encoding="utf-8"), str(path), "exec"), namespace)  # noqa: S102

    first = read_node_source(namespace["pair"][0])
    second = read_node_source(namespace["pair"][1])

    assert first.rule is SourceRule.READ
    assert second.rule is SourceRule.READ
    assert isinstance(first.definition, ast.Lambda)
    assert first.definition.args.args[0].arg == "alpha"
    assert isinstance(second.definition, ast.Lambda)
    assert second.definition.args.args[0].arg == "beta"


@pytest.mark.parametrize(
    "target",
    [
        len,
        functools.partial(si.reads_literal_subscripts),
        si.CallableNode(),
        "not a callable at all",
    ],
    ids=["builtin", "partial", "callable-object", "not-callable"],
)
def test_a_target_with_no_python_body_is_not_followed(target: object) -> None:
    """§6's wrapper walk is the resolution card's, so §4 stops at the object it was given.

    A ``functools.partial`` is the case worth naming: it *has* a Python function inside it,
    and reaching in for it would be following a wrapper — which is exactly the rule ANNOTATION
    §6 states and which belongs where the precedence chain is applied.
    """
    source = read_node_source(target)

    assert source.rule is SourceRule.NOT_A_PYTHON_FUNCTION
    assert source.definition is None


def test_a_body_that_could_not_be_read_takes_the_write_floor(tmp_path: Path) -> None:
    """D-011's ``pure`` is for "**provably** read-only", and an unread body proves nothing.

    §4's second bullet tests what the body *shows*; a body that shows nothing is not a body
    that shows no writes. Reading the absence of evidence as evidence of absence is the one
    mistake the D-011 floor exists to prevent — INTROSPECTION §5 rule 5 repeats the same
    words for the opaque-lambda case.
    """
    for candidate in (si.CallableNode(), compiled_elsewhere("<string>"), _unparsable(tmp_path)):
        inference = infer_node(candidate, state_schema=SCHEMA)

        assert inference.default is DefaultRule.BODY_UNAVAILABLE
        assert inference.contract.effect == DEFAULT_EFFECT
        assert inference.contract.pure is None
        assert Blocker.BODY_UNAVAILABLE in inference.blockers


def test_an_opaque_node_skips_inference_and_goes_straight_to_defaults() -> None:
    """§4: "opaque nodes (``RunnableLambda`` bodies …) skip inference entirely and go
    straight to defaults" — even when the callable would have been perfectly readable."""
    readable = si.reads_literal_subscripts

    assert infer_node(readable, state_schema=SCHEMA).contract.input is not None

    opaque = infer_node(readable, state_schema=SCHEMA, opaque=True)

    assert opaque.contract == NodeContract(effect=DEFAULT_EFFECT)
    assert opaque.default is DefaultRule.BODY_UNAVAILABLE


def test_a_source_file_that_is_not_a_regular_file_is_not_opened(tmp_path: Path) -> None:
    """A directory — and anything else ``is_file()`` refuses — is "no body", not an error.

    The gate is a stat call and it comes first, which is what keeps a ``co_filename`` naming a
    FIFO or a character device from blocking an extraction on a read that never returns.
    """
    source = read_node_source(compiled_elsewhere(str(tmp_path)))

    assert source.rule is SourceRule.SOURCE_UNAVAILABLE
    assert source.detail["file"] == str(tmp_path)


def test_a_source_file_past_the_size_bound_is_not_parsed(tmp_path: Path) -> None:
    """The bound is a fuse, not a policy: past it the node takes the D-011 floor."""
    from gebra.annotations.inference import _MAX_SOURCE_BYTES

    path = _write(tmp_path, "huge.py", "# " + "x" * _MAX_SOURCE_BYTES + "\n")

    assert read_node_source(compiled_elsewhere(str(path))).rule is SourceRule.SOURCE_UNAVAILABLE


def test_the_reader_reads_the_defining_file_and_names_it() -> None:
    """The detail is where the ``contract-defaulted`` row's "why" gets its file from."""
    source = read_node_source(si.reads_literal_subscripts)

    assert source.read is True
    assert source.detail["file"] == si.__file__
    assert source.detail["name"] == "reads_literal_subscripts"
    assert isinstance(source.definition, ast.FunctionDef)


def test_a_source_that_could_not_be_read_says_so_in_one_word() -> None:
    """:attr:`NodeSource.read` is the question every caller of the reader actually asks."""
    assert read_node_source(si.CallableNode()).read is False


def test_a_bound_method_of_a_builtin_has_no_python_body() -> None:
    """A bound method is unwrapped once, and what is under it may still not be Python.

    ``types.MethodType`` accepts any callable, so ``__func__`` is not always a function; the
    reader checks rather than assumes, because the alternative is an ``AttributeError`` out of
    an extraction.
    """
    bound = types.MethodType(len, [1, 2, 3])

    assert read_node_source(bound).rule is SourceRule.NOT_A_PYTHON_FUNCTION


def test_a_file_that_cannot_be_opened_is_no_body_rather_than_an_error(tmp_path: Path) -> None:
    """The reader is total: a file it may not read is the D-011 floor, not an exception.

    ``is_file()`` says yes and the read still fails — the one gap the stat gate cannot close,
    and the reason the read is inside the same guard.
    """
    path = _write(tmp_path, "unreadable.py", "def node(state):\n    return {}\n")
    node = compiled_elsewhere(str(path))
    path.chmod(0o000)
    if os.access(path, os.R_OK):  # pragma: no cover - only on a root or permission-free FS
        pytest.skip("this user is not subject to file permissions")

    try:
        assert read_node_source(node).rule is SourceRule.SOURCE_UNAVAILABLE
    finally:
        path.chmod(0o644)


def _summed(terms: int) -> str:
    """A node whose body is one left-nested ``BinOp`` chain ``terms`` deep."""
    return f"def node(state):\n    x = {'+'.join(['1'] * terms)}\n    return x\n"


def _the_parser_here_accepts(source: str) -> bool:
    """Whether *this* interpreter's own ``ast.parse`` accepts ``source``.

    The tested interpreters do not agree about how deep an expression may be, and the two
    tests below say what each one actually does rather than what 3.13 does (EX-17 /
    PD-038 Finding 3). Measured on this machine's CPython builds: a 6000-term sum parses
    on 3.10, 3.12 and 3.13 and raises ``RecursionError`` on 3.11, whose limit sits between
    2500 and 3000 terms. Nothing about ``gebra`` or the substrate is involved — this is
    ``ast.parse`` on a temporary file.
    """
    try:
        ast.parse(source)
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        return False
    return True


def test_a_body_nested_past_the_walk_is_no_body_rather_than_an_error(tmp_path: Path) -> None:
    """The walk descends recursively, and a body can out-nest the interpreter's stack.

    Parsing is guarded (:func:`ast.parse` has its own limits and they are caught); this is the
    second half — the body *parses*, and then the walk over it is what runs out of stack. A
    ``RecursionError`` escaping ``infer()`` would end an extraction over a node whose contract
    is a guess in the first place, so it is the D-011 floor instead.

    1000 terms is chosen to reach the walk on every tested interpreter: the walk gives up
    between 400 and 500 terms on all four, and the earliest parser limit among them (3.11's) is
    between 2500 and 3000 — so this depth is over the one and well under the other. The first
    assertion pins that choice, so an interpreter whose parser stopped accepting it fails here
    naming the reason instead of failing further down as a mystery.
    """
    source = _summed(1000)
    path = _write(tmp_path, "deep.py", source)

    assert _the_parser_here_accepts(source), "this interpreter's parser refuses 1000 terms"

    inference = infer_node(compiled_elsewhere(str(path)), state_schema=SCHEMA)

    assert inference.source.rule is SourceRule.READ
    assert Blocker.BODY_TOO_DEEP in inference.blockers
    assert inference.default is DefaultRule.BODY_UNAVAILABLE
    assert inference.contract.effect == DEFAULT_EFFECT


def test_a_body_the_parser_itself_gives_up_on_is_no_body_rather_than_an_error(
    tmp_path: Path,
) -> None:
    """The same floor by the other route, written against what each interpreter does.

    A 6000-term body is past CPython 3.11's parser and inside every other tested
    interpreter's, so the two routes to the D-011 floor swap between the matrix's Python axes
    (EX-17 / PD-038 Finding 3). The property this pins does not swap with them, and it is
    asserted first and unconditionally: a body too deep for the machinery is *no body* —
    the D-011 default, on every interpreter — never an exception out of ``infer()``.

    Which of the two routes got there is then pinned against this interpreter's own
    ``ast.parse``, so the test states the difference it accommodates rather than encoding a
    version number: parser gives up → ``source-unparsable`` + ``body-unavailable``; parser
    succeeds and the walk gives up → ``read`` + ``body-too-deep``.
    """
    source = _summed(6000)
    path = _write(tmp_path, "deeper.py", source)

    inference = infer_node(compiled_elsewhere(str(path)), state_schema=SCHEMA)

    assert inference.default is DefaultRule.BODY_UNAVAILABLE
    assert inference.contract.effect == DEFAULT_EFFECT
    if _the_parser_here_accepts(source):
        assert inference.source.rule is SourceRule.READ
        assert Blocker.BODY_TOO_DEEP in inference.blockers
    else:
        assert inference.source.rule is SourceRule.SOURCE_UNPARSABLE
        assert Blocker.BODY_UNAVAILABLE in inference.blockers


def test_the_cache_starts_over_rather_than_growing_without_bound() -> None:
    """A bound, not a policy: an extraction over more files than this is not a thing, and a
    cache that could grow forever in a long-lived process would be."""
    from gebra.annotations.inference import _MAX_CACHED_MODULES

    cache = SourceCache()
    for index in range(_MAX_CACHED_MODULES + 1):
        cache.remember((f"module-{index}.py", index, index), (None, SourceRule.SOURCE_UNAVAILABLE))

    assert len(cache) == 1
    assert cache.get(("module-0.py", 0, 0)) is None


def test_a_relative_source_path_is_not_searched_for_on_sys_path(tmp_path: Path) -> None:
    """``linecache`` searches ``sys.path`` for a matching basename; this reader does not.

    Reading a *different* file with the same name would infer a contract from source the node
    does not have — a wrong answer where "no answer, D-011 floor" is available.
    """
    _write(tmp_path, "elsewhere.py", "def node(state):\n    return {'plan': 1}\n")
    monkey = compiled_elsewhere("elsewhere.py")

    with_cwd_elsewhere = read_node_source(monkey)

    assert with_cwd_elsewhere.rule is SourceRule.SOURCE_UNAVAILABLE


def test_the_cache_parses_one_file_once(tmp_path: Path) -> None:
    """The per-extraction cache is an optimisation and must change no outcome."""
    cache = SourceCache()
    nodes = (si.reads_literal_subscripts, si.reads_literal_attributes, si.writes_a_literal_dict)

    cached = [infer_node(node, state_schema=SCHEMA, cache=cache) for node in nodes]
    uncached = [infer_node(node, state_schema=SCHEMA) for node in nodes]

    assert len(cache) == 1
    assert [inference.contract for inference in cached] == [
        inference.contract for inference in uncached
    ]


def test_the_cache_re_reads_a_file_that_changed(tmp_path: Path) -> None:
    """Keyed by size and modification time, so a file edited mid-extraction is read again."""
    path = _write(tmp_path, "edited.py", "def node(state):\n    return {'plan': state['query']}\n")
    cache = SourceCache()
    before = infer_node(compiled_elsewhere(str(path)), state_schema=SCHEMA, cache=cache)

    _write(tmp_path, "edited.py", "def node(state):\n    return {'budget': state['plan']}\n")
    after = infer_node(compiled_elsewhere(str(path)), state_schema=SCHEMA, cache=cache)

    assert before.contract.output == ("plan",)
    assert after.contract.output == ("budget",)


# ── Determinism ──────────────────────────────────────────────────────────────────────────


def test_inference_is_a_value_and_repeats() -> None:
    """A pure per-node function (§4): the same node and schema give the same contract.

    Value equality rather than identity, because what §3 will compare is the contract.
    """
    for fixture in si.INFERENCE_FIXTURES.values():
        first = outcome(fixture)
        second = outcome(fixture)

        assert first.contract == second.contract
        assert first.default == second.default
        assert [f.detail for f in first.findings] == [f.detail for f in second.findings]


def test_an_already_read_source_can_be_inferred_from_directly() -> None:
    """§4's own signature is ``infer(node_ast, state_schema)``, and it is the public one."""
    source = read_node_source(si.reads_literal_subscripts)

    assert (
        infer(source, state_schema=SCHEMA).contract
        == infer_node(si.reads_literal_subscripts, state_schema=SCHEMA).contract
    )


# ── WA-07 — the tripwire for the path this card lands ────────────────────────────────────

#: The guarded child. Two phases, for the two strengths the halves can honestly claim.
#:
#: **Phase A — the imports.** :mod:`gebra.annotations.inference` reaches no substrate, so the
#: child asserts that langgraph, langchain-core and ``gebra.extraction`` are absent from
#: ``sys.modules`` after importing it and the fixture modules. Sockets, name resolution and
#: connection raise from the first line, before anything is imported at all.
#:
#: **Phase B — inference over every fixture, with the evaluators armed.** ``eval`` and ``exec``
#: raise outright. ``compile`` is *wrapped* rather than armed, because ``ast.parse`` is a call
#: to it: the wrapper refuses any call that is not a parse (``PyCF_ONLY_AST``), which turns
#: "this path parses and never compiles anything runnable" into a checked claim rather than a
#: reviewed one, and counts the parses so a run that reached none would fail. The two routes
#: into user code that this reader exists to avoid — ``inspect``'s source lookup and
#: ``linecache``'s lazy loader — raise, as does :func:`typing.get_type_hints`, which is how a
#: string annotation would get resolved if §4's no-evaluation rule were ever relaxed. DEC-08's
#: other half — "no imports are followed" — is armed as "nothing new is *loaded*": ``__import__``
#: refuses any module that is not already in ``sys.modules``, which leaves the stdlib's own
#: in-function imports alone (``ast.walk`` does one on every call) and refuses the thing the
#: rule is about, a module brought in on a node's behalf.
_TRIPWIRE = """
import builtins, ast, socket, sys

attempts = []
parses = []


def _record(name):
    def _seen(*a, **k):
        attempts.append(name); print("WA07-TRIP", file=sys.stderr)
        raise AssertionError(name + " was reached")
    return _seen


class _TripSocket(socket.socket):
    def __new__(cls, *a, **k):
        attempts.append("socket"); print("WA07-TRIP", file=sys.stderr)
        raise AssertionError("a socket was created on the inference path")


socket.socket = _TripSocket
socket.getaddrinfo = _record("getaddrinfo")
socket.gethostbyname = _record("gethostbyname")
socket.create_connection = _record("create_connection")

# ── Phase A: the imports, with no substrate excused ──
from gebra.annotations.inference import StateSchema, infer_node, read_node_source
from tests.sample_workflows import sentinel_inference as si
from tests.sample_workflows import sentinel_inference_futures as sif

assert "langgraph" not in sys.modules, sorted(sys.modules)
assert "langchain_core" not in sys.modules, sorted(sys.modules)
assert "gebra.extraction" not in sys.modules

# ── Phase B: inference over every fixture ──
# Armed only now: `dataclasses` and pydantic build classes with `exec` at *import* time, so
# arming before the imports above would trip on gebra's own construction rather than on
# anything a node caused. Everything below this line reads source and builds an AST.
import inspect, linecache, typing

_real_compile = builtins.compile


def _only_parses(*a, **k):
    flags = k.get("flags", a[3] if len(a) > 3 else 0)
    if not flags & ast.PyCF_ONLY_AST:
        attempts.append("compile"); print("WA07-TRIP", file=sys.stderr)
        raise AssertionError("compile() was called for something other than a parse")
    parses.append(1)
    return _real_compile(*a, **k)


_real_eval, _real_exec, _real_import = builtins.eval, builtins.exec, builtins.__import__


def _no_new_modules(name, *a, **k):
    # DEC-08: "no imports are followed". Stated as "nothing new is *loaded*", because the
    # stdlib imports lazily inside its own functions — `ast.walk` does `from collections import
    # deque` on every call — and a module already in `sys.modules` is a dict lookup, not a
    # module being brought in on a node's behalf.
    if name not in sys.modules:
        attempts.append("__import__"); print("WA07-TRIP", file=sys.stderr)
        raise AssertionError("__import__ loaded " + name + ", which was not already imported")
    return _real_import(name, *a, **k)


builtins.eval = _record("eval")
builtins.exec = _record("exec")
builtins.compile = _only_parses
builtins.__import__ = _no_new_modules
inspect.getsource = _record("inspect.getsource")
inspect.getsourcelines = _record("inspect.getsourcelines")
inspect.findsource = _record("inspect.findsource")
linecache.getlines = _record("linecache.getlines")
linecache.updatecache = _record("linecache.updatecache")
typing.get_type_hints = _record("typing.get_type_hints")

schema = StateSchema.of(*si.FULL_STATE_SCHEMAS)
inferred = 0
for name, fixture in si.INFERENCE_FIXTURES.items():
    result = infer_node(fixture.node, state_schema=schema if fixture.schema else None)
    assert result.source.rule.value == fixture.source, name
    assert (result.default.value if result.default else None) == fixture.default, name
    inferred += 1

future = infer_node(sif.annotated_under_future_import, state_schema=StateSchema.of(*sif.FULL_STATE_SCHEMAS))
assert future.contract.output == ("plan",)

assert inferred == %d, inferred
assert parses, "nothing was parsed, so the wrapper proved nothing"
# Restored from the saved originals, not from the bare names — which by now resolve through
# `builtins` to the armed closures, so `builtins.eval = eval` would rearm rather than restore.
builtins.eval, builtins.exec = _real_eval, _real_exec
builtins.compile, builtins.__import__ = _real_compile, _real_import
"""

#: Probes for the evaluators and the source-lookup routes, which are armed in Phase B only —
#: so each control re-arms the one it is testing rather than running after the child, the way
#: the network probes do. Kept beside the tripwire so the two cannot drift apart.
_PROBES: Final[tuple[tuple[str, str, str], ...]] = (
    ("eval", "builtins.eval = _record('eval'); builtins.eval('1')\n", "eval was reached"),
    ("exec", "builtins.exec = _record('exec'); builtins.exec('pass')\n", "exec was reached"),
    (
        "compile",
        "builtins.compile = _only_parses; builtins.compile('1', '<probe>', 'eval')\n",
        "compile() was called for something other than a parse",
    ),
    (
        "inspect.getsource",
        "inspect.getsource(si.reads_literal_subscripts)\n",
        "inspect.getsource was reached",
    ),
    (
        "inspect.getsourcelines",
        "inspect.getsourcelines(si.reads_literal_subscripts)\n",
        "inspect.getsourcelines was reached",
    ),
    (
        "inspect.findsource",
        "inspect.findsource(si.reads_literal_subscripts)\n",
        "inspect.findsource was reached",
    ),
    ("linecache.getlines", "linecache.getlines('x')\n", "linecache.getlines was reached"),
    (
        "linecache.updatecache",
        "linecache.updatecache('x')\n",
        "linecache.updatecache was reached",
    ),
    (
        "typing.get_type_hints",
        "typing.get_type_hints(si.reads_a_typed_dict_projection)\n",
        "typing.get_type_hints was reached",
    ),
    (
        "__import__",
        "builtins.__import__ = _no_new_modules; __import__('this')\n",
        "__import__ loaded this",
    ),
)

_REPORT = "print(attempts)\n"


def _run_guarded(probe: str = "") -> subprocess.CompletedProcess[str]:
    body = _TRIPWIRE % len(si.INFERENCE_FIXTURES)
    return subprocess.run(
        [sys.executable, "-c", body + probe + _REPORT],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_inference_invokes_nothing_and_evaluates_nothing() -> None:
    """The WA-07 claim for the §4 path, in a fresh interpreter.

    Four things at once. Every fixture in the table is inferred — bodies whose every node
    function, ``Command`` and state access raises if it is touched — and nothing is called,
    resolved or connected to. ``eval`` and ``exec`` raise for the whole run and ``compile``
    accepts nothing but a parse, so "shallow inference reads an AST and evaluates nothing" is
    armed rather than argued. The two library routes that would have reached user code —
    ``inspect``'s source lookup, which goes through ``linecache``'s ``__loader__.get_source()``
    fallback, and ``typing.get_type_hints``, which would ``eval`` a string annotation — raise
    from the first inference to the last. And importing the engine reaches neither langgraph
    nor ``gebra.extraction``, asserted in the child rather than reviewed, which is what keeps
    the annotation surface usable without the substrate.

    The child asserts its own counts from the fixture table, so a pass that stopped reaching
    the fixtures would fail here rather than prove nothing.
    """
    result = _run_guarded()

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "[]", result.stdout
    assert "WA07-TRIP" not in result.stderr, result.stderr


@pytest.mark.parametrize(
    ("probe", "expected"),
    [
        ("socket.socket()\n", "a socket was created"),
        ("socket.getaddrinfo('example.invalid', 80)\n", "getaddrinfo was reached"),
        ("socket.gethostbyname('example.invalid')\n", "gethostbyname was reached"),
        ("socket.create_connection(('example.invalid', 80))\n", "create_connection was reached"),
    ],
    ids=["socket", "getaddrinfo", "gethostbyname", "create_connection"],
)
def test_each_network_raiser_is_armed(probe: str, expected: str) -> None:
    """A tripwire nobody trips proves nothing, so every raiser gets its own control.

    These run *after* the child's own assertions, so each shows the raiser was live at the end
    of the very run that made the claim.
    """
    result = _run_guarded(probe)

    assert result.returncode != 0
    assert expected in result.stderr


@pytest.mark.parametrize(("name", "probe", "expected"), _PROBES, ids=[p[0] for p in _PROBES])
def test_each_evaluation_raiser_is_armed(name: str, probe: str, expected: str) -> None:
    """The same control for the six raisers whose arming window is Phase B.

    They cannot simply run after the child the way the network probes do: Phase B restores
    ``eval``/``exec``/``compile`` at its end so that the interpreter can shut down. Each probe
    therefore re-arms the one it is testing and calls it, which shows both that the raiser is a
    real one and that the child's prologue installs the same object.
    """
    result = _run_guarded(probe)

    assert result.returncode != 0
    assert expected in result.stderr


def test_the_tripwire_covers_the_fixtures_this_path_handles() -> None:
    """A floor on the tripwire's reach, so the claim cannot shrink silently.

    The child is quantified over the fixture table; this is what stops the table from being
    quietly emptied, and names the shapes the WA-07 claim is *about* — a body with a literal
    return, one with a ``Command``, one whose annotations are strings, and one with no
    readable body at all.
    """
    assert len(si.INFERENCE_FIXTURES) >= 50
    covered = set(si.INFERENCE_FIXTURES)
    assert {
        "output_literal_dict",
        "output_command_update",
        "input_annotation_string",
        "shape_callable_object",
        "shape_lambda",
    } <= covered


def test_every_fixture_body_is_armed() -> None:
    """The other half of "nothing was invoked": every sentinel is live.

    A table of callables that quietly stopped raising would make the tripwire vacuous. Checked
    **statically**, by reading each body's own AST for the call to :func:`_arm` — because
    calling them to find out would be the suite executing a workflow node, which is the thing
    WA-07 forbids outright. That :func:`_arm` itself raises is the one call this test makes,
    and it is the test harness's own helper rather than anybody's node.
    """
    with pytest.raises(si.InferenceSentinelError):
        si._arm("probe")

    unarmed = []
    for name, fixture in si.INFERENCE_FIXTURES.items():
        source = read_node_source(fixture.node)
        if source.definition is None:
            continue  # the two fixtures whose whole point is that they have no body
        if not _arms_first(source.definition):
            unarmed.append(name)

    assert unarmed == []


def _arms_first(definition: Any) -> bool:
    """Whether ``definition``'s body *begins* with the ``_arm`` call.

    The strong form of "is armed", and the one the fixture module claims ("the first thing
    every body reaches"): an ``_arm`` found anywhere would also be satisfied by one inside a
    nested ``def`` that never runs. A ``lambda`` has a single expression, so its arming is
    wherever that expression puts it.
    """
    if isinstance(definition, ast.Lambda):
        return any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "_arm"
            for node in ast.walk(definition.body)
        )
    body = definition.body
    docstring = body[0]
    if (
        isinstance(docstring, ast.Expr)
        and isinstance(docstring.value, ast.Constant)
        and isinstance(docstring.value.value, str)
    ):
        body = body[1:]  # every fixture states what it is a fixture *of* before arming
    first = body[0]
    return (
        isinstance(first, ast.Expr)
        and isinstance(first.value, ast.Call)
        and isinstance(first.value.func, ast.Name)
        and first.value.func.id == "_arm"
    )


def test_the_engine_imports_neither_the_substrate_nor_a_source_lookup() -> None:
    """The import list ANNOTATION §4 and WA-07 both depend on, read off the module's source.

    Two claims in one, and the second is the half the guarded child cannot make: patching
    ``inspect.getsource`` catches a call through the module, but a
    ``from inspect import getsource`` would hold the original and walk straight past it. So
    the names are checked where they would have to appear — in the imports — which is also
    where an import added inside a function body would show up.
    """
    import gebra.annotations.inference as engine

    imported = sorted(_module_imports(engine.__file__))

    assert not [name for name in imported if name.startswith(("langgraph", "langchain"))]
    assert "inspect" not in imported
    assert "linecache" not in imported
    assert "typing.get_type_hints" not in imported
    assert "gebra.annotations.contract" in imported


def _module_imports(path: str | None) -> Iterable[str]:
    """What the file at ``path`` imports: each module name, and each ``module.name`` it takes.

    Both forms, because the hazard has both spellings: ``import inspect`` then
    ``inspect.getsource(...)``, and ``from typing import get_type_hints``. A module patched in
    a guarded child catches only the first.
    """
    tree = ast.parse(Path(path or "").read_bytes())
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            yield from (alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            yield node.module
            yield from (f"{node.module}.{alias.name}" for alias in node.names)
