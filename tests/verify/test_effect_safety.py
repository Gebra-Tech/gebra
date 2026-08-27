"""P-06 ``effect-safety`` against the vendored corpus (PROPERTY-CATALOG-SPEC §6).

The protection lattice: which trigger-tagged nodes carry an obligation, which declarations
discharge it, and which region flavour the finding names — asserted as **model equality**
against the fixtures' own ``expected:`` blocks (A6 PC-6). The golden harness owns that
comparison corpus-wide (:mod:`gebra.testing.harness`); as in ``test_dataflow_completeness.py``
this module reaches the fixtures through PyYAML and the models directly, so it is an
*independent* second path to the same assertion rather than a caller of the harness that would
pass whenever the harness agreed with itself.

Five things this module is careful about, because each is a place P-06 could look right and be
wrong:

* **The graph is asked of VAL-03, and that is asserted rather than reviewed.** §6.4 opens
  "Phases 0 and 2 are steps (1)–(2) of the SCC-condensation procedure in
  TERMINATION-WITNESS-SPEC — **cited, not redefined**". A recording proxy over a shared
  :class:`~gebra.verify.graph.GraphModel` pins the *exact* surface P-06 reads, and the shared
  model's own memos are inspected after a run: the Tarjan partition and every emitted anchor
  are found in its caches, which is direct evidence they were not recomputed locally.
* **Every arm of the DEC-13 region rule is separated by a fixture that would flip.** The send
  closure is what makes ``mixed/09`` a retry region and its absence is what keeps
  ``negative-02`` a plain cycle; both are asserted, and so are the two variant rules PD-009
  rejected — each is re-derived here and shown to misclassify exactly the fixtures PD-009 said
  it would.
* **Protection is checked for binding, in both directions.** A key that is not a declared read
  (``mixed/06``) and a hook that names no node are *not* protection; a key that is and a hook
  that does are. The negative controls are built beside the positives so neither passes for the
  wrong reason.
* **The two §6.7 gap shapes the corpus lacks are built here.** DEC-13 left the gap-fixture half
  of §6.7 (v) open as a WA-04 item — a ``retry_policy``-only retry region with no cycle, and a
  dangling compensation hook. Both are exercised as hand-built IRs, with the registry-closure
  consequence (no new condition ID) asserted rather than assumed.
* **The condition-ID registry stays closed.** P-07's ``idempotency-key-not-in-declared-reads``
  is the diagnostic ``mixed/06`` is *about*, and P-06 must never emit it. That is asserted three
  ways: the registry refuses it to this property, no report over the whole corpus carries it,
  and the emission constructor raises.

WA-07: nothing here executes a workflow, a node, or a network call. Fixtures are read with
PyYAML's safe loader; the ``ir:`` block is validated into the frozen IR models and read as data;
``source_snippet`` is never touched.
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from collections import deque
from pathlib import Path
from typing import Any

import pytest
import yaml

from gebra.ir import WorkflowIR
from gebra.ir.identity import is_valid_node_id
from gebra.verify import (
    CoFailure,
    EffectSafetyWitness,
    Failure,
    P06EffectRecord,
    P06NodeLocation,
    PropertyReport,
    build_graph_model,
    condition,
    conditions_for,
    emit_failure,
    is_implemented,
    models_equivalent,
    run_property,
    to_data,
    validate_location,
    validate_report,
)
from gebra.verify.conditions import ConditionOwnershipError, NonEmittableConditionError
from gebra.verify.graph import GraphModel, ledger_sort_key
from gebra.verify.properties import effect_safety
from gebra.verify.properties.effect_safety import (
    IRREVERSIBLE_WITH_KEYLESS_IDEMPOTENT,
    PROPERTY_SLUG,
    TRIGGER_TAGS,
    UNPROTECTED_EFFECT_IN_CYCLE,
    UNPROTECTED_EFFECT_IN_RETRY_REGION,
    check_effect_safety,
)
from tests.conftest import FIXTURES_DIR

#: The eight P-06 property fixtures (§6.6's six + the DEC-16 negatives, TE-14), by path.
FIXTURES: tuple[str, ...] = (
    "effect-safety/positive-01-keyed-idempotent-billable-retry.yaml",
    "effect-safety/positive-02-irreversible-outside-cycle.yaml",
    "effect-safety/positive-03-compensated-billable-hold-loop.yaml",
    "effect-safety/negative-01-billable-in-unguarded-retry.yaml",
    "effect-safety/negative-02-irreversible-in-refinement-cycle.yaml",
    "effect-safety/negative-03-keyless-idempotent-on-irreversible.yaml",
    "effect-safety/negative-04-retry-policy-annotation-no-cycle-unprotected.yaml",
    "effect-safety/negative-05-dangling-compensation-hook.yaml",
)

POSITIVES: tuple[str, ...] = FIXTURES[:3]
NEGATIVES: tuple[str, ...] = FIXTURES[3:]

#: The four mixed-corpus members §6.6 names as exercising P-06.
MIXED_01 = "mixed/01-witnessed-cycle-with-unkeyed-billable-node.yaml"
MIXED_06 = "mixed/06-irreversible-cycle-idempotency-key-not-read.yaml"
MIXED_09 = "mixed/09-send-fanout-billable-no-idempotency-in-retry.yaml"
MIXED_10 = "mixed/10-all-properties-pass-healthy-research-pipeline.yaml"

#: The three §0.4 condition IDs P-06 owns — §6.3: "the registry is closed, so the validator
#: may emit no other string".
P06_CONDITIONS: frozenset[str] = frozenset(
    {
        IRREVERSIBLE_WITH_KEYLESS_IDEMPOTENT,
        UNPROTECTED_EFFECT_IN_RETRY_REGION,
        UNPROTECTED_EFFECT_IN_CYCLE,
    }
)

#: P-07's RESERVED diagnostic for ``mixed/06``'s bad key — held for its property, never P-06's.
P07_BAD_KEY = "idempotency-key-not-in-declared-reads"


# ── Fixture loading (§0.3's rule, spelled out — the second, independent path) ────────────


def _load(relative: str) -> dict[str, Any]:
    document = yaml.safe_load((FIXTURES_DIR / relative).read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    return document


def _ir_of(relative: str, key: str = "ir") -> WorkflowIR:
    """A fixture's IR block, validated into the frozen models (JSON mode, §2.5 note 4)."""
    return WorkflowIR.model_validate_json(json.dumps(_load(relative)[key]))


def _expected_report(relative: str) -> PropertyReport:
    """The fixture's ``expected:`` block as P-06's report — §0.3's loading rule verbatim."""
    return validate_report({"property": PROPERTY_SLUG, **_load(relative)["expected"]})


def _corpus_irs() -> list[tuple[str, WorkflowIR]]:
    """Every IR snapshot in the vendored corpus, both members of each evolution pair."""
    found: list[tuple[str, WorkflowIR]] = []
    for path in sorted(FIXTURES_DIR.glob("*/*.yaml")):
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        for key in ("ir", "ir_before", "ir_after"):
            block = document.get(key)
            if block:
                identity = f"{path.parent.name}/{path.stem}:{key}"
                found.append((identity, WorkflowIR.model_validate_json(json.dumps(block))))
    return found


CORPUS: list[tuple[str, WorkflowIR]] = _corpus_irs()
CORPUS_IDS: list[str] = [identity for identity, _ in CORPUS]


# ── Building IRs by hand, for the §6.7 edge cases the corpus does not carry ──────────────


def _ir(
    *,
    entry: str,
    finish: str,
    nodes: dict[str, dict[str, Any]],
    edges: list[dict[str, Any]],
    state: dict[str, Any] | None = None,
) -> WorkflowIR:
    """An IR carrying topology plus the five annotation slots §6.3 lists."""
    return WorkflowIR.model_validate_json(
        json.dumps(
            {
                "ir_version": "1.0",
                "entry": entry,
                "finish": finish,
                **({"state": state} if state is not None else {}),
                "nodes": [
                    {"id": name, "annotations": annotations} for name, annotations in nodes.items()
                ],
                "edges": edges,
            }
        )
    )


