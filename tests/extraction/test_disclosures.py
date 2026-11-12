"""The extraction disclosures: a closed vocabulary beside the warnings, and the subgraph record.

Normative authority: INTROSPECTION-SPEC §8, "Extraction disclosures" (ratified — DEC-36), for
the record, its vocabulary and its order; §3 row (iv) and §4.1 for the two reads whose union the
``subgraph-read-as-one-node`` record is emitted over; DEC-19 Ruling 1 as DEC-36 §3.7 amends it;
DEC-36 §3.8 for the strict-mode consequence; IR-SPEC §6.2 and the ledger's §6 comparator for
what "node-id order" means.

Four claims, one section each. The **vocabulary** is the ratified one and is not the warning
taxonomy. The **record** carries what its row says it carries. The **extraction** discloses each
node either read finds, on each path, in node-id order — and the set is a lower bound, which the
fixtures that no read can see pin as plainly as the ones that are seen. And **nothing is
invoked**: the direct-mount read is the ruled ``isinstance``, whose residual — the ``__class__``
read through the object's own attribute access, and the ``abc`` hooks the check can reach outside
the object — is pinned here rather than narrated, and every subgraph shape extracts in a fresh
interpreter whose network, ``compile()``, ``Runnable.invoke`` and ``Pregel.invoke``/``stream``
all raise.
"""

from __future__ import annotations

import gc
import json
import subprocess
import sys
from abc import ABC, ABCMeta
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from langgraph.pregel import Pregel
from pydantic import ValidationError

from gebra.extraction import (
    DISCLOSURE_RULES,
    CompiledSurfaces,
    DisclosureRule,
    ExtractedFrom,
    ExtractionDisclosure,
    ExtractionDisclosureCode,
    ExtractionEnvelope,
    ExtractionWarningCode,
    ObjectFamily,
    disclosure_rule,
    extract,
    to_data,
    to_json,
)
from gebra.extraction.builder import _mounts_compiled_graph
from gebra.extraction.disclosures import (
    CHILD_EXPANSION,
    DIRECT_MOUNT_READ,
    GET_SUBGRAPHS_READ,
    GETTER_UNREADABLE,
    INTERIOR_NOT_READ,
    LOWER_BOUND,
    NO_GETTER_ON_A_BUILDER,
    node_id_order,
    subgraph_disclosures,
)
from gebra.ir import WorkflowIR, graph_version
from tests.sample_workflows import sentinel_compiled as sc
from tests.sample_workflows import sentinel_graph as sg
from tests.sample_workflows import sentinel_lcel as sl
from tests.sample_workflows import sentinel_subgraphs as ss

REPO_ROOT = str(Path(__file__).resolve().parents[2])
GOLDEN_IR = Path(__file__).resolve().parents[1] / "ir" / "golden" / "vector-001.canonical.json"

SUBGRAPH = ExtractionDisclosureCode.SUBGRAPH_READ_AS_ONE_NODE

#: INTROSPECTION-SPEC §8's disclosure table, row by row, as spelled there: DEC-36's two rows and
#: DEC-40's one. Written out rather than derived, so the vocabulary is compared with the spec.
RATIFIED_DISCLOSURE_ROWS = {
    "subgraph-read-as-one-node",
    "recursion-limit-bound-without-justification",
    "barrier-read-per-edge",
}

#: The ruled wording's load-bearing clauses (INTROSPECTION-SPEC §8, the ``(<reason>)`` clause
#: absent in 1.0/1.1 output; DEC-36 §3.6 for the pointer to child expansion).
CARRIED_AS_ONE_NODE = "mounts or reaches a compiled subgraph that this document carries as one node"
INTERIOR_CLAUSE = "its interior (child nodes, edges, entry, finish and state) was not read"
CHILD_EXPANSION_CLAUSE = "child expansion is the named ir 1.x feature of DEC-19's design register"

BOTH_READS = (DIRECT_MOUNT_READ, GET_SUBGRAPHS_READ)


@pytest.fixture(autouse=True)
def _clear_ledgers() -> Iterator[None]:
    """Every test starts with empty ledgers and ends with no sentinel fired."""
    sg.TRIPPED.clear()
    ss.MOUNT_READS.clear()
    yield
    assert sg.TRIPPED == [], sg.TRIPPED


def _seen(envelope: ExtractionEnvelope) -> dict[str, tuple[str, ...]]:
    """Node id → the reads that saw it, over the envelope's subgraph records."""
    return {
        disclosure.node: disclosure.detail["seen_by"]
        for disclosure in envelope.disclosures_of(SUBGRAPH)
        if disclosure.node is not None
    }


def _nodes(envelope: ExtractionEnvelope) -> list[str]:
    """The disclosed node ids, in the order the envelope holds them."""
    return [disclosure.node for disclosure in envelope.disclosures if disclosure.node]


