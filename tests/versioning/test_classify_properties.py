"""Property tests for the comparator — the claims the constructed deltas are examples of.

Four claims, each of which a table of hand-written pairs can only illustrate:

* **The three components cover the whole hash scope.** Recombining the S, F and E slices
  reproduces the canonical document except ``ir_version`` — so no change to a workflow can
  move the digest without moving a counter, whatever the change was.
* **Every core-IR field has a component** (or is the one documented exception). The walk is
  over the *live* ``WorkflowIR`` model tree, so a field added to the IR without a row in
  :data:`~gebra.versioning.classify.FIELD_COMPONENTS` fails here rather than being
  classified by accident.
* **Equal content, no bump.** Two IRs with the same ``graph_version`` select no component.
* **The comparison is symmetric and reflexive** — it reports domains, not directions.

Everything here is pure data (WA-07): strategies build IR models, and the comparison is a
function of two of them.
"""

from __future__ import annotations

import string
import types
from collections.abc import Iterator
from typing import Annotated, Any, Union, get_args, get_origin

from hypothesis import given
from hypothesis import strategies as st
from pydantic import BaseModel

from gebra.ir import dump_json, load_json
from gebra.ir.canonical import canonical_foreign_bytes, graph_version
from gebra.ir.models import (
    Annotations,
    Checkpointer,
    Compensation,
    ConditionalEdge,
    DeterministicSpec,
    IdempotentKey,
    Interrupts,
    Node,
    NormalEdge,
    RecursionLimit,
    RetryPolicy,
    Runtime,
    StateField,
    Variant,
    WorkflowIR,
)
from gebra.versioning import (
    FIELD_COMPONENTS,
    Component,
    canonical_view,
    changed_components,
    component_slice,
    components_for_path,
)

#: ASCII text — NFC by construction, so a generated document always has a canonical form
#: (IR-SPEC §6.1 step 5 refuses a non-NFC identifier, and this suite is about versions).
TEXT = st.text(alphabet=string.ascii_letters + string.digits + "_", min_size=1, max_size=6)

#: Integers inside the I-JSON exact range (IR-SPEC §6.3; PD-004).
INTEGERS = st.integers(min_value=-(2**53 - 1), max_value=2**53 - 1)

#: Finite doubles. Bounded to the same range: §6.3 reads an *integral* double as an integer,
#: so ``9007199254740992.0`` is an out-of-range integer and has no canonical form.
FLOATS = st.floats(
    allow_nan=False, allow_infinity=False, min_value=-(2**53 - 1), max_value=2**53 - 1
)

#: Node ids: plain names and one nested path, both §5-legal without escaping.
NODE_IDS = TEXT | st.builds(lambda parent, child: f"{parent}/{child}", TEXT, TEXT)


def foreign_json(max_leaves: int = 8) -> st.SearchStrategy[Any]:
    """The ``args_schema`` interior: a JSON Schema object, carried verbatim (IR-SPEC §3.1).

    The one place in ir 1.0 where the JSON *type* at a path is unconstrained, so it is the
    one place where two documents can differ in a way Python equality cannot see
    (``True == 1``). Every claim below is quantified over it deliberately.
    """
    leaves = st.none() | st.booleans() | INTEGERS | FLOATS
    return st.recursive(
        leaves | TEXT,
        lambda children: (
            st.lists(children, max_size=3) | st.dictionaries(TEXT, children, max_size=3)
        ),
        max_leaves=max_leaves,
    )


@st.composite
def node_contracts(draw: st.DrawFn) -> Annotations:
    """A node contract with a reachable value in every slot the frozen model carries."""
    return Annotations(
        pure=draw(st.none() | st.booleans()),
        effect=draw(st.none() | st.lists(TEXT, max_size=2).map(tuple)),
        idempotent=draw(st.none() | st.booleans() | st.builds(IdempotentKey, key=TEXT)),
        deterministic=draw(
            st.none()
            | st.booleans()
            | st.builds(
                DeterministicSpec,
                seed=INTEGERS,
                temperature=st.none() | FLOATS,
            )
        ),
        input=draw(st.none() | st.lists(TEXT, max_size=2).map(tuple)),
        output=draw(st.none() | st.lists(TEXT, max_size=2).map(tuple)),
        source=draw(st.none() | TEXT),
        map=draw(st.none() | TEXT),
        args_schema=draw(st.none() | st.dictionaries(TEXT, foreign_json(), max_size=3)),
        retry_policy=draw(
            st.none()
            | st.builds(
                RetryPolicy, max_attempts=INTEGERS, retry_on=st.lists(TEXT, max_size=2).map(tuple)
            )
        ),
        variant=draw(st.none() | st.builds(Variant, key=TEXT, measure=TEXT)),
        compensation=draw(st.none() | st.builds(Compensation, hook=TEXT)),
        prompt_digest=draw(st.none() | TEXT),
        config_digest=draw(st.none() | TEXT),
    )


