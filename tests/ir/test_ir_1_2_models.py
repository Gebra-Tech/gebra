"""The 1.2 loader MUSTs and the format-migration down-projection — IR-09 (DEC-39, DEC-40).

Two halves, matching the card's fourth acceptance box and the validity rules the two records
word at the loader:

1. **Loader validity.** The two DEC-39 MUSTs — every child id carries its carrier's id as a
   proper segment-prefix, and node ids are unique over the whole tree (IR-SPEC §2.1, §3.8;
   DEC-39 §3.2) — refused through every ingestion path the package ships, in the DEC-22
   pattern: refused, named, never repaired. Beside them, DEC-40's part-B MUSTs: the four
   ``barriers`` rules (§3.11), a repeated ``codomain`` label (§2.4), the empty and repeated
   ``join_key`` forms (§3.10) and a ``managed`` entry carrying ``optional`` or ``reducer``
   (§2.2).
2. **The down-projection** (:func:`gebra.ir.down_project`, IR-SPEC §8; DEC-39 §3.7, DEC-40
   §3.7) — each branch the event bullets name, what it never removes, and that a projected
   document is valid, never re-stamped, and byte-equal to its hand-written 1.1 twin apart from
   ``ir_version``.

The 1.2 conformance vectors themselves are IR-10's; nothing here is a golden. Everything is
pure data (WA-07): hand-authored literals, validated and canonicalized, nothing executed.
"""

from __future__ import annotations

import copy
import itertools
import json
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any, Final

import pytest
import yaml
from pydantic import ValidationError

from gebra.ir import (
    Annotations,
    ConditionalEdge,
    DynamicEdge,
    Node,
    NormalEdge,
    Runtime,
    SendEdge,
    StateField,
    Subgraph,
    WorkflowIR,
    canonical_bytes,
    down_project,
    dump_json,
    dump_yaml,
    graph_version,
    load_json,
    load_yaml,
    lowest_ir_version,
    read_ir,
)
from tests.ir.test_node_id_uniqueness import _ir_blocks


def _ingest_everywhere(document: dict[str, Any], tmp_path: Path) -> list[str]:
    """Load ``document`` through every path the package ships; return each refusal's text.

    The constructor and Python-mode ``model_validate`` are fed the JSON-mode twin's members
    (strict mode admits no list for a tuple in Python mode — IR-SPEC §2.5 note 4), built level
    by level so the refusal under test is reached on those paths too.
    """
    text = json.dumps(document)
    messages: list[str] = []
    attempts: list[Callable[[], object]] = [
        lambda: WorkflowIR.model_validate_json(text),
        lambda: load_json(WorkflowIR, text),
        lambda: load_yaml(WorkflowIR, yaml.safe_dump(document)),
        lambda: WorkflowIR.model_validate(_python_mode(document)),
        lambda: WorkflowIR(**_python_mode(document)),
    ]
    for attempt in attempts:
        with pytest.raises(ValidationError) as raised:
            attempt()
        messages.append(str(raised.value))
    path = tmp_path / "document.ir.yaml"
    path.write_text(yaml.safe_dump(document), encoding="utf-8")
    with pytest.raises(ValidationError) as raised:
        read_ir(path)
    messages.append(str(raised.value))
    return messages


def _python_mode(value: Any) -> Any:
    """Lists → tuples, recursively, except inside the ``dict``-typed members — Python-mode input."""
    if isinstance(value, list):
        return tuple(_python_mode(item) for item in value)
    if isinstance(value, dict):
        return {key: _python_mode(item) for key, item in value.items()}
    return value


def _child(carrier: str, *names: str, **members: Any) -> dict[str, Any]:
    ids = [f"{carrier}/{name}" for name in names]
    level: dict[str, Any] = {
        "entry": ids[0],
        "finish": ids[-1],
        "nodes": [{"id": node_id} for node_id in ids],
        "edges": [{"from": a, "to": b} for a, b in itertools.pairwise(ids)],
    }
    level.update(members)
    return level


def _carrying(child: dict[str, Any], **members: Any) -> dict[str, Any]:
    document: dict[str, Any] = {
        "ir_version": "1.2",
        "entry": "plan",
        "finish": "book",
        "nodes": [{"id": "plan"}, {"id": "book", "subgraph": child}],
        "edges": [{"from": "plan", "to": "book"}],
    }
    document.update(members)
    return document


# ── DEC-39 §3.2: the carrier prefix ───────────────────────────────────────────────────────


def test_a_child_written_under_its_carriers_prefix_loads() -> None:
    """The positive half: full-path child ids, two levels deep."""
    grandchild = _child("book/search", "query")
    child = _child("book", "search", "confirm")
    child["nodes"][0]["subgraph"] = grandchild
    ir = WorkflowIR.model_validate_json(json.dumps(_carrying(child)))

    carrier = ir.nodes[1]
    assert carrier.subgraph is not None
    assert [node.id for node in carrier.subgraph.nodes] == ["book/search", "book/confirm"]
    nested = carrier.subgraph.nodes[0].subgraph
    assert nested is not None and nested.nodes[0].id == "book/search/query"


@pytest.mark.parametrize(
    "child_id",
    [
        "search",  # no prefix at all
        "plan/search",  # another node's prefix
        "booking/search",  # a string prefix, not a segment prefix
        "bookx",  # shares characters, no delimiter
    ],
)
def test_a_child_id_outside_its_carriers_prefix_is_refused_everywhere(
    child_id: str, tmp_path: Path
) -> None:
    """IR-SPEC §2.1/§3.8: "MUST carry the carrier's id as a proper segment-prefix … loaders MUST
    reject a document breaking [it]" — through every ingestion path."""
    child = {"entry": child_id, "finish": child_id, "nodes": [{"id": child_id}], "edges": []}

    for message in _ingest_everywhere(_carrying(child), tmp_path):
        assert "does not carry its carrier's id 'book' as a proper segment-prefix" in message
        assert "DEC-39" in message


def test_the_prefix_is_proper_so_a_child_cannot_reuse_its_carriers_own_id() -> None:
    """``book`` inside ``book``'s subgraph is not under ``book/`` — and would repeat the id."""
    child = {"entry": "book", "finish": "book", "nodes": [{"id": "book"}], "edges": []}
    with pytest.raises(ValidationError, match="proper segment-prefix"):
        WorkflowIR.model_validate_json(json.dumps(_carrying(child)))


def test_a_grandchild_is_checked_against_its_own_carrier() -> None:
    """Each level against the node that carries it; the relation is transitive (§3.8)."""
    child = _child("book", "search")
    child["nodes"][0]["subgraph"] = _child("book", "query")  # under book/, not book/search/
    with pytest.raises(ValidationError) as raised:
        WorkflowIR.model_validate_json(json.dumps(_carrying(child)))
    assert "carrier's id 'book/search'" in str(raised.value)


# ── DEC-39 §3.2: uniqueness over every level ──────────────────────────────────────────────


def test_a_duplicate_id_across_levels_is_refused_everywhere(tmp_path: Path) -> None:
    """A top-level fragment child ``book/search`` beside a mounted child of the same path: the
    carrier-prefix MUST holds, and the tree-wide uniqueness MUST is what refuses it."""
    document = _carrying(_child("book", "search"))
    document["nodes"].append({"id": "book/search"})

    for message in _ingest_everywhere(document, tmp_path):
        assert (
            "node id 'book/search' is declared twice, at nodes[1].subgraph.nodes[0] and nodes[2]"
            in message
        )
        assert "every subgraph level included" in message


