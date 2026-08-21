"""The state-schema delta on constructed pairs — keys, facets, both absences, the E bridge.

Each row of :data:`SCHEMAS` is one deliberate edit to the base workflow's Σ (``{task: str,
result: str}``), with the exact :class:`StateDelta` it must produce. Every facet IR-SPEC §2.2
gives a Σ value has a row — ``type``, ``reducer``, ``optional`` — because each is read by a
different consumer and because brief D-11's canonical "read-key removal **or retype**" case
turns on telling a retype apart from a removal-plus-addition.

The bridge to the version engine is asserted on every row: a state delta is non-empty exactly
when :func:`~gebra.versioning.changed_components` selects E. That is the claim
:mod:`gebra.diff.workflow` derives its bump class against, so the two cannot drift apart
silently.

Everything is hand-built IR models (WA-07): no extractor, no substrate, nothing to invoke.
"""

from __future__ import annotations

from typing import NamedTuple

import pytest

from gebra.diff import KeyDeclaration, StateDelta, StateKeyChanged, StateKeyRef, state_diff
from gebra.ir.models import StateField, WorkflowIR
from gebra.versioning import Component, changed_components
from tests.versioning.workflows import STATE, workflow

Schema = dict[str, "str | StateField"]


def declared(**keys: str | StateField) -> Schema:
    """A Σ written inline — ``declared(task="str", result=StateField(type="int"))``."""
    return dict(keys)


def key(
    name: str, type: str, reducer: str | None = None, optional: bool | None = None
) -> StateKeyRef:
    return StateKeyRef(
        key=name, declaration=KeyDeclaration(type=type, reducer=reducer, optional=optional)
    )


class Row(NamedTuple):
    """One constructed Σ pair and the delta it must produce."""

    name: str
    before: Schema | None
    after: Schema | None
    expected: StateDelta


#: The base Σ, and it re-spelled — the surface forms §6.3 normalizes onto one another.
BASE: Schema = dict(STATE)


SCHEMAS: list[Row] = [
    # ── Authored differences the canonical form normalizes away ─────────────────────────
    Row(
        "the same schema",
        BASE,
        BASE,
        StateDelta(present_before=True, present_after=True),
    ),
    Row(
        # §6.3 representation-normalization: a bare ``{type: "str"}`` with no other member
        # collapses to the bare type-name string, so the two spellings are one declaration.
        "a value written in object form",
        BASE,
        declared(task=StateField(type="str"), result="str"),
        StateDelta(present_before=True, present_after=True),
    ),
    Row(
        "the keys written in another order",
        BASE,
        declared(result="str", task="str"),
        StateDelta(present_before=True, present_after=True),
    ),
    # ── Brief D-11's canonical read-key cases ───────────────────────────────────────────
    Row(
        # "removed key `return_date` still read by `book_flight`" — the key leaves Σ while
        # every node's contract stays put, so E moves alone. Whether anything still reads it
        # is P-04's question over one IR; this engine reports the removal and stops there.
        "a read key removed",
        BASE,
        declared(task="str"),
        StateDelta.of(removed=[key("result", "str")], present_before=True, present_after=True),
    ),
    Row(
        "a read key retyped",
        BASE,
        declared(task="str", result="int"),
        StateDelta.of(
            changed=[
                StateKeyChanged(
                    key="result",
                    before=KeyDeclaration(type="str"),
                    after=KeyDeclaration(type="int"),
                )
            ],
            present_before=True,
            present_after=True,
        ),
    ),
    # ── D-11's safe extension: a new optional key ───────────────────────────────────────
    Row(
        "a new optional key",
        BASE,
        {**BASE, "receipt": StateField(type="str", optional=True)},
        StateDelta.of(
            added=[key("receipt", "str", optional=True)], present_before=True, present_after=True
        ),
    ),
    Row(
        "a new required key",
        BASE,
        {**BASE, "receipt": "str"},
        StateDelta.of(added=[key("receipt", "str")], present_before=True, present_after=True),
    ),
    # ── The other two declared facets ───────────────────────────────────────────────────
    Row(
        "a reducer declared",
        BASE,
        declared(task="str", result=StateField(type="str", reducer="operator.add")),
        StateDelta.of(
            changed=[
                StateKeyChanged(
                    key="result",
                    before=KeyDeclaration(type="str"),
                    after=KeyDeclaration(type="str", reducer="operator.add"),
                )
            ],
            present_before=True,
            present_after=True,
        ),
    ),
    Row(
        # ``optional: false`` is a declared flag, not the absence of one: §6.3 collapses a
        # value to the bare string only when it carries *no* optional flag, so the two are
        # different canonical bytes and a real change.
        "an optional flag declared false",
        BASE,
        declared(task="str", result=StateField(type="str", optional=False)),
        StateDelta.of(
            changed=[
                StateKeyChanged(
                    key="result",
                    before=KeyDeclaration(type="str"),
                    after=KeyDeclaration(type="str", optional=False),
                )
            ],
            present_before=True,
            present_after=True,
        ),
    ),
    Row(
        "a key made optional and retyped at once",
        BASE,
        declared(task="str", result=StateField(type="list", optional=True)),
        StateDelta.of(
            changed=[
                StateKeyChanged(
                    key="result",
                    before=KeyDeclaration(type="str"),
                    after=KeyDeclaration(type="list", optional=True),
                )
            ],
            present_before=True,
            present_after=True,
        ),
    ),
    # ── The absences a key-only comparison would miss ───────────────────────────────────
    Row(
        # ``state`` absent and ``state: {}`` are different canonical documents ({} against
        # {"state":{}}) and so different digests. No key moved; the presence flags are the
        # whole report.
        "an empty schema replaced no schema at all",
        None,
        {},
        StateDelta(present_before=False, present_after=True),
    ),
    Row(
        "the schema emptied",
        BASE,
        {},
        StateDelta.of(
            removed=[key("result", "str"), key("task", "str")],
            present_before=True,
            present_after=True,
        ),
    ),
    Row(
        "the schema dropped",
        BASE,
        None,
        StateDelta.of(
            removed=[key("result", "str"), key("task", "str")],
            present_before=True,
            present_after=False,
        ),
    ),
]


