"""The per-slot precedence chain — ANNOTATION-API-SPEC §3, ratified as DEC-07.

This module holds the chain itself, substrate-free: which tier wins a slot, when a losing
tier is a conflict and when it is silent, what the resolved-contract pass does with a
contract no single surface authored, and what happens to a value the canonical form refuses.
Which *live object* supplies each tier is ``tests/extraction/test_contracts.py``'s subject.

The card's first acceptance box is the section immediately below: the precedence matrix is
enumerated per slot rather than spot-checked, from :data:`~gebra.annotations.resolve.
TIER_SLOTS` (which tiers can speak about a slot) crossed with every non-empty subset of them,
so a slot with a tier missing from the table fails the suite rather than being absent from it.

Nothing here imports langgraph, opens a socket, or executes anything.
"""

from __future__ import annotations

import itertools
import unicodedata
from typing import TYPE_CHECKING, Any, Final

import pytest

import gebra
from gebra.annotations import (
    ANNOTATION_SLOTS,
    PRECEDENCE,
    TIER_SLOTS,
    AnnotationSlot,
    Contribution,
    IssueKind,
    NodeContract,
    ResolutionRule,
    Surface,
    carriable,
    resolve,
    slot_bytes,
    slot_data,
)
from gebra.annotations.errors import GebraContractError
from gebra.annotations.inference import INFERENCE_SLOTS
from gebra.ir.models import Compensation, DeterministicSpec, IdempotentKey, Variant

if TYPE_CHECKING:
    from collections.abc import Sequence

    from gebra.annotations import Resolution

#: One value per (slot, tier), all Python-distinct except where the slot's domain forbids it.
#:
#: ``pure`` is that exception and it is left in deliberately: a boolean slot has two values
#: and three tiers can set it, so the decorator and the inference tier here declare the *same*
#: thing — which is §3's "identical values are not a conflict" arriving inside the matrix
#: rather than only in the test written for it. The expectations below are derived from plain
#: Python equality of these values, never from the canonicalization the implementation uses,
#: so the two agree only if both are right.
SLOT_VALUES: Final[dict[AnnotationSlot, dict[Surface, Any]]] = {
    "input": {
        Surface.DECORATOR: ("query",),
        Surface.SIDECAR: ("budget",),
        Surface.INFERENCE: ("plan",),
    },
    "output": {
        Surface.DECORATOR: ("plan",),
        Surface.SIDECAR: ("answer",),
        Surface.INFERENCE: ("draft",),
    },
    "effect": {
        Surface.DECORATOR: ("network",),
        Surface.SIDECAR: ("billable",),
        Surface.INFERENCE: ("write",),
    },
    "pure": {
        Surface.DECORATOR: True,
        Surface.SIDECAR: False,
        Surface.INFERENCE: True,
    },
    "idempotent": {
        Surface.DECORATOR: True,
        Surface.SIDECAR: IdempotentKey(key="booking_ref"),
    },
    "deterministic": {
        Surface.DECORATOR: DeterministicSpec(seed=1),
        Surface.SIDECAR: DeterministicSpec(seed=2, temperature=0.0),
    },
    "args_schema": {
        Surface.DECORATOR: {"title": "declared"},
        Surface.TOOL: {"title": "carried"},
        Surface.SIDECAR: {"title": "configured"},
    },
    "variant": {
        Surface.DECORATOR: Variant(key="remaining", measure="len"),
        Surface.SIDECAR: Variant(key="budget", measure="int"),
    },
    "compensation": {
        Surface.DECORATOR: Compensation(hook="undo"),
        Surface.SIDECAR: Compensation(hook="cancel"),
    },
}


def tiers_for(slot: AnnotationSlot) -> tuple[Surface, ...]:
    """The tiers §3 lets speak about ``slot``, highest first."""
    return tuple(surface for surface in PRECEDENCE if slot in TIER_SLOTS[surface])