def test_a_duplicate_id_within_a_child_level_is_refused_at_that_level() -> None:
    """The DEC-22 rule per level: a child's own ``nodes[]`` repeats an id."""
    child = _child("book", "search")
    child["nodes"].append({"id": "book/search"})
    with pytest.raises(ValidationError) as raised:
        WorkflowIR.model_validate_json(json.dumps(_carrying(child)))
    assert "declared twice, at nodes[0] and nodes[1]" in str(raised.value)


def test_the_same_child_under_two_carriers_is_two_identities() -> None:
    """§3.2: "The same child mounted under two carriers is two subdocuments under two
    prefixes — two identities (§5.3), not a re-entry." No id repeats."""
    document = {
        "ir_version": "1.2",
        "entry": ["a", "b"],
        "finish": ["a", "b"],
        "nodes": [
            {"id": "a", "subgraph": _child("a", "search")},
            {"id": "b", "subgraph": _child("b", "search")},
        ],
        "edges": [],
    }
    ir = WorkflowIR.model_validate_json(json.dumps(document))
    assert lowest_ir_version(ir) == "1.2"


# ── DEC-40 §3.3: the four `barriers` MUSTs ─────────────────────────────────────────────────

#: ``a`` and ``b`` both wired into ``t`` by plain edges — the substrate's one-edge-per-member.
WIRED: Final = {
    "ir_version": "1.2",
    "entry": ["a", "b"],
    "finish": "t",
    "nodes": [{"id": "a"}, {"id": "b"}, {"id": "c"}, {"id": "t"}],
    "edges": [{"from": "a", "to": "t"}, {"from": "b", "to": "t"}, {"from": "c", "to": "t"}],
}


def _barriers(*groups: list[str], document: dict[str, Any] = WIRED) -> dict[str, Any]:
    nodes = [dict(node) for node in document["nodes"]]
    nodes[-1]["barriers"] = list(groups)
    return {**document, "nodes": nodes}


def test_well_formed_groups_load_including_two_groups_into_one_target() -> None:
    """Two groups into one target are an OR of all-ofs (§3.11) — and both load."""
    ir = WorkflowIR.model_validate_json(json.dumps(_barriers(["a", "b"], ["b", "c"])))
    assert ir.nodes[-1].barriers == (("a", "b"), ("b", "c"))


@pytest.mark.parametrize(
    ("groups", "fragment"),
    [
        ((["a"],), "barriers[0] has 1 member(s)"),
        (([],), "barriers[0] has 0 member(s)"),
        ((["a", "a"],), "barriers[0] repeats the member 'a', at [0] and [1]"),
        ((["a", "b"], ["b", "a"]), "barriers[0] and barriers[1] are one group"),
        ((["a", "x"],), "has the member 'x', which names no node of this level"),
    ],
    ids=["one-member", "empty", "repeated-member", "repeated-group", "no-such-node"],
)
def test_each_barriers_must_is_refused(groups: tuple[list[str], ...], fragment: str) -> None:
    """Every group ≥ 2 members; members distinct; groups distinct as sets; members name nodes
    of the level (IR-SPEC §3.11's four MUSTs, the DEC-22 pattern)."""
    with pytest.raises(ValidationError) as raised:
        WorkflowIR.model_validate_json(json.dumps(_barriers(*groups)))
    assert fragment in str(raised.value)
    assert "DEC-40" in str(raised.value)


def test_a_member_must_be_the_source_of_a_normal_edge_into_the_target() -> None:
    """The wiring half of the fourth MUST: a ``send``, ``conditional`` or ``dynamic`` edge from
    the member, or a ``normal`` edge elsewhere, is not the edge the group restates."""
    for edge in (
        {"from": "c", "kind": "send", "to": "t"},
        {"from": "c", "kind": "conditional", "path_map": {"go": "t"}},
        {"from": "c", "kind": "dynamic"},
        {"from": "c", "to": "a"},
    ):
        document = {**WIRED, "edges": [*WIRED["edges"][:2], edge]}
        with pytest.raises(ValidationError) as raised:
            WorkflowIR.model_validate_json(json.dumps(_barriers(["a", "c"], document=document)))
        assert "'c', which is the source of no `normal` edge into 't'" in str(raised.value)


def test_the_barriers_musts_hold_inside_a_child_level() -> None:
    """Per level: a child's group is read against the child's own nodes and edges."""
    child: dict[str, Any] = {
        "entry": ["book/a", "book/b"],
        "finish": "book/t",
        "nodes": [
            {"id": "book/a"},
            {"id": "book/b"},
            {"id": "book/t", "barriers": [["book/a", "book/b"]]},
        ],
        "edges": [{"from": "book/a", "to": "book/t"}],
    }
    with pytest.raises(ValidationError) as raised:
        WorkflowIR.model_validate_json(json.dumps(_carrying(child)))
    assert "'book/b', which is the source of no `normal` edge into 'book/t'" in str(raised.value)

    child["edges"].append({"from": "book/b", "to": "book/t"})
    assert WorkflowIR.model_validate_json(json.dumps(_carrying(child))).nodes[1].subgraph


def test_an_empty_barriers_array_is_absence() -> None:
    """``[]`` is omit-normalized to absence (§6.3): admitted, floors nothing, never written."""
    ir = WorkflowIR.model_validate_json(json.dumps({**_barriers(), "ir_version": "1.0"}))
    assert ir.nodes[-1].barriers == ()
    assert lowest_ir_version(ir) == "1.0"
    assert b"barriers" not in canonical_bytes(ir)


# ── DEC-40 §3.1, §3.2, §3.4: the member MUSTs of part B ────────────────────────────────────


def test_a_repeated_codomain_label_is_refused() -> None:
    edge = {"from": "a", "kind": "conditional", "path_map": {"go": "a"}, "codomain": ["x", "x"]}
    with pytest.raises(ValidationError, match="`codomain` repeats the label 'x'"):
        ConditionalEdge.model_validate_json(json.dumps(edge))


@pytest.mark.parametrize(
    ("join_key", "fragment"),
    [
        ("", "`join_key` is the empty string"),
        ([], "`join_key` is the empty list"),
        (["a", ""], "`join_key[1]` is the empty string"),
        (["a", "a"], "`join_key` repeats the key 'a'"),
        ([1], "valid string"),
    ],
)
def test_the_empty_and_repeated_join_key_forms_are_refused(join_key: Any, fragment: str) -> None:
    """IR-SPEC §3.10: "loaders MUST reject a ``join_key`` that is an empty string, or a list
    that is empty or carries an empty, non-string or repeated member"."""
    node = {"id": "m", "annotations": {"join_key": join_key}}
    with pytest.raises(ValidationError) as raised:
        Node.model_validate_json(json.dumps(node))
    assert fragment in str(raised.value)


@pytest.mark.parametrize("other", [{"optional": True}, {"optional": False}, {"reducer": "add"}])
def test_a_managed_entry_beside_optional_or_reducer_is_refused(other: dict[str, Any]) -> None:
    """IR-SPEC §2.2: "loaders MUST reject an entry carrying ``managed`` beside either"."""
    with pytest.raises(ValidationError, match="a managed state entry carries neither"):
        StateField.model_validate_json(json.dumps({"type": "int", "managed": True, **other}))