def _condition_ids(report: PropertyReport) -> tuple[str, ...]:
    """Every condition ID a report states, primary first then its same-property co-failures."""
    failure = report.failure
    if failure is None:
        return ()
    return (
        failure.property_condition,
        *(record.property_condition for record in failure.co_failures or ()),
    )


def _records(report: PropertyReport) -> tuple[tuple[str, Any], ...]:
    """The ``(condition ID, location)`` pairs a report states — the harness's PR-2 view."""
    failure = report.failure
    if failure is None:
        return ()
    return (
        (failure.property_condition, failure.location),
        *((record.property_condition, record.location) for record in failure.co_failures or ()),
    )


# ── Acceptance box 1: the corpus reproduces, model for model ─────────────────────────────


@pytest.mark.parametrize("relative", FIXTURES, ids=[name.split("/")[1][:11] for name in FIXTURES])
def test_the_validator_reproduces_the_fixture_report(relative: str) -> None:
    """§0.3/A6 PC-6: one model, two duties — the validator's output and the fixture's
    ``expected:`` block validate into the same class and compare as models.

    Compared against the **raw** block, nothing normalized on either side, so a validator that
    only agreed after a helper had massaged it would fail here.
    """
    produced = check_effect_safety(_ir_of(relative))

    assert models_equivalent(produced, _expected_report(relative)), to_data(produced)


@pytest.mark.parametrize("relative", FIXTURES, ids=[name.split("/")[1][:11] for name in FIXTURES])
def test_the_report_is_spec_shaped_and_round_trips(relative: str) -> None:
    """PC-4: the report serializes with ``None``-valued optionals dropped and reloads equal.

    That is the property a fixture's ``expected:`` block depends on — every field the fixture
    omits is a field the validator must not serialize.
    """
    produced = check_effect_safety(_ir_of(relative))

    assert models_equivalent(validate_report(to_data(produced)), produced)


@pytest.mark.parametrize("relative", POSITIVES, ids=[name.split("/")[1][:11] for name in POSITIVES])
def test_a_positive_passes_with_the_section_6_3_witness(relative: str) -> None:
    """A pass carries an ``EffectSafetyWitness`` and no failure at all (§0.3's xor)."""
    report = check_effect_safety(_ir_of(relative))

    assert report.result == "pass"
    assert isinstance(report.witness, EffectSafetyWitness)
    assert report.failure is None


@pytest.mark.parametrize("relative", NEGATIVES, ids=[name.split("/")[1][:11] for name in NEGATIVES])
def test_a_negative_fails_with_a_p06_condition_and_no_witness(relative: str) -> None:
    """A fail carries a ``Failure`` anchored on a ``P06NodeLocation`` and no witness."""
    report = check_effect_safety(_ir_of(relative))

    assert report.result == "fail"
    assert report.witness is None
    failure = report.failure
    assert isinstance(failure, Failure)
    assert isinstance(failure.location, P06NodeLocation)
    assert failure.property_condition in P06_CONDITIONS


def test_the_mixed_01_primary_projection_reproduces() -> None:
    """``mixed/01``'s PR-1 share: the expected block with the P-07 co-failure removed.

    The projection is recomputed here from the raw document rather than taken from the harness,
    so the two paths are genuinely independent. What is left is P-06's whole report — a
    witnessed cycle is not a safe one.
    """
    document = _load(MIXED_01)
    failure = {
        key: value for key, value in document["expected"]["failure"].items() if key != "co_failures"
    }
    expected = validate_report(
        {"property": PROPERTY_SLUG, "result": document["expected"]["result"], "failure": failure}
    )

    produced = check_effect_safety(_ir_of(MIXED_01))

    assert models_equivalent(produced, expected), to_data(produced)
    assert _condition_ids(produced) == (UNPROTECTED_EFFECT_IN_RETRY_REGION,)


def test_the_mixed_09_primary_projection_reproduces_with_the_send_fanout_evidence() -> None:
    """``mixed/09``'s PR-1 share — the ``fanout: send`` case, with its advisory dropped.

    The P-09 advisory and the P-07 co-failure are both other properties' records, which
    ``emit_co_failure``'s ownership check forbids P-06 from emitting; what P-06 owns is the
    primary, including the ``fanout: send`` evidence that says the unprotected effect is
    multiplied by the ``Send`` fan-out as well as by the retry rounds.
    """
    document = _load(MIXED_09)
    failure = {
        key: value
        for key, value in document["expected"]["failure"].items()
        if key not in {"co_failures", "advisories"}
    }
    expected = validate_report(
        {"property": PROPERTY_SLUG, "result": document["expected"]["result"], "failure": failure}
    )

    produced = check_effect_safety(_ir_of(MIXED_09))

    assert models_equivalent(produced, expected), to_data(produced)
    location = produced.failure.location if produced.failure else None
    assert isinstance(location, P06NodeLocation)
    assert (location.node, location.fanout) == ("book_segment", "send")


def test_the_mixed_10_witness_entry_reproduces() -> None:
    """``mixed/10``'s PR-4 share: the run-level multi-property witness's P-06 entry.

    The corpus's one all-properties-pass fixture. It is the strongest over-flagging guard P-06
    has: the IR carries a cycle, a parallel fan-out, a billable effect and two keyed-idempotent
    network fetches, and the only record the witness may carry is ``publish_digest``'s — the
    ``network``-only fetches create no obligation.
    """
    entry = _load(MIXED_10)["expected"]["witness"]["properties"][PROPERTY_SLUG]
    expected = validate_report({"property": PROPERTY_SLUG, "result": "pass", "witness": entry})

    produced = check_effect_safety(_ir_of(MIXED_10))

    assert models_equivalent(produced, expected), to_data(produced)
    witness = produced.witness
    assert isinstance(witness, EffectSafetyWitness)
    assert tuple(record.node for record in witness.effects) == ("publish_digest",)


# ── Acceptance box 1, second half: mixed/06's co-failure encoding ────────────────────────


def test_the_mixed_06_co_failure_records_reproduce_as_a_multiset() -> None:
    """``mixed/06``'s PR-2 share: P-06 rides another property's report as a ``co_failures``
    entry, so what is comparable is the ``(condition ID, location)`` records.

    Both sides are built here — the expected records straight off the raw document, the produced
    ones off P-06's own report — and neither is normalized. The point of the fixture is the
    interaction: ``issue_refund`` *looks* protected, and P-06 must not take the annotation at
    face value.
    """
    expected = tuple(
        (record["property_condition"], validate_location(record["location"]))
        for record in _load(MIXED_06)["expected"]["failure"]["co_failures"]
        if record["property"] == PROPERTY_SLUG
    )

    produced = _records(check_effect_safety(_ir_of(MIXED_06)))

    assert len(produced) == len(expected) == 1
    assert produced[0][0] == expected[0][0] == UNPROTECTED_EFFECT_IN_RETRY_REGION
    assert models_equivalent(produced[0][1], expected[0][1]), to_data(produced[0][1])


def test_the_p07_reserved_id_is_honored_and_never_emitted() -> None:
    """``mixed/06``'s bad key is P-07's diagnostic; P-06 reports the node as unprotected.

    §6.3 states the boundary — "P-06 owns effect-class protection, P-07 owns purity/idempotence
    coherence" — and §0.4 keeps ``idempotency-key-not-in-declared-reads`` RESERVED, "held for
    their properties … MUST NOT be reused for anything else". Three independent enforcements:
    the registry entry itself, the emission constructor, and P-06's own output.
    """
    anchor = P06NodeLocation(kind="node", node="issue_refund", effect=("irreversible",))

    entry = condition(P07_BAD_KEY)
    assert (entry.tier, entry.property_slug, entry.emittable) == (
        "reserved",
        "retry-coherence",
        False,
    )

    # Two gates, and the RESERVED tier is the one that fires first: a held name is not
    # emittable by *anybody*, so P-06 never reaches the ownership check on it. Ownership is
    # asserted separately, on a name that is ratified and belongs to another property.
    with pytest.raises(NonEmittableConditionError):
        emit_failure(PROPERTY_SLUG, P07_BAD_KEY, anchor)
    with pytest.raises(ConditionOwnershipError):
        emit_failure(PROPERTY_SLUG, "read-key-never-written-on-path", anchor)

    assert P07_BAD_KEY not in _condition_ids(check_effect_safety(_ir_of(MIXED_06)))