def cells() -> list[tuple[AnnotationSlot, tuple[Surface, ...]]]:
    """Every matrix cell: one slot and one non-empty set of tiers that declare it."""
    return [
        (slot, subset)
        for slot in ANNOTATION_SLOTS
        for size in range(1, len(tiers_for(slot)) + 1)
        for subset in itertools.combinations(tiers_for(slot), size)
    ]


MATRIX: Final = cells()
MATRIX_IDS: Final = [
    f"{slot}:{'+'.join(surface.value for surface in subset)}" for slot, subset in MATRIX
]


def declaring(slot: AnnotationSlot, surface: Surface) -> Contribution:
    """One tier's contribution, declaring ``slot`` and nothing else."""
    return Contribution(surface, NodeContract.model_validate({slot: SLOT_VALUES[slot][surface]}))


def conflicts(resolution: Resolution) -> tuple[Any, ...]:
    """The ``annotation-conflict`` findings, in order."""
    return tuple(issue for issue in resolution.issues if issue.kind is IssueKind.CONFLICT)


def invalids(resolution: Resolution) -> tuple[Any, ...]:
    """The ``annotation-invalid`` findings, in order."""
    return tuple(issue for issue in resolution.issues if issue.kind is IssueKind.INVALID)


# ── The card's first acceptance box: the precedence matrix, per slot ─────────────────────


def test_the_matrix_covers_every_slot_and_every_tier_that_can_set_it() -> None:
    """The table is complete before anything is run against it.

    An equality rather than a count: the tier sets come from :data:`TIER_SLOTS`, which is the
    spec's own closure (§1's nine for the two declaration surfaces, §3's one slot for the
    tool-carried tier, §4's four for inference), so a slot missing a value fails here instead
    of quietly shrinking the matrix below.
    """
    assert {slot for slot, _ in MATRIX} == set(ANNOTATION_SLOTS)
    for slot in ANNOTATION_SLOTS:
        assert set(SLOT_VALUES[slot]) == set(tiers_for(slot)), slot
    assert TIER_SLOTS[Surface.TOOL] == frozenset({"args_schema"})
    assert TIER_SLOTS[Surface.INFERENCE] == frozenset(INFERENCE_SLOTS)
    assert PRECEDENCE == (Surface.DECORATOR, Surface.TOOL, Surface.SIDECAR, Surface.INFERENCE)


@pytest.mark.parametrize(("slot", "subset"), MATRIX, ids=MATRIX_IDS)
def test_the_highest_declaring_tier_wins_the_slot(
    slot: AnnotationSlot, subset: tuple[Surface, ...]
) -> None:
    """§3: resolution is "per-slot, strict", in the order the chain fixes.

    The winner is the first tier of :data:`PRECEDENCE` present in the cell, and the surface is
    recorded — which is what §5's grade lookup and every warning payload are written against.
    """
    resolution = resolve([declaring(slot, surface) for surface in subset])

    winner = subset[0]
    assert resolution.contract.slot_value(slot) == SLOT_VALUES[slot][winner]
    assert resolution.surfaces[slot] is winner
    assert resolution.contract.declared_slots() == (slot,)


@pytest.mark.parametrize(("slot", "subset"), MATRIX, ids=MATRIX_IDS)
def test_the_order_the_tiers_arrive_in_never_changes_the_outcome(
    slot: AnnotationSlot, subset: tuple[Surface, ...]
) -> None:
    """§6's parity requirement, at the level where it is decidable: the chain sorts.

    "Extracting the same workflow before and after ``.compile()`` yields identical resolved
    contracts" can only hold if the resolution does not depend on the order a caller happened
    to collect the tiers in. Quantified over every permutation of every cell, so it is a
    property of the chain rather than of the one order the caller uses today.
    """
    canonical = resolve([declaring(slot, surface) for surface in subset])

    for permutation in itertools.permutations(subset):
        assert resolve([declaring(slot, surface) for surface in permutation]) == canonical