def _surfaces(envelope: ExtractionEnvelope) -> CompiledSurfaces:
    surfaces = envelope.extracted_from.compiled
    assert surfaces is not None, "a §4 extraction always records its compiled-level surfaces"
    return surfaces


def _record(**overrides: Any) -> ExtractionDisclosure:
    """A valid subgraph record, with per-test overrides applied on top."""
    fields: dict[str, Any] = {
        "code": SUBGRAPH,
        "message": "node `legs` mounts or reaches a compiled subgraph",
        "node": "legs",
        "detail": {
            "seen_by": (DIRECT_MOUNT_READ,),
            "interior_not_read": INTERIOR_NOT_READ,
            "lower_bound": LOWER_BOUND,
            "child_expansion": CHILD_EXPANSION,
        },
    }
    fields.update(overrides)
    return ExtractionDisclosure(**fields)


def _envelope(*disclosures: ExtractionDisclosure) -> ExtractionEnvelope:
    return ExtractionEnvelope(
        ir=WorkflowIR.model_validate_json(GOLDEN_IR.read_bytes()),
        extracted_from=ExtractedFrom(source="langgraph:StateGraph", family=ObjectFamily.BUILDER),
        disclosures=disclosures,
    )


# ── The vocabulary: the ratified rows, beside the warnings and never among them ──────────


def test_the_vocabulary_is_a_ratified_row_and_this_build_emits_one() -> None:
    """§8's disclosure table has three rows; each joins the enum with the change that emits it.

    DEC-36 §4: "Whichever of EX-19 and EX-20 merges first introduces the disclosure carrier; the
    other appends its code" — and DEC-40's row is emitted from the same member by its own card.
    So the enum is a subset of the spec's rows, and today exactly the subgraph row.
    """
    codes = {code.value for code in ExtractionDisclosureCode}

    assert codes <= RATIFIED_DISCLOSURE_ROWS
    assert codes == {"subgraph-read-as-one-node"}


def test_no_disclosure_code_is_a_warning_code() -> None:
    """DEC-36 §3.6: "beside the §8 warning taxonomy, and deliberately outside it"."""
    warnings = {code.value for code in ExtractionWarningCode}

    assert {code.value for code in ExtractionDisclosureCode}.isdisjoint(warnings)
    assert "subgraph-read-as-one-node" not in warnings
    # The interim code DEC-19 retired is not revived under either vocabulary (DEC-36 §3.7).
    assert "subgraph-not-expanded" not in warnings | RATIFIED_DISCLOSURE_ROWS
    assert len(warnings) == 10


def test_every_code_has_a_rule_and_the_subgraph_rule_is_its_rows() -> None:
    """The rule table is what the record validates against; a code without one is unchecked."""
    assert set(DISCLOSURE_RULES) == set(ExtractionDisclosureCode)
    rule = disclosure_rule(SUBGRAPH)

    assert isinstance(rule, DisclosureRule)
    assert rule.node_required
    assert rule.detail_required == {
        "seen_by",
        "interior_not_read",
        "lower_bound",
        "child_expansion",
    }
    assert "DEC-36" in rule.origin
    assert "lower bound" in rule.carries


# ── The record: what its row says it carries ─────────────────────────────────────────────


def test_a_record_carries_code_message_node_and_structured_detail() -> None:
    """§8: "each record carries ``code``, a display-only ``message``, an optional ``node`` and a
    structured ``detail``, never a bare string"."""
    record = _record()

    assert record.code is SUBGRAPH
    assert record.node == "legs"
    assert record.detail["seen_by"] == (DIRECT_MOUNT_READ,)
    assert to_data(record)["detail"]["interior_not_read"] == list(INTERIOR_NOT_READ)


def test_the_subgraph_record_names_its_node() -> None:
    with pytest.raises(ValidationError, match="names a node id"):
        _record(node=None)


@pytest.mark.parametrize(
    "missing", ["seen_by", "interior_not_read", "lower_bound", "child_expansion"]
)
def test_the_subgraph_record_carries_every_member_its_row_names(missing: str) -> None:
    detail = dict(_record().detail)
    del detail[missing]

    with pytest.raises(ValidationError, match=missing):
        _record(detail=detail)


def test_a_record_detail_is_reportable_data_and_says_whose_it_is() -> None:
    """The warnings' reportable-data discipline, naming the record it refused for."""
    detail = {**_record().detail, "where": object()}

    with pytest.raises(ValidationError, match="not JSON data; a disclosure carries"):
        _record(detail=detail)


def test_a_record_message_is_never_empty_and_a_code_never_unratified() -> None:
    with pytest.raises(ValidationError):
        _record(message="")
    with pytest.raises(ValidationError):
        ExtractionDisclosure.model_validate_json(
            json.dumps({"code": "subgraph-not-expanded", "message": "x", "node": "legs"})
        )


