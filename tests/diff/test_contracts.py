"""The contract delta on constructed pairs — every slot, both absences, and the F bridge.

Each row of :data:`CONTRACTS` is one deliberate edit to the ``work`` node's contract in the
base workflow of ``tests.versioning.workflows``, with the exact :class:`NodeContractChanged`
it must produce. The vocabulary mirrors the SD-02 delta table on purpose: where that suite
asserts *which counter* a contract edit moves, this one asserts *what the diff says about it*.
Every slot the frozen ``annotations`` model carries has a row, including the six new-in-1.0
§3 slots, and both of the absences a slot-only comparison would miss — ``annotations``
present-but-empty against absent, and the same for the ``runtime`` block.

The bridge to the version engine is asserted on every row: a contract delta is non-empty
exactly when :func:`~gebra.versioning.changed_components` selects F. That is the claim
:mod:`gebra.diff.workflow` derives its bump class against, so the two cannot drift apart
silently.

Everything is hand-built IR models (WA-07): no extractor, no substrate, nothing to invoke.
The tripwire that proves it for this path lives beside the workflow-diff suite, whose guarded
child runs these rows.
"""

from __future__ import annotations

from typing import NamedTuple

import pytest

from gebra.diff import (
    ContractsDelta,
    NodeContractChanged,
    NodeContractRef,
    RuntimeDelta,
    SlotChange,
    contracts_diff,
)
from gebra.ir.canonical import graph_version
from gebra.ir.models import (
    Annotations,
    Checkpointer,
    Compensation,
    DeterministicSpec,
    IdempotentKey,
    Interrupts,
    Node,
    RecursionLimit,
    RetryPolicy,
    Runtime,
    Variant,
    WorkflowIR,
)
from gebra.versioning import Component, changed_components
from tests.versioning.workflows import NODES, contract_of, node, with_contract, workflow

#: The contract the base workflow gives ``work`` — every row edits this one.
WORK = contract_of("work")

#: The base workflow carries a ``runtime`` block, and the presence flags describe the two
#: *sides*, not the change — so a pair that leaves the block alone still reports it on both.
#: The delta is falsy either way, which is what ``__bool__`` is for.
RUNTIME_KEPT = RuntimeDelta(present_before=True, present_after=True)


def edited(**slots: object) -> Annotations:
    """``work``'s contract with some slots replaced — a row reads as the edit it is."""
    return Annotations(**{**WORK.model_dump(exclude_none=True), **slots})


def contracts_of(annotations: Annotations | None) -> WorkflowIR:
    """The base workflow with ``work`` carrying ``annotations`` instead."""
    if annotations is None:
        return workflow(nodes=tuple(node(n.id, None) if n.id == "work" else n for n in NODES))
    return workflow(nodes=with_contract("work", annotations))


class Row(NamedTuple):
    """One constructed contract pair and the slot changes it must report."""

    name: str
    before: Annotations | None
    after: Annotations | None
    present_before: bool
    present_after: bool
    slots: tuple[SlotChange, ...]


def slot(name: str, before: str | None, after: str | None) -> SlotChange:
    return SlotChange(slot=name, before=before, after=after)