@pytest.mark.parametrize(("slot", "subset"), MATRIX, ids=MATRIX_IDS)
def test_every_losing_tier_that_disagrees_is_warned_and_kept_out(
    slot: AnnotationSlot, subset: tuple[Surface, ...]
) -> None:
    """The card's second box: "conflicts warn and keep the winner".

    Both halves at once — one ``annotation-conflict`` per losing tier whose value differs,
    each naming the slot, both surfaces and both values; and none at all for a losing tier
    that says the same thing, which is §3's "identical values are not a conflict". The
    expectation is computed from Python equality of the declared values, so a chain that
    decided identity some other way would disagree with it here.
    """
    winner, *losers = subset
    resolution = resolve([declaring(slot, surface) for surface in subset])

    expected = [loser for loser in losers if SLOT_VALUES[slot][loser] != SLOT_VALUES[slot][winner]]
    found = conflicts(resolution)

    assert [issue.detail["surfaces"]["discarded"] for issue in found] == [
        loser.value for loser in expected
    ]
    for issue in found:
        assert issue.rule is ResolutionRule.LOWER_TIER_DIFFERS
        assert issue.slots == (slot,)
        assert issue.detail["slot"] == slot
        assert issue.detail["surfaces"]["kept"] == winner.value
        assert issue.detail["values"]["kept"] == slot_data(slot, SLOT_VALUES[slot][winner])
        discarded = Surface(issue.detail["surfaces"]["discarded"])
        assert issue.detail["values"]["discarded"] == slot_data(slot, SLOT_VALUES[slot][discarded])


def test_a_tier_fills_only_the_slots_the_higher_ones_left_open() -> None:
    """DEC-07 in one assertion: "the sidecar **fills gaps only**".

    The two tiers overlap on one slot and are disjoint on the rest, which is the shape the
    ruling is about — a decorator that declares part of a contract does not block the config
    from completing it, and does not lose the part it declared either.
    """
    resolution = resolve(
        [
            Contribution(Surface.DECORATOR, NodeContract(input=("query",), pure=False)),
            Contribution(
                Surface.SIDECAR,
                NodeContract(input=("budget",), output=("plan",), effect=("network",)),
            ),
        ]
    )

    assert resolution.contract == NodeContract(
        input=("query",), output=("plan",), effect=("network",), pure=False
    )
    assert resolution.surfaces == {
        "input": Surface.DECORATOR,
        "output": Surface.SIDECAR,
        "effect": Surface.SIDECAR,
        "pure": Surface.DECORATOR,
    }
    assert [issue.detail["slot"] for issue in conflicts(resolution)] == ["input"]


def test_an_explicit_negative_occupies_its_slot() -> None:
    """§3: ""Set" means not-``None``" — an explicit ``False`` blocks lower-tier fill.

    "An explicit negative declaration (``pure=False``, ``idempotent=False``,
    ``deterministic=False``) is a declaration: it occupies its slot and blocks lower-tier fill
    exactly like a positive value; only ``None``/absent leaves a slot open." The distinction
    reaches the digest, since §6.3's omit-normalization "strips only ``null``/absent".
    """
    negatives = NodeContract(pure=False, idempotent=False, deterministic=False)
    resolution = resolve(
        [
            Contribution(Surface.DECORATOR, negatives),
            Contribution(
                Surface.SIDECAR,
                NodeContract(pure=True, idempotent=True, deterministic=True),
            ),
        ]
    )

    assert resolution.contract == negatives
    assert [issue.detail["slot"] for issue in conflicts(resolution)] == [
        "pure",
        "idempotent",
        "deterministic",
    ]


def test_an_empty_contribution_is_a_tier_that_said_nothing() -> None:
    """A tier with no slot set neither wins nor conflicts — it is simply not there."""
    resolution = resolve(
        [
            Contribution(Surface.DECORATOR, NodeContract()),
            Contribution(Surface.SIDECAR, NodeContract(pure=True)),
            Contribution(Surface.INFERENCE, NodeContract()),
        ]
    )

    assert resolution.contract == NodeContract(pure=True)
    assert resolution.surfaces == {"pure": Surface.SIDECAR}
    assert resolution.issues == ()