@pytest.mark.parametrize(("identity", "ir"), CORPUS, ids=CORPUS_IDS)
def test_no_corpus_snapshot_makes_p06_emit_a_string_outside_its_three_ids(
    identity: str, ir: WorkflowIR
) -> None:
    """§6.3: "the registry is closed, so the validator may emit no other string".

    Run over every IR snapshot in the corpus, both members of each evolution pair — the widest
    input surface available without authoring one — and every condition ID that comes back is
    one of P-06's three. ``ConditionId`` is a ``Literal`` so an unregistered string could not be
    built at all; what this adds is that no *registered* name belonging to another property
    (P-07's two, most of all) is ever reached.
    """
    assert set(_condition_ids(check_effect_safety(ir))) <= P06_CONDITIONS, identity


# ── Acceptance box 2: the graph machinery is VAL-03's, not redefined ─────────────────────


def test_the_shared_model_supplies_the_partition_and_every_anchor() -> None:
    """§6.4: Phases 0 and 2 are "cited, not redefined" — asserted through VAL-03's own memos.

    :class:`~gebra.verify.graph.GraphModel` memoizes its Tarjan partition and each anchor cycle,
    so their *presence* in a model P-06 has run over is direct evidence they were asked of it
    rather than recomputed locally. The anchors found in the cache are then compared to the ones
    the report carries, key for key, which closes the other half: a locally computed anchor that
    happened to agree would still leave the cache empty.
    """
    shared = build_graph_model(_ir_of(MIXED_09), carry_unresolved_references=False)
    assert "components" not in shared.__dict__

    report = check_effect_safety(_ir_of(MIXED_09), model=shared)

    assert "components" in shared.__dict__, "the Tarjan pass was not asked of the shared model"
    location = report.failure.location if report.failure else None
    assert isinstance(location, P06NodeLocation)
    assert location.cycle is not None
    assert shared._anchor_cache[location.node] == location.cycle


def test_the_module_asks_the_shared_model_for_exactly_this_surface() -> None:
    """The whole graph surface P-06 reads, pinned — a recording proxy over the shared model.

    Anything P-06 needed and did not find here it would have had to derive itself, so the set is
    the machine-checkable form of "graph machinery is cited from VAL-03, not redefined". Every
    member is VAL-03's: the resolvable-subgraph check (``carried``), $V$ (``node_ids``), the
    expanded edge list, the Tarjan partition, the multigraph in-edge view for ``fanout``, and
    the anchor.

    Two fixtures, unioned, because a single one under-reports: ``node_ids`` is read only to
    resolve a declared compensation hook, which ``mixed/09`` has none of and ``positive-03``
    is the corpus's one example of.
    """
    touched: set[str] = set()
    hooked = "effect-safety/positive-03-compensated-billable-hold-loop.yaml"

    for relative in (MIXED_09, hooked):
        shared = build_graph_model(_ir_of(relative), carry_unresolved_references=False)

        class _Recorder:
            def __init__(self, wrapped: GraphModel) -> None:
                self._wrapped = wrapped

            def __getattr__(self, name: str) -> Any:
                touched.add(name)
                return getattr(self._wrapped, name)

        report = check_effect_safety(_ir_of(relative), model=_Recorder(shared))  # type: ignore[arg-type]
        assert models_equivalent(report, check_effect_safety(_ir_of(relative)))

    assert touched == {"anchor_cycle", "carried", "components", "edges", "in_edges", "node_ids"}


def test_the_module_imports_its_graph_primitives_and_nothing_else() -> None:
    """The import set is exact, so a second graph implementation cannot arrive unnoticed.

    ``networkx`` is the specific thing this refuses: the catalog's primitive rows are
    implementability checklists, and ``tests/verify/test_base.py`` keeps it out of
    ``import gebra.verify``'s closure entirely.
    """
    tree = ast.parse(Path(effect_safety.__file__).read_text(encoding="utf-8"))
    imported = {
        (node.module or "").split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    } | {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }

    assert imported == {"__future__", "collections", "gebra", "typing"}


@pytest.mark.parametrize(("identity", "ir"), CORPUS, ids=CORPUS_IDS)
def test_a_shared_model_and_a_private_one_give_the_same_report(
    identity: str, ir: WorkflowIR
) -> None:
    """``verify()`` will build one model for every topology validator; sharing changes nothing.

    Two builds of one IR are equal values (VAL-03), so this is the property that lets VAL-11 pay
    for the build once — asserted over the whole corpus rather than argued.
    """
    shared = build_graph_model(ir, carry_unresolved_references=False)

    assert models_equivalent(check_effect_safety(ir, model=shared), check_effect_safety(ir)), (
        identity
    )


def test_a_model_carrying_phantoms_is_refused() -> None:
    """§0.3 gives P-06 the degradation convention "P-06 skips the edge" — P-02's and P-04's
    carried-phantom model is a different convention and is refused, not silently mis-analysed.
    """
    ir = _ir_of("mixed/04-dangling-path-map-target-orphans-downstream-reader.yaml")
    carried = build_graph_model(ir, carry_unresolved_references=True)
    assert carried.carried

    with pytest.raises(ValueError, match="P-06 skips the edge"):
        check_effect_safety(ir, model=carried)


# ── Phase 3 — the DEC-13 region rule, and the two variants PD-009 rejected ───────────────


def _reference_regions(model: GraphModel, *, send_closure: bool) -> frozenset[str]:
    """§6.4 Phase 3's ``T(S)``, re-derived here from the ruled text alone.

    Written against the DEC-13 statement rather than against the validator, so agreement is
    evidence. ``send_closure=False`` is PD-009's rejected option C — "only the literal target of
    the re-entry conditional edge is retry".
    """
    components = model.components
    inside: set[str] = set()
    for edge in model.edges:
        index = components.index(edge.source)
        if (
            edge.kind == "conditional"
            and index == components.index(edge.target)
            and index in components.nontrivial
        ):
            inside.add(edge.target)
    if not send_closure:
        return frozenset(inside)
    queue = deque(inside)
    while queue:
        vertex = queue.popleft()
        for edge in model.out_edges(vertex):
            if (
                edge.kind == "send"
                and edge.target not in inside
                and components.same_component(vertex, edge.target)
            ):
                inside.add(edge.target)
                queue.append(edge.target)
    return frozenset(inside)


@pytest.mark.parametrize(
    ("relative", "node", "region"),
    (
        ("effect-safety/negative-01-billable-in-unguarded-retry.yaml", "book_flight", "retry"),
        (
            "effect-safety/negative-02-irreversible-in-refinement-cycle.yaml",
            "submit_change_request",
            "cycle",
        ),
        ("effect-safety/positive-01-keyed-idempotent-billable-retry.yaml", "book_hotel", "retry"),
        ("effect-safety/positive-02-irreversible-outside-cycle.yaml", "charge_card", "acyclic"),
        (
            "effect-safety/positive-03-compensated-billable-hold-loop.yaml",
            "place_hotel_hold",
            "cycle",
        ),
        (MIXED_09, "book_segment", "retry"),
        (MIXED_10, "publish_digest", "retry"),
    ),
)
def test_the_ratified_region_rule_classifies_each_corpus_effect_node(
    relative: str, node: str, region: str
) -> None:
    """The four PD-009 traces plus three more, re-derived from the ruled text.

    ``T(S)`` is recomputed here from DEC-13's statement, and the region it implies is compared
    with what the validator put in the report — witness record or failure condition. Neither the
    expected region nor the ``T(S)`` computation comes from the validator.
    """
    model = build_graph_model(_ir_of(relative), carry_unresolved_references=False)
    reference = _reference_regions(model, send_closure=True)
    in_cycle = model.components.is_nontrivial(node)
    derived = "retry" if in_cycle and node in reference else "cycle" if in_cycle else "acyclic"
    assert derived == region

    report = check_effect_safety(_ir_of(relative))
    if report.result == "pass":
        witness = report.witness
        assert isinstance(witness, EffectSafetyWitness)
        assert {record.node: record.region for record in witness.effects}[node] == region
    else:
        expected_condition = (
            UNPROTECTED_EFFECT_IN_RETRY_REGION if region == "retry" else UNPROTECTED_EFFECT_IN_CYCLE
        )
        assert _condition_ids(report)[0] == expected_condition