@st.composite
def workflow_irs(draw: st.DrawFn) -> WorkflowIR:
    """A generated ``WorkflowIR`` — shape-valid and canonicalizable, not necessarily
    well-formed as a graph (P-01's question, not this engine's).

    **Not the same strategy as** :func:`gebra.testing.strategies.workflow_irs`, and not
    superseded by it: that one is *well-formed*, so every reference resolves and P-01 passes,
    which is what the validator metaproperties need and what a mutation operator starts from.
    This one is deliberately wider — a dangling ``to``, an unreachable node and an orphan are
    all in its range — because the version engine and the diff are defined over any
    canonicalizable document, and narrowing them to P-01-clean input would shrink the shape
    space these properties are quantified over. Two different jobs, two strategies.
    """
    ids = draw(st.lists(NODE_IDS, min_size=1, max_size=3, unique=True))
    nodes = tuple(
        Node(id=node_id, annotations=draw(st.none() | node_contracts())) for node_id in ids
    )
    targets = st.sampled_from([*ids, "END"])
    edges: tuple[NormalEdge | ConditionalEdge, ...] = tuple(
        NormalEdge(
            kind="normal",
            **{"from": node_id},
            to=draw(targets),
            condition=draw(st.none() | TEXT),
        )
        if draw(st.booleans())
        else ConditionalEdge(
            kind="conditional",
            **{"from": node_id},
            condition=draw(st.none() | TEXT),
            path_map=draw(st.dictionaries(TEXT, targets, max_size=2)),
        )
        for node_id in ids
    )
    state = draw(
        st.none()
        | st.dictionaries(
            TEXT,
            TEXT | st.builds(StateField, type=TEXT, optional=st.none() | st.booleans()),
            max_size=3,
        )
    )
    runtime = draw(
        st.none()
        | st.builds(
            Runtime,
            recursion_limit=st.none()
            | st.builds(RecursionLimit, value=INTEGERS, justification=TEXT),
            interrupts=st.none()
            | st.builds(Interrupts, before=st.lists(st.sampled_from(ids), max_size=2).map(tuple)),
            checkpointer=st.none() | st.builds(Checkpointer, present=st.booleans()),
        )
    )
    return WorkflowIR(
        ir_version="1.0",
        entry=draw(st.sampled_from(ids) | st.just(tuple(ids))),
        finish=draw(st.sampled_from(ids) | st.just(tuple(ids))),
        state=state,
        nodes=nodes,
        edges=edges,
        runtime=runtime,
    )


# ── The three components cover the hash scope ────────────────────────────────────────────


def _recombined(view: dict[str, Any]) -> dict[str, Any]:
    """The canonical document rebuilt from its three component slices."""
    topology = component_slice(view, Component.S)
    contracts = component_slice(view, Component.F)
    schema = component_slice(view, Component.E)

    assert topology["nodes"] == [node_id for node_id, _contract in contracts["nodes"]]

    rebuilt: dict[str, Any] = {
        "entry": topology["entry"],
        "finish": topology["finish"],
        "nodes": [
            {"id": node_id, **({} if contract is None else {"annotations": contract})}
            for node_id, contract in contracts["nodes"]
        ],
        "edges": topology["edges"],
    }
    if schema["state"] is not None:
        rebuilt["state"] = schema["state"]
    if contracts["runtime"] is not None:
        rebuilt["runtime"] = contracts["runtime"]
    return rebuilt


@given(ir=workflow_irs())
def test_the_three_slices_rebuild_the_whole_canonical_document(ir: WorkflowIR) -> None:
    """Everything the digest is taken over is inside S, F or E — except ``ir_version``,
    which IR-SPEC §8 puts in the other migration regime entirely. So a change that moves
    ``graph_version`` cannot leave every counter standing."""
    view = canonical_view(ir)
    without_the_format_version = {
        name: value for name, value in view.items() if name != "ir_version"
    }

    # By bytes through the §6 emitter, the same identity the comparison itself uses.
    assert canonical_foreign_bytes(_recombined(view)) == canonical_foreign_bytes(
        without_the_format_version
    )