# ── The envelope member: after the warnings, in the §8 order, outside hash scope ─────────


def test_the_envelope_carries_no_disclosure_by_default() -> None:
    assert _envelope().disclosures == ()


def test_disclosures_never_perturb_the_graph_version() -> None:
    """IR-SPEC §6.4 EXCLUDE names ``disclosures`` beside ``warnings`` (DEC-39 §3.8)."""
    disclosed = _envelope(_record())
    silent = _envelope()

    assert disclosed.graph_version() == silent.graph_version() == graph_version(silent.ir)


def test_the_envelope_holds_the_section_8_order_strictly() -> None:
    """Node-scoped records in node-id order, one per node and code — refused otherwise."""
    alpha, zeta = _record(node="alpha"), _record(node="zeta")

    assert _envelope(alpha, zeta).disclosures == (alpha, zeta)
    with pytest.raises(ValidationError, match="INTROSPECTION-SPEC §8"):
        _envelope(zeta, alpha)
    with pytest.raises(ValidationError, match="one record per node and code"):
        _envelope(alpha, alpha)


def test_node_id_order_is_the_ledger_comparator_not_code_point_order() -> None:
    """IR-SPEC §6.2: ``nodes[]`` are "compared as UTF-16 code units". U+1F600 is a surrogate pair
    there (lead unit 0xD83D) and comes before U+FF21, which comes first by code point."""
    beyond, high = _record(node=ss.BEYOND_BMP_NAME), _record(node=ss.HIGH_BMP_NAME)

    assert sorted([ss.HIGH_BMP_NAME, ss.BEYOND_BMP_NAME]) == [ss.HIGH_BMP_NAME, ss.BEYOND_BMP_NAME]
    assert sorted([ss.HIGH_BMP_NAME, ss.BEYOND_BMP_NAME], key=node_id_order) == [
        ss.BEYOND_BMP_NAME,
        ss.HIGH_BMP_NAME,
    ]
    assert _envelope(beyond, high).disclosures == (beyond, high)
    with pytest.raises(ValidationError, match="INTROSPECTION-SPEC §8"):
        _envelope(high, beyond)


def test_disclosures_read_by_node_and_by_code_and_reload_equal() -> None:
    envelope = _envelope(_record(node="alpha"), _record(node="zeta"))

    assert [d.node for d in envelope.disclosures_for("zeta")] == ["zeta"]
    assert envelope.disclosures_for("missing") == ()
    assert len(envelope.disclosures_of(SUBGRAPH)) == 2
    assert ExtractionEnvelope.model_validate_json(to_json(envelope)) == envelope


# ── The reads, per path and per shape ────────────────────────────────────────────────────

#: Per parent: the nodes the builder path discloses and the reads that saw each. An uncompiled
#: builder has one subgraph read, the direct mount (DEC-36 §3.6; PD-064 §10).
BUILDER_PATH: dict[str, dict[str, tuple[str, ...]]] = {
    "direct": {"legs": (DIRECT_MOUNT_READ,)},
    "unchecked-direct": {"legs": (DIRECT_MOUNT_READ,)},
    "reached": {},
    "unchecked-reached": {},
    "every-mount": {
        "alpha_unchecked_direct": (DIRECT_MOUNT_READ,),
        "zeta_direct": (DIRECT_MOUNT_READ,),
    },
    "unicode-names": {
        ss.BEYOND_BMP_NAME: (DIRECT_MOUNT_READ,),
        ss.HIGH_BMP_NAME: (DIRECT_MOUNT_READ,),
    },
}

#: Per parent: the same, compiled — the union of the two reads (DEC-36 §3.6).
COMPILED_PATH: dict[str, dict[str, tuple[str, ...]]] = {
    "direct": {"legs": BOTH_READS},
    "unchecked-direct": {"legs": (DIRECT_MOUNT_READ,)},
    "reached": {"legs": (GET_SUBGRAPHS_READ,)},
    "unchecked-reached": {},
    "every-mount": {
        "alpha_unchecked_direct": (DIRECT_MOUNT_READ,),
        "mid_reached": (GET_SUBGRAPHS_READ,),
        "zeta_direct": BOTH_READS,
    },
    "unicode-names": {ss.BEYOND_BMP_NAME: BOTH_READS, ss.HIGH_BMP_NAME: BOTH_READS},
}


@pytest.mark.parametrize("name", sorted(ss.PARENTS))
def test_the_builder_path_discloses_what_the_direct_mount_read_sees(name: str) -> None:
    envelope = extract(ss.PARENTS[name]())

    assert envelope.extracted_from.family is ObjectFamily.BUILDER
    assert _seen(envelope) == BUILDER_PATH[name]
    for disclosure in envelope.disclosures:
        assert disclosure.detail["reads_performed"] == (DIRECT_MOUNT_READ,)