# ── The down-projection (IR-SPEC §8; DEC-39 §3.7, DEC-40 §3.7) ────────────────────────────


def _load(document: dict[str, Any]) -> WorkflowIR:
    return WorkflowIR.model_validate_json(json.dumps(document))


def _without_stamp(ir: WorkflowIR) -> bytes:
    """Canonical bytes apart from ``ir_version`` — the pair's comparison (§8)."""
    tree = json.loads(canonical_bytes(ir))
    tree.pop("ir_version")
    return json.dumps(tree, sort_keys=True).encode("utf-8")


#: A 1.2 extraction of an unchanged source, carrying every extraction-populated construct, and
#: the 1.1 document the older build wrote for the same source, by hand.
NEWER: Final = {
    "ir_version": "1.2",
    "entry": "%seq[0]",
    "finish": ["t"],
    "state": {
        "messages": {"type": "list", "reducer": "operator.add"},
        "remaining_steps": {"type": "int", "managed": True},
    },
    "nodes": [
        {"id": "%seq[0]", "annotations": {"input": ["remaining_steps"]}},
        {"id": "%seq[1]"},
        {"id": "%seq[1]/%assign[context]", "annotations": {"pure": True}},
        {"id": "%seq[1]/%assign[context]/%seq[0]"},
        {"id": "%seq[1]/%assign[context]/%seq[1]"},
        {"id": "a"},
        {"id": "t", "barriers": [["%seq[1]", "a"]], "subgraph": _child("t", "x", "y")},
    ],
    "edges": [
        {"from": "%seq[0]", "to": "%seq[1]"},
        {"from": "%seq[1]/%assign[context]/%seq[0]", "to": "%seq[1]/%assign[context]/%seq[1]"},
        {"from": "%seq[1]", "to": "t"},
        {"from": "a", "to": "t"},
        {
            "from": "a",
            "kind": "conditional",
            "path_map": {"go": "t", "into": "%seq[1]/%assign[context]"},
        },
        {
            "from": "%seq[0]",
            "kind": "conditional",
            "path_map": {"go": "t"},
            "codomain": ["go", "no"],
        },
    ],
}

OLDER: Final = {
    "ir_version": "1.1",
    "entry": "%seq[0]",
    "finish": "t",
    "state": {"messages": {"type": "list", "reducer": "operator.add"}},
    "nodes": [
        {"id": "%seq[0]", "annotations": {"input": ["remaining_steps"]}},
        {"id": "%seq[1]"},
        {"id": "a"},
        {"id": "t"},
    ],
    "edges": [
        {"from": "%seq[0]", "to": "%seq[1]"},
        {"from": "%seq[1]", "to": "t"},
        {"from": "a", "to": "t"},
        {"from": "%seq[0]", "kind": "conditional", "path_map": {"go": "t"}},
    ],
}


def test_a_pure_format_migration_projects_to_the_older_bytes() -> None:
    """Every branch at once: ``subgraph``, ``barriers``, ``codomain``, the ``managed`` entry
    (whole — the declared ``input`` naming it stays) and the ``assign`` frame's children with
    every edge incident to them (a ``path_map`` target included). The residual is empty: the two
    canonical forms are byte-equal apart from ``ir_version``."""
    newer, older = _load(NEWER), _load(OLDER)

    projected = down_project(newer, lowest_ir_version(older))

    assert lowest_ir_version(older) == "1.0"
    assert _without_stamp(projected) == _without_stamp(older)
    assert projected.ir_version == "1.2"  # never re-stamped
    assert lowest_ir_version(projected) == "1.0"


def test_the_projection_is_never_a_re_stamp_and_always_valid() -> None:
    """The stamp is left as it is — a floor only falls under removal, so the result is a valid
    document at or above its own floor (DEC-34's loader never re-stamps; neither does this)."""
    projected = down_project(_load(NEWER), "1.0")
    reloaded = WorkflowIR.model_validate_json(json.dumps(json.loads(canonical_bytes(projected))))
    assert canonical_bytes(reloaded) == canonical_bytes(projected)


def test_nothing_lies_above_1_2_so_projecting_to_it_is_the_identity() -> None:
    newer = _load(NEWER)
    assert down_project(newer, "1.2") is newer


def test_the_declared_slots_are_never_removed() -> None:
    """``projection`` and ``join_key`` are declared and never produced by re-extraction alone
    (§8), so a projection keeps them — such a declaration added at an upgrade is a change."""
    document = _carrying(
        _child("book", "search"),
        nodes=[
            {"id": "plan", "annotations": {"join_key": ["city", "day"]}},
            {
                "id": "book",
                "subgraph": _child("book", "search"),
                "annotations": {"projection": {"in": {"q": "q"}, "out": {}}},
            },
        ],
    )
    projected = down_project(_load(document), "1.1")

    assert projected.nodes[0].annotations is not None
    assert projected.nodes[0].annotations.join_key == ("city", "day")
    assert projected.nodes[1].subgraph is None
    assert projected.nodes[1].annotations is not None
    assert projected.nodes[1].annotations.projection is not None
    assert lowest_ir_version(projected) == "1.2"  # still above: the declarations are content


@pytest.mark.parametrize(
    "ids",
    [
        ("%assign[context]", "%assign[question]"),  # an assign root
        ("%each[0]", "%each[0]/%bind[0]"),  # an each root
        ("%leaf[0]",),  # a leaf root
    ],
)
def test_a_root_token_names_nothing(ids: tuple[str, ...]) -> None:
    """``leaf``, and an ``assign``/``each`` root, name nothing: the 1.1 build refused such a
    root, so no older document exists and the projection removes nothing (§8, §5.3)."""
    document = {
        "ir_version": "1.2",
        "entry": ids[0],
        "finish": ids[-1],
        "nodes": [{"id": node_id} for node_id in ids],
        "edges": [],
    }
    ir = _load(document)
    assert down_project(ir, "1.1") == ir


def test_an_each_frames_children_go_and_the_frame_stays() -> None:
    """``each`` beside ``assign``: its bound runnable is a child the 1.1 emitter never read."""
    document = {
        "ir_version": "1.2",
        "entry": "%seq[0]",
        "finish": "%seq[1]",
        "nodes": [{"id": "%seq[0]"}, {"id": "%seq[1]"}, {"id": "%seq[1]/%each[0]"}],
        "edges": [{"from": "%seq[0]", "to": "%seq[1]"}],
    }
    projected = down_project(_load(document), "1.1")
    assert [node.id for node in projected.nodes] == ["%seq[0]", "%seq[1]"]


def test_an_unknown_floor_is_refused() -> None:
    with pytest.raises(ValueError, match="is not an ir_version this build implements"):
        down_project(_load(NEWER), "0.9")  # type: ignore[arg-type]


def test_a_subgraph_level_is_one_value_whose_removal_takes_every_level_with_it() -> None:
    """Part A's bullet names ``subgraph`` "at every level": removing the top-level member
    removes the levels beneath it, nested carriers included."""
    child = _child("book", "search")
    child["nodes"][0]["subgraph"] = _child("book/search", "query")
    projected = down_project(_load(_carrying(child)), "1.1")

    assert all(node.subgraph is None for node in projected.nodes)
    assert isinstance(_load(_carrying(child)).nodes[1].subgraph, Subgraph)