def test_resolving_nothing_at_all_is_the_empty_contract() -> None:
    """The degenerate case is a value, not a special case."""
    resolution = resolve([])

    assert resolution.contract == NodeContract()
    assert resolution.surfaces == {}
    assert resolution.issues == ()
    assert resolution.declared() == ()


# ── §3's value identity: canonicalized bytes, not text ───────────────────────────────────


def test_two_spellings_of_one_value_are_not_a_conflict() -> None:
    """§3: identity is "byte-equal" ledger §6 canonicalizations, "never textually".

    Three pairs that a textual comparison would call different and §6 calls one: a reordered
    ``reads`` (§6.2 sorts the array before any byte exists), a ``temperature`` written as an
    integer where the ledger types it a number, and an ``args_schema`` whose members are in
    another order (JCS sorts member names). Each is a spelling one surface can produce and the
    other cannot, which is why §3 had to make the rule structural.
    """
    pairs: tuple[tuple[AnnotationSlot, Any, Any], ...] = (
        ("input", ("query", "budget"), ("budget", "query")),
        ("deterministic", DeterministicSpec(seed=7), DeterministicSpec(seed=7)),
        (
            "args_schema",
            {"type": "object", "title": "t"},
            {"title": "t", "type": "object"},
        ),
    )

    for slot, declared, configured in pairs:
        resolution = resolve(
            [
                Contribution(Surface.DECORATOR, NodeContract.model_validate({slot: declared})),
                Contribution(Surface.SIDECAR, NodeContract.model_validate({slot: configured})),
            ]
        )
        assert slot_bytes(slot, declared) == slot_bytes(slot, configured), slot
        assert resolution.issues == (), slot
        assert resolution.contract.slot_value(slot) == declared, slot


def test_the_two_decoration_surfaces_land_on_one_value_for_one_declaration() -> None:
    """The seam EX-09 built for exactly this rule, exercised end to end through the chain.

    A decorator ``temperature=0.0`` and a TOML ``temperature = 0`` are the same declaration
    written twice, and they must not read as a disagreement. Both go through
    :func:`~gebra.annotations.contract.normalize_declared_value`, so they are the same *value*
    before §3 ever compares them — which is what makes the rule true by construction rather
    than by two implementations agreeing today.
    """
    from gebra.annotations.contract import normalize_declared_value

    declared = normalize_declared_value("deterministic", {"seed": 7, "temperature": 0.0})
    configured = normalize_declared_value("deterministic", {"seed": 7, "temperature": 0})

    assert declared == configured
    assert (
        resolve(
            [
                Contribution(Surface.DECORATOR, NodeContract(deterministic=declared)),  # type: ignore[arg-type]
                Contribution(Surface.SIDECAR, NodeContract(deterministic=configured)),  # type: ignore[arg-type]
            ]
        ).issues
        == ()
    )


def test_the_canonicalization_a_slot_is_compared_by_is_the_ir_s_own() -> None:
    """:func:`slot_bytes` is the ledger §6 projection of the slot, not a rendering of it.

    Worth pinning, because the whole rule rests on it: what §3 compares is what the digest
    would carry, so an empty optional array — which §6.3 omits — compares equal to a contract
    that never set the slot at all.
    """
    assert slot_bytes("input", ("b", "a")) == b'{"input":["a","b"]}'
    assert slot_bytes("input", ()) == b"{}"
    assert slot_bytes("pure", True) == b'{"pure":true}'
    assert slot_bytes("idempotent", IdempotentKey(key="k")) == b'{"idempotent":{"key":"k"}}'


# ── Carriability: what the IR could not carry is dropped, never emitted ──────────────────