@pytest.mark.parametrize("name", sorted(ss.PARENTS))
def test_the_compiled_path_discloses_the_union_of_both_reads(name: str) -> None:
    envelope = extract(ss.PARENTS[name]().compile())

    assert envelope.extracted_from.family is ObjectFamily.COMPILED
    assert _seen(envelope) == COMPILED_PATH[name]
    for disclosure in envelope.disclosures:
        assert disclosure.detail["reads_performed"] == BOTH_READS


@pytest.mark.parametrize("name", sorted(ss.PARENTS))
def test_the_getters_record_stays_the_getters_half(name: str) -> None:
    """``CompiledSurfaces.subgraphs`` keeps what ``get_subgraphs()`` reported, as DEC-19 placed it
    and DEC-36 keeps it — the getter's half of the union, never the union — in node-id order."""
    envelope = extract(ss.PARENTS[name]().compile())

    getter = {node for node, reads in COMPILED_PATH[name].items() if GET_SUBGRAPHS_READ in reads}
    assert set(_surfaces(envelope).subgraphs) == getter
    assert list(_surfaces(envelope).subgraphs) == sorted(getter, key=node_id_order)


def test_the_union_sees_a_direct_unchecked_mount_the_getter_misses() -> None:
    """A1-D36, measured: the direct-mount read sees a ``checkpointer=False`` child mounted
    directly, which ``get_subgraphs()`` skips — the reason DEC-36 rules the union."""
    envelope = extract(ss.build_unchecked_direct_mount_parent().compile())

    assert _surfaces(envelope).subgraphs == ()
    assert _seen(envelope) == {"legs": (DIRECT_MOUNT_READ,)}


def test_a_reached_unchecked_child_is_seen_by_no_read() -> None:
    """The lower bound's remainder, pinned as what it is: a ``checkpointer=False`` child reached
    only from inside a node body is invisible to both reads, on both paths — so nothing is
    disclosed for it, and every disclosure that *is* made says this case exists."""
    parent = ss.build_unchecked_reached_mount_parent()

    assert extract(parent).disclosures == ()
    compiled = extract(parent.compile())
    assert compiled.disclosures == ()
    assert _surfaces(compiled).subgraphs == ()


@pytest.mark.parametrize(
    ("name", "expected"),
    [("mounted-pregel", {"pregel_step": (GET_SUBGRAPHS_READ,)}), ("unchecked-mounted-pregel", {})],
)
def test_the_compiled_only_path_discloses_the_getters_set(
    name: str, expected: dict[str, tuple[str, ...]]
) -> None:
    """§4.3 rule 4: no builder, so no direct-mount read — and every ``checkpointer=False``
    child is invisible, which the ruled lower-bound sentence says of this path in terms."""
    envelope = extract(ss.PREGELS[name]())

    assert envelope.warnings_of(ExtractionWarningCode.COMPILED_ONLY_EXTRACTION)
    assert _seen(envelope) == expected
    for disclosure in envelope.disclosures:
        assert disclosure.detail["reads_performed"] == (GET_SUBGRAPHS_READ,)


def test_disclosures_come_in_node_id_order_whatever_the_order_nodes_were_added() -> None:
    """§8: "one per node, in node-id order" — the fixture adds its mounts z, m, a, b."""
    for envelope in (
        extract(ss.build_every_mount_parent()),
        extract(ss.build_every_mount_parent().compile()),
    ):
        nodes = _nodes(envelope)
        assert len(nodes) == len(envelope.disclosures) >= 2
        assert nodes == sorted(nodes, key=node_id_order)
        assert len(nodes) == len(set(nodes))


def test_node_id_order_holds_for_names_the_two_comparators_disagree_on() -> None:
    """The ledger comparator, not Python's string order, on both paths and on the getter's
    record — the parent adds U+FF21 first, and U+1F600 is disclosed first."""
    parent = ss.build_unicode_mounts_parent()
    expected = [ss.BEYOND_BMP_NAME, ss.HIGH_BMP_NAME]

    assert _nodes(extract(parent)) == expected
    compiled = extract(parent.compile())
    assert _nodes(compiled) == expected
    assert list(_surfaces(compiled).subgraphs) == expected


@pytest.mark.parametrize(
    "factory",
    [
        sg.build_sentinel_graph,
        lambda: sg.build_sentinel_graph().compile(),
        sc.build_gated_pregel,
        sl.build_three_step_sequence,
    ],
    ids=["builder", "compiled", "compiled-only", "lcel"],
)
def test_a_graph_with_no_subgraph_carries_no_disclosure(factory: Callable[[], Any]) -> None:
    """The card's converse: one disclosure per discovered parent, and none without one."""
    assert extract(factory()).disclosures == ()


# ── A getter that cannot be read is not named as a read ──────────────────────────────────