# ── Nothing that conformed before moved (the card's third box) ────────────────────────────
#
# Every committed 1.0/1.1 document loads through the 1.2 models and re-serializes to the bytes
# and digest it was committed with. The absolute pin over the corpus and the IR goldens is
# IR-07/IR-08's fingerprint (``test_no_canonical_byte_or_digest_moves``), left where it was;
# this sweep restates it file by file and adds the extraction conformance goldens, which that
# table does not cover.

IR_GOLDEN: Final = Path(__file__).parent / "golden"
CONFORMANCE: Final = Path(__file__).parents[1] / "extraction" / "golden" / "conformance"


def test_golden_vector_001_reloads_to_its_bytes_and_digest() -> None:
    ir = read_ir(IR_GOLDEN / "vector-001.authored.yaml")
    committed = (IR_GOLDEN / "vector-001.canonical.json").read_bytes()

    assert canonical_bytes(ir) == committed
    assert canonical_bytes(load_json(WorkflowIR, committed)) == committed
    assert (
        graph_version(ir) == (IR_GOLDEN / "vector-001.digest").read_text(encoding="ascii").strip()
    )
    assert lowest_ir_version(ir) == ir.ir_version == "1.0"


@pytest.mark.parametrize(
    "authored",
    sorted((IR_GOLDEN / "roundtrip").glob("*.authored.yaml")),
    ids=lambda path: path.name.removesuffix(".authored.yaml"),
)
def test_every_roundtrip_golden_reserializes_to_its_committed_surface(authored: Path) -> None:
    stem = authored.name.removesuffix(".authored.yaml")
    ir = read_ir(authored)

    assert dump_json(ir) == (authored.parent / f"{stem}.surface.json").read_text(encoding="utf-8")
    assert dump_yaml(ir) == (authored.parent / f"{stem}.surface.yaml").read_text(encoding="utf-8")
    # Model equality, not canonical bytes: one of these goldens pins the surface of an
    # out-of-range integer, which has no canonical form by design (PD-004).
    assert load_json(WorkflowIR, dump_json(ir)) == ir
    assert IR_VERSIONS_OF_GOLDENS >= {ir.ir_version}
    assert lowest_ir_version(ir) in IR_VERSIONS_OF_GOLDENS


#: The minors any committed document is stamped at and needs: no committed golden or corpus
#: payload carries a 1.2 member (the first 1.2 vectors are a later card's, never a regenerated
#: golden — WA-05).
IR_VERSIONS_OF_GOLDENS: Final = frozenset({"1.0", "1.1"})


@pytest.mark.parametrize(
    "canonical",
    sorted(CONFORMANCE.glob("*.canonical.json")),
    ids=lambda path: path.name.removesuffix(".canonical.json"),
)
def test_every_extraction_conformance_golden_reloads_to_its_bytes_and_digest(
    canonical: Path,
) -> None:
    committed = canonical.read_bytes()
    digest = canonical.with_name(canonical.name.replace(".canonical.json", ".digest"))
    ir = load_json(WorkflowIR, committed)

    assert canonical_bytes(ir) == committed
    assert graph_version(ir) == digest.read_text(encoding="ascii").strip()
    assert ir.ir_version in IR_VERSIONS_OF_GOLDENS
    assert lowest_ir_version(ir) == ir.ir_version  # minimally stamped, as extraction writes


def test_every_corpus_payload_loads_at_its_own_stamp_and_needs_nothing_newer() -> None:
    """The vendored corpus (read, never written): every IR block loads, floors at ``"1.0"``,
    and keeps its canonical bytes on a reload of those bytes."""
    blocks = _ir_blocks()
    assert blocks
    for label, block in blocks:
        ir = WorkflowIR.model_validate_json(json.dumps(block))
        assert lowest_ir_version(ir) == "1.0", label
        assert canonical_bytes(load_json(WorkflowIR, canonical_bytes(ir))) == canonical_bytes(ir)


# ── WA-07: nothing planted past validation runs in the 1.2 reads ──────────────────────────
#
# ``model_copy(update=...)`` skips validation, and pydantic does not re-validate a model
# instance it is handed, so a ``str``, ``tuple`` or ``dict`` subclass — or any object — can sit
# inside a model a later document is built from. The construct scan, the 1.2 validity rules and
# the down-projection copy strings, read containers through ``str``/``tuple``/``dict``'s own
# methods called unbound, and test classes with ``issubclass(type(x), C)``. The recorders below
# log every hook they override, attribute access included; they are armed only while the code
# under test runs, and the control at the end calls each hook the ordinary (bound) way and shows
# every one records — a zero proves nothing without its red half.

CALLS: list[str] = []


class _Armed:
    on = False


def _record(name: str) -> None:
    if _Armed.on:
        CALLS.append(name)


class RecStr(str):
    def __getattribute__(self, name: str) -> Any:
        _record(f"str.{name}")
        return str.__getattribute__(self, name)

    def __hash__(self) -> int:
        _record("str.__hash__")
        return str.__hash__(self)

    def __eq__(self, other: object) -> bool:
        _record("str.__eq__")
        return str.__eq__(self, other)

    def __ne__(self, other: object) -> bool:
        _record("str.__ne__")
        return str.__ne__(self, other)

    def __lt__(self, other: str) -> bool:
        _record("str.__lt__")
        return str.__lt__(self, other)

    def __repr__(self) -> str:
        _record("str.__repr__")
        return str.__repr__(self)

    def __str__(self) -> str:
        _record("str.__str__")
        return str.__str__(self)

    def __format__(self, spec: str) -> str:
        _record("str.__format__")
        return str.__format__(self, spec)

    def __len__(self) -> int:
        _record("str.__len__")
        return str.__len__(self)

    def __iter__(self) -> Iterator[str]:
        _record("str.__iter__")
        return str.__iter__(self)

    def __getitem__(self, index: Any) -> str:
        _record("str.__getitem__")
        return str.__getitem__(self, index)

    def __contains__(self, other: object) -> bool:
        _record("str.__contains__")
        return str.__contains__(self, other)  # type: ignore[operator]

    def __add__(self, other: str) -> str:
        _record("str.__add__")
        return str.__add__(self, other)

    def split(self, *args: Any, **kwargs: Any) -> list[str]:
        _record("str.split")
        return str.split(self, *args, **kwargs)

    def startswith(self, *args: Any, **kwargs: Any) -> bool:
        _record("str.startswith")
        return str.startswith(self, *args, **kwargs)

    def encode(self, *args: Any, **kwargs: Any) -> bytes:
        _record("str.encode")
        return str.encode(self, *args, **kwargs)


class RecTuple(tuple[Any, ...]):
    def __getattribute__(self, name: str) -> Any:
        _record(f"tuple.{name}")
        return tuple.__getattribute__(self, name)

    def __iter__(self) -> Iterator[Any]:
        _record("tuple.__iter__")
        return tuple.__iter__(self)

    def __len__(self) -> int:
        _record("tuple.__len__")
        return tuple.__len__(self)

    def __getitem__(self, index: Any) -> Any:
        _record("tuple.__getitem__")
        return tuple.__getitem__(self, index)

    def __contains__(self, item: object) -> bool:
        _record("tuple.__contains__")
        return tuple.__contains__(self, item)

    def __eq__(self, other: object) -> bool:
        _record("tuple.__eq__")
        return tuple.__eq__(self, other)

    def __hash__(self) -> int:
        _record("tuple.__hash__")
        return tuple.__hash__(self)


