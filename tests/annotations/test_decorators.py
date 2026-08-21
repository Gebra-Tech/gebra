"""The §1 decorator surface: identity, the four consistency rules, the closed nine slots.

Three claims, and the file is organized as three sections plus the WA-07 tripwire:

1. **Decoration returns the object it was given, and touches nothing else.** Every target in
   ``tests/sample_workflows/sentinel_contracts.py`` raises if it is called, so "never
   invokes" is checked rather than reviewed; identity is asserted with ``is``.
2. **Each of the four §1 consistency rules raises ``GebraContractError``, at import time.**
   The per-rule tests raise in process; ``test_each_consistency_rule_raises_at_import_time``
   makes the *timing* half real by importing four modules in a fresh interpreter.
3. **The annotatable-slot set is closed at nine.** Reachability (all nine are declarable) and
   closure (nothing else is) are asserted separately, because either one alone would pass
   with a surface that was wrong in the other direction.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

import gebra
from gebra.annotations import (
    ANNOTATION_SLOTS,
    CONTRACT_ATTRIBUTE,
    EFFECT_TAGS,
    ContractErrorReason,
    GebraContractError,
    NodeContract,
    read_contract,
)
from gebra.ir.models import Compensation, DeterministicSpec, IdempotentKey, Node, Variant
from tests.sample_workflows import sentinel_contracts as sc
from tests.sample_workflows.sentinel_contracts import ContractSentinelError, armed

REPO_ROOT = Path(__file__).resolve().parents[2]

#: ``gebra``, with its types erased. The refusal tables below hand the decorators values
#: of deliberately the wrong kind, and a type checker is right to reject every one of them
#: — that is the declared surface doing its job. What those tests are about is the *runtime*
#: refusal, which is the half a type checker cannot make: nothing stops a caller with no
#: type checking, or a value that is only wrong at run time. Every other call site in this
#: file goes through the typed surface.
untyped: Any = gebra


# ── 1. Identity: decoration never wraps and never invokes ────────────────────────────────


@pytest.mark.parametrize("name", sorted(sc.ARMED_DECORATIONS))
def test_every_decoration_returns_the_very_same_object(name: str) -> None:
    """§1: decorators "return the function unchanged — they never wrap, reorder, or invoke it".

    ``is``, not ``==``: §6 requires annotations to survive ``.compile()``, and they do so
    because LangGraph re-wraps *this* object rather than a wrapper gebra inserted. An equal
    copy would satisfy every other assertion in this file and break that.
    """
    target = armed(name)

    decorated = sc.ARMED_DECORATIONS[name](target)

    assert decorated is target
    assert read_contract(decorated) is not None


@pytest.mark.parametrize("name", sorted(sc.ARMED_DECORATIONS))
def test_decoration_leaves_every_other_attribute_alone(name: str) -> None:
    """The attached attribute is the only difference decoration makes.

    ``__wrapped__`` is called out on its own because it is the marker §6's chain walk follows:
    if decoration ever set one, extraction would start walking a chain that does not exist.
    """
    target = armed(name)
    before = {
        "code": target.__code__,
        "name": target.__name__,
        "qualname": target.__qualname__,
        "module": target.__module__,
        "doc": target.__doc__,
        "defaults": target.__defaults__,
        "keys": set(vars(target)),
    }

    sc.ARMED_DECORATIONS[name](target)

    assert target.__code__ is before["code"]
    assert target.__name__ == before["name"]
    assert target.__qualname__ == before["qualname"]
    assert target.__module__ == before["module"]
    assert target.__doc__ == before["doc"]
    assert target.__defaults__ is before["defaults"]
    assert set(vars(target)) - before["keys"] == {CONTRACT_ATTRIBUTE}  # type: ignore[operator]
    assert not hasattr(target, "__wrapped__")


@pytest.mark.parametrize("name", sorted(sc.ARMED_DECORATIONS))
def test_decoration_invokes_nothing(name: str) -> None:
    """Every target raises if called, so a decorator that invoked one would fail here.

    The armed body is checked *after* decoration too: a pass that came from a sentinel which
    had quietly stopped raising would prove nothing, and this is what keeps the fixture live.
    """
    target = armed(name)

    sc.ARMED_DECORATIONS[name](target)

    with pytest.raises(ContractSentinelError):
        target({"query": "unused"})


def test_a_stack_is_still_one_object_carrying_one_contract() -> None:
    """Five decorators, one object, one contract — the shape §1's at-most-once rule governs."""
    target = armed("book_flight")

    decorated = sc.ARMED_DECORATIONS["stack"](target)

    assert decorated is target
    carried = read_contract(target)
    assert carried == NodeContract(
        input=("itinerary", "budget"),
        output=("booking_ref",),
        effect=("network", "billable", "irreversible"),
        idempotent=IdempotentKey(key="booking_ref"),
        deterministic=DeterministicSpec(seed=7),
        compensation=Compensation(hook="cancel_booking"),
    )


def test_the_carrier_is_the_attribute_the_spec_names() -> None:
    """§1 and §6 both name ``__gebra_contract__``; nothing else is the carrier."""
    target = gebra.pure(armed("plan"))

    assert CONTRACT_ATTRIBUTE == "__gebra_contract__"
    assert target.__gebra_contract__ is read_contract(target)  # type: ignore[attr-defined]


def test_an_attached_contract_cannot_be_changed_after_the_fact() -> None:
    """Frozen, and ``model_construct`` banned: a contract is digested through §3 resolution.

    A slot that could be rebound after attachment would move a ``graph_version`` with no
    re-decoration in sight. What freezing does *not* cover is mutation inside a slot's value;
    that residual is asserted, not assumed, in
    ``test_an_args_schema_is_copied_out_of_the_authors_object_with_its_arrays_frozen``.
    """
    carried = read_contract(gebra.pure(armed("plan")))
    assert carried is not None

    with pytest.raises(ValidationError):
        carried.pure = False
    with pytest.raises(NotImplementedError, match="model_construct"):
        NodeContract.model_construct(pure=True)