def _unreadable_getter(*args: Any, **kwargs: Any) -> Any:
    raise RuntimeError("subgraph discovery is unreadable here")


@pytest.mark.parametrize("getter", [None, _unreadable_getter], ids=["missing", "raising"])
def test_a_getter_that_could_not_be_read_is_not_recorded_as_a_read(getter: Any) -> None:
    """A record names the reads its extraction ran, because the lower bound rests on them; a
    getter that is missing or raised did not run, and the message says what that leaves unseen.
    """
    compiled = ss.build_direct_mount_parent().compile()
    compiled.get_subgraphs = getter  # type: ignore[method-assign]

    envelope = extract(compiled)

    (record,) = envelope.disclosures
    assert record.detail["seen_by"] == (DIRECT_MOUNT_READ,)
    assert record.detail["reads_performed"] == (DIRECT_MOUNT_READ,)
    assert record.detail["lower_bound"] == LOWER_BOUND
    assert record.message.endswith(GETTER_UNREADABLE)
    assert _surfaces(envelope).subgraphs == ()


# ── What a record says ───────────────────────────────────────────────────────────────────


def _every_disclosure() -> Iterator[ExtractionDisclosure]:
    for factory in ss.PARENTS.values():
        yield from extract(factory()).disclosures
        yield from extract(factory().compile()).disclosures
    for pregel in ss.PREGELS.values():
        yield from extract(pregel()).disclosures


def test_every_record_says_the_set_is_a_lower_bound_in_the_ruled_words() -> None:
    """Acceptance: the lower-bound sentence appears in the disclosure — in its ``detail``, which
    is what a consumer branches on, and in its message, which is what a reader sees."""
    records = list(_every_disclosure())

    assert records, "the fixtures disclose something, or this test checks nothing"
    for record in records:
        assert record.detail["lower_bound"] == LOWER_BOUND
        assert record.detail["child_expansion"] == CHILD_EXPANSION
        assert LOWER_BOUND in record.message
        assert "lower bound, not a census" in record.message
        assert "complete" not in record.message


def test_the_message_is_the_ruled_wording() -> None:
    (record,) = extract(ss.build_direct_mount_parent().compile()).disclosures

    assert record.message.startswith(f"node `legs` {CARRIED_AS_ONE_NODE}; {INTERIOR_CLAUSE}")
    assert CHILD_EXPANSION_CLAUSE in record.message
    assert record.detail["interior_not_read"] == INTERIOR_NOT_READ
    assert "reason" not in record.detail  # §8: absent in 1.0/1.1 output


def test_only_a_path_without_the_getter_says_what_that_path_cannot_see() -> None:
    """An uncompiled builder has no ``get_subgraphs()``, so a subgraph that is not a node's own
    bound object is invisible there whatever its checkpointer — said in that path's messages,
    and only there; ``detail`` keeps the ruled sentence alone, and ``reads_performed`` is the
    structured fact."""
    (on_builder,) = extract(ss.build_direct_mount_parent()).disclosures
    (on_compiled,) = extract(ss.build_direct_mount_parent().compile()).disclosures

    assert on_builder.detail["lower_bound"] == on_compiled.detail["lower_bound"] == LOWER_BOUND
    assert on_builder.message.endswith(NO_GETTER_ON_A_BUILDER)
    assert NO_GETTER_ON_A_BUILDER not in on_compiled.message
    assert GETTER_UNREADABLE not in on_compiled.message


def test_the_record_builder_refuses_an_inconsistent_emitter() -> None:
    """A node attributed to a read the extraction did not run is an emitter bug, named."""
    with pytest.raises(ValueError, match="did not run"):
        subgraph_disclosures(discovered=("legs",), reads_performed=(DIRECT_MOUNT_READ,))
    with pytest.raises(ValueError, match="no subgraph read"):
        subgraph_disclosures(reads_performed=("xray",))
    assert subgraph_disclosures(reads_performed=BOTH_READS) == ()


# ── What does not move ───────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("name", sorted(ss.PARENTS))
def test_the_document_is_untouched_and_carries_no_warning_for_the_unexpansion(name: str) -> None:
    """DEC-19 Ruling 1's first half stands: the parent node only — no child id, no ``/`` — and
    DEC-36 §3.8: the disclosure is not a warning, so the only warning the parents carry is the
    D-011 default every contract-free node gets, and none marks the IR partial."""
    for envelope in (extract(ss.PARENTS[name]()), extract(ss.PARENTS[name]().compile())):
        assert not any("/" in node.id for node in envelope.ir.nodes)
        assert {w.code for w in envelope.warnings} <= {ExtractionWarningCode.CONTRACT_DEFAULTED}
        assert all(w.detail.get("ir_partial") is not True for w in envelope.warnings)
        assert envelope.ir.ir_version == "1.0"