#: One row per ``annotations`` slot, plus the presence cases.
CONTRACTS: list[Row] = [
    # ── The eight retained slots (IR-SPEC §2.3) ─────────────────────────────────────────
    Row(
        "effect escalated",
        WORK,
        edited(effect=("billable", "irreversible")),
        True,
        True,
        (slot("effect", '["write"]', '["billable","irreversible"]'),),
    ),
    Row(
        # IR-SPEC §6.3: "Empty optional arrays are omitted" — an emptied ``effect`` list and a
        # dropped ``effect`` slot share one canonical form, so they share one delta. Both
        # constructions are kept, because it is the *spec* that makes them one thing and a
        # reader of this table should see that rather than infer it.
        "effect list emptied",
        WORK,
        edited(effect=()),
        True,
        True,
        (slot("effect", '["write"]', None),),
    ),
    Row(
        "effect dropped",
        WORK,
        Annotations(input=("task",), output=("result",)),
        True,
        True,
        (slot("effect", '["write"]', None),),
    ),
    Row("pure declared", WORK, edited(pure=False), True, True, (slot("pure", None, "false"),)),
    Row(
        "idempotent keyed",
        WORK,
        edited(idempotent=IdempotentKey(key="task")),
        True,
        True,
        (slot("idempotent", None, '{"key":"task"}'),),
    ),
    Row(
        "idempotent bare to keyed",
        edited(idempotent=True),
        edited(idempotent=IdempotentKey(key="task")),
        True,
        True,
        (slot("idempotent", "true", '{"key":"task"}'),),
    ),
    Row(
        "deterministic seeded",
        edited(deterministic=True),
        edited(deterministic=DeterministicSpec(seed=7)),
        True,
        True,
        (slot("deterministic", "true", '{"seed":7}'),),
    ),
    Row(
        "deterministic temperature pinned",
        edited(deterministic=DeterministicSpec(seed=7)),
        edited(deterministic=DeterministicSpec(seed=7, temperature=0.0)),
        True,
        True,
        (slot("deterministic", '{"seed":7}', '{"seed":7,"temperature":0}'),),
    ),
    Row(
        "a read key dropped from input",
        WORK,
        edited(input=()),
        True,
        True,
        (slot("input", '["task"]', None),),
    ),
    Row(
        "a write key added to output",
        WORK,
        edited(output=("result", "receipt")),
        True,
        True,
        (slot("output", '["result"]', '["receipt","result"]'),),
    ),
    Row(
        "source bound",
        WORK,
        edited(source="ledger"),
        True,
        True,
        (slot("source", None, '"ledger"'),),
    ),
    Row("map bound", WORK, edited(map="rows"), True, True, (slot("map", None, '"rows"'),)),
    # ── The six new-in-1.0 §3 slots ─────────────────────────────────────────────────────
    Row(
        "args_schema declared",
        WORK,
        edited(args_schema={"const": True}),
        True,
        True,
        (slot("args_schema", None, '{"const":true}'),),
    ),
    Row(
        # SD-02's blocking pre-review finding, pinned here too: ``True == 1`` in Python, and
        # ``args_schema`` is the one path in ir 1.0 whose JSON type is unconstrained. A
        # comparison by value would report nothing while the digest moved.
        "a JSON Schema value retyped from true to 1",
        edited(args_schema={"const": True}),
        edited(args_schema={"const": 1}),
        True,
        True,
        (slot("args_schema", '{"const":true}', '{"const":1}'),),
    ),
    Row(
        "retry policy declared",
        WORK,
        edited(retry_policy=RetryPolicy(max_attempts=3, retry_on=("TimeoutError",))),
        True,
        True,
        (slot("retry_policy", None, '{"max_attempts":3,"retry_on":["TimeoutError"]}'),),
    ),
    Row(
        # P-02 witness form (c) leaving — one of the three carriers of brief D-11's
        # "termination-witness removal" case. What the diff says is that the slot went; what
        # that *means* is P-02's over one IR and P-12's over two, and P-12 is deferred.
        "variant witness removed",
        edited(variant=Variant(key="result", measure="len")),
        WORK,
        True,
        True,
        (slot("variant", '{"key":"result","measure":"len"}', None),),
    ),
    Row(
        "compensation hook declared",
        WORK,
        edited(compensation=Compensation(hook="rollback")),
        True,
        True,
        (slot("compensation", None, '{"hook":"rollback"}'),),
    ),
    Row(
        # D-025's opaque-body gap, at the diff: the prompt bytes are nowhere in the IR, but
        # the digest they move is a node's, so a prompt edit reads as a contract change.
        "prompt body edited",
        edited(prompt_digest="sha256:" + "a" * 64),
        edited(prompt_digest="sha256:" + "b" * 64),
        True,
        True,
        (
            slot(
                "prompt_digest",
                f'"sha256:{"a" * 64}"',
                f'"sha256:{"b" * 64}"',
            ),
        ),
    ),
    Row(
        "config digest edited",
        edited(config_digest="sha256:" + "c" * 64),
        WORK,
        True,
        True,
        (slot("config_digest", f'"sha256:{"c" * 64}"', None),),
    ),
    # ── The absences a slot-only comparison would miss ──────────────────────────────────
    Row(
        "a contract arrived",
        None,
        WORK,
        False,
        True,
        tuple(
            sorted(
                (
                    slot("effect", None, '["write"]'),
                    slot("input", None, '["task"]'),
                    slot("output", None, '["result"]'),
                ),
                key=SlotChange.sort_key,
            )
        ),
    ),
    Row(
        # ``annotations`` absent and ``annotations: {}`` are different canonical documents
        # ({"id":"work"} against {"annotations":{},"id":"work"}) and so different digests.
        # No slot moved; the presence flags are the whole report.
        "an empty contract object replaced no contract at all",
        None,
        Annotations(),
        False,
        True,
        (),
    ),
    Row(
        "two edits in one contract",
        WORK,
        edited(effect=("billable",), pure=False),
        True,
        True,
        (slot("effect", '["write"]', '["billable"]'), slot("pure", None, "false")),
    ),
]


def _delta(before: WorkflowIR, after: WorkflowIR) -> ContractsDelta:
    """Diff a pair and assert the F bridge to the version engine on the way through."""
    delta = contracts_diff(before, after)
    assert bool(delta) == (Component.F in changed_components(before, after))
    return delta