def test_the_send_closure_is_transitive_and_reconverging() -> None:
    """``send_closure`` is *reachability* through ``send`` edges, not one hop.

    ``mixed/09``'s closure is one hop deep and re-dispatches to a single target, which leaves
    two things it cannot separate: whether the closure follows a second ``send`` hop, and
    whether a target reachable by two distinct ``send`` routes is handled once. Both are here —
    a fan-out to ``left``/``right`` that reconverges on ``merge``, all inside one SCC — because
    a re-dispatch unit is a sub-graph, not a pair.
    """
    ir = _ir(
        entry="plan",
        finish="out",
        nodes={
            "plan": {"pure": True, "input": [], "output": []},
            "dispatch_node": {"pure": True, "input": [], "output": []},
            "left": {"pure": True, "input": [], "output": []},
            "right": {"pure": True, "input": [], "output": []},
            "merge": {"effect": ["billable"], "input": []},
            "check": {"pure": True, "input": [], "output": []},
            "out": {"input": [], "output": []},
        },
        edges=[
            {"from": "plan", "to": "dispatch_node"},
            {"from": "dispatch_node", "to": "left", "kind": "send"},
            {"from": "dispatch_node", "to": "right", "kind": "send"},
            {"from": "left", "to": "merge", "kind": "send"},
            {"from": "right", "to": "merge", "kind": "send"},
            {"from": "merge", "to": "check"},
            {
                "from": "check",
                "kind": "conditional",
                "condition": "declared content, never evaluated",
                "path_map": {"retry": "dispatch_node", "done": "out"},
            },
        ],
    )
    model = build_graph_model(ir, carry_unresolved_references=False)

    assert _reference_regions(model, send_closure=True) == {
        "dispatch_node",
        "left",
        "right",
        "merge",
    }
    assert _condition_ids(check_effect_safety(ir)) == (UNPROTECTED_EFFECT_IN_RETRY_REGION,)


def test_the_send_closure_is_what_separates_mixed_09_from_negative_02() -> None:
    """PD-009's uniqueness argument, machine-checked on the two fixtures it turns on.

    ``mixed/09``'s ``book_segment`` is one ``send`` hop past the literal re-entry target and is
    ``retry``; ``negative-02``'s ``submit_change_request`` is one ``normal`` hop past its own and
    is ``cycle``. PD-009's rejected option C — no send-closure expansion — is re-derived and
    shown to lose exactly ``book_segment`` and to change nothing on ``negative-02``, which is
    what makes the closure load-bearing rather than decorative.
    """
    fanout = build_graph_model(_ir_of(MIXED_09), carry_unresolved_references=False)
    refinement = build_graph_model(
        _ir_of("effect-safety/negative-02-irreversible-in-refinement-cycle.yaml"),
        carry_unresolved_references=False,
    )

    assert _reference_regions(fanout, send_closure=True) == {"dispatch_bookings", "book_segment"}
    assert _reference_regions(fanout, send_closure=False) == {"dispatch_bookings"}
    assert _reference_regions(refinement, send_closure=True) == {"propose_change"}
    assert _reference_regions(refinement, send_closure=False) == {"propose_change"}

    assert _condition_ids(check_effect_safety(_ir_of(MIXED_09))) == (
        UNPROTECTED_EFFECT_IN_RETRY_REGION,
    )


def test_the_coarser_rule_pd_009_rejected_would_break_two_ratified_fixtures() -> None:
    """PD-009 option B — "any trigger-tagged node in a non-trivial SCC is ``retry``" — rejected.

    Asserted as a *difference*, not as an opinion: on ``negative-02`` and ``positive-03`` the
    coarse rule says ``retry`` where the ratified rule and both ``expected:`` blocks say
    ``cycle``. So the two candidate rules are separated by the corpus, and the one implemented
    is the one the corpus agrees with.
    """
    for relative, node in (
        (
            "effect-safety/negative-02-irreversible-in-refinement-cycle.yaml",
            "submit_change_request",
        ),
        ("effect-safety/positive-03-compensated-billable-hold-loop.yaml", "place_hotel_hold"),
    ):
        model = build_graph_model(_ir_of(relative), carry_unresolved_references=False)
        assert model.components.is_nontrivial(node)  # the coarse rule would say "retry"
        assert node not in _reference_regions(model, send_closure=True)


def test_a_retry_policy_alone_is_a_retry_region_with_no_anchor_cycle() -> None:
    """§6.4 arm (a) and §6.7 edge case 5 — the gap fixture DEC-13 left open (§6.7 (v)).

    A node-local ``retry_policy`` makes the region ``retry`` **without any cycle**, because the
    runtime re-executes the node whether or not the graph loops back to it. §6.3 says the
    consequence in the model: ``cycle`` is "absent for the acyclic FATAL and for retry_policy-only
    regions". Both arms are built — unprotected fails with no ``cycle``, protected passes with a
    record whose ``cycle`` is likewise absent — so the shape is pinned in both directions.
    """
    policy = {"max_attempts": 3, "retry_on": ["TimeoutError"]}
    unprotected = _ir(
        entry="collect",
        finish="receipt",
        nodes={
            "collect": {"pure": True, "input": [], "output": ["ticket"]},
            "charge": {"effect": ["billable"], "retry_policy": policy, "input": ["ticket"]},
            "receipt": {"input": ["ticket"], "output": []},
        },
        edges=[{"from": "collect", "to": "charge"}, {"from": "charge", "to": "receipt"}],
    )

    report = check_effect_safety(unprotected)

    assert _condition_ids(report) == (UNPROTECTED_EFFECT_IN_RETRY_REGION,)
    location = report.failure.location if report.failure else None
    assert isinstance(location, P06NodeLocation)
    assert location.cycle is None

    protected = _ir(
        entry="collect",
        finish="receipt",
        nodes={
            "collect": {"pure": True, "input": [], "output": ["ticket"]},
            "charge": {
                "effect": ["billable"],
                "retry_policy": policy,
                "idempotent": {"key": "ticket"},
                "input": ["ticket"],
            },
            "receipt": {"input": ["ticket"], "output": []},
        },
        edges=[{"from": "collect", "to": "charge"}, {"from": "charge", "to": "receipt"}],
    )

    passing = check_effect_safety(protected)
    witness = passing.witness
    assert isinstance(witness, EffectSafetyWitness)
    assert witness.cycles == ()
    assert witness.effects == (
        P06EffectRecord(
            node="charge",
            effect=("billable",),
            region="retry",
            protection="idempotency_key",
            key="ticket",
        ),
    )


def test_a_self_loop_is_a_cycle() -> None:
    """T-W-SPEC §1's non-triviality definition, which §6.4's ``in_cycle`` cites verbatim:
    a single node with a self-loop is a simple cycle and MUST count.

    Read off the shared model rather than re-tested here — the anchor is ``(node,)``.
    """
    ir = _ir(
        entry="poll",
        finish="poll",
        nodes={"poll": {"effect": ["billable"], "input": [], "output": []}},
        edges=[{"from": "poll", "to": "poll"}],
    )

    report = check_effect_safety(ir)

    assert _condition_ids(report) == (UNPROTECTED_EFFECT_IN_CYCLE,)
    location = report.failure.location if report.failure else None
    assert isinstance(location, P06NodeLocation)
    assert location.cycle == ("poll",)


# ── Phase 4 — the obligation × protection lattice ────────────────────────────────────────