def test_an_identifier_role_key_is_normalized_rather_than_refused() -> None:
    """IR-SPEC §6.3 puts these strings in the NFC identifier role, and §5.1 normalizes.

    The alternative is the one thing INTROSPECTION §2 rules out: an IR that exists and has no
    ``graph_version``, because canonicalization *refuses* a non-NFC identifier rather than
    normalizing one. :mod:`gebra.extraction.builder` already applies exactly this reading to a
    ``path_map`` label; a declared ``reads`` entry is the same role one level along.
    """
    decomposed = unicodedata.normalize("NFD", "café")
    assert decomposed != "café"

    resolution = resolve(
        [Contribution(Surface.DECORATOR, NodeContract(input=(decomposed,), output=("café",)))]
    )

    assert resolution.contract == NodeContract(input=("café",), output=("café",))
    assert resolution.issues == ()
    assert carriable("idempotent", IdempotentKey(key=decomposed)) == IdempotentKey(key="café")
    assert carriable("variant", Variant(key=decomposed, measure="len")) == Variant(
        key="café", measure="len"
    )
    assert carriable("compensation", Compensation(hook=decomposed)) == Compensation(hook="café")


def test_two_spellings_of_one_key_stop_being_a_conflict_once_they_are_normalized() -> None:
    """The normalization runs before the comparison, which is the order that matters.

    A decorator that spelled a key in NFD and a sidecar that spelled it in NFC declare the
    same state key — §6.3 says so, by putting both in one normal form — and reporting a
    conflict between them would be reporting on the file's encoding.
    """
    resolution = resolve(
        [
            Contribution(
                Surface.DECORATOR, NodeContract(input=(unicodedata.normalize("NFD", "café"),))
            ),
            Contribution(Surface.SIDECAR, NodeContract(input=("café",))),
        ]
    )

    assert resolution.contract == NodeContract(input=("café",))
    assert resolution.issues == ()


def test_a_value_the_canonical_form_refuses_is_dropped_with_its_warning() -> None:
    """Extraction stays total, and it stays *digestible* — which is the same sentence.

    A lone surrogate has no UTF-8 encoding, so IR-SPEC §6.1 step 6 cannot serialize it and
    ``graph_version()`` would raise for the whole document. §3's own repair vocabulary is what
    it is dropped with, and the record degrades the value to its type rather than putting an
    unreportable string inside a warning that exists to be reported.
    """
    surrogate = "budget\ud800"
    resolution = resolve([Contribution(Surface.SIDECAR, NodeContract(input=(surrogate,)))])

    (issue,) = invalids(resolution)
    assert resolution.contract == NodeContract()
    assert resolution.surfaces == {}
    assert issue.rule is ResolutionRule.SLOT_NOT_CARRIABLE
    assert issue.slots == ("input",)
    assert issue.detail["surfaces"] == {"discarded": "sidecar"}
    assert issue.detail["values"]["discarded"] == "tuple"
    assert carriable("input", (surrogate,)) is None


def test_a_lower_tier_survives_when_the_winner_is_uncarriable() -> None:
    """The drop is the winner's, and the slot is simply gone — the loser is not promoted.

    Promoting it would let an unrepresentable declaration hand its slot to a tier the author
    ranked below it, which is a different contract from the one anyone wrote. What the loser
    keeps is the conflict it was already reported for.
    """
    resolution = resolve(
        [
            Contribution(Surface.DECORATOR, NodeContract(input=("budget\ud800",), pure=True)),
            Contribution(Surface.SIDECAR, NodeContract(input=("budget",))),
        ]
    )

    assert resolution.contract == NodeContract(pure=True)
    assert [issue.rule for issue in resolution.issues] == [
        ResolutionRule.LOWER_TIER_DIFFERS,
        ResolutionRule.SLOT_NOT_CARRIABLE,
    ]


def test_every_resolved_contract_this_chain_returns_has_canonical_bytes() -> None:
    """The property the carriability pass exists for, quantified over the whole matrix.

    "Extraction is total over supported objects" is worth nothing if the IR it produces has no
    digest, so the pass is what turns "the chain emitted something" into "the chain emitted
    something a ``graph_version`` can be taken of".
    """
    for slot, subset in MATRIX:
        resolution = resolve([declaring(slot, surface) for surface in subset])
        for filled in resolution.contract.declared_slots():
            assert slot_bytes(filled, resolution.contract.slot_value(filled))


# ── §3's resolved-contract validation ────────────────────────────────────────────────────