class RecDict(dict[str, Any]):
    def __getattribute__(self, name: str) -> Any:
        _record(f"dict.{name}")
        return dict.__getattribute__(self, name)

    def __iter__(self) -> Iterator[str]:
        _record("dict.__iter__")
        return dict.__iter__(self)

    def __len__(self) -> int:
        _record("dict.__len__")
        return dict.__len__(self)

    def keys(self) -> Any:
        _record("dict.keys")
        return dict.keys(self)

    def values(self) -> Any:
        _record("dict.values")
        return dict.values(self)

    def items(self) -> Any:
        _record("dict.items")
        return dict.items(self)

    def __getitem__(self, key: str) -> Any:
        _record("dict.__getitem__")
        return dict.__getitem__(self, key)

    def __contains__(self, key: object) -> bool:
        _record("dict.__contains__")
        return dict.__contains__(self, key)


class Lurker:
    """An object of no IR class whose every attribute read is recorded — ``__class__`` included,
    which is what an ``isinstance`` miss reads and ``issubclass(type(x), C)`` never does."""

    def __getattribute__(self, name: str) -> Any:
        _record(f"Lurker.{name}")
        return object.__getattribute__(self, name)


class RecNode(Node):
    """A ``Node`` subclass whose copy, dump and comparison methods record — the bound calls a
    rebuild must not make. Pydantic admits it through the plain constructor, unre-validated."""

    def model_copy(self, *args: Any, **kwargs: Any) -> Any:
        _record("Node.model_copy")
        return Node.model_copy(self, *args, **kwargs)

    def __copy__(self) -> Any:
        _record("Node.__copy__")
        return Node.__copy__(self)

    def __deepcopy__(self, memo: Any = None) -> Any:
        _record("Node.__deepcopy__")
        return Node.__deepcopy__(self, memo)

    def model_dump(self, *args: Any, **kwargs: Any) -> Any:
        _record("Node.model_dump")
        return Node.model_dump(self, *args, **kwargs)

    def __eq__(self, other: object) -> bool:
        _record("Node.__eq__")
        return Node.__eq__(self, other)

    def __hash__(self) -> int:
        _record("Node.__hash__")
        return Node.__hash__(self)


def _armed(call: Callable[[], object]) -> object:
    CALLS.clear()
    _Armed.on = True
    try:
        return call()
    finally:
        _Armed.on = False


def _rs(value: str | None) -> RecStr | None:
    return None if value is None else RecStr(value)


def _planted_edge(edge: Any, *, kind: bool) -> Any:
    """``edge`` with every string member a ``RecStr`` and every container a recording one."""
    update: dict[str, Any] = {"from_": RecStr(edge.from_), "condition": _rs(edge.condition)}
    if kind:
        update["kind"] = RecStr(edge.kind)
    if isinstance(edge, ConditionalEdge):
        update["path_map"] = RecDict({RecStr(k): RecStr(v) for k, v in edge.path_map.items()})
        if edge.codomain is not None:
            update["codomain"] = RecTuple(RecStr(label) for label in edge.codomain)
    elif hasattr(edge, "to"):
        update["to"] = RecStr(edge.to)
    return edge.model_copy(update=update)


def _planted_node(node: Node) -> Node:
    update: dict[str, Any] = {"id": RecStr(node.id)}
    if node.barriers is not None:
        update["barriers"] = RecTuple(
            RecTuple(RecStr(member) for member in group) for group in node.barriers
        )
    if node.subgraph is not None:
        child = node.subgraph
        update["subgraph"] = child.model_copy(
            update={
                "entry": RecStr(child.entry) if isinstance(child.entry, str) else child.entry,
                "finish": RecStr(child.finish) if isinstance(child.finish, str) else child.finish,
                "nodes": RecTuple(_planted_node(grandchild) for grandchild in child.nodes),
                "edges": RecTuple(_planted_edge(edge, kind=True) for edge in child.edges),
            }
        )
    return node.model_copy(update=update)


def _armed_source() -> dict[str, Any]:
    """``NEWER`` plus every construct whose floor message formats a member — a ``dynamic`` edge, a
    ``projection`` and both ``join_key`` forms — and a ``runtime`` for the projection to hand on."""
    document: dict[str, Any] = json.loads(json.dumps(NEWER))
    document["runtime"] = {
        "recursion_limit": {"value": 5, "justification": "declared"},
        "interrupts": {"before": ["a"]},
    }
    nodes = document["nodes"]
    nodes[0]["annotations"]["join_key"] = ["k1", "k2"]
    [declared] = [node for node in nodes if node["id"] == "a"]
    declared["annotations"] = {
        "join_key": "solo",
        "projection": {"in": {"p": "c"}, "out": {"c": "p"}},
    }
    document["edges"].append({"from": "a", "kind": "dynamic"})
    return document


def _planted_document() -> WorkflowIR:
    """The armed source with every string, container and 1.2 member planted — the stamp, the
    wiring, each edge's ``kind`` and every Σ value included — for the scan and the projection."""
    ir = _load(_armed_source())
    assert ir.state is not None
    state: dict[str, Any] = {}
    for key, value in ir.state.items():
        planted_value: Any = value
        if isinstance(value, StateField):
            planted_value = value.model_copy(
                update={"type": RecStr(value.type), "reducer": _rs(value.reducer)}
            )
        state[RecStr(key)] = planted_value
    state[RecStr("note")] = RecStr("str")  # a bare type-string Σ value
    return ir.model_copy(
        update={
            "ir_version": RecStr(ir.ir_version),
            "entry": RecStr(ir.entry) if isinstance(ir.entry, str) else ir.entry,
            "finish": RecTuple(RecStr(member) for member in ir.finish)
            if isinstance(ir.finish, tuple)
            else RecStr(ir.finish),
            "state": RecDict(state),
            "nodes": RecTuple(_planted_node(node) for node in ir.nodes),
            "edges": RecTuple(_planted_edge(edge, kind=True) for edge in ir.edges),
        }
    )


def test_the_scan_and_the_projection_run_no_method_of_a_planted_member() -> None:
    planted = _planted_document()

    floor = _armed(lambda: lowest_ir_version(planted))
    assert CALLS == []
    projected = _armed(lambda: down_project(planted, "1.1"))
    assert CALLS == []
    assert floor == "1.2"
    assert isinstance(projected, WorkflowIR)
    assert projected.state is not None
    assert sorted(projected.state) == ["messages", "note"]
    assert all(type(key) is str for key in projected.state)
    assert not isinstance(projected.ir_version, RecStr)
    assert not any(
        isinstance(edge.kind, RecStr) or isinstance(edge.from_, RecStr) for edge in projected.edges
    )
    assert projected.runtime is not None
    assert sum(isinstance(edge, DynamicEdge) for edge in projected.edges) == 1
    twin_source = _armed_source()
    twin_source["state"]["note"] = "str"
    assert _without_stamp(projected) == _without_stamp(down_project(_load(twin_source), "1.1"))