def _hold_loop(**charge: Any) -> WorkflowIR:
    """A three-node billable refinement cycle, with the effect node's annotations supplied.

    One shape, varied only in the declaration under test, so every protection assertion below
    has the same topology and the same region behind it.
    """
    return _ir(
        entry="propose",
        finish="done",
        nodes={
            "propose": {"pure": True, "input": [], "output": ["draft"]},
            "charge": {"effect": ["billable"], "input": ["draft"], **charge},
            "review": {"pure": True, "input": ["draft"], "output": []},
            "release": {"effect": ["network"], "input": ["draft"], "output": []},
            "done": {"input": ["draft"], "output": ["receipt"]},
        },
        edges=[
            {"from": "propose", "to": "charge"},
            {"from": "charge", "to": "review"},
            {
                "from": "review",
                "kind": "conditional",
                "condition": "declared content, never evaluated",
                "path_map": {"again": "release", "ok": "done"},
            },
            {"from": "release", "to": "propose"},
        ],
    )


@pytest.mark.parametrize(
    ("annotations", "protection", "detail"),
    (
        ({"idempotent": {"key": "draft"}}, "idempotency_key", "draft"),
        ({"compensation": {"hook": "release"}}, "compensation_hook", "release"),
    ),
    ids=("keyed-idempotency", "compensation-hook"),
)
def test_both_protection_arms_discharge_the_obligation(
    annotations: dict[str, Any], protection: str, detail: str
) -> None:
    """§6.4 Phase 4's two arms, on one topology.

    Compensation is protection because §6.1 restates DEC-05 D7 normatively — "A declared
    compensation hook discharges the P-06 obligation exactly as a keyed idempotency declaration
    does" — which ``effect-safety/positive-03`` is the corpus witness for. The record names *what*
    discharged it, so a reader can check the declaration rather than trust the verdict.
    """
    report = check_effect_safety(_hold_loop(**annotations))

    assert report.result == "pass"
    witness = report.witness
    assert isinstance(witness, EffectSafetyWitness)
    (record,) = witness.effects
    assert (record.node, record.region, record.protection) == ("charge", "cycle", protection)
    assert (record.key or record.hook) == detail


@pytest.mark.parametrize(
    ("annotations", "why"),
    (
        ({}, "nothing declared at all"),
        ({"idempotent": {"key": "receipt"}}, "the key is not a declared read"),
        ({"compensation": {"hook": "no_such_node"}}, "the hook names no node"),
    ),
    ids=("undeclared", "key-not-in-input", "dangling-hook"),
)
def test_protection_that_does_not_bind_is_not_protection(
    annotations: dict[str, Any], why: str
) -> None:
    """§6.3: "Protection **binding**, not mere presence."

    The two side conditions are the ledger §3 one (an object-form key MUST appear in ``input``)
    and DEC-05 D7's (a hook MUST name an existing node). Each is checked against the same
    topology as the positives above, so the difference is the declaration and nothing else.
    """
    report = check_effect_safety(_hold_loop(**annotations))

    assert _condition_ids(report) == (UNPROTECTED_EFFECT_IN_CYCLE,), why


def test_a_dangling_hook_rides_as_evidence_and_earns_no_new_condition_id() -> None:
    """§6.4 Phase 4's ``dangling_compensation_hook`` — the second §6.7 (v) gap shape.

    DEC-13 ratified the handling verbatim: the hook is NOT protection, the node falls through to
    the ordinary unprotected-effect condition, and the bad id rides as evidence. §6.7 item 5
    states the consequence this asserts — "registry stays closed": no new condition ID, because a
    dangling hook does not change the finding, only the reason the declared protection did not
    bind (DEC-05 D4's granularity rule).
    """
    report = check_effect_safety(_hold_loop(compensation={"hook": "no_such_node"}))

    assert set(_condition_ids(report)) <= P06_CONDITIONS
    location = report.failure.location if report.failure else None
    assert isinstance(location, P06NodeLocation)
    assert location.dangling_compensation_hook == "no_such_node"

    #: A hook that binds carries no evidence field — the negative control for the assertion above.
    passing = check_effect_safety(_hold_loop(compensation={"hook": "release"}))
    assert passing.result == "pass"


@pytest.mark.parametrize(
    "hook",
    ("__end__", "%zz", "", "a//b", "café"),
    ids=("reserved-segment", "bad-escape", "empty", "empty-segment", "not-nfc"),
)
def test_a_hook_that_breaks_the_node_id_grammar_costs_the_evidence_not_the_verdict(
    hook: str,
) -> None:
    """The one narrowing this module takes, on a case the frozen texts jointly exclude.

    IR-SPEC §3.4 types ``hook`` as "a node id under the §5 grammar" while ``Compensation.hook``
    is an unconstrained ``str``, and §6.3 types the evidence field ``Optional[NodeId]`` — so on
    conforming IR the two always agree. On IR that breaks §3.4's own typing, emitting the field
    would raise inside the validator on declared content, so the evidence is dropped instead.
    The verdict cannot move: an id that breaks the grammar is not in ``node_ids`` either, so it
    was never protection.

    The two shapes are the reachable ones — a reserved segment (``__end__``: "compensate by
    going to END", which is a real authoring reflex and a §5 reserved name) and a malformed
    escape. Note how narrow the case is: the §5 grammar admits spaces and punctuation, so an
    ordinary typo stays expressible and keeps its evidence, which the ``no_such_node`` test
    above asserts.
    """
    assert not is_valid_node_id(hook)

    report = check_effect_safety(_hold_loop(compensation={"hook": hook}))

    assert _condition_ids(report) == (UNPROTECTED_EFFECT_IN_CYCLE,)
    location = report.failure.location if report.failure else None
    assert isinstance(location, P06NodeLocation)
    assert location.dangling_compensation_hook is None


def test_the_key_takes_precedence_over_the_hook() -> None:
    """§6.4 Phase 4 comments the order: "precedence: key before hook".

    Observable only when both bind, which no fixture does; the record names the key.
    """
    report = check_effect_safety(
        _hold_loop(idempotent={"key": "draft"}, compensation={"hook": "release"})
    )

    witness = report.witness
    assert isinstance(witness, EffectSafetyWitness)
    (record,) = witness.effects
    assert (record.protection, record.key, record.hook) == ("idempotency_key", "draft", None)


@pytest.mark.parametrize(
    "tags",
    (["network"], ["external"], ["audit"], ["network", "external", "audit", "team:custom"]),
    ids=("network", "external", "audit", "many"),
)
def test_non_trigger_tags_create_no_obligation_and_no_record(tags: list[str]) -> None:
    """§6.3: the trigger set is exactly ``{billable, irreversible}``.

    Every other tag — including a user-defined one — is evidence context, never an obligation
    source. A node carrying only such tags, unprotected, in a cycle, produces neither a finding
    nor a witness record; the corpus's own evidence for the same rule is ``mixed/10``, whose two
    ``network`` fetches are absent from its witness.
    """
    ir = _hold_loop()
    document = json.loads(ir.model_dump_json(by_alias=True))
    for node in document["nodes"]:
        if node["id"] == "charge":
            node["annotations"]["effect"] = tags
    report = check_effect_safety(WorkflowIR.model_validate_json(json.dumps(document)))

    assert report.result == "pass"
    witness = report.witness
    assert isinstance(witness, EffectSafetyWitness)
    assert witness.effects == ()
    assert TRIGGER_TAGS == frozenset({"billable", "irreversible"})


def test_the_full_declared_effect_set_is_carried_as_evidence() -> None:
    """§6.3: ``effect`` carries "a node's **full declared set** as evidence context".

    ``mixed/09``'s ``book_segment`` is ``[billable, network]`` — the obligation comes from
    ``billable`` alone, and ``network`` still appears in the location, because a reader needs the
    declaration as authored.
    """
    report = check_effect_safety(_ir_of(MIXED_09))
    location = report.failure.location if report.failure else None

    assert isinstance(location, P06NodeLocation)
    assert set(location.effect) == {"billable", "network"}


# ── Phase 1 — the FATAL arm, and same-node dominance ─────────────────────────────────────