def test_a_contract_no_single_surface_authored_is_validated_and_repaired() -> None:
    """§3's own worked example, and the repair rule it states.

    "A decorator ``pure=True`` plus a sidecar ``effects=[...]``: no slot was set twice, so it
    is not an ``annotation-conflict``, yet the resolved contract violates decision D-011
    exclusivity." The repair is stated in the same paragraph: "the contribution from the
    **lower-precedence** tier is discarded, the higher tier's slots stand".
    """
    resolution = resolve(
        [
            Contribution(Surface.DECORATOR, NodeContract(pure=True)),
            Contribution(Surface.SIDECAR, NodeContract(effect=("network",), output=("plan",))),
        ]
    )

    (issue,) = invalids(resolution)
    assert resolution.contract == NodeContract(pure=True, output=("plan",))
    assert issue.rule is ResolutionRule.PURE_EFFECT_EXCLUSIVE
    assert issue.slots == ("pure", "effect")
    assert issue.detail["surfaces"] == {"pure": "decorator", "effect": "sidecar"}
    assert issue.detail["values"] == {"pure": True, "effect": ["network"]}


def test_the_repair_discards_the_lower_tier_even_when_it_is_inference() -> None:
    """Inference is the lowest tier, so it is the one a cross-tier repair takes out.

    Constructed rather than produced: §4's engine decides ``pure``/``effect`` as a *pair* and
    withdraws when either half is declared, precisely so it cannot assemble this. The chain
    still has to answer for it, because the tier interface admits any contract.
    """
    resolution = resolve(
        [
            Contribution(Surface.SIDECAR, NodeContract(pure=True)),
            Contribution(Surface.INFERENCE, NodeContract(effect=("write",))),
        ]
    )

    (issue,) = invalids(resolution)
    assert resolution.contract == NodeContract(pure=True)
    assert issue.detail["surfaces"] == {"pure": "sidecar", "effect": "inference"}


def test_a_violation_inside_one_tier_is_reported_and_left_standing() -> None:
    """Decision D-012's pair, and the repair rule's precondition.

    §3's repair discards "the contribution from the **lower-precedence** tier", which
    presupposes two tiers; when every participating slot came from one, there is no lower
    contribution to discard. §1 puts both D-012 checks at warning grade for exactly this
    reason — they "need the *resolved* contract, so they run at extraction, not decoration" —
    so the record is what the author gets, and P-06/P-07 judge the declaration itself. This
    pair is reachable from a single decorator stack, unlike the D-011 one, which §1 catches at
    import time.
    """
    resolution = resolve(
        [
            Contribution(
                Surface.DECORATOR,
                NodeContract(idempotent=True, effect=("network", "irreversible")),
            )
        ]
    )

    (issue,) = invalids(resolution)
    assert resolution.contract == NodeContract(idempotent=True, effect=("network", "irreversible"))
    assert issue.rule is ResolutionRule.IRREVERSIBLE_IDEMPOTENT
    assert issue.slots == ("idempotent", "effect")
    assert issue.detail["surfaces"] == {"idempotent": "decorator", "effect": "decorator"}


def test_the_d012_pair_is_repaired_when_it_spans_two_tiers() -> None:
    """The same invariant, with a lower contribution to discard — so §3's repair applies."""
    resolution = resolve(
        [
            Contribution(Surface.DECORATOR, NodeContract(idempotent=True)),
            Contribution(Surface.SIDECAR, NodeContract(effect=("irreversible",))),
        ]
    )

    (issue,) = invalids(resolution)
    assert resolution.contract == NodeContract(idempotent=True)
    assert issue.rule is ResolutionRule.IRREVERSIBLE_IDEMPOTENT