def test_the_projection_runs_no_method_of_a_node_subclass() -> None:
    """A ``Node`` subclass admitted through the plain constructor is rebuilt by the projection
    from its id and class-tested ``annotations`` — never copied, dumped, hashed or compared
    through its own methods."""
    ir = _load(_armed_source())
    nodes = tuple(
        RecNode(
            id=node.id,
            annotations=node.annotations,
            subgraph=node.subgraph,
            barriers=node.barriers,
        )
        for node in ir.nodes
    )
    built = WorkflowIR(
        ir_version="1.2",
        entry=ir.entry,
        finish=ir.finish,
        state=ir.state,
        nodes=nodes,
        edges=ir.edges,
        runtime=ir.runtime,
    )
    assert all(type(node) is RecNode for node in built.nodes)

    projected = _armed(lambda: down_project(built, "1.1"))

    assert CALLS == []
    assert isinstance(projected, WorkflowIR)
    assert all(type(node) is Node for node in projected.nodes)
    assert _without_stamp(projected) == _without_stamp(down_project(ir, "1.1"))


def test_a_planted_floor_argument_runs_nothing() -> None:
    """The caller's own arguments are class-tested by type too: a ``str`` subclass as the floor,
    an object of no class as the floor or as ``lowest_ir_version``'s argument — nothing of
    either is read, ``__class__`` included."""
    ir = _load(NEWER)
    _armed(lambda: down_project(ir, RecStr("1.1")))  # type: ignore[arg-type]
    assert CALLS == []

    def refused_floor() -> object:
        with pytest.raises(ValueError, match="not an ir_version this build implements"):
            down_project(ir, Lurker())  # type: ignore[arg-type]
        return None

    def refused_argument() -> object:
        with pytest.raises(TypeError):
            lowest_ir_version(Lurker())
        return None

    for call in (refused_floor, refused_argument):
        _armed(call)
        assert CALLS == []


def test_the_1_2_validity_rules_run_no_method_of_a_planted_member() -> None:
    """The constructor route: built ``Node``/edge instances carrying recording members, handed
    in exact tuples, are not re-validated — the carrier-prefix, uniqueness, ``barriers`` and
    floor rules read them through the unbound reads. ``kind`` and the stamp stay exact here:
    pydantic itself reads those on a value it is handed (the discriminator, the literal), which
    is the caller's hand-off, not this module's read."""
    ir = _load(_armed_source())
    nodes = tuple(_planted_node(node) for node in ir.nodes)
    edges = tuple(_planted_edge(edge, kind=False) for edge in ir.edges)

    rebuilt = _armed(
        lambda: WorkflowIR(ir_version="1.2", entry="%seq[0]", finish="t", nodes=nodes, edges=edges)
    )

    assert CALLS == []
    assert isinstance(rebuilt, WorkflowIR) and rebuilt.nodes[-1].barriers is not None


def test_a_node_built_around_a_planted_subgraph_runs_nothing() -> None:
    """The carrier-prefix MUST's own route: ``Node(...)`` handed a built ``Subgraph`` whose
    ``nodes`` and ids are recording — admitted and refused alike without a recorded call."""
    child = Subgraph(
        entry="book/search", finish="book/search", nodes=(Node(id="book/search"),), edges=()
    )
    inside = child.model_copy(
        update={
            "nodes": RecTuple(
                (Node(id="book/search").model_copy(update={"id": RecStr("book/search")}),)
            )
        }
    )
    outside = child.model_copy(
        update={"nodes": RecTuple((Node(id="search").model_copy(update={"id": RecStr("search")}),))}
    )

    carrier = _armed(lambda: Node(id="book", subgraph=inside))
    assert CALLS == [] and isinstance(carrier, Node)

    def refused() -> object:
        try:
            Node(id="book", subgraph=outside)
        except ValidationError as error:
            return error
        return None

    error = _armed(refused)
    assert CALLS == []
    # Rendered only now, disarmed: pydantic's message repr()s the input it was handed.
    assert isinstance(error, ValidationError) and "proper segment-prefix" in str(error)


def test_an_object_of_no_ir_class_is_class_tested_without_being_read() -> None:
    """``issubclass(type(x), C)`` reads the type only: a ``Lurker`` planted as an edge, a Σ value,
    a node, a node's annotations or the runtime has no attribute read — ``__class__`` included —
    by the scan or the projection, and each refuses it with ``TypeError`` (the scan an edge or a
    Σ value, which it never reads as no construct)."""
    ir = _load(NEWER)
    assert ir.state is not None
    with_edge = ir.model_copy(update={"edges": (*ir.edges, Lurker())})
    with_value = ir.model_copy(update={"state": {**ir.state, "x": Lurker()}})
    with_node = ir.model_copy(update={"nodes": (*ir.nodes, Lurker())})
    with_annotations = ir.model_copy(
        update={"nodes": (ir.nodes[0].model_copy(update={"annotations": Lurker()}), *ir.nodes[1:])}
    )
    with_runtime = ir.model_copy(update={"runtime": Lurker()})

    for planted in (with_edge, with_value):

        def scan(planted: WorkflowIR = planted) -> object:
            with pytest.raises(TypeError, match="whatever its `__class__` claims"):
                lowest_ir_version(planted)
            return None

        _armed(scan)
        assert CALLS == []
    for planted in (with_edge, with_value, with_node, with_annotations, with_runtime):

        def project(planted: WorkflowIR = planted) -> object:
            with pytest.raises(TypeError):
                down_project(planted, "1.1")
            return None

        _armed(project)
        assert CALLS == []


def test_a_member_that_is_not_its_declared_container_is_refused_not_iterated() -> None:
    """A ``list`` planted where a tuple is declared — ``nodes``, ``barriers``, ``codomain`` — is a
    ``TypeError`` in the scan, never iterated."""
    ir = _load(NEWER)
    barrier_node = ir.nodes[-1]
    assert barrier_node.barriers is not None
    conditional = next(e for e in ir.edges if isinstance(e, ConditionalEdge) and e.codomain)
    assert conditional.codomain is not None
    mistyped = (
        ir.model_copy(update={"nodes": list(ir.nodes)}),
        ir.model_copy(
            update={
                "nodes": (
                    *ir.nodes[:-1],
                    barrier_node.model_copy(update={"barriers": list(barrier_node.barriers)}),
                )
            }
        ),
        ir.model_copy(
            update={
                "edges": tuple(
                    e.model_copy(update={"codomain": list(conditional.codomain)})
                    if e is conditional
                    else e
                    for e in ir.edges
                )
            }
        ),
    )
    for planted in mistyped:
        with pytest.raises(TypeError):
            lowest_ir_version(planted)


#: Every hook the recorders define, by the name each logs (attribute access by the name read).
HOOKS: Final = frozenset(
    {
        *(f"str.{name}" for name in ("upper", "split", "startswith", "encode")),
        *(
            f"str.__{name}__"
            for name in (
                "hash", "eq", "ne", "lt", "repr", "str", "format",
                "len", "iter", "getitem", "contains", "add",
            )
        ),
        "tuple.count",
        *(f"tuple.__{name}__" for name in ("iter", "len", "getitem", "contains", "eq", "hash")),
        *(f"dict.{name}" for name in ("copy", "keys", "values", "items")),
        *(f"dict.__{name}__" for name in ("iter", "len", "getitem", "contains")),
        "Lurker.__class__",
        *(f"Node.{name}" for name in ("model_copy", "model_dump")),
        *(f"Node.__{name}__" for name in ("copy", "deepcopy", "eq", "hash")),
    }
)  # fmt: skip