def test_the_forbidden_combination_is_fatal_and_cycle_independent() -> None:
    """D-012's forbidden combination, on the fixture built to be acyclic for exactly this.

    ``negative-03``'s graph carries no cycle and no retry region anywhere, and the FATAL fires
    regardless: a keyless ``@gebra.idempotent`` on an ``irreversible`` node is a claim Gebra can
    tie to no input field, which is a design error wherever it sits.
    """
    report = check_effect_safety(
        _ir_of("effect-safety/negative-03-keyless-idempotent-on-irreversible.yaml")
    )
    failure = report.failure

    assert isinstance(failure, Failure)
    assert (failure.property_condition, failure.severity) == (
        IRREVERSIBLE_WITH_KEYLESS_IDEMPOTENT,
        "fatal",
    )
    location = failure.location
    assert isinstance(location, P06NodeLocation)
    assert (location.idempotent, location.cycle) == ("keyless", None)


def test_a_keyless_idempotent_billable_node_is_not_the_fatal_case() -> None:
    """The combination is ``irreversible`` + keyless, not "any trigger tag" + keyless.

    ``billable`` alone in a cycle with a bare boolean is the ERROR arm, and the boolean still
    rides the location as evidence — which is what tells a reader the node did claim something.
    """
    report = check_effect_safety(_hold_loop(idempotent=True))

    assert _condition_ids(report) == (UNPROTECTED_EFFECT_IN_CYCLE,)
    location = report.failure.location if report.failure else None
    assert isinstance(location, P06NodeLocation)
    assert location.idempotent == "keyless"


def test_the_phase_one_fatal_dominates_the_same_nodes_error() -> None:
    """§6.4 Phase 4's ``elif n.id in fatal_nodes: skip`` — DEC-05 D2, one root cause one report.

    An ``irreversible`` node with a keyless claim, this time *inside* a cycle: the FATAL owns it,
    and the ERROR that the same node would otherwise earn is not emitted. The negative control is
    the same graph with the boolean dropped, where the ERROR does appear — so the skip is
    demonstrated to be the dominance rule rather than a missing branch.
    """
    dominated = check_effect_safety(_hold_loop(effect=["irreversible"], idempotent=True))
    assert _condition_ids(dominated) == (IRREVERSIBLE_WITH_KEYLESS_IDEMPOTENT,)

    control = check_effect_safety(_hold_loop(effect=["irreversible"]))
    assert _condition_ids(control) == (UNPROTECTED_EFFECT_IN_CYCLE,)


# ── Phase 5 — ordering and packaging ─────────────────────────────────────────────────────


def _three_finding_loop() -> WorkflowIR:
    """A cycle carrying one FATAL node and two unprotected ERROR nodes."""
    return _ir(
        entry="a_node",
        finish="d_node",
        nodes={
            "a_node": {"effect": ["irreversible"], "idempotent": True, "input": []},
            "b_node": {"effect": ["billable"], "input": []},
            "c_node": {"effect": ["irreversible"], "input": []},
            "d_node": {"input": [], "output": []},
        },
        edges=[
            {"from": "a_node", "to": "b_node"},
            {"from": "b_node", "to": "c_node"},
            {"from": "c_node", "to": "a_node"},
            {"from": "c_node", "to": "d_node"},
        ],
    )


def test_the_findings_are_ordered_fatal_first_then_by_node_and_nothing_drops() -> None:
    """§6.4 Phase 5: sort by ``(severity: fatal < error, location.node UTF-16,
    property_condition)``, ``failures[0]`` is the primary, and the rest ride as same-property
    ``co_failures`` — "nothing drops (§0.3; §6.7 (ii))".

    Three findings on one graph: the FATAL leads even though its node id sorts first anyway, and
    the two ERRORs follow in node order. The count is asserted because dropping a finding is the
    failure mode §0.3's packaging rule exists to forbid.

    The third sort key is unexercisable by construction and deliberately not faked: a node earns
    at most one ERROR, and its FATAL — if any — already sorts ahead of that by severity, so two
    findings never share a ``location.node``.
    """
    report = check_effect_safety(_three_finding_loop())
    failure = report.failure
    assert isinstance(failure, Failure)

    assert failure.property_condition == IRREVERSIBLE_WITH_KEYLESS_IDEMPOTENT
    assert failure.severity == "fatal"
    co_failures = failure.co_failures or ()
    assert len(co_failures) == 2
    assert [record.location.node for record in co_failures] == ["b_node", "c_node"]  # type: ignore[union-attr]
    assert {record.severity for record in co_failures} == {"error"}


def test_every_co_failure_names_this_property() -> None:
    """§0.3: ``co_failures`` is **same-property** carriage.

    Cross-property records are the run-level wrapper's, which §0.3 hands to REPORT-FORMAT-SPEC;
    ``emit_co_failure``'s ownership check is what enforces it, and this is that enforcement
    observed on P-06's own output.
    """
    report = check_effect_safety(_three_finding_loop())
    failure = report.failure
    assert isinstance(failure, Failure)

    for record in failure.co_failures or ():
        assert isinstance(record, CoFailure)
        assert record.property == PROPERTY_SLUG


@pytest.mark.parametrize(("identity", "ir"), CORPUS, ids=CORPUS_IDS)
def test_the_severity_and_claim_class_of_every_record_come_off_the_registry(
    identity: str, ir: WorkflowIR
) -> None:
    """§0.1: every record classifies its own claim, and §0.4 pins one grade per condition.

    Read back off the registry rather than restated here, so a regrade moves both sides at once.
    P-06 is DEFENSIBLE-A throughout (§6.2), with FATAL for the forbidden combination and ERROR
    for the two unprotected-effect conditions.
    """
    report = check_effect_safety(ir)
    failure = report.failure
    if failure is None:
        return
    records: tuple[Failure | CoFailure, ...] = (failure, *(failure.co_failures or ()))
    for record in records:
        entry = condition(record.property_condition)
        assert (record.severity, record.claim_class) == (
            entry.severity,
            entry.claim_class,
        ), identity
        assert record.claim_class == "defensible-a"


def test_no_report_carries_display_only_prose_the_corpus_does_not_expect() -> None:
    """§6.4 emits no ``remediation``, and the corpus's ``expected:`` blocks carry none.

    Recorded as its own assertion because it is the kind of helpful addition that would silently
    break model equality on all four negatives at once. §6.7 item 3 permits prose in
    ``remediation``; §6.4's pseudocode does not produce any, and P-06's user-facing rendering is
    the D-12 renderer's, not this module's.
    """
    for relative in (*NEGATIVES, MIXED_01, MIXED_06, MIXED_09):
        failure = check_effect_safety(_ir_of(relative)).failure
        assert isinstance(failure, Failure)
        assert failure.remediation is None, relative


# ── The pass witness ─────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(("identity", "ir"), CORPUS, ids=CORPUS_IDS)
def test_the_witness_cycle_inventory_is_one_canonical_anchor_per_non_trivial_scc(
    identity: str, ir: WorkflowIR
) -> None:
    """§6.4 Phase 5: ``cycles=(anchor_cycle(min(S)) for non-trivial S sorted by min id)``.

    Re-derived from the shared model over every passing corpus snapshot: one entry per
    non-trivial component, each rotated least-id-first (§0.3 ``CycleLocation``), the whole tuple
    ordered by each component's least member. Every member of every anchor is checked to lie in
    the component it anchors, which is what makes it an anchor rather than any old cycle.
    """
    report = check_effect_safety(ir)
    witness = report.witness
    if witness is None:
        return
    assert isinstance(witness, EffectSafetyWitness)
    model = build_graph_model(ir, carry_unresolved_references=False)
    components = model.components

    assert len(witness.cycles) == len(components.nontrivial), identity
    for cycle in witness.cycles:
        assert cycle[0] == min(cycle, key=ledger_sort_key), identity
        assert len({components.index(member) for member in cycle}) == 1, identity
    minima = [components.members[components.index(cycle[0])][0] for cycle in witness.cycles]
    assert minima == sorted(minima, key=ledger_sort_key), identity