def test_an_idempotency_key_outside_the_resolved_input_is_reported() -> None:
    """§1: ``idempotent={"key": k}`` "requires ``k`` to appear in the node's resolved ``input``".

    Resolved, not declared-on-one-surface: the key and the input set can come from different
    tiers, which is why §1 says the check "needs the *resolved* contract, so it runs at
    extraction, not decoration".
    """
    resolution = resolve(
        [
            Contribution(Surface.DECORATOR, NodeContract(idempotent=IdempotentKey(key="plan"))),
            Contribution(Surface.SIDECAR, NodeContract(input=("query", "budget"))),
        ]
    )

    (issue,) = invalids(resolution)
    assert issue.rule is ResolutionRule.IDEMPOTENT_KEY_NOT_IN_INPUT
    assert issue.detail["advisory"] is False
    assert issue.detail["grades"] == {"idempotent": "declared", "input": "declared"}
    assert resolution.contract == NodeContract(idempotent=IdempotentKey(key="plan"))


def test_the_key_check_is_advisory_against_an_inference_grade_input() -> None:
    """§1, in terms: "a heuristic-grade input set cannot ground a hard verdict".

    "When the resolved ``input`` is inference-grade (``contract-inferred``/
    ``contract-defaulted``, §4), the key-membership check is advisory only … the warning
    records both grades." So the record is emitted and **nothing is discarded** — the inferred
    input set stays, because §4's patterns are shallow and their silence is not evidence.
    """
    resolution = resolve(
        [
            Contribution(Surface.DECORATOR, NodeContract(idempotent=IdempotentKey(key="plan"))),
            Contribution(Surface.INFERENCE, NodeContract(input=("query",))),
        ]
    )

    (issue,) = invalids(resolution)
    assert resolution.contract == NodeContract(
        idempotent=IdempotentKey(key="plan"), input=("query",)
    )
    assert issue.detail["advisory"] is True
    assert issue.detail["grades"] == {"idempotent": "declared", "input": "inferred"}


def test_a_key_in_the_resolved_input_is_not_reported() -> None:
    """The complement, without which the two tests above would pass on a chain that always warns."""
    resolution = resolve(
        [
            Contribution(Surface.DECORATOR, NodeContract(idempotent=IdempotentKey(key="plan"))),
            Contribution(Surface.SIDECAR, NodeContract(input=("query", "plan"))),
        ]
    )

    assert resolution.issues == ()


def test_no_key_check_runs_when_no_tier_declared_an_input() -> None:
    """An absent ``input`` is an unknown read set, not an empty one.

    §1's rule is membership in "the node's resolved ``input`` set"; with no tier declaring
    one, there is no set to be outside of, and warning would fire on every keyed-idempotent
    node whose author did not also declare its reads — which is most of them.
    """
    resolution = resolve(
        [Contribution(Surface.DECORATOR, NodeContract(idempotent=IdempotentKey(key="plan")))]
    )

    assert resolution.issues == ()
    assert resolution.contract == NodeContract(idempotent=IdempotentKey(key="plan"))


def test_a_repair_that_uncovers_a_second_violation_repairs_that_one_too() -> None:
    """The pass runs to a fixed point, because a repair changes what the next check sees.

    Discarding the sidecar's ``pure`` to settle D-011 exclusivity is exactly what can leave
    a D-012 pair behind, so a single pass would emit one finding and hand on a contract that
    still violates the other invariant.
    """
    resolution = resolve(
        [
            Contribution(
                Surface.DECORATOR, NodeContract(effect=("irreversible",), idempotent=True)
            ),
            Contribution(Surface.SIDECAR, NodeContract(pure=True)),
        ]
    )

    assert [issue.rule for issue in invalids(resolution)] == [
        ResolutionRule.PURE_EFFECT_EXCLUSIVE,
        ResolutionRule.IRREVERSIBLE_IDEMPOTENT,
    ]
    assert resolution.contract == NodeContract(effect=("irreversible",), idempotent=True)


def test_the_seedless_deterministic_object_cannot_reach_a_resolved_contract() -> None:
    """§3's fourth named invariant, checked as the three refusals that make it unreachable.

    §3 lists "the ``deterministic`` object shape (ledger §3)" among what the resolved-contract
    pass validates, and :mod:`gebra.annotations.resolve` deliberately carries no branch for
    it. This is that absence stated as a claim: the decorator raises at import time (§1), the
    sidecar rejects the slot and leaves it unset (§2 bullet 5), and the carrier both surfaces
    build types ``seed`` required — so no tier can hand the chain one.
    """
    with pytest.raises(GebraContractError):
        gebra.deterministic(temperature=0.0)(lambda state: state)

    with pytest.raises(Exception, match="seed"):
        DeterministicSpec.model_validate({"temperature": 0.0})

    assert "seed" in DeterministicSpec.model_fields
    assert DeterministicSpec.model_fields["seed"].is_required()