def test_the_recorders_record_when_armed() -> None:
    """The red half: every hook the recorders define, called the ordinary (bound) way while
    armed, is logged — so the zeros above are measurements, not a recorder that never fires."""
    text, items, mapping, lurker = RecStr("a"), RecTuple(("a",)), RecDict({"a": 1}), Lurker()
    node = RecNode(id="a")

    def bound_reads() -> object:
        return [
            text.upper,
            hash(text),
            text == "b",
            text != "b",
            text < "b",
            repr(text),
            str(text),
            format(text, ""),
            len(text),
            list(text),
            text[0],
            "a" in text,
            text + "b",
            text.split("/"),
            text.startswith("a"),
            text.encode(),
            items.count,
            list(items),
            len(items),
            items[0],
            "a" in items,
            items == ("a",),
            hash(items),
            mapping.copy,
            list(mapping),
            len(mapping),
            mapping.keys(),
            mapping.values(),
            mapping.items(),
            mapping["a"],
            "a" in mapping,
            isinstance(lurker, DynamicEdge),
            node.model_copy(),
            copy.copy(node),
            copy.deepcopy(node),
            node.model_dump(),
            node == Node(id="a"),
            hash(node),
        ]

    _armed(bound_reads)
    assert len(HOOKS) == 38
    assert set(CALLS) >= HOOKS, sorted(HOOKS - set(CALLS))


# ── A subclass of a model class is read as its base kind (round-2 regression, pinned) ──────
#
# Pydantic admits an instance of a subclass of a model class for the field and does not
# re-validate it. Each class test reads such an instance as its base kind — as HEAD's
# ``isinstance`` tests did — and these are the red halves: an exact-type test that skipped the
# subclass fails every one of them.


class SubDynamic(DynamicEdge):
    pass


class SubConditional(ConditionalEdge):
    pass


class SubNormal(NormalEdge):
    pass


class SubState(StateField):
    pass


def _python_document(**members: Any) -> dict[str, Any]:
    document: dict[str, Any] = {
        "ir_version": "1.0",
        "entry": "a",
        "finish": "t",
        "nodes": (Node(id="a"), Node(id="b"), Node(id="t")),
        "edges": (),
    }
    document.update(members)
    return document


def test_a_dynamic_edge_subclass_still_floors_its_document_at_1_1() -> None:
    """HEAD (IR-08) refuses a ``"1.0"`` document holding a ``dynamic`` edge, subclass or not."""
    edge = SubDynamic(kind="dynamic", **{"from": "a"})
    document = _python_document(edges=(edge,))

    assert lowest_ir_version((edge,)) == "1.1"
    with pytest.raises(ValidationError, match="below the lowest minor"):
        WorkflowIR(**document)
    with pytest.raises(ValidationError, match="below the lowest minor"):
        WorkflowIR.model_validate(document)
    assert lowest_ir_version(WorkflowIR(**{**document, "ir_version": "1.1"})) == "1.1"


def test_a_codomain_on_a_conditional_edge_subclass_still_floors_at_1_2() -> None:
    edge = SubConditional(
        kind="conditional", **{"from": "a"}, path_map={"go": "t"}, codomain=("go", "no")
    )
    for stamp in ("1.0", "1.1"):
        with pytest.raises(ValidationError, match="'1.2' is the lowest sufficient minor"):
            WorkflowIR(**_python_document(ir_version=stamp, edges=(edge,)))
    assert lowest_ir_version((edge,)) == "1.2"


def test_a_managed_entry_on_a_state_field_subclass_still_floors_at_1_2() -> None:
    state = {"remaining_steps": SubState(type="int", managed=True), "messages": "list"}
    for stamp in ("1.0", "1.1"):
        with pytest.raises(ValidationError, match="carries `managed`"):
            WorkflowIR(**_python_document(ir_version=stamp, state=state))
    ir = WorkflowIR(**_python_document(ir_version="1.2", state=state))
    assert lowest_ir_version(ir) == "1.2"
    projected = down_project(ir, "1.1")
    assert projected.state == {"messages": "list"}  # removed whole, as an exact StateField's is


def test_barrier_wiring_carried_by_a_normal_edge_subclass_is_wiring() -> None:
    edges = (
        SubNormal(kind="normal", **{"from": "a"}, to="t"),
        SubNormal(kind="normal", **{"from": "b"}, to="t"),
    )
    nodes = (Node(id="a"), Node(id="b"), Node(id="t", barriers=(("a", "b"),)))

    ir = WorkflowIR(
        **_python_document(ir_version="1.2", entry=("a", "b"), nodes=nodes, edges=edges)
    )

    assert lowest_ir_version(ir) == "1.2"


def test_the_projection_reads_an_edge_subclass_as_its_base_kind() -> None:
    edges = (
        SubNormal(kind="normal", **{"from": "a"}, to="t"),
        SubDynamic(kind="dynamic", **{"from": "b"}),
        SubConditional(
            kind="conditional", **{"from": "a"}, path_map={"go": "t"}, codomain=("go", "no")
        ),
    )
    ir = WorkflowIR(**_python_document(ir_version="1.2", edges=edges))

    projected = down_project(ir, "1.1")

    assert [type(edge) for edge in projected.edges] == [NormalEdge, DynamicEdge, ConditionalEdge]
    assert all(
        not isinstance(edge, ConditionalEdge) or edge.codomain is None for edge in projected.edges
    )


class SubSend(SendEdge):
    pass


class SubAnnotations(Annotations):
    pass


class SubRuntime(Runtime):
    pass


def test_the_projection_reads_every_model_subclass_as_its_base_kind() -> None:
    """The projection's other class tests keep subclasses too: a ``send`` edge, a node, its
    ``annotations``, a kept Σ value and the ``runtime`` — the first three rebuilt as their base
    models, ``annotations`` and ``runtime`` handed on as the instances they are."""
    annotations = SubAnnotations(pure=True)
    runtime = SubRuntime()
    ir = WorkflowIR(
        **_python_document(
            ir_version="1.2",
            state={"messages": SubState(type="list", reducer="operator.add")},
            nodes=(RecNode(id="a", annotations=annotations), Node(id="b"), Node(id="t")),
            edges=(SubSend(kind="send", **{"from": "a"}, to="t"),),
            runtime=runtime,
        )
    )

    projected = down_project(ir, "1.1")

    assert [type(edge) for edge in projected.edges] == [SendEdge]
    assert [type(node) for node in projected.nodes] == [Node, Node, Node]
    assert projected.nodes[0].annotations is annotations
    assert projected.state is not None and type(projected.state["messages"]) is StateField
    assert projected.runtime is runtime


class ClaimingNormal(NormalEdge):
    """A ``NormalEdge`` subclass whose ``__class__`` claims ``DynamicEdge``, recording the read."""

    @property  # type: ignore[misc]
    def __class__(self) -> type:
        _record("ClaimingNormal.__class__")
        return DynamicEdge