def test_the_witness_records_are_in_ledger_node_order() -> None:
    """§6.3: "one record per trigger-tagged node, **by node id**" — the ledger §6 comparator.

    Built rather than read off a fixture, because no corpus positive carries two records: the
    order is only observable with more than one.
    """
    ir = _ir(
        entry="zeta",
        finish="alpha",
        nodes={
            "zeta": {"effect": ["billable"], "idempotent": {"key": "seed"}, "input": ["seed"]},
            "middle": {"effect": ["irreversible"], "compensation": {"hook": "alpha"}, "input": []},
            "alpha": {"effect": ["billable"], "idempotent": {"key": "seed"}, "input": ["seed"]},
        },
        edges=[{"from": "zeta", "to": "middle"}, {"from": "middle", "to": "alpha"}],
    )

    witness = check_effect_safety(ir).witness
    assert isinstance(witness, EffectSafetyWitness)

    assert tuple(record.node for record in witness.effects) == ("alpha", "middle", "zeta")


def test_an_acyclic_record_carries_no_cycle_and_requires_no_protection() -> None:
    """``positive-02``'s whole subject: the region analysis, not a blanket effect flag.

    ``charge_card`` is ``irreversible`` **and** ``billable`` and declares neither protection —
    and P-06 passes, because it executes at most once per run. A validator that flagged every
    irreversible effect would fail here, which is why the fixture exists.
    """
    witness = check_effect_safety(
        _ir_of("effect-safety/positive-02-irreversible-outside-cycle.yaml")
    ).witness
    assert isinstance(witness, EffectSafetyWitness)

    (record,) = witness.effects
    assert (record.node, record.region, record.protection) == (
        "charge_card",
        "acyclic",
        "none_required",
    )
    assert (record.cycle, record.key, record.hook) == (None, None, None)


# ── Determinism, and §6.5's "no simple-cycle enumeration occurs anywhere" ────────────────


@pytest.mark.parametrize(("identity", "ir"), CORPUS, ids=CORPUS_IDS)
def test_the_report_is_a_pure_function_of_the_ir(identity: str, ir: WorkflowIR) -> None:
    """Two runs over one IR are equal reports — every ordering is the ledger §6 comparator,
    never ``dict`` insertion order or ``hash`` randomization.
    """
    assert models_equivalent(check_effect_safety(ir), check_effect_safety(ir)), identity


def _diamond_ring(links: int) -> WorkflowIR:
    """A ring of ``links`` diamonds — 2^links distinct simple cycles through ``join_0``.

    Each diamond splits to ``a_i``/``b_i`` and merges at ``join_{i+1}``; the last join closes
    back to ``join_0``, so every choice of arm gives a distinct simple cycle.
    """
    nodes: dict[str, dict[str, Any]] = {
        "join_0": {"effect": ["billable"], "input": [], "output": []}
    }
    edges: list[dict[str, Any]] = []
    for index in range(links):
        left, right, following = f"a_{index}", f"b_{index}", f"join_{index + 1}"
        nodes[left] = {"pure": True, "input": [], "output": []}
        nodes[right] = {"pure": True, "input": [], "output": []}
        nodes[following] = {"pure": True, "input": [], "output": []}
        edges += [
            {"from": f"join_{index}", "to": left},
            {"from": f"join_{index}", "to": right},
            {"from": left, "to": following},
            {"from": right, "to": following},
        ]
    nodes["exit_node"] = {"input": [], "output": []}
    edges += [
        {"from": f"join_{links}", "to": "join_0"},
        {"from": f"join_{links}", "to": "exit_node"},
    ]
    return _ir(entry="join_0", finish="exit_node", nodes=nodes, edges=edges)


def test_a_graph_with_two_to_the_sixty_cycles_is_analysed_without_enumerating_them() -> None:
    """§6.5: "No simple-cycle enumeration occurs anywhere … P-06 needs region membership plus
    one deterministic anchor, not cycle coverage."

    Sixty chained diamonds closed into a ring carry 2^60 distinct simple cycles through
    ``join_0``, over 182 nodes. An implementation that enumerated them could not return at all;
    this returns the right verdict, and the anchor it emits is **one** of them — 121 vertices,
    one arm per diamond, linear in the graph rather than exponential in it. Not a timing budget:
    the claim is that the analysis returns where enumeration would not.
    """
    report = check_effect_safety(_diamond_ring(60))

    assert _condition_ids(report) == (UNPROTECTED_EFFECT_IN_CYCLE,)
    location = report.failure.location if report.failure else None
    assert isinstance(location, P06NodeLocation)
    assert location.cycle is not None
    assert len(location.cycle) == 121  # join_0 .. join_60 plus one arm of each diamond
    assert len(set(location.cycle)) == 121  # simple: no repeated vertex
    assert location.cycle[0] == "a_0"  # canonically rotated, least id first (§0.3)


# ── §6.3's "Fields read", enforced against the models ────────────────────────────────────


def test_the_module_reads_only_the_section_6_3_fields() -> None:
    """A recording proxy over a validated ``WorkflowIR``: the touched top-level attribute set.

    §6.3 is explicit about two negatives, and both are visible here as *absences*: $\\Sigma$
    (``state``) is not read — P-06's verdict is independent of the state schema (§6.5) — and
    neither is ``runtime``, which is P-02's. ``entry``/``finish``/``edges`` are read through the
    shared model's (m1)/(m2) wiring, which is why they appear.
    """
    touched: set[str] = set()

    class _Recorder:
        def __init__(self, wrapped: Any) -> None:
            object.__setattr__(self, "_wrapped", wrapped)

        def __getattr__(self, name: str) -> Any:
            touched.add(name)
            return getattr(object.__getattribute__(self, "_wrapped"), name)

    check_effect_safety(_Recorder(_ir_of(MIXED_09)))  # type: ignore[arg-type]

    assert touched == {"entry", "finish", "nodes", "edges"}


def test_the_state_schema_changes_nothing() -> None:
    """§6.3: "$\\Sigma$ (``state``) is **not** read"; §6.5: the bound is "independent of |Σ|".

    Asserted behaviourally as well as structurally: ``negative-01``'s report is unchanged when
    the state schema is rewritten underneath it.
    """
    document = _load("effect-safety/negative-01-billable-in-unguarded-retry.yaml")["ir"]
    baseline = check_effect_safety(WorkflowIR.model_validate_json(json.dumps(document)))

    rewritten = {**document, "state": {"unrelated": "str", "flight_id": "str"}}
    assert models_equivalent(
        check_effect_safety(WorkflowIR.model_validate_json(json.dumps(rewritten))), baseline
    )


def test_the_pure_annotation_is_never_consulted() -> None:
    """DEC-13 (2026-07-31) delisted ``pure`` as a P-06 reader — §6.3 says so in its own words.

    The contradiction the ruling is about is D-011 exclusivity: a node cannot coherently declare
    both ``pure: true`` and a trigger-tagged effect, and that check is a future P-03-adjacent
    lint, not P-06's. So P-06's verdict must be identical whether the contradictory flag is
    present or not — which is what this asserts, on the fixture the contradiction is easiest to
    author on.
    """
    document = _load("effect-safety/negative-01-billable-in-unguarded-retry.yaml")["ir"]
    baseline = check_effect_safety(WorkflowIR.model_validate_json(json.dumps(document)))

    contradictory = json.loads(json.dumps(document))
    for node in contradictory["nodes"]:
        if node["id"] == "book_flight":
            node["annotations"]["pure"] = True
    assert models_equivalent(
        check_effect_safety(WorkflowIR.model_validate_json(json.dumps(contradictory))), baseline
    )


def test_a_router_guard_string_changes_nothing() -> None:
    """Phase 3 keys on edge **kind**, never on what a router's ``condition`` says.

    P-02 owns guard strings (TERMINATION-WITNESS-SPEC §3); P-06 does not read one, and must never
    gain a way to. Rewriting ``negative-01``'s guard to something the P-02 grammar rejects leaves
    the P-06 report identical.

    **Read this as verdict-invariance, not as the execution guarantee** — the payload below is
    inert, so an implementation that *did* evaluate it would still compare equal here and pass.
    Non-execution is asserted structurally instead, in three places that cannot be satisfied
    accidentally: ``ExpandedEdge`` has no ``condition`` field at all, so the string is absent from
    the object P-06 reads (VAL-03's ``gebra.verify.graph``); the AST scan below refuses
    ``.condition`` as an attribute access anywhere in the module; and the §6.3 recording proxy
    pins the whole top-level read set. Named because a later reader could otherwise mistake this
    test for the tripwire (never-invokes pre-review, VAL-10).
    """
    document = _load("effect-safety/negative-01-billable-in-unguarded-retry.yaml")["ir"]
    baseline = check_effect_safety(WorkflowIR.model_validate_json(json.dumps(document)))

    rewritten = json.loads(json.dumps(document))
    for edge in rewritten["edges"]:
        if edge.get("kind") == "conditional":
            edge["condition"] = "__import__('os').system('true')"
    assert models_equivalent(
        check_effect_safety(WorkflowIR.model_validate_json(json.dumps(rewritten))), baseline
    )