def test_a_target_that_cannot_carry_the_attribute_is_pointed_at_the_sidecar() -> None:
    """§6: "the **sidecar is the designated fallback**" — so the error says so."""
    with pytest.raises(GebraContractError) as caught:
        gebra.pure(sc.SlottedNode())

    assert caught.value.reason is ContractErrorReason.ATTACHMENT_IMPOSSIBLE
    assert "gebra.toml sidecar" in str(caught.value)


def test_a_foreign_carrier_is_not_overwritten() -> None:
    """``__gebra_contract__`` is gebra's attribute; something else's value is not clobbered."""
    target = armed("foreign")
    target.__gebra_contract__ = {"pure": True}  # type: ignore[attr-defined]

    with pytest.raises(GebraContractError) as caught:
        gebra.pure(target)

    assert caught.value.reason is ContractErrorReason.SLOT_VALUE_INVALID
    assert target.__gebra_contract__ == {"pure": True}  # type: ignore[attr-defined]


def test_an_inherited_contract_is_not_read_as_the_subclass_own() -> None:
    """``read_contract`` reads the object's own namespace, not its MRO.

    A subclass of a decorated class has declared nothing; reporting its base's contract would
    make a second decoration on the subclass look like a §1 duplicate.
    """

    @gebra.pure
    class Base:
        def __call__(self, state: dict[str, Any]) -> dict[str, Any]:
            raise ContractSentinelError("Base was invoked")

    class Derived(Base):
        pass

    assert read_contract(Base) is not None
    assert read_contract(Derived) is None
    assert read_contract(object()) is None


# ── 2. The four §1 consistency rules ─────────────────────────────────────────────────────


#: One two-decorator stack per annotatable slot, each setting that slot twice. Written per
#: slot rather than once, because §1's rule is quantified over slots and a surface that
#: leaked one of them would otherwise pass.
_DUPLICATE_STACKS: dict[str, Any] = {
    "input": (gebra.contract(reads=["a"]), gebra.contract(reads=["b"])),
    "output": (gebra.contract(writes=["a"]), gebra.contract(writes=["b"])),
    "effect": (gebra.effect("network"), gebra.contract(effects=["write"])),
    "pure": (gebra.pure, gebra.contract(pure=False)),
    "idempotent": (gebra.idempotent, gebra.contract(idempotent={"key": "a"})),
    "deterministic": (gebra.deterministic, gebra.contract(deterministic={"seed": 1})),
    "args_schema": (
        gebra.contract(args_schema={"type": "object"}),
        gebra.contract(args_schema={"type": "string"}),
    ),
    "variant": (gebra.variant(key="a", measure="len"), gebra.variant(key="b", measure="len")),
    "compensation": (gebra.compensation(hook="a"), gebra.compensation(hook="b")),
}


@pytest.mark.parametrize("slot", ANNOTATION_SLOTS)
def test_rule_1_a_slot_is_settable_at_most_once_per_stack(slot: str) -> None:
    """§1: "Each slot is settable **at most once** across a decorator stack"."""
    inner, outer = _DUPLICATE_STACKS[slot]
    target = armed(f"twice_{slot}")

    with pytest.raises(GebraContractError) as caught:
        outer(inner(target))

    assert caught.value.reason is ContractErrorReason.DUPLICATE_SLOT
    assert caught.value.slot == slot


def test_rule_1_holds_for_identical_values_too() -> None:
    """§1: "regardless of value, identical duplicates included".

    This is where §1 is deliberately stricter than §3's cross-surface rule, in which identical
    values are not a conflict at all — "a single author's stack has no drift to excuse".
    """
    target = armed("identical")

    with pytest.raises(GebraContractError) as caught:
        gebra.contract(reads=["itinerary"])(gebra.contract(reads=["itinerary"])(target))

    assert caught.value.reason is ContractErrorReason.DUPLICATE_SLOT
    assert "identical values included" in str(caught.value)


def test_rule_1_counts_the_shorthand_and_the_long_form_as_one_slot() -> None:
    """``@gebra.effect(...)`` and ``contract(effects=...)`` are the same slot, not two."""
    with pytest.raises(GebraContractError) as caught:
        gebra.contract(effects=["write"])(gebra.effect("network")(armed("both")))

    assert caught.value.slot == "effect"


@pytest.mark.parametrize(
    "decorate",
    [
        pytest.param(lambda fn: gebra.contract(pure=True, effects=["network"])(fn), id="one-call"),
        pytest.param(lambda fn: gebra.effect("network")(gebra.pure(fn)), id="pure-then-effect"),
        pytest.param(lambda fn: gebra.pure(gebra.effect("network")(fn)), id="effect-then-pure"),
    ],
)
def test_rule_2_pure_and_effects_are_mutually_exclusive(decorate: Any) -> None:
    """§1/decision D-011, checked over the merged stack so decorator order cannot dodge it."""
    with pytest.raises(GebraContractError) as caught:
        decorate(armed("impure"))

    assert caught.value.reason is ContractErrorReason.PURE_EFFECT_EXCLUSIVE
    assert "D-011" in str(caught.value)


def test_rule_2_reads_pure_true_and_a_non_empty_effects_exactly() -> None:
    """The rule names ``pure=True`` and a *non-empty* ``effects``; neither half is widened.

    ``pure=False`` with effects is an ordinary declaration, and an empty ``effects`` alongside
    ``pure=True`` declares no effect at all — refusing either would be this build inventing an
    invariant the spec does not state.
    """
    assert read_contract(gebra.contract(pure=False, effects=["network"])(armed("a"))) is not None
    assert read_contract(gebra.contract(pure=True, effects=[])(armed("b"))) is not None