# ── The findings are records, not strings ────────────────────────────────────────────────


def test_every_finding_carries_the_fields_its_registry_row_names() -> None:
    """§4: the annotation warnings "carry structured fields — never bare strings".

    Quantified over one contract that trips a conflict, a carriability drop and a
    resolved-contract repair at once, so the shape is checked per rule rather than per test.
    """
    resolution = resolve(
        [
            Contribution(
                Surface.DECORATOR, NodeContract(pure=True, output=("plan\ud800",), input=("q",))
            ),
            Contribution(Surface.SIDECAR, NodeContract(input=("budget",), effect=("network",))),
        ]
    )

    seen = {issue.rule for issue in resolution.issues}
    assert seen == {
        ResolutionRule.LOWER_TIER_DIFFERS,
        ResolutionRule.SLOT_NOT_CARRIABLE,
        ResolutionRule.PURE_EFFECT_EXCLUSIVE,
    }
    for issue in resolution.issues:
        assert issue.message
        assert issue.slots
        assert issue.detail["rule"] == issue.rule.value
        assert set(issue.detail) >= {"rule", "surfaces", "values"}


def test_the_declared_slots_are_everything_the_lowest_tier_did_not_fill() -> None:
    """:meth:`Resolution.declared` is §5's line drawn where the tier is still known."""
    resolution = resolve(
        [
            Contribution(Surface.DECORATOR, NodeContract(input=("query",))),
            Contribution(Surface.SIDECAR, NodeContract(effect=("network",))),
            Contribution(Surface.INFERENCE, NodeContract(output=("plan",))),
        ]
    )

    assert resolution.declared() == ("input", "effect")
    assert resolution.contract.declared_slots() == ("input", "output", "effect")


def test_slot_data_renders_a_sub_model_as_the_object_the_ir_would_carry() -> None:
    """A payload carries the IR's shape, never a repr — the field §4 asks warnings to carry."""
    assert slot_data("idempotent", IdempotentKey(key="k")) == {"key": "k"}
    assert slot_data("deterministic", DeterministicSpec(seed=7, temperature=0.0)) == {
        "seed": 7,
        "temperature": 0.0,
    }
    assert slot_data("variant", Variant(key="n", measure="len")) == {"key": "n", "measure": "len"}
    assert slot_data("compensation", Compensation(hook="undo")) == {"hook": "undo"}
    assert slot_data("input", ("b", "a")) == ["b", "a"]


def test_a_repeated_surface_is_resolved_in_the_order_it_was_given() -> None:
    """Two contributions from one tier are not a representable disagreement in §3's model.

    The chain sorts by precedence and a stable sort keeps equal keys in input order, so the
    first one given wins and the second is reported like any other loser. Pinned because a
    caller that built two contributions for one tier has a bug this module cannot see, and
    what it gets should be deterministic rather than incidental.
    """
    resolution = resolve(
        [
            Contribution(Surface.SIDECAR, NodeContract(pure=True)),
            Contribution(Surface.SIDECAR, NodeContract(pure=False)),
        ]
    )

    assert resolution.contract == NodeContract(pure=True)
    assert [issue.detail["surfaces"] for issue in conflicts(resolution)] == [
        {"kept": "sidecar", "discarded": "sidecar"}
    ]


def test_the_chain_never_raises_on_any_matrix_cell() -> None:
    """Totality, over the whole matrix at once — §3's posture is that nothing here is an error."""
    for slot, subset in MATRIX:
        contributions: Sequence[Contribution] = [declaring(slot, surface) for surface in subset]
        assert resolve(contributions) is not None