class ClaimingSend(SendEdge):
    """A ``SendEdge`` subclass whose ``__class__`` claims ``NormalEdge``, recording the read."""

    @property  # type: ignore[misc]
    def __class__(self) -> type:
        _record("ClaimingSend.__class__")
        return NormalEdge


def test_the_projection_rebuilds_an_edge_by_its_type_never_its_claim() -> None:
    """The rebuild picks an edge's kind from its type: an edge-model subclass whose ``__class__``
    claims another kind is rebuilt as its own base kind and its ``__class__`` is never read —
    where an ``isinstance`` miss earlier in the chain would read the claim and rebuild the
    claimed kind (a ``normal`` edge as ``dynamic``, its target dropped)."""
    edges = (
        ClaimingNormal(kind="normal", **{"from": "a"}, to="t"),
        ClaimingSend(kind="send", **{"from": "b"}, to="t"),
    )
    ir = WorkflowIR(**_python_document(ir_version="1.2", edges=edges))

    projected = _armed(lambda: down_project(ir, "1.1"))

    assert CALLS == []
    assert isinstance(projected, WorkflowIR)
    assert [(type(edge), getattr(edge, "to", None)) for edge in projected.edges] == [
        (NormalEdge, "t"),
        (SendEdge, "t"),
    ]


# ── An object that claims a model class is refused, never read as no construct ─────────────
#
# Pydantic admits, for a model-typed field, an object whose ``__class__`` claims the model
# (``type.__instancecheck__`` reads ``__class__`` when the type test misses). The scan's class
# tests read only the type, so such an edge or Σ value is refused — at the stamp floor through
# validation, with ``TypeError`` from ``lowest_ir_version`` — where reading it as no construct
# admitted a ``"1.0"`` document carrying a ``dynamic`` edge that HEAD (IR-08) refuses (round-3
# IR-contract read).


def _claiming(model: type, **members: Any) -> Any:
    """An object of no IR class whose ``__class__`` claims ``model``, carrying ``members``."""

    class Claimant:
        @property  # type: ignore[misc]
        def __class__(self) -> type:
            return model

    claimant = Claimant()
    for name, value in members.items():
        setattr(claimant, name, value)
    return claimant


CLAIMANTS: Final[dict[str, tuple[str, Callable[[], Any]]]] = {
    "dynamic": (
        "edges",
        lambda: _claiming(DynamicEdge, kind="dynamic", from_="a", condition=None),
    ),
    "conditional-with-codomain": (
        "edges",
        lambda: _claiming(
            ConditionalEdge,
            kind="conditional",
            from_="a",
            condition=None,
            path_map={"go": "t"},
            codomain=("go", "no"),
        ),
    ),
    "normal": (
        "edges",
        lambda: _claiming(NormalEdge, kind="normal", from_="a", to="t", condition=None),
    ),
    "managed-state-value": (
        "state",
        lambda: _claiming(StateField, type="int", reducer=None, optional=None, managed=True),
    ),
}


@pytest.mark.parametrize("name", sorted(CLAIMANTS))
def test_an_object_claiming_a_model_class_is_refused_at_the_floor(name: str) -> None:
    member, make = CLAIMANTS[name]
    claimant = make()
    members = {"edges": (claimant,)} if member == "edges" else {"state": {"k": claimant}}
    document = _python_document(**members)

    with pytest.raises(ValidationError, match="whatever its `__class__` claims"):
        WorkflowIR(**document)
    with pytest.raises(ValidationError, match="whatever its `__class__` claims"):
        WorkflowIR.model_validate(document)
    if member == "edges":
        with pytest.raises(TypeError, match="whatever its `__class__` claims"):
            lowest_ir_version([claimant])


def test_a_claimant_is_not_barrier_wiring() -> None:
    """The wiring MUST's class test reads the type only: an edge whose ``__class__`` claims
    ``NormalEdge`` wires nothing, so the group it would wire is refused as unwired."""
    nodes = (Node(id="a"), Node(id="b"), Node(id="t", barriers=(("a", "b"),)))
    edges = (
        _claiming(NormalEdge, kind="normal", from_="a", to="t", condition=None),
        NormalEdge(kind="normal", **{"from": "b"}, to="t"),
    )
    document = _python_document(ir_version="1.2", entry=("a", "b"), nodes=nodes, edges=edges)

    with pytest.raises(ValidationError, match="is the source of no `normal` edge"):
        WorkflowIR(**document)


def test_a_claimant_inside_a_child_level_is_refused_naming_its_level() -> None:
    child = Subgraph(
        entry="t/x",
        finish="t/y",
        nodes=(Node(id="t/x"), Node(id="t/y")),
        edges=(_claiming(DynamicEdge, kind="dynamic", from_="t/x", condition=None),),
    )
    document = _python_document(
        ir_version="1.2", nodes=(Node(id="a"), Node(id="t", subgraph=child))
    )

    with pytest.raises(ValidationError, match=r"nodes\[1\]\.subgraph\.edges\[0\] is not an"):
        WorkflowIR(**document)


# ── The projection's one refusal, stated and pinned ────────────────────────────────────────


@pytest.mark.parametrize(
    "ids",
    [("%assign[a]/%each[0]",), ("%seq[0]/%assign[a]", "%seq[0]/%assign[b]")],
)
def test_a_document_whose_every_node_lies_beneath_a_frame_has_no_projection(
    ids: tuple[str, ...],
) -> None:
    """IR-SPEC §2.1 makes ``nodes`` minItems 1, so a valid 1.2 document that loses every node is
    refused with a ``ValueError`` naming why — never returned empty (a hand-built document: a
    conforming emitter writes the frame's own node beside its children)."""
    ir = _load(
        {
            "ir_version": "1.2",
            "entry": ids[0],
            "finish": ids[-1],
            "nodes": [{"id": node_id} for node_id in ids],
            "edges": [],
        }
    )
    with pytest.raises(ValueError, match="removes every node"):
        down_project(ir, "1.1")


# ── The fold-in's two decisions, pinned ────────────────────────────────────────────────────


def test_a_frame_nested_beneath_a_root_frame_is_a_frame_like_any_other() -> None:
    """Only the root frame's own token — the id's first segment — names nothing (§8: removed
    "in any position" but the root): a frame nested beneath an ``assign`` root has its
    children removed."""
    document = {
        "ir_version": "1.2",
        "entry": "%assign[a]",
        "finish": "%assign[b]",
        "nodes": [
            {"id": "%assign[a]"},
            {"id": "%assign[a]/%each[0]"},
            {"id": "%assign[a]/%each[0]/%bind[0]"},
            {"id": "%assign[b]"},
        ],
        "edges": [],
    }
    projected = down_project(_load(document), "1.1")
    assert [node.id for node in projected.nodes] == ["%assign[a]", "%assign[b]"]


def test_lowest_ir_version_keeps_its_frozen_keyword() -> None:
    """``edges`` is the name IR-MODELS-FREEZE §1 froze; a keyword call written against 1.1 works,
    and a document is passed in the same place."""
    ir = _load(_carrying(_child("book", "search")))
    assert lowest_ir_version(edges=ir.edges) == "1.0"  # the edges alone need nothing newer
    assert lowest_ir_version(edges=ir) == "1.2"  # the carrier does