def _diff(before: Schema | None, after: Schema | None) -> StateDelta:
    """Diff a pair of schemas and assert the E bridge to the version engine on the way."""
    left: WorkflowIR = workflow(state=before)
    right: WorkflowIR = workflow(state=after)
    delta = state_diff(left, right)
    assert bool(delta) == (Component.E in changed_components(left, right))
    return delta


@pytest.mark.parametrize("row", [pytest.param(row, id=row.name) for row in SCHEMAS])
def test_a_schema_edit_reports_exactly_its_keys(row: Row) -> None:
    assert _diff(row.before, row.after) == row.expected


@pytest.mark.parametrize("row", [pytest.param(row, id=row.name) for row in SCHEMAS])
def test_the_reverse_schema_diff_mirrors(row: Row) -> None:
    """Swapping the sides swaps added with removed, both halves of every change, and the two
    presence flags."""
    reverse = _diff(row.after, row.before)

    assert reverse == StateDelta.of(
        added=row.expected.removed,
        removed=row.expected.added,
        changed=[
            StateKeyChanged(key=change.key, before=change.after, after=change.before)
            for change in row.expected.changed
        ],
        present_before=row.expected.present_after,
        present_after=row.expected.present_before,
    )


def test_a_change_names_which_facet_moved() -> None:
    """``retyped``/``reducer_changed``/``optional_changed`` are what a renderer branches on
    rather than re-deriving — and brief D-11's canonical case names the first of them."""
    retyped = StateKeyChanged(
        key="return_date", before=KeyDeclaration(type="str"), after=KeyDeclaration(type="date")
    )
    reduced = StateKeyChanged(
        key="offers",
        before=KeyDeclaration(type="list"),
        after=KeyDeclaration(type="list", reducer="operator.add"),
    )
    relaxed = StateKeyChanged(
        key="hotel",
        before=KeyDeclaration(type="str"),
        after=KeyDeclaration(type="str", optional=True),
    )

    assert retyped.retyped and not retyped.reducer_changed and not retyped.optional_changed
    assert reduced.reducer_changed and not reduced.retyped and not reduced.optional_changed
    assert relaxed.optional_changed and not relaxed.retyped and not relaxed.reducer_changed


def test_keys_report_in_ledger_order() -> None:
    delta = _diff(BASE, {**BASE, "audit": "str", "\U000106a0": "str", "\ue000": "str"})

    # Ledger §6 compares UTF-16 code units, not code points: a non-BMP key is a surrogate
    # pair (0xD800..), so it sorts *before* U+E000 — the reverse of code-point order.
    assert [ref.key for ref in delta.added] == ["audit", "\U000106a0", "\ue000"]


def test_a_key_removed_and_a_key_added_are_not_a_change() -> None:
    """Σ keys are matched by name and nothing else — there is no rename heuristic here, for
    the same reason IR-SPEC §5.3 gives for nodes."""
    delta = _diff(BASE, declared(task="str", outcome="str"))

    assert delta.added == (key("outcome", "str"),)
    assert delta.removed == (key("result", "str"),)
    assert delta.changed == ()


@pytest.mark.parametrize("row", [pytest.param(row, id=row.name) for row in SCHEMAS])
def test_diffing_a_schema_twice_yields_one_value(row: Row) -> None:
    first = state_diff(workflow(state=row.before), workflow(state=row.after))
    second = state_diff(workflow(state=row.before), workflow(state=row.after))

    assert first == second
    assert repr(first) == repr(second)