def test_the_builder_and_compiled_documents_of_one_parent_agree() -> None:
    """ANNOTATION §6 parity: the compiled path adds ``runtime`` and the getter's half of the
    union, never a byte of the builder's document."""
    builder = ss.build_every_mount_parent()
    from_builder = extract(builder)
    from_compiled = extract(builder.compile())

    assert to_data(from_builder)["ir"] == {
        key: value for key, value in to_data(from_compiled)["ir"].items() if key != "runtime"
    }
    assert set(_seen(from_builder)) < set(_seen(from_compiled))


# ── WA-07: the direct-mount read is the ruled isinstance, and its residual is pinned ──────


def test_the_direct_mount_read_is_the_ruled_isinstance_and_reads_only_class() -> None:
    """DEC-36 §3.6 / A1-D36: ``isinstance(runnable, langgraph.pregel.Pregel)``. On a mounted
    graph — a ``Pregel`` subclass, as every stock compiled graph is — it reads ``__class__``
    through the object's own attribute access and nothing else of the object: no interior
    surface, and no call beyond that one attribute access."""
    armed = ss.build_armed_mount_parent().nodes["legs"].runnable
    ss.MOUNT_READS.clear()

    assert _mounts_compiled_graph(armed) is True
    assert ss.MOUNT_READS == ["__class__"]


def test_a_class_liar_is_read_as_what_its_class_claims() -> None:
    """The residual INTROSPECTION-SPEC §3 row (iv) names for every ``isinstance`` on a bound
    object, measured: the object's ``__getattribute__`` and its ``__class__`` property run for
    the one name, and the check believes the answer — so this object would be disclosed."""
    liar = ss.ClassLiar()
    ss.MOUNT_READS.clear()

    assert _mounts_compiled_graph(liar) is True
    assert ss.MOUNT_READS == ["__class__", "ClassLiar.__class__"]


def test_the_abc_half_of_the_residual_reaches_author_hooks_outside_the_object() -> None:
    """The residual's other half, which §3 row (iv) does not name, measured: ``Pregel`` is an
    ``abc`` class, so a check of a type its caches do not hold runs ``__subclasscheck__`` on the
    metaclass and ``__subclasshook__`` of the classes in ``Pregel``'s subclass tree and registry,
    and hashes the object's type through that type's metaclass. The caches hold the type after
    one check — until an ``ABCMeta.register`` anywhere in the process clears them. The contract
    walk's ``isinstance`` tests against the ``abc`` classes it names carry the same residual.
    Every class here is the test's own, and is collected when it ends."""
    calls: list[str] = []

    class RecordingMeta(ABCMeta):
        def __subclasscheck__(cls, subclass: type) -> bool:
            calls.append(f"__subclasscheck__({subclass.__name__})")
            return super().__subclasscheck__(subclass)

    class AuthorsPregel(Pregel[Any, Any, Any, Any]):
        @classmethod
        def __subclasshook__(cls, subclass: type) -> Any:
            calls.append(f"__subclasshook__({subclass.__name__})")
            return NotImplemented

    class Registered(metaclass=RecordingMeta):
        pass

    class HashingMeta(type):
        def __hash__(cls) -> int:
            calls.append("__hash__")
            return type.__hash__(cls)

    class NeverCheckedBefore:
        pass

    class HashedType(metaclass=HashingMeta):
        pass

    class Elsewhere(ABC):
        pass

    Pregel.register(Registered)
    try:
        hooks = ["__subclasscheck__(NeverCheckedBefore)", "__subclasshook__(NeverCheckedBefore)"]
        calls.clear()
        assert _mounts_compiled_graph(NeverCheckedBefore()) is False
        assert sorted(calls) == sorted(hooks)

        calls.clear()
        assert _mounts_compiled_graph(NeverCheckedBefore()) is False
        assert calls == []

        Elsewhere.register(int)  # any registration, anywhere in the process, clears the caches
        calls.clear()
        assert _mounts_compiled_graph(NeverCheckedBefore()) is False
        assert sorted(calls) == sorted(hooks)

        calls.clear()
        assert _mounts_compiled_graph(HashedType()) is False
        assert "__hash__" in calls
    finally:
        del AuthorsPregel, Registered, RecordingMeta, HashingMeta, HashedType, Elsewhere
        gc.collect()


def test_extracting_an_armed_mount_reads_none_of_its_interior() -> None:
    """End to end on the builder path: the armed graph is disclosed, nothing it would answer
    about its interior is read, and none of its entry points runs (``TRIPPED`` stays empty).

    The armed object does record reads — the direct-mount read's ``__class__``, and the contract
    and digest walks' reads of every node's bound object (``isinstance`` tests and
    wrapper-chain attributes) — which ``tests/never_invokes_audit.md`` names for this card;
    none is an interior surface.
    """
    parent = ss.build_armed_mount_parent()
    ss.MOUNT_READS.clear()

    envelope = extract(parent)

    assert _seen(envelope) == {"legs": (DIRECT_MOUNT_READ,)}
    assert set(ss.MOUNT_READS).isdisjoint(ss.INTERIOR_SURFACES), ss.MOUNT_READS