@pytest.mark.parametrize("row", [pytest.param(row, id=row.name) for row in CONTRACTS])
def test_a_contract_edit_reports_exactly_its_slots(row: Row) -> None:
    delta = _delta(contracts_of(row.before), contracts_of(row.after))

    assert delta == ContractsDelta.of(
        changed=[
            NodeContractChanged(
                node="work",
                present_before=row.present_before,
                present_after=row.present_after,
                slots=row.slots,
            )
        ],
        runtime=RUNTIME_KEPT,
    )
    assert delta.added == () and delta.removed == () and not delta.runtime


@pytest.mark.parametrize("row", [pytest.param(row, id=row.name) for row in CONTRACTS])
def test_the_reverse_contract_diff_mirrors(row: Row) -> None:
    """Swapping the sides swaps every slot's halves and the two presence flags — the delta
    reports a difference in a direction, never a different difference."""
    reverse = _delta(contracts_of(row.after), contracts_of(row.before))

    assert reverse == ContractsDelta.of(
        changed=[
            NodeContractChanged(
                node="work",
                present_before=row.present_after,
                present_after=row.present_before,
                slots=tuple(
                    sorted(
                        (
                            SlotChange(slot=change.slot, before=change.after, after=change.before)
                            for change in row.slots
                        ),
                        key=SlotChange.sort_key,
                    )
                ),
            )
        ],
        runtime=RUNTIME_KEPT,
    )


@pytest.mark.parametrize("row", [pytest.param(row, id=row.name) for row in CONTRACTS])
def test_every_reported_slot_actually_moved(row: Row) -> None:
    """No row reports a slot whose two sides are equal, and every reported change names one
    of the two sides as absent exactly when that side declares nothing there."""
    for change in row.slots:
        assert change.before != change.after
        assert change.added == (change.before is None)
        assert change.removed == (change.after is None)


def test_an_unchanged_contract_reports_nothing() -> None:
    """A workflow against itself, and against an authored re-spelling of itself."""
    assert not _delta(workflow(), workflow())
    assert not _delta(workflow(), workflow(nodes=tuple(reversed(NODES))))


def test_a_contract_edit_on_one_node_leaves_the_others_alone() -> None:
    delta = _delta(workflow(), contracts_of(edited(pure=False)))

    assert [change.node for change in delta.changed] == ["work"]


# ── Node identity: a contract arrives and leaves with its node ───────────────────────────


def test_an_added_node_brings_its_contract() -> None:
    """A node's presence is F as well as S (SD-02 maps ``nodes`` to both): the contract set
    gained a member, empty or not — and the delta says *which* contract arrived."""
    delta = _delta(workflow(), workflow(nodes=(*NODES, node("audit", Annotations(pure=True)))))

    assert delta == ContractsDelta.of(
        added=[NodeContractRef("audit", '{"pure":true}')], runtime=RUNTIME_KEPT
    )


def test_a_node_added_without_a_contract_reports_its_absence() -> None:
    delta = _delta(workflow(), workflow(nodes=(*NODES, node("audit", None))))

    assert delta.added == (NodeContractRef("audit", None),)


def test_a_removed_node_takes_its_contract() -> None:
    delta = _delta(workflow(), workflow(nodes=NODES[:2], finish="work"))

    assert delta.removed == (NodeContractRef("report", '{"input":["result"],"pure":true}'),)
    assert delta.changed == ()


def test_a_renamed_node_is_a_removal_and_an_addition() -> None:
    """IR-SPEC §5.3 makes a rename a new identity, so no contract is ever "carried over" —
    there is no similarity matching anywhere in this engine. The two entries carry the same
    contract text, which is what makes the rename legible without one being invented."""
    renamed = tuple(node("labour", n.annotations) if n.id == "work" else n for n in NODES)
    delta = _delta(workflow(), workflow(nodes=renamed))
    carried = '{"effect":["write"],"input":["task"],"output":["result"]}'

    assert delta == ContractsDelta.of(
        added=[NodeContractRef("labour", carried)],
        removed=[NodeContractRef("work", carried)],
        runtime=RUNTIME_KEPT,
    )


def test_node_ids_report_in_ledger_order() -> None:
    added = (Node(id="\U000106a0"), Node(id="\ue000"), Node(id="audit"))
    delta = _delta(workflow(), workflow(nodes=(*NODES, *added)))

    # Ledger §6 compares UTF-16 code units, not code points: a non-BMP id is a surrogate
    # pair (0xD800..), so it sorts *before* U+E000 — the reverse of code-point order.
    assert [ref.node for ref in delta.added] == ["audit", "\U000106a0", "\ue000"]