@pytest.mark.parametrize("tag", sorted(EFFECT_TAGS))
def test_rule_3_every_tag_in_the_closed_vocabulary_is_accepted(tag: str) -> None:
    """The decision D-011 five, each usable — the positive half of the closed-set claim."""
    carried = read_contract(gebra.effect(tag)(armed(f"tag_{tag}")))

    assert carried is not None
    assert carried.effect == (tag,)


@pytest.mark.parametrize("tag", ["teleport", "Network", "network ", "", "read", "writes"])
def test_rule_3_an_unknown_tag_is_an_error(tag: str) -> None:
    """§1: "an unknown tag is an error" — including the near-misses, which is the point."""
    with pytest.raises(GebraContractError) as caught:
        gebra.effect(tag)(armed("tagged"))

    assert caught.value.reason is ContractErrorReason.UNKNOWN_EFFECT_TAG
    assert caught.value.slot == "effect"
    assert "D-011" in str(caught.value)


def test_rule_3_the_vocabulary_is_exactly_the_five_the_decision_names() -> None:
    """Written out rather than imported from the code, so the comparison is against the spec."""
    assert set(EFFECT_TAGS) == {"network", "write", "external", "irreversible", "billable"}


@pytest.mark.parametrize(
    "decorate",
    [
        pytest.param(lambda fn: gebra.deterministic(temperature=0.0)(fn), id="shorthand"),
        pytest.param(lambda fn: gebra.contract(deterministic={"temperature": 0.0})(fn), id="dict"),
        pytest.param(lambda fn: gebra.contract(deterministic={})(fn), id="empty-object"),
    ],
)
def test_rule_4_the_deterministic_object_form_requires_seed(decorate: Any) -> None:
    """§1 names the case: "``@gebra.deterministic(temperature=0.0)`` without ``seed=`` raises"."""
    with pytest.raises(GebraContractError) as caught:
        decorate(armed("replayable"))

    assert caught.value.reason is ContractErrorReason.DETERMINISTIC_SEED_REQUIRED
    assert caught.value.slot == "deterministic"


def test_rule_4_leaves_the_other_two_deterministic_forms_alone() -> None:
    """``True``/``False`` and a seeded object are the forms the ledger §3 shape admits."""
    assert read_contract(gebra.deterministic(armed("bare"))) == NodeContract(deterministic=True)
    assert read_contract(gebra.contract(deterministic=False)(armed("no"))) == NodeContract(
        deterministic=False
    )
    assert read_contract(gebra.deterministic(seed=42, temperature=0.5)(armed("s"))) == NodeContract(
        deterministic=DeterministicSpec(seed=42, temperature=0.5)
    )


@pytest.mark.parametrize(
    "decorate",
    [
        pytest.param(
            lambda fn: gebra.contract(effects=["irreversible"], idempotent=True)(fn),
            id="irreversible-and-idempotent",
        ),
        pytest.param(
            lambda fn: gebra.contract(idempotent={"key": "not_an_input"}, reads=["other"])(fn),
            id="idempotency-key-outside-input",
        ),
    ],
)
def test_the_two_d012_checks_are_not_decoration_time(decorate: Any) -> None:
    """§1 puts both at extraction, warning-grade — so neither may raise here.

    "Both checks need the *resolved* contract, so they run at extraction, not decoration —
    warning-grade, never an error, per the extraction-stays-total posture". Pinned as a test
    because the two rules sit in the same bullet list as the four this module enforces, and
    the easy mistake is to implement all six in one place: that would turn a warning into an
    import failure, and would judge a decorator stack against an ``input`` set that does not
    exist until the §3 resolution has run.
    """
    target = armed("resolved_later")

    assert decorate(target) is target
    assert read_contract(target) is not None


#: One agent module per §1 consistency rule, each violating exactly that rule at module scope
#: — the shape a real codebase has, where the decorator runs because the module was imported.
_OFFENDING_MODULES: dict[str, str] = {
    "duplicate-slot": "import gebra\n\n\n@gebra.pure\n@gebra.pure\ndef node(state): ...\n",
    "pure-effect-exclusive": (
        'import gebra\n\n\n@gebra.contract(pure=True, effects=["network"])\ndef node(state): ...\n'
    ),
    "unknown-effect-tag": 'import gebra\n\n\n@gebra.effect("teleport")\ndef node(state): ...\n',
    "deterministic-seed-required": (
        "import gebra\n\n\n@gebra.deterministic(temperature=0.0)\ndef node(state): ...\n"
    ),
}