def test_the_mount_ledgers_record() -> None:
    """Armed controls: reading an interior surface of the armed graph records it, and running it
    raises the sentinel — so the empty ledgers above are evidence, not silence."""
    armed: Any = ss.build_armed_mount_parent().nodes["legs"].runnable
    ss.MOUNT_READS.clear()

    assert armed.nodes
    assert "nodes" in ss.MOUNT_READS
    with pytest.raises(sg.SentinelExecutedError):
        armed.invoke({"question": "q"})
    assert sg.TRIPPED
    sg.TRIPPED.clear()


def _compiled_children(bound: Any) -> list[Any]:
    """The compiled graphs a node's bound object holds: itself, or a closure's cell contents."""
    if isinstance(bound, Pregel):
        return [bound]
    function = getattr(bound, "func", None)
    cells = getattr(function, "__closure__", None) or ()
    return [cell.cell_contents for cell in cells if isinstance(cell.cell_contents, Pregel)]


def _bodies_under(graph: Any) -> list[Any]:
    """Every node body of a compiled graph: through its builder, or its own Pregel nodes."""
    builder = getattr(graph, "builder", None)
    if builder is not None:
        return [spec.runnable for spec in builder.nodes.values()]
    return [node.bound for node in graph.nodes.values()]


def test_every_body_in_the_subgraph_fixtures_is_armed() -> None:
    """Every parent node, closure, child node and Pregel step body raises
    ``SentinelExecutedError`` — the children reached through a direct mount, through a closure's
    cell, and through a builderless ``Pregel``'s node, so no body goes unarmed."""
    state: Any = {"query": "q", "plan": "p", "answer": "a"}
    bodies: list[Any] = []
    for factory in (*ss.PARENTS.values(), *ss.BUILDER_ONLY.values()):
        for spec in factory().nodes.values():
            bound: Any = spec.runnable
            if not isinstance(bound, Pregel):
                bodies.append(bound)
            for child in _compiled_children(bound):
                bodies.extend(_bodies_under(child))
    for pregel in ss.PREGELS.values():
        for node in pregel().nodes.values():
            bodies.extend(_bodies_under(node.bound))

    for body in bodies:
        function = getattr(body, "func", body)
        with pytest.raises(sg.SentinelExecutedError):
            function(state)
    sg.TRIPPED.clear()

    assert len(bodies) >= 40, len(bodies)


# ── WA-07: every subgraph shape, extracted in a guarded interpreter ───────────────────────

#: The guarded child — the guard prologue ``test_compiled`` uses, plus ``Pregel.invoke`` and
#: ``Pregel.stream``: a subgraph is a compiled graph, and running one is what extraction must
#: never do. The fixtures are built and compiled before the guard goes up (compiling is the
#: fixture's step); ``ChannelWrite.invoke`` stays allow-listed and counted, because the compiled
#: path's cross-check drawing of a stock graph runs it (route 4, ``test_compiled``).
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
        raise AssertionError("a socket was created on the disclosure path")


socket.socket = _CountSocket
socket.getaddrinfo = _record("getaddrinfo")
socket.gethostbyname = _record("gethostbyname")
socket.create_connection = _record("create_connection")

import gebra
from langchain_core.runnables.base import Runnable
from langgraph.graph.state import StateGraph
from langgraph.pregel import Pregel
from langgraph.pregel._write import ChannelWrite
from tests.sample_workflows import sentinel_graph as sg
from tests.sample_workflows import sentinel_subgraphs as ss

builders = {name: factory() for name, factory in ss.PARENTS.items()}
compiled = {name: builder.compile() for name, builder in builders.items()}
pregels = {name: factory() for name, factory in ss.PREGELS.items()}
builder_only = {name: factory() for name, factory in ss.BUILDER_ONLY.items()}
sg.TRIPPED.clear()
del ss.MOUNT_READS[:]

assert attempts == [], attempts
socket.socket = _TripSocket
StateGraph.compile = _record("StateGraph.compile")
Pregel.invoke = _record("Pregel.invoke")
Pregel.stream = _record("Pregel.stream")

channelwrite_invokes = []
_invoke_owner = next(cls for cls in ChannelWrite.__mro__ if "invoke" in vars(cls))
_real_invoke = _invoke_owner.invoke


def _guarded_invoke(self, *a, **k):
    if isinstance(self, ChannelWrite):
        channelwrite_invokes.append(type(self).__name__)
        return _real_invoke(self, *a, **k)
    attempts.append("invoke:" + type(self).__name__); print("WA07-TRIP", file=sys.stderr)
    raise AssertionError("Runnable.invoke reached a non-ChannelWrite: " + type(self).__name__)