# ── Registration and dispatch ────────────────────────────────────────────────────────────


def test_the_validator_is_registered_and_dispatches() -> None:
    """Importing the module registers it, which is what ``run_property`` dispatches on."""
    assert is_implemented(PROPERTY_SLUG)

    dispatched = run_property(PROPERTY_SLUG, _ir_of(MIXED_01))

    assert isinstance(dispatched, PropertyReport)
    assert models_equivalent(dispatched, check_effect_safety(_ir_of(MIXED_01)))


def test_the_three_condition_ids_are_the_registrys_p06_entries() -> None:
    """§6.3's condition table is "exactly the three RATIFIED P-06 entries of the §0.4 registry".

    The registry is enumerated in the direction that can fail: ``conditions_for`` returns every
    entry filed against this property, so a **fourth** one added to §0.4 without a validator
    change lands on the left-hand side and fails here rather than passing silently. Reading the
    module's own three constants back through ``condition()`` would only ever confirm itself.
    """
    filed = {entry.id for entry in conditions_for(PROPERTY_SLUG)}

    assert filed == P06_CONDITIONS
    assert {entry.tier for entry in conditions_for(PROPERTY_SLUG)} == {"ratified"}
    assert {condition(name).severity for name in P06_CONDITIONS} == {"fatal", "error"}


# ── WA-07 — never-invokes, on the import *and* the call leg ──────────────────────────────

#: VAL-06's list, unchanged: the execution substrate plus the HTTP and LLM clients whose
#: presence in the closure would mean a validator had grown a way to reach the network.
_FORBIDDEN = (
    "{'langgraph', 'langgraph_sdk', 'langchain', 'langchain_core', 'langchain_openai', "
    "'langchain_anthropic', 'langsmith', 'litellm', 'networkx', 'openai', "
    "'anthropic', 'httpx', 'requests', 'aiohttp', 'urllib3'}"
)


def _tripwire_script(probe: str = "") -> str:
    """The guarded child: patch, import, run P-06 over every corpus snapshot, report.

    ``probe`` arms the raiser; the tripwire and its negative controls share this one script so a
    control cannot drift onto a different raiser from the one the real test relies on.
    """
    return (
        "import glob, json, socket, sys\n"
        "attempts = []\n"
        "class _TripSocket(socket.socket):\n"
        "    def __new__(cls, *a, **k):\n"
        "        attempts.append('socket'); print('WA07-TRIP', file=sys.stderr)\n"
        "        raise AssertionError('socket created on the effect-safety path')\n"
        "def _trip(name):\n"
        "    def _raise(*a, **k):\n"
        "        attempts.append(name); print('WA07-TRIP', file=sys.stderr)\n"
        "        raise AssertionError(name + ' reached on the effect-safety path')\n"
        "    return _raise\n"
        "socket.socket = _TripSocket\n"
        "socket.getaddrinfo = _trip('getaddrinfo')\n"
        "socket.gethostbyname = _trip('gethostbyname')\n"
        "socket.create_connection = _trip('create_connection')\n"
        "import yaml\n"
        "from gebra.ir import WorkflowIR\n"
        "from gebra.verify import check_effect_safety\n"
        "seen = failed = 0\n"
        f"for path in sorted(glob.glob({str(FIXTURES_DIR)!r} + '/*/*.yaml')):\n"
        "    with open(path, encoding='utf-8') as handle:\n"
        "        document = yaml.safe_load(handle)\n"
        "    for key in ('ir', 'ir_before', 'ir_after'):\n"
        "        block = document.get(key)\n"
        "        if not block:\n"
        "            continue\n"
        "        ir = WorkflowIR.model_validate_json(json.dumps(block))\n"
        "        report = check_effect_safety(ir)\n"
        "        failed += report.result == 'fail'\n"
        "        seen += 1\n"
        "assert (seen, failed) == (78, 8), (seen, failed)\n"
        f"{probe}"
        f"print([m for m in sys.modules if m.split('.')[0] in {_FORBIDDEN}] + attempts)\n"
    )


def test_running_p06_over_the_corpus_creates_no_socket_and_resolves_no_name() -> None:
    """WA-07 on the P-06 path, import **and** call, to the VAL-13 tripwire standard.

    A fresh interpreter, because another test in this session may have imported anything. Three
    claims, separately enforced: no execution-substrate or HTTP/LLM-client package enters the
    import closure; no socket is created and no name resolved, either while importing the module
    or while validating every IR snapshot in the vendored corpus; and a swallowed exception still
    fails the run, because every attempt is recorded before the raise and also announced on
    stderr. The child asserts its own counts (78 snapshots, 8 failing) so a glob that silently
    stopped matching would fail the tripwire rather than pass it vacuously.

    One residual, named rather than left implicit, the same one VAL-03/VAL-05/VAL-06/VAL-09
    recorded: the package leg is a post-hoc ``sys.modules`` scan, not an import blocker.
    ``tests/testing/test_hermeticity.py`` installs a real blocker on the wider path, and it runs
    this validator through the harness.
    """
    completed = subprocess.run(
        [sys.executable, "-c", _tripwire_script()], capture_output=True, text=True, check=True
    )

    assert completed.stdout.strip() == "[]", completed.stdout
    assert "WA07-TRIP" not in completed.stderr, completed.stderr


@pytest.mark.parametrize(
    "probe",
    (
        "socket.socket()\n",
        "socket.getaddrinfo('example.invalid', 80)\n",
        "socket.gethostbyname('example.invalid')\n",
        "socket.create_connection(('example.invalid', 80))\n",
    ),
    ids=("socket", "getaddrinfo", "gethostbyname", "create_connection"),
)
def test_the_tripwire_fires_when_the_guarded_path_is_armed(probe: str) -> None:
    """The negative control: prove the raiser is live, on the *same* script the tripwire runs.

    Without this, a patch that silently stopped installing ``_TripSocket`` would leave the
    tripwire passing for the wrong reason. Arming it after the sweep has already run isolates the
    raiser: the green run above got that far too.
    """
    completed = subprocess.run(
        [sys.executable, "-c", _tripwire_script(probe)],
        capture_output=True,
        text=True,
        check=False,  # a non-zero exit is the expected result here, not an error
    )

    assert completed.returncode != 0, completed.stdout
    assert "WA07-TRIP" in completed.stderr, completed.stderr


def test_the_validator_contains_no_evaluation_primitive() -> None:
    """P-06 never reads a declared ``condition`` string, and it must never gain a way to.

    Every ``ast.Name`` in any context is collected, not only call targets, so an aliased
    ``_e = eval; _e(text)`` cannot slip past; the import set is pinned by its own test above,
    which is what closes ``ast.literal_eval`` (whose callee is an ``Attribute``, not a ``Name``).
    The attribute scan is the second half and is deliberately an AST scan rather than a substring
    one: ``condition``, ``source_snippet``, ``runtime``, ``state`` and ``pure`` are the members
    §6.3 leaves out, and what matters is that the module never *accesses* them, not that their
    names never appear in a sentence about them.
    """
    tree = ast.parse(Path(effect_safety.__file__).read_text(encoding="utf-8"))
    named = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    attributes = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}

    assert named.isdisjoint(
        {"eval", "exec", "compile", "literal_eval", "__import__", "getattr", "globals", "vars"}
    )
    assert attributes.isdisjoint({"condition", "source_snippet", "runtime", "state", "pure"})