@pytest.mark.parametrize("rule", sorted(_OFFENDING_MODULES))
def test_each_consistency_rule_raises_at_import_time(rule: str, tmp_path: Path) -> None:
    """The timing half of §1: "at import time — cheap, early, never at extraction".

    One module per rule, written to disk and reached by a real ``import`` statement in a fresh
    interpreter. An in-process ``pytest.raises`` shows only that a *call* raises; this shows
    that importing the author's own module is what surfaces the violation — which is the
    property §1 is trading for when it puts these four rules here rather than in the
    resolved-contract pass, and the reason it can afford to be strict about them.

    The traceback is asserted to name the offending module, because the value of raising early
    is that the error points at the decoration site rather than at somewhere downstream.
    """
    module = f"agent_{rule.replace('-', '_')}"
    (tmp_path / f"{module}.py").write_text(_OFFENDING_MODULES[rule], encoding="utf-8")
    child = (
        "import traceback\n"
        "from gebra.annotations import GebraContractError\n"
        "try:\n"
        f"    import {module}\n"
        "except GebraContractError as error:\n"
        "    traceback.print_exc()\n"
        "    print(error.reason.value)\n"
        "else:\n"
        "    raise SystemExit('importing the module raised nothing')\n"
    )

    result = subprocess.run(
        [sys.executable, "-c", child],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines()[-1] == rule
    assert f"{module}.py" in result.stderr


# ── 3. The nine-slot closed surface ──────────────────────────────────────────────────────


def test_the_carrier_carries_exactly_the_nine_annotatable_slots() -> None:
    """§1: "Exactly nine node-annotation slots (ledger §3) are settable through this spec's
    surfaces". The set is written out here rather than imported, so this compares the code
    against the spec instead of against itself."""
    assert set(NodeContract.model_fields) == {
        "input",
        "output",
        "effect",
        "pure",
        "idempotent",
        "deterministic",
        "args_schema",
        "variant",
        "compensation",
    }
    assert set(ANNOTATION_SLOTS) == set(NodeContract.model_fields)
    assert len(ANNOTATION_SLOTS) == 9


def test_the_slot_set_has_one_definition() -> None:
    """The warnings taxonomy quantifies its §5 lookup over this set, so it is the same object.

    Two copies of a closed set that reaches ``graph_version`` through the §3 resolution would
    be a drift hazard in exactly the place that is hardest to notice.
    """
    from gebra.extraction import ANNOTATION_SLOTS as taxonomy_slots

    assert taxonomy_slots is ANNOTATION_SLOTS


def test_all_nine_slots_are_reachable_through_the_decorators() -> None:
    """Closure would be trivially satisfiable by a surface that reached fewer than nine.

    ``pure=False`` rather than ``True``: D-011 exclusivity makes "pure and effectful"
    unauthorable, so ``False`` is the only way one stack declares both slots — which is the
    rule working, not a gap in it.
    """
    target = armed("everything")

    sc.ARMED_DECORATIONS["all-nine"](target)

    carried = read_contract(target)
    assert carried is not None
    assert carried.declared_slots() == ANNOTATION_SLOTS
    assert carried.variant == Variant(key="remaining", measure="len")


@pytest.mark.parametrize(
    "slot",
    [
        "retry_policy",
        "prompt_digest",
        "config_digest",
        "interrupts",
        "checkpointer",
        "source",
        "map",
    ],
)
def test_a_slot_out_of_annotation_reach_is_refused_with_its_reason(slot: str) -> None:
    """§1: every other ledger slot is "extracted or computed, never annotated"."""
    with pytest.raises(GebraContractError) as caught:
        untyped.contract(**{slot: "anything"})(armed("reaching"))

    assert caught.value.reason is ContractErrorReason.UNKNOWN_SLOT
    assert caught.value.slot == slot
    assert "closed at nine" in str(caught.value)


@pytest.mark.parametrize(
    ("slot", "decorator"), [("variant", "@gebra.variant"), ("compensation", "@gebra.compensation")]
)
def test_an_annotatable_slot_without_a_contract_route_points_at_its_decorator(
    slot: str, decorator: str
) -> None:
    """``variant`` and ``compensation`` are two of the nine, but not ``contract()`` keywords."""
    with pytest.raises(GebraContractError) as caught:
        untyped.contract(**{slot: {}})(armed("misrouted"))

    assert caught.value.reason is ContractErrorReason.UNKNOWN_SLOT
    assert decorator in str(caught.value)


@pytest.mark.parametrize(
    ("typo", "meant"),
    [
        ("read", "reads"),
        ("write", "writes"),
        ("effcts", "effects"),
        ("args_schemas", "args_schema"),
    ],
)
def test_a_near_miss_keyword_is_refused_with_the_keyword_that_was_meant(
    typo: str, meant: str
) -> None:
    """An ordinary typo gets the nearest keyword back.

    The IR spellings — ``input``/``output``/``effect`` — are a different mistake and take the
    branch above this one, which names the keyword outright instead of guessing at it.
    """
    with pytest.raises(GebraContractError) as caught:
        untyped.contract(**{typo: ["x"]})(armed("typo"))

    assert caught.value.reason is ContractErrorReason.UNKNOWN_SLOT
    assert f"Did you mean {meant!r}?" in str(caught.value)


@pytest.mark.parametrize(
    ("spelling", "keyword"), [("input", "reads"), ("output", "writes"), ("effect", "effects")]
)
def test_an_ir_spelling_is_refused_with_the_keyword_that_carries_it(
    spelling: str, keyword: str
) -> None:
    """Three of the nine have a keyword spelled differently from the slot they set.

    Telling someone who wrote ``input=[...]`` that it is "not one of the nine annotatable
    slots" would be false — it is one of the nine, under the name the IR uses. The answer they
    need is the keyword.
    """
    with pytest.raises(GebraContractError) as caught:
        untyped.contract(**{spelling: ["x"]})(armed("ir_spelling"))

    assert caught.value.reason is ContractErrorReason.UNKNOWN_SLOT
    assert f"Write {keyword}=." in str(caught.value)


def test_the_carrier_refuses_a_member_outside_the_nine() -> None:
    """Closure is structural, not a convention the decorators happen to keep."""
    with pytest.raises(ValidationError):
        NodeContract(retry_policy={"max_attempts": 3})  # type: ignore[call-arg]


# ── Slot values: what is declared, and what is refused ───────────────────────────────────


def test_set_means_not_none() -> None:
    """§3's rule, which is what makes ``declared_slots()`` derivable rather than bookkept.

    An explicit negative "occupies its slot and blocks lower-tier fill exactly like a positive
    value"; only absence leaves a slot open. An empty ``reads`` is the same kind of statement:
    "this node reads nothing", not "unstated".
    """
    negatives = read_contract(sc.ARMED_DECORATIONS["contract-negatives"](armed("negatives")))
    empties = read_contract(sc.ARMED_DECORATIONS["contract-empty-sets"](armed("empties")))

    assert negatives is not None and empties is not None
    assert negatives.declared_slots() == ("pure", "idempotent", "deterministic")
    assert (negatives.pure, negatives.idempotent, negatives.deterministic) == (False, False, False)
    assert empties.declared_slots() == ("input", "output", "effect")
    assert (empties.input, empties.output, empties.effect) == ((), (), ())
    assert NodeContract().declared_slots() == ()


def test_state_keys_and_tags_keep_the_order_they_were_authored_in() -> None:
    """Nothing here sorts or de-duplicates: canonical serialization is where IR order is set."""
    carried = read_contract(
        gebra.contract(reads=["z", "a", "z"], effects=["write", "network", "write"])(armed("order"))
    )

    assert carried is not None
    assert carried.input == ("z", "a", "z")
    assert carried.effect == ("write", "network", "write")


@pytest.mark.parametrize("argument", ["reads", "writes", "effects"])
def test_a_bare_string_is_refused_rather_than_read_as_its_characters(argument: str) -> None:
    """``str`` satisfies ``Iterable[str]``, so nothing but this check would catch it.

    Reading ``reads="budget"`` as six one-character state keys would reach canonical bytes,
    and from there ``graph_version`` — a silent wrong answer rather than a loud one.
    """
    with pytest.raises(GebraContractError) as caught:
        untyped.contract(**{argument: "budget"})(armed("bare"))

    assert caught.value.reason is ContractErrorReason.SLOT_VALUE_INVALID
    assert "per character" in str(caught.value)


@pytest.mark.parametrize(
    "decorate",
    [
        pytest.param(lambda fn: untyped.contract(reads=[1])(fn), id="non-string-state-key"),
        pytest.param(lambda fn: untyped.contract(reads=42)(fn), id="not-iterable"),
        pytest.param(lambda fn: untyped.contract(pure=1)(fn), id="int-for-bool"),
        pytest.param(lambda fn: untyped.contract(idempotent="yes")(fn), id="string-for-idempotent"),
        pytest.param(
            lambda fn: untyped.contract(idempotent={"k": "a"})(fn), id="wrong-member-name"
        ),
        pytest.param(lambda fn: untyped.contract(idempotent={"key": 1})(fn), id="non-string-key"),
        pytest.param(
            lambda fn: untyped.contract(deterministic={"seed": True})(fn), id="bool-for-seed"
        ),
        pytest.param(
            lambda fn: untyped.contract(deterministic={"seed": 1, "top_p": 0.9})(fn),
            id="member-outside-the-shape",
        ),
        pytest.param(
            lambda fn: untyped.deterministic(seed=1, temperature=True)(fn), id="bool-temp"
        ),
        pytest.param(
            lambda fn: untyped.contract(args_schema=["not", "an", "object"])(fn), id="list"
        ),
        pytest.param(
            lambda fn: untyped.contract(args_schema={"x": {1, 2}})(fn), id="set-in-schema"
        ),
        pytest.param(
            lambda fn: gebra.contract(args_schema={"x": float("nan")})(fn), id="nan-in-schema"
        ),
        pytest.param(lambda fn: untyped.variant(key="a", measure=7)(fn), id="non-string-measure"),
        pytest.param(lambda fn: untyped.compensation(hook=None)(fn), id="none-hook"),
    ],
)
def test_a_value_that_is_not_of_its_slots_kind_is_refused(decorate: Any) -> None:
    """Refused, never coerced: every one of these would otherwise reach the digest as data."""
    with pytest.raises(GebraContractError) as caught:
        decorate(armed("wrong_kind"))

    assert caught.value.reason is ContractErrorReason.SLOT_VALUE_INVALID


def test_an_integer_temperature_is_read_as_the_number_it_is() -> None:
    """The ledger shape is ``temperature?: number`` and an integer is one.

    The model types the member ``float`` under strict validation, so ``temperature=0`` would
    otherwise be an error at the one place a reader would not expect one.
    """
    carried = read_contract(gebra.deterministic(seed=1, temperature=0)(armed("int_temp")))

    assert carried == NodeContract(deterministic=DeterministicSpec(seed=1, temperature=0.0))


def test_any_iterable_of_state_keys_is_accepted() -> None:
    """§1 types the argument ``Iterable[str]``, so a set or a generator is as good as a list.

    Only ``str``/``bytes`` is singled out, and only because iterating one silently succeeds
    with the wrong answer. Everything else is materialized as authored — for a set that means
    the set's own iteration order, which the author chose by picking an unordered container.
    """
    from_set = read_contract(gebra.contract(reads={"solo"})(armed("set")))
    from_generator = read_contract(gebra.contract(writes=(k for k in ("a", "b")))(armed("gen")))

    assert from_set is not None and from_generator is not None
    assert from_set.input == ("solo",)
    assert from_generator.output == ("a", "b")


def test_an_args_schema_carries_every_json_scalar() -> None:
    """JSON Schema uses all five; each is stored as itself, and none is coerced.

    ``exclusiveMinimum: 0`` staying an ``int`` rather than becoming ``0.0`` is fidelity, not
    digest arithmetic: IR-SPEC §6.2 carries the schema interior *verbatim*, and RFC 8785
    formats ``0`` and ``0.0`` identically wherever both are representable — so the reason not
    to coerce is that the author wrote an integer, and the schema is theirs.
    """
    schema: dict[str, Any] = {
        "type": "number",
        "default": None,
        "deprecated": False,
        "exclusiveMinimum": 0,
        "multipleOf": 0.5,
        "examples": [{"nested": True}],
    }

    carried = read_contract(gebra.contract(args_schema=schema)(armed("scalars")))

    assert carried is not None
    assert carried.args_schema == {
        "type": "number",
        "default": None,
        "deprecated": False,
        "exclusiveMinimum": 0,
        "multipleOf": 0.5,
        "examples": ({"nested": True},),
    }
    assert type(carried.args_schema["exclusiveMinimum"]) is int


def test_an_unknown_keyword_with_no_near_miss_is_still_refused() -> None:
    """The suggestion is a courtesy; the refusal is the rule, and it does not depend on it."""
    with pytest.raises(GebraContractError) as caught:
        untyped.contract(quantum_entanglement=True)(armed("novel"))

    assert caught.value.reason is ContractErrorReason.UNKNOWN_SLOT
    assert "Did you mean" not in str(caught.value)


@pytest.mark.parametrize(
    "decorate",
    [
        pytest.param(lambda fn: untyped.contract(idempotent={})(fn), id="idempotent-empty-object"),
        pytest.param(
            lambda fn: untyped.contract(deterministic="always")(fn), id="deterministic-str"
        ),
    ],
)
def test_an_object_form_missing_its_only_member_is_refused(decorate: Any) -> None:
    """The ledger §3 shapes are ``{key}`` and ``{seed, temperature?}``; neither is optional."""
    with pytest.raises(GebraContractError):
        decorate(armed("shapeless"))


def test_a_self_referential_args_schema_becomes_a_message() -> None:
    """A bound, so a cycle is reported rather than raising ``RecursionError`` from the walk."""
    cycle: dict[str, Any] = {"type": "object"}
    cycle["properties"] = cycle

    with pytest.raises(GebraContractError) as caught:
        gebra.contract(args_schema=cycle)(armed("cyclic"))

    assert caught.value.reason is ContractErrorReason.SLOT_VALUE_INVALID
    assert caught.value.slot == "args_schema"


def test_an_args_schema_is_copied_out_of_the_authors_object_with_its_arrays_frozen() -> None:
    """What the carrier holds, and — stated because ``frozen=True`` is easy to over-read —
    what it does not.

    Holds: a copy, so editing the authored object afterwards does not reach the declared
    contract, and arrays as tuples, so two spellings of one schema are one contract. Does not:
    the schema's *objects* stay ordinary ``dict``s and can be edited in place. A read-only
    proxy could not be canonicalized (``graph_version`` reads foreign content with
    ``isinstance(..., dict)``), so this is the residual that choice leaves, asserted here so
    it stays visible rather than being discovered by whoever relies on the word "frozen".
    """
    schema: dict[str, Any] = {"type": "object", "required": ["q"], "properties": {"q": {}}}

    carried = read_contract(gebra.contract(args_schema=schema)(armed("schema")))

    assert carried is not None
    assert carried.args_schema == {"type": "object", "required": ("q",), "properties": {"q": {}}}
    schema["required"].append("mutated")
    schema["type"] = "mutated"
    assert carried.args_schema == {"type": "object", "required": ("q",), "properties": {"q": {}}}
    # The residual, asserted rather than described.
    carried.args_schema["properties"]["q"]["type"] = "string"
    assert carried.args_schema["properties"] == {"q": {"type": "string"}}


def test_a_list_and_a_tuple_authored_args_schema_digest_alike() -> None:
    """The tuple normalization is digest-neutral only because canonicalization says so.

    Nothing in this package would notice if the two arms of ``_foreign`` drifted apart, and
    the consequence would be that re-spelling one array in a JSON Schema moved a
    ``graph_version``. Pinned across the module boundary, since neither module owns it alone.
    """
    from gebra.ir.canonical import graph_version
    from gebra.ir.models import Annotations, WorkflowIR

    def ir_with(schema: dict[str, Any]) -> WorkflowIR:
        return WorkflowIR(
            ir_version="1.0",
            entry="n",
            finish="n",
            nodes=(Node(id="n", annotations=Annotations(args_schema=schema)),),
            edges=(),
        )

    from_list = ir_with({"enum": ["a", "b"], "nested": {"items": [1, 2]}})
    from_tuple = ir_with({"enum": ("a", "b"), "nested": {"items": (1, 2)}})

    assert graph_version(from_list) == graph_version(from_tuple)


def test_a_hostile_value_is_named_by_type_and_never_rendered() -> None:
    """The EX-02 lesson, at this surface: a rejected value's ``__repr__`` is never called.

    ``HostileValue`` raises from both ``__repr__`` and ``__str__``, so a message built with
    ``{value!r}`` would replace ``GebraContractError`` with the sentinel's own exception —
    which is precisely how the extraction path's ``str(label)`` defect showed itself.
    """
    with pytest.raises(GebraContractError) as caught:
        untyped.contract(reads=sc.HostileValue())(armed("hostile"))

    assert caught.value.reason is ContractErrorReason.SLOT_VALUE_INVALID
    assert "HostileValue" in str(caught.value)


def test_builtin_subclasses_are_read_through_the_builtins_own_accessors() -> None:
    """A ``str``/``dict``/``list`` subclass is legitimate data with hooks gebra does not run.

    Each subclass in this fixture raises from its own ``__str__``/``items``/``__iter__``, so a
    green run says the reads went through ``str.__str__``, ``dict.items`` and
    ``list.__iter__`` — and the stored values are plain built-ins, not the subclasses.
    """
    target = armed("subclassed")

    sc.ARMED_DECORATIONS["hostile-subclass-values"](target)

    carried = read_contract(target)
    assert carried is not None
    assert carried.input == ("itinerary",)
    assert carried.effect == ("network",)
    assert type(carried.effect[0]) is str
    assert carried.idempotent == IdempotentKey(key="booking_ref")
    assert carried.args_schema == {"enum": (1, 2)}


@pytest.mark.parametrize("name", sorted(sc.REFUSED_DECORATIONS))
def test_every_refusal_is_a_contract_error_and_nothing_else(name: str) -> None:
    """One table, one claim: each refusal path raises ``GebraContractError`` and runs no hook.

    A ``ContractSentinelError`` escaping here would mean a refusal rendered a value or called
    a container's own accessor on its way to the message.
    """
    with pytest.raises(GebraContractError):
        sc.REFUSED_DECORATIONS[name]()


def test_the_bare_effect_decorator_says_so() -> None:
    """``@gebra.effect`` without arguments would otherwise read the function itself as a tag."""
    with pytest.raises(GebraContractError) as caught:
        untyped.effect(armed("bare"))

    assert "has no bare form" in str(caught.value)


def test_a_namespace_that_is_a_dict_subclass_is_read_through_the_builtin_accessor() -> None:
    """An instance ``__dict__`` can be *assigned* a ``dict`` subclass, hooks and all.

    ``read_contract`` therefore reads it with ``dict.get`` rather than ``namespace.get``, the
    same discipline the schema and object-shape walks use — otherwise merely asking whether a
    target already carries a contract would run code belonging to the target.
    """
    target = sc.hostile_namespace_target()

    assert gebra.pure(target) is target
    assert read_contract(target) == NodeContract(pure=True)


def test_a_str_subclass_keyword_is_refused_without_running_its_hooks() -> None:
    """CPython admits a ``str`` subclass as a ``**kwargs`` key, and it is the one value that
    never goes through slot normalization — so it is copied into a plain ``str`` first.

    Otherwise the membership tests, the close-match search and the message would each resolve
    through the subclass. The stored ``slot`` is checked to be a plain ``str`` too: it is the
    field a consumer branches on, and its declared type says so.
    """
    with pytest.raises(GebraContractError) as caught:
        untyped.contract(**{sc.HostileStr("retry_policy"): 1})(armed("subclassed_keyword"))

    assert caught.value.reason is ContractErrorReason.UNKNOWN_SLOT
    assert type(caught.value.slot) is str
    assert caught.value.slot == "retry_policy"


def test_an_arbitrary_iterable_is_materialized_and_the_residual_is_real() -> None:
    """The positive control for §1's ``Iterable[str]``: this ``__iter__`` is *meant* to run.

    §1 types the argument as an iterable, and an iterable has to be iterated to be read, so
    the decorator surface cannot claim to execute nothing a caller handed it. It is bounded
    the other way instead — exactly once, at decoration, with nothing re-iterated afterwards.
    """
    source = sc.RecordingIterable("itinerary", "budget")

    carried = read_contract(gebra.contract(reads=source)(armed("iterated")))

    assert carried is not None
    assert carried.input == ("itinerary", "budget")
    assert source.iterations == 1


def test_a_contract_copied_inward_by_functools_wraps_merges() -> None:
    """Recorded behaviour at the §1 ⊗ §6 seam, pinned so it stays visible (WA-03).

    §6 *requires* an intervening user decorator to apply ``functools.wraps``, and
    ``functools.wraps`` copies ``__dict__`` — so a contract attached below the wrapper arrives
    on the wrapper as its own attribute. §1's at-most-once rule then reads it as a decorator
    "below it in this stack": a different slot merges, and the same slot raises.

    §6's own multiple-carriers rule reads the other way — "the first contract-bearing callable
    encountered walking inward from the outermost wrapper wins wholesale … no per-slot merge",
    warning-grade — so the two sections give different answers for the same code, and the
    difference lands inside ``graph_version`` (``pure`` is in hash scope). Which reading
    governs is a spec question and not this build's to settle (WA-03); this test records what
    the code does today so the question survives contact with the next card rather than being
    answered by accident. The resolution belongs to the precedence card, which is where §6's
    walk is implemented.
    """
    import functools

    def user_decorator(fn: Any) -> Any:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            return fn(*args, **kwargs)

        return wrapper

    inner = gebra.pure(armed("inner"))
    wrapper = user_decorator(inner)
    assert read_contract(wrapper) == NodeContract(pure=True)  # `wraps` copied it outward

    gebra.contract(reads=["a"])(wrapper)
    assert read_contract(wrapper) == NodeContract(pure=True, input=("a",))

    with pytest.raises(GebraContractError) as caught:
        gebra.pure(user_decorator(gebra.pure(armed("same_slot"))))
    assert caught.value.reason is ContractErrorReason.DUPLICATE_SLOT


# ── WA-07 — the tripwire for the path this card lands ────────────────────────────────────

#: The guarded child. Substrate imports, sockets, name resolution and connections all raise
#: from the first line — before ``import gebra`` — because the claim this path makes is
#: stronger than the extraction paths' can be: decoration reaches no substrate at all, so
#: there is no bounded import phase to exclude.
_TRIPWIRE = """
import socket, sys

BLOCKED = (
    "langgraph", "langchain", "langchain_core", "langsmith",
    "openai", "anthropic", "httpx", "requests", "aiohttp", "urllib3",
)

attempts = []


class SubstrateBlocker:
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in BLOCKED:
            attempts.append("import:" + fullname)
            print("WA07-TRIP", file=sys.stderr)
            raise ImportError("WA-07 tripwire: the decorator surface imported " + repr(fullname))
        return None


class _TripSocket(socket.socket):
    def __new__(cls, *a, **k):
        attempts.append("socket"); print("WA07-TRIP", file=sys.stderr)
        raise AssertionError("a socket was created on the decoration path")


def _record(name):
    def _seen(*a, **k):
        attempts.append(name); print("WA07-TRIP", file=sys.stderr)
        raise AssertionError(name + " was reached")
    return _seen


sys.meta_path.insert(0, SubstrateBlocker())
socket.socket = _TripSocket
socket.getaddrinfo = _record("getaddrinfo")
socket.gethostbyname = _record("gethostbyname")
socket.create_connection = _record("create_connection")

import gebra
from gebra.annotations import GebraContractError, read_contract
# Importing the fixtures runs every decorator factory in the tables — under the guard.
from tests.sample_workflows import sentinel_contracts as sc

decorated = 0
for name, decorate in sc.ARMED_DECORATIONS.items():
    target = sc.armed(name)
    assert decorate(target) is target, name
    assert read_contract(target) is not None, name
    assert not hasattr(target, "__wrapped__"), name
    decorated += 1

refused = 0
for name, thunk in sc.REFUSED_DECORATIONS.items():
    try:
        thunk()
    except GebraContractError:
        refused += 1

# A target whose own __dict__ is a hostile dict subclass: reading and writing a namespace
# goes through the unbound built-in accessors, so its own `get` must never run.
hostile_target = sc.hostile_namespace_target()
assert gebra.pure(hostile_target) is hostile_target
assert read_contract(hostile_target) is not None

leaked = sorted(n for n in sys.modules if n.split(".")[0] in BLOCKED)
assert leaked == [], leaked
assert (decorated, refused) == (%d, %d), (decorated, refused)
"""

_REPORT = "print(attempts)\n"


def _run_guarded(probe: str = "") -> subprocess.CompletedProcess[str]:
    body = _TRIPWIRE % (len(sc.ARMED_DECORATIONS), len(sc.REFUSED_DECORATIONS))
    return subprocess.run(
        [sys.executable, "-c", body + probe + _REPORT],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_decoration_invokes_nothing_and_imports_no_substrate() -> None:
    """The WA-07 claim for the §1 path, in a fresh interpreter.

    Four claims at once, and the fixtures are what make them real rather than asserted. Every
    decoration target raises if it is called, so a decorator that invoked one would fail the
    run. Every rejected value raises from ``__repr__``/``__str__`` and every foreign container
    raises from its own accessors, so a refusal path that rendered or read through a hook
    would fail it too. No substrate package can be imported at all — the blocker is installed
    before ``import gebra``, which is the whole reason the decorators resolve out of
    :mod:`gebra.annotations` rather than through the extractor. And nothing constructs a
    socket, resolves a name, or opens a connection.

    The child asserts its own counts from the fixture tables, so a run that silently stopped
    reaching them would fail rather than pass with nothing to prove — and a decoration shape
    or a refusal added to either table joins this claim with it.
    """
    result = _run_guarded()

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "[]", result.stdout
    assert "WA07-TRIP" not in result.stderr, result.stderr


@pytest.mark.parametrize(
    ("probe", "expected"),
    [
        ("import langgraph\n", "the decorator surface imported"),
        ("socket.socket()\n", "a socket was created"),
        ("socket.getaddrinfo('example.invalid', 80)\n", "getaddrinfo was reached"),
        ("socket.gethostbyname('example.invalid')\n", "gethostbyname was reached"),
        ("socket.create_connection(('example.invalid', 80))\n", "create_connection was reached"),
        ("sc.armed('control')()\n", "was invoked — decoration must never call it"),
        ("repr(sc.HostileValue())\n", "__repr__ was called on a rejected decorator argument"),
        ("sc.HostileDict({'a': 1}).items()\n", "dict.items was resolved through the subclass"),
        ("list(sc.HostileList([1]))\n", "list.__iter__ was resolved through the subclass"),
        ("str(sc.HostileStr('x'))\n", "str.__str__ was resolved through the subclass"),
        ("repr(sc.HostileStr('x'))\n", "repr() reached a str subclass's own hook"),
        ("'%s' % sc.HostileValue()\n", "__str__ was called on a rejected decorator argument"),
        ("sc.HostileDict({'a': 1}).get('a')\n", "dict.get was resolved through the subclass"),
        ("sc.HostileDict({'a': 1}).keys()\n", "dict.keys was resolved through the subclass"),
        ("sc.HostileDict({'a': 1})['a']\n", "dict.__getitem__ was resolved through the subclass"),
        ("list(sc.HostileDict({'a': 1}))\n", "dict.__iter__ was resolved through the subclass"),
        ("sc.SlottedNode()()\n", "a slotted node was invoked"),
    ],
    ids=[
        "substrate",
        "socket",
        "getaddrinfo",
        "gethostbyname",
        "create_connection",
        "armed-target",
        "hostile-repr",
        "hostile-dict-items",
        "hostile-list",
        "hostile-str-str",
        "hostile-str-repr",
        "hostile-value-str",
        "hostile-dict-get",
        "hostile-dict-keys",
        "hostile-dict-getitem",
        "hostile-dict-iter",
        "slotted-call",
    ],
)
def test_each_raiser_is_armed(probe: str, expected: str) -> None:
    """A tripwire nobody trips proves nothing, so every raiser gets its own control.

    All ten, not just the network ones: this child is an independent copy of the guard
    prologue and the fixtures are an independent module, so a slip that left one raiser
    unarmed would leave the claim it carries silently vacuous with everything still green.
    The controls run after the child's own assertions, so each proves its raiser was live at
    the end of the very run that made the claim.
    """
    result = _run_guarded(probe)

    assert result.returncode != 0
    assert expected in result.stderr


def test_the_tripwire_covers_the_surface_this_card_lands() -> None:
    """The claim above is only as wide as the tables it quantifies over.

    The child's counts derive from these tables, so both sides move together if a fixture is
    dropped — which means the tables themselves need a floor. Without one the guarded run
    could shrink to a single decoration and every assertion would still pass. The decoration
    floor is one per decorator plus the composite shapes; the refusal floor covers the four
    §1 rules, the closed-slot refusals and the hostile-value paths.
    """
    assert len(sc.ARMED_DECORATIONS) >= 14
    assert len(sc.REFUSED_DECORATIONS) >= 18
    assert set(sc.ARMED_DECORATIONS) & set(sc.REFUSED_DECORATIONS) == set()
    # Counts alone would let a load-bearing entry be swapped for a trivial one, so the
    # entries that carry the *distinctive* half of the claim are pinned by name.
    assert {"stack", "all-nine", "hostile-subclass-values"} <= set(sc.ARMED_DECORATIONS)
    assert {
        "duplicate-slot",
        "pure-with-effects",
        "unknown-effect-tag",
        "deterministic-without-seed",
        "hostile-reads",
        "hostile-args-schema-key",
        "hostile-keyword",
        "slotted-target",
        "foreign-carrier",
    } <= set(sc.REFUSED_DECORATIONS)