@given(left=workflow_irs(), right=workflow_irs())
def test_a_digest_change_always_selects_a_component(left: WorkflowIR, right: WorkflowIR) -> None:
    """The covering claim, stated over pairs: different content, at least one counter."""
    if graph_version(left) != graph_version(right):
        assert changed_components(left, right) != frozenset()


# ── Equal content, no bump ───────────────────────────────────────────────────────────────


@given(ir=workflow_irs())
def test_a_workflow_never_bumps_against_itself(ir: WorkflowIR) -> None:
    assert changed_components(ir, ir) == frozenset()


@given(ir=workflow_irs())
def test_a_workflow_never_bumps_against_a_reserialized_copy(ir: WorkflowIR) -> None:
    """A round trip through the serialized form is how the *stored* IR reaches a comparison
    in the first place — a snapshot is read back before the working IR is compared to it."""
    reloaded = load_json(WorkflowIR, dump_json(ir))

    assert graph_version(reloaded) == graph_version(ir)
    assert changed_components(ir, reloaded) == frozenset()


@given(ir=workflow_irs())
def test_reordering_what_the_canonical_form_sorts_is_not_a_change(ir: WorkflowIR) -> None:
    """§6.2 normalizes authored array order away, so the version engine does not see it —
    a re-authored file is not a new version."""
    reordered = WorkflowIR(
        ir_version=ir.ir_version,
        entry=ir.entry,
        finish=ir.finish,
        state=ir.state,
        nodes=tuple(reversed(ir.nodes)),
        edges=tuple(reversed(ir.edges)),
        runtime=ir.runtime,
    )

    assert changed_components(ir, reordered) == frozenset()


# ── Domains, not directions ──────────────────────────────────────────────────────────────


@given(left=workflow_irs(), right=workflow_irs())
def test_the_comparison_is_symmetric(left: WorkflowIR, right: WorkflowIR) -> None:
    assert changed_components(left, right) == changed_components(right, left)


@given(left=workflow_irs(), right=workflow_irs())
def test_v_is_never_selected(left: WorkflowIR, right: WorkflowIR) -> None:
    assert Component.V not in changed_components(left, right)


# ── Every core-IR field has a component ──────────────────────────────────────────────────


def _nested_models(annotation: Any) -> Iterator[type[BaseModel]]:
    """The model classes reachable through a field annotation — through ``Annotated``,
    optionals and unions, and the ``tuple[...]``/``dict[...]`` containers the IR uses."""
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        yield annotation
        return
    origin = get_origin(annotation)
    # ``X | None`` is a ``types.UnionType``, not a ``typing.Union`` — both spellings are in
    # the IR's field annotations, and missing one silently stops the walk.
    if origin in {Annotated, Union, types.UnionType, tuple, list, dict}:
        for argument in get_args(annotation):
            yield from _nested_models(argument)


def _field_paths(model: type[BaseModel], prefix: tuple[str, ...] = ()) -> Iterator[tuple[str, ...]]:
    """Every field path of ``model``, by the name the canonical form writes (so ``from``,
    the alias, rather than ``from_``), with array indices left out."""
    for name, field in model.model_fields.items():
        path = (*prefix, field.alias or name)
        yield path
        for nested in _nested_models(field.annotation):
            yield from _field_paths(nested, path)


def test_every_core_ir_field_classifies() -> None:
    """The anti-drift check: a new IR field with no row in ``FIELD_COMPONENTS`` fails here.

    ``ir_version`` is the one field that classifies to no component, and it says so
    explicitly rather than by omission (IR-SPEC §8: a format migration is not a workflow
    migration).
    """
    paths = list(_field_paths(WorkflowIR))

    assert len(paths) > 30, "the walk found nothing — it stopped recursing"
    for path in paths:
        components = components_for_path(path)
        assert components <= frozenset(Component.derived()), path
    assert [path for path in paths if not components_for_path(path)] == [("ir_version",)]


def test_every_top_level_core_ir_field_has_its_own_row() -> None:
    """The table is stated at the top level rather than left to a fallback, so adding a
    field to the IR is a decision someone has to make here."""
    top_level = {path[0] for path in FIELD_COMPONENTS}

    assert top_level == {field.alias or name for name, field in WorkflowIR.model_fields.items()}