def _trip_invoke(self, *a, **k):
    attempts.append("invoke:" + type(self).__name__); print("WA07-TRIP", file=sys.stderr)
    raise AssertionError("Runnable.invoke reached: " + type(self).__name__)


_invoke_owner.invoke = _guarded_invoke
Runnable.invoke = _trip_invoke

disclosed = 0
for workflow in (*builders.values(), *compiled.values(), *pregels.values(), *builder_only.values()):
    envelope = gebra.extract(workflow)
    assert envelope.ir.nodes
    envelope.graph_version()          # canonicalize and digest, still under the guard
    disclosed += len(envelope.disclosures)

assert disclosed == %d, disclosed


def _claims():
    # The run's end-of-run claims, in one place so the controls can re-run the very assertions
    # the claim rests on rather than copies of them.
    assert channelwrite_invokes, "no ChannelWrite.invoke ran — the cross-check drawing never ran"
    remote = [m for m in sys.modules if m == "langgraph.pregel.remote"]
    assert not remote, "remote module imported: " + repr(remote)
    assert sg.TRIPPED == [], "tripped ledger: " + repr(sg.TRIPPED)
    reads = sorted(set(ss.MOUNT_READS) & ss.INTERIOR_SURFACES)
    assert not reads, "mount ledger: " + repr(reads)


_claims()
"""

_REPORT = "print(attempts)\n"


def _expected_disclosures() -> int:
    """How many records the guarded run must see — the per-path tables, plus the armed mount."""
    return (
        sum(len(seen) for seen in BUILDER_PATH.values())
        + sum(len(seen) for seen in COMPILED_PATH.values())
        + 1  # mounted-pregel; its unchecked twin discloses nothing
        + len(ss.BUILDER_ONLY)
    )


def _run_guarded(probe: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", _TRIPWIRE % _expected_disclosures() + probe + _REPORT],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_every_subgraph_shape_extracts_without_invoking_anything() -> None:
    """The WA-07 claim for the disclosure path, in a fresh interpreter.

    Every subgraph shape on every path it has — builder, compiled, compiled-only, and the armed
    mount on the builder path — with name resolution, socket construction, ``compile()``,
    ``Runnable.invoke`` (``ChannelWrite`` allow-listed and counted), ``Pregel.invoke`` and
    ``Pregel.stream`` all raising. The child asserts the number of records it saw, so a run that
    stopped disclosing would fail rather than pass with nothing to prove; that no sentinel body
    fired, the armed ones recording before they raise; that the armed mount's interior was never
    read; and that ``langgraph.pregel.remote`` was never imported.
    """
    result = _run_guarded()

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "[]", result.stdout
    assert "WA07-TRIP" not in result.stderr, result.stderr


@pytest.mark.parametrize(
    ("probe", "expected"),
    [
        ("ss.build_leg_child().compile()\n", "StateGraph.compile was reached"),
        ("compiled['direct'].invoke({})\n", "Pregel.invoke was reached"),
        ("compiled['direct'].stream({})\n", "Pregel.stream was reached"),
        ("socket.socket()\n", "a socket was created"),
        ("socket.getaddrinfo('example.invalid', 80)\n", "getaddrinfo was reached"),
        ("socket.gethostbyname('example.invalid')\n", "gethostbyname was reached"),
        ("socket.create_connection(('example.invalid', 80))\n", "create_connection was reached"),
        (
            "builders['direct'].nodes['plan_step'].runnable.invoke({})\n",
            "reached a non-ChannelWrite",
        ),
        ("Runnable.invoke(compiled['direct'], {})\n", "Runnable.invoke reached: "),
        ("builder_only['armed-mount'].nodes['legs'].runnable.nodes\n_claims()\n", "mount ledger"),
        ("sg.SentinelExecutedError('a probe sentinel')\n_claims()\n", "tripped ledger"),
        ("sys.modules['langgraph.pregel.remote'] = sys\n_claims()\n", "remote module imported"),
    ],
    ids=[
        "compile",
        "pregel-invoke",
        "pregel-stream",
        "socket",
        "getaddrinfo",
        "gethostbyname",
        "create_connection",
        "runnable-invoke",
        "runnable-invoke-backstop",
        "mount-ledger",
        "tripped-ledger",
        "remote-module",
    ],
)
def test_each_raiser_in_the_guarded_child_is_armed(probe: str, expected: str) -> None:
    """A tripwire nobody trips proves nothing — each raiser of the child gets its own control, run
    after the child's own assertions so it proves the raiser was live at the end of that run; and
    each ledger and module claim gets one that seeds its event and re-runs the child's own
    ``_claims()``, so the control fails if those assertions were ever taken out."""
    result = _run_guarded(probe)

    assert result.returncode != 0
    assert expected in result.stderr