# ── The document class this engine refuses ─────────────────────────────────


def test_a_node_id_declared_twice_is_refused_rather_than_collapsed() -> None:
    """IR-SPEC §2.1 makes node-id uniqueness a MUST (ratified DEC-22, resolving the PD-032
    defect this suite's pre-review found). Until the constraint lands on the model itself
    (card IR-07) the models still admit such a document, and keying a delta by id would
    collapse the two entries and report nothing while ``graph_version`` moved — PD-012 makes
    a V.S.F.E label a file name, so an under-reported counter is a second workflow content
    under a file that already holds one. Refused at the boundary instead."""
    doubled = workflow(nodes=(*NODES, node("work", None)))

    with pytest.raises(ValueError, match="declared twice"):
        contracts_diff(workflow(), doubled)
    with pytest.raises(ValueError, match="declared twice"):
        contracts_diff(doubled, workflow())
    with pytest.raises(ValueError, match="declared twice"):
        contracts_diff(doubled, doubled)


def test_the_refusal_cites_the_ratified_rule() -> None:
    """DEC-22's in-repo obligation for this engine: the message names the rule it enforces,
    so a reader hitting it is one search away from §2.1 rather than from an opinion."""
    doubled = workflow(nodes=(*NODES, node("work", None)))

    with pytest.raises(ValueError) as raised:
        contracts_diff(workflow(), doubled)

    assert "IR-SPEC §2.1" in str(raised.value)
    assert "DEC-22" in str(raised.value)


def test_the_refused_document_is_one_the_digest_does_distinguish() -> None:
    """The refusal is not academic: the pair really does move ``graph_version`` and really
    does select components, which is exactly why reporting nothing was the danger — and is
    the PD-032 repro the owner re-executed at ratification."""
    doubled = workflow(nodes=(*NODES, node("work", None)))

    assert graph_version(workflow()) != graph_version(doubled)
    assert changed_components(workflow(), doubled) == frozenset({Component.S, Component.F})


# ── The graph-level runtime block ────────────────────────────────────────────────────────


def test_the_runtime_block_leaving_is_a_contract_change() -> None:
    """P-02 witness form (b) — ``runtime.recursion_limit`` — is the second of the three
    carriers of the "termination-witness removal" case, and it lands under F."""
    delta = _delta(workflow(), workflow(runtime=None))

    assert delta.runtime == RuntimeDelta(
        present_before=True,
        present_after=False,
        slots=(
            slot(
                "recursion_limit",
                '{"justification":"the line is three nodes long","value":10}',
                None,
            ),
        ),
    )
    assert delta.changed == ()


def test_an_emptied_runtime_block_is_kept_apart_from_an_absent_one() -> None:
    """``runtime: {}`` and no ``runtime`` are different canonical documents, so the presence
    flags carry a change the slot list cannot."""
    emptied = _delta(workflow(runtime=Runtime()), workflow(runtime=None))

    assert emptied.runtime.present_before and not emptied.runtime.present_after
    assert emptied.runtime.slots == ()
    assert bool(emptied.runtime)


def test_the_runtime_sub_slots_each_report() -> None:
    after = Runtime(
        recursion_limit=RecursionLimit(value=25, justification="the line is three nodes long"),
        interrupts=Interrupts(before=("work",)),
        checkpointer=Checkpointer(present=True),
    )
    delta = _delta(workflow(), workflow(runtime=after))

    assert delta.runtime.slots == (
        slot("checkpointer", None, '{"present":true}'),
        slot("interrupts", None, '{"before":["work"]}'),
        slot(
            "recursion_limit",
            '{"justification":"the line is three nodes long","value":10}',
            '{"justification":"the line is three nodes long","value":25}',
        ),
    )
    assert delta.runtime.present_before and delta.runtime.present_after


def test_an_empty_interrupts_list_is_not_a_change() -> None:
    """IR-SPEC §6.3: an OPTIONAL array-valued member whose value is ``[]`` is treated as
    absent, so the two spellings share one canonical form — and one delta."""
    assert not _delta(
        workflow(runtime=Runtime(interrupts=Interrupts(before=()))),
        workflow(runtime=Runtime(interrupts=Interrupts())),
    )


# ── Determinism of the report ────────────────────────────────────────────────────────────


@pytest.mark.parametrize("row", [pytest.param(row, id=row.name) for row in CONTRACTS])
def test_diffing_a_contract_twice_yields_one_value(row: Row) -> None:
    first = contracts_diff(contracts_of(row.before), contracts_of(row.after))
    second = contracts_diff(contracts_of(row.before), contracts_of(row.after))

    assert first == second
    assert repr(first) == repr(second)
