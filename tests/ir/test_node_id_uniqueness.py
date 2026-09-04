"""IR-SPEC §2.1's node-id uniqueness MUST, on the model — the DEC-22 regression (IR-07).

The rule and its history: §6.2 orders ``nodes[]`` by ``id`` and called the order total
because "ids are unique" — a *premise*, not a rule, since §2.1 said only "array, minItems 1"
and §2.5's stub carried no uniqueness constraint. SD-05's IR-spec pre-review found the
gap and reproduced it: two authorings of one node set both validated and produced two
different ``graph_version`` digests, because the tied sort key falls back to authored order —
which §6.4 explicitly excludes from the hash. Filed as PD-032, ratified 2026-08-04 as
**DEC-22, option A**: uniqueness is normative, ``ir_version`` stays 1.0, and no emitted digest
moves, because no *conforming* document changes.

This module is the regression suite for the model half of that ruling. Three claims, matching
the card's three acceptance boxes:

1. **The PD-032 repro documents are rejected at model validation**, through every ingestion
   path the package offers, with the repeated id named
   (:func:`~gebra.ir.models._require_unique_node_ids`).
2. **Nothing that conformed before changed.** Every vendored corpus IR payload and every
   committed golden still loads, and its canonical bytes and digest are byte-identical to
   what this build produced before the constraint landed — pinned absolutely, not merely
   recomputed self-consistently (:data:`CANONICAL_FINGERPRINT`).
3. The boundary is *this* rule and no wider one: reference-role strings, ``entry``/``finish``
   members and edge multiplicity are all still free to repeat, and the constraint stays out
   of ``model_json_schema()`` so IR-05's lockstep check still sees the vendored vocabulary.

Everything here is pure data (WA-07): documents are literals or fixture text read off disk,
and nothing is executed. The corpus is read read-only and never written (WA-04/WA-11).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Final

import pytest
import yaml
from pydantic import ValidationError

from gebra.ir import (
    CanonicalizationError,
    Node,
    WorkflowIR,
    canonical_bytes,
    graph_version,
    load_json,
    load_yaml,
    read_ir,
    write_ir,
)
from tests.conftest import FIXTURES_DIR

GOLDEN_DIR: Final = Path(__file__).parent / "golden"

#: The two documents PD-032's spec-defect record reproduces the defect with, verbatim from
#: its issue body: one node set, two authorings, two digests. Both are refused now.
PD032_REPRO: Final = (
    (
        '{"edges":[],"entry":"a","finish":"a","ir_version":"1.0",'
        '"nodes":[{"annotations":{"pure":true},"id":"a"},{"annotations":{"pure":false},"id":"a"}]}'
    ),
    (
        '{"edges":[],"entry":"a","finish":"a","ir_version":"1.0",'
        '"nodes":[{"annotations":{"pure":false},"id":"a"},{"annotations":{"pure":true},"id":"a"}]}'
    ),
)

#: A conforming sibling of the repro: the same document with the second node given its own
#: id. It loads, and it is what the repro documents were trying to say.
CONFORMING = (
    '{"edges":[],"entry":"a","finish":"a","ir_version":"1.0",'
    '"nodes":[{"annotations":{"pure":true},"id":"a"},{"annotations":{"pure":false},"id":"b"}]}'
)


def _ir_blocks() -> list[tuple[str, dict[str, Any]]]:
    """Every IR payload embedded in the vendored corpus, labelled by file and member.

    Pure data: the corpus is YAML read off disk and never imported or executed (WA-07), and
    never written (WA-04 — the fixtures are vendored read-only).
    """
    blocks: list[tuple[str, dict[str, Any]]] = []
    for path in sorted(FIXTURES_DIR.rglob("*.yaml")):
        if path.name == "schema.yaml":
            continue
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(document, dict):
            continue
        for key in ("ir", "ir_before", "ir_after"):
            block = document.get(key)
            if isinstance(block, dict):
                blocks.append((f"{path.relative_to(FIXTURES_DIR).as_posix()}::{key}", block))
    return blocks


def _canonical_table() -> list[str]:
    """One ``label<TAB>digest<TAB>byte-length`` row per corpus payload and committed golden.

    Golden 05 is deliberately a row that says ``refused``: it is a valid §2 document that
    round-trips losslessly and that ``graph_version`` refuses at §6.1 step 5 (a wide integer
    inside ``args_schema``; IR-04's recorded ruling, PD-004's rule). Recording *which* way
    each entry answers makes the pin sensitive to a refusal turning into a digest as well as
    to a digest moving.
    """
    rows: list[str] = []
    for label, block in _ir_blocks():
        ir = WorkflowIR.model_validate_json(json.dumps(block))
        rows.append(f"{label}\t{graph_version(ir)}\t{len(canonical_bytes(ir))}")
    for path in sorted(GOLDEN_DIR.rglob("*.authored.yaml")):
        ir = read_ir(path)
        label = f"golden/{path.relative_to(GOLDEN_DIR).as_posix()}"
        try:
            rows.append(f"{label}\t{graph_version(ir)}\t{len(canonical_bytes(ir))}")
        except CanonicalizationError as refusal:
            rows.append(f"{label}\trefused\tCanonicalizationError:{refusal.reason.value}")
    return rows


#: How many rows :func:`_canonical_table` renders — the vendored corpus's IR payloads plus
#: the six committed goldens (``vector-001`` and the five round-trip triples).
CANONICAL_ENTRIES: Final = 84

#: SHA-256 over the rendered table, captured from this build **before** the IR-07 constraint
#: landed and unchanged by it. This is acceptance box 2's absolute pin: the existing corpus
#: tests prove canonicalization is self-consistent (recompute-and-compare), which stays true
#: even if every digest moved together — this says they did not move at all.
#:
#: Three things legitimately move it, and none of them is a quiet edit: the corpus is
#: re-vendored (WA-04, R-05 sign-off), a ratified canonicalization change moves digests
#: (WA-05 + an ``ir_version`` bump per DEC-09), or a golden is added to the committed set
#: (which also moves :data:`CANONICAL_ENTRIES`, so the count says which kind of move it was).
#: The failure message prints the whole table, so the mover is visible.
#:
#: Regenerating it deliberately is one command, and it is written here so the next legitimate
#: update is mechanical rather than archaeological::
#:
#:     python -c "import hashlib; from tests.ir.test_node_id_uniqueness import _canonical_table
#:     rows = _canonical_table()
#:     text = chr(10).join(rows) + chr(10)
#:     print(len(rows), hashlib.sha256(text.encode()).hexdigest())"
CANONICAL_FINGERPRINT: Final = "329ff2f216df261b91f697f18d1bc92930a1735b6bef01bd63771292ff78a9dd"


# ── Box 1: the PD-032 repro documents are rejected at model validation ────────────────────


@pytest.mark.parametrize("document", PD032_REPRO, ids=("pure-true-first", "pure-false-first"))
def test_the_pd032_repro_documents_are_rejected_with_the_duplicate_named(document: str) -> None:
    """Both authorings of PD-032's node set, refused where DEC-22 puts the rule.

    The error is an ordinary ``ValidationError`` at ``loc = ("nodes",)`` — the array the rule
    constrains, not one of its elements, because no single element violates it — and it names
    the repeated id and both positions, so the fix is readable off the message.
    """
    with pytest.raises(ValidationError) as raised:
        WorkflowIR.model_validate_json(document)

    (error,) = raised.value.errors()
    assert error["type"] == "value_error"
    assert error["loc"] == ("nodes",)
    assert "'a' is declared twice" in error["msg"]
    assert "nodes[0] and nodes[1]" in error["msg"]
    assert "§2.1" in error["msg"] and "DEC-22" in error["msg"]


def test_the_two_digest_repro_is_now_unconstructible() -> None:
    """The defect itself, stated as the property that closes it.

    PD-032's finding was that these two documents *both load* and digest differently — one
    node set, two ``graph_version`` values, which §6.4 excludes by excluding authored array
    order. Neither loads now, so the pair cannot be built to compare in the first place: the
    §6.2 sort's totality holds by construction rather than by assumption.
    """
    for document in PD032_REPRO:
        with pytest.raises(ValidationError):
            WorkflowIR.model_validate_json(document)

    # And the conforming sibling — the same document with two ids — is untouched.
    conforming = WorkflowIR.model_validate_json(CONFORMING)
    assert [node.id for node in conforming.nodes] == ["a", "b"]
    assert graph_version(conforming).startswith("sha256:")


def test_every_ingestion_path_refuses_it(tmp_path: Path) -> None:
    """§2.1's MUST is worded at the *loader*, so every loader this package ships enforces it.

    The constructor, both ``model_validate`` modes, the two format entry points and the
    suffix-dispatching :func:`~gebra.ir.serialization.read_ir` all route through the same
    field validator, so there is one refusal rather than five spellings of one. The
    Python-mode call is spelled with tuples because strict mode admits nothing wider there
    (A6 PC-3; IR-SPEC §2.5 note 4 is why the JSON path exists at all).
    """
    payload = json.loads(PD032_REPRO[0])
    built = {"ir_version": "1.0", "entry": "a", "finish": "a", "edges": ()}

    with pytest.raises(ValidationError, match="declared twice"):
        WorkflowIR(
            ir_version="1.0",
            entry="a",
            finish="a",
            nodes=(Node(id="a"), Node(id="a")),
            edges=(),
        )
    with pytest.raises(ValidationError, match="declared twice"):
        WorkflowIR.model_validate({**built, "nodes": (Node(id="a"), Node(id="a"))})
    with pytest.raises(ValidationError, match="declared twice"):
        WorkflowIR.model_validate_json(PD032_REPRO[0])
    with pytest.raises(ValidationError, match="declared twice"):
        load_json(WorkflowIR, PD032_REPRO[0])
    with pytest.raises(ValidationError, match="declared twice"):
        load_yaml(WorkflowIR, yaml.safe_dump(payload))

    document = tmp_path / "duplicated.ir.yaml"
    document.write_text(yaml.safe_dump(payload), encoding="utf-8")
    with pytest.raises(ValidationError, match="declared twice"):
        read_ir(document)


@pytest.mark.parametrize(
    ("ids", "duplicate", "positions"),
    [
        (("a", "a"), "a", "nodes[0] and nodes[1]"),
        (("a", "b", "a"), "a", "nodes[0] and nodes[2]"),
        (("a", "b", "b"), "b", "nodes[1] and nodes[2]"),
        (("a", "b", "a", "b"), "a", "nodes[0] and nodes[2]"),
        (("a", "a", "a"), "a", "nodes[0] and nodes[1]"),
        (("sub/inner", "sub/inner"), "sub/inner", "nodes[0] and nodes[1]"),
        (("a%2Fb", "a%2Fb"), "a%2Fb", "nodes[0] and nodes[1]"),
    ],
)
def test_the_message_names_the_first_repeat_and_both_of_its_positions(
    ids: tuple[str, ...], duplicate: str, positions: str
) -> None:
    """Which repeat is reported is the earliest one in authored order, at both indices.

    The last two rows are the ones a nesting- or escaping-blind implementation gets wrong: a
    node id is a whole ``/``-joined path (§5.1), and ``%2F`` is an escaped separator inside a
    single segment — both are compared as the strings they are, which is also the form §6.2
    sorts by. When several ids repeat, the first repeat encountered is the reported one, so
    the message is deterministic rather than dependent on set iteration order.
    """
    with pytest.raises(ValidationError) as raised:
        WorkflowIR(
            ir_version="1.0",
            entry=ids[0],
            finish=ids[0],
            nodes=tuple(Node(id=node_id) for node_id in ids),
            edges=(),
        )

    (error,) = raised.value.errors()
    assert f"node id {duplicate!r} is declared twice" in error["msg"]
    assert positions in error["msg"]


def test_a_repeat_is_refused_rather_than_collapsed() -> None:
    """Two nodes sharing an id are *different* items, and neither survives silently.

    Deduplicating would discard a declared node contract and change the digest of a document
    its author wrote; §5.3's "one id names at most one node" says the document is wrong, not
    that one of its rows is redundant. So the differing-contract case and the byte-identical
    case are refused alike.
    """
    for second in ({"pure": True}, {"pure": False}):
        with pytest.raises(ValidationError, match="declared twice"):
            WorkflowIR.model_validate_json(
                json.dumps(
                    {
                        "ir_version": "1.0",
                        "entry": "a",
                        "finish": "a",
                        "nodes": [
                            {"id": "a", "annotations": {"pure": True}},
                            {"id": "a", "annotations": second},
                        ],
                        "edges": [],
                    }
                )
            )


def test_the_duplicate_is_reported_alongside_other_field_errors() -> None:
    """A field validator, not a model-after one, so one bad field never hides the other.

    A ``model_validator(mode="after")`` runs only once every field has validated, so a
    document that is *also* missing ``edges`` would report the missing member alone and the
    author would fix one fault to discover the next. Both are reported here.
    """
    with pytest.raises(ValidationError) as raised:
        WorkflowIR.model_validate(
            {"ir_version": "1.0", "entry": "a", "finish": "a", "nodes": (Node(id="a"),) * 2}
        )

    reported = {error["loc"]: error["type"] for error in raised.value.errors()}
    assert reported == {("nodes",): "value_error", ("edges",): "missing"}


# ── Box 3: the boundary — this rule and no wider one ──────────────────────────────────────


def test_reference_role_strings_may_still_repeat() -> None:
    """§2.1's MUST is on the ``nodes`` array; nothing else gained a uniqueness rule.

    ``entry``/``finish`` list forms are *sets* whose duplicate members §6.3 collapses (§4.2
    m5), and ``edges[]`` deliberately keeps duplicate objects — §6.2 sorts them without
    deduplicating, so multiplicity is content there. Repeating a reference is therefore
    ordinary, and only a repeated *declaration* is refused.
    """
    ir = WorkflowIR.model_validate_json(
        json.dumps(
            {
                "ir_version": "1.0",
                "entry": ["a", "a", "b"],
                "finish": ["b", "b"],
                "nodes": [{"id": "a"}, {"id": "b"}],
                "edges": [
                    {"from": "a", "to": "b"},
                    {"from": "a", "to": "b"},
                ],
            }
        )
    )

    assert ir.entry == ("a", "a", "b")
    assert len(ir.edges) == 2
    assert graph_version(ir).startswith("sha256:")


def test_an_nfd_spelled_id_is_refused_before_uniqueness_is_ever_compared() -> None:
    """Byte equality is a sound identity test only because NFC is enforced one stage earlier.

    §5.1 fixes comparison as "exact byte equality of the escaped form", and this module's
    check is Python ``str`` equality, which is exactly that. The pair that would defeat it is
    an NFC/NFD spelling of one name: two byte-different ids that §6.1 step 5 later normalizes
    onto one, which would tie §6.2's sort key after uniqueness had already passed — PD-032
    reintroduced one stage downstream. It cannot happen, because item validation runs first
    and ``Node.id`` refuses a segment that is not NFC (IR-02's ruling, checked on the
    *decoded* segment). That composition is what this test records, so a future relaxation
    upstream fails here rather than silently weakening the rule above.
    """
    # Spelled as escapes: the two ids display identically, so a literal pair here would
    # be a test whose whole point is invisible in the source (and re-normalizable by an
    # editor). U+00E9 versus "e" + U+0301, both rendering as the same five glyphs.
    nfc, nfd = "caf\u00e9", "cafe\u0301"
    assert nfc != nfd

    with pytest.raises(ValidationError) as raised:
        WorkflowIR.model_validate_json(
            json.dumps(
                {
                    "ir_version": "1.0",
                    "entry": nfc,
                    "finish": nfc,
                    "nodes": [{"id": nfc}, {"id": nfd}],
                    "edges": [],
                }
            )
        )

    (error,) = raised.value.errors()
    assert error["loc"] == ("nodes", 1, "id")
    assert "not NFC-normalized" in error["msg"]


def test_the_constraint_stays_out_of_the_generated_json_schema() -> None:
    """IR-05's lockstep compares the model's schema against the vendored ``schema.yaml``.

    The rule is uniqueness of the ``id`` *member*, which JSON Schema's ``uniqueItems`` does
    not express (two nodes sharing an id and differing in annotations are distinct items), and
    the vendored schema declares neither. An ``AfterValidator`` leaves the generated schema
    exactly as it was — the same posture IR-02 took for the §5 id grammar.
    """
    schema = WorkflowIR.model_json_schema()
    nodes = schema["properties"]["nodes"]

    assert "uniqueItems" not in nodes
    assert nodes["minItems"] == 1
    assert "uniqueItems" not in json.dumps(schema)


def test_a_model_copy_can_still_build_one_so_the_engine_floors_stay_load_bearing() -> None:
    """Why ``gebra.diff``'s resolver check is kept rather than downgraded to an assertion.

    ``model_construct`` is banned outright on the frozen base (A6 PC-6), but
    ``model_copy(update=...)`` is public pydantic API and skips validation by design — so a
    document repeating an id is still *constructible*, just no longer loadable. The engines
    that key every delta on node identity therefore keep refusing it themselves, with the
    ``ValueError`` their callers already branch on
    (``tests/diff``, ``tests/snapshot`` and ``tests/audit`` pin those refusals).
    """
    base = WorkflowIR.model_validate_json(CONFORMING)
    doubled = base.model_copy(update={"nodes": (*base.nodes, base.nodes[0])})

    assert [node.id for node in doubled.nodes] == ["a", "b", "a"]
    with pytest.raises(ValidationError, match="declared twice"):
        WorkflowIR.model_validate(doubled.model_dump(by_alias=True))


def test_no_str_subclass_method_runs_while_the_ids_are_compared() -> None:
    """WA-07 at the smallest scale: the check calls ``str``'s methods, never an object's.

    Strict mode coerces ``Node.id`` to an exact ``str`` on every validated path, so this is
    unreachable through a loader; ``model_copy`` puts a foreign ``str`` subclass there anyway,
    which is the residual reach. The dict key and the message are taken through unbound
    ``str.__str__``/``str.__repr__``, so a hostile ``__hash__``, ``__eq__`` or ``__repr__``
    is never given the chance to run — the same discipline
    :func:`~gebra.ir.identity.synthetic_segment` uses on selectors.
    """

    class Hostile(str):
        def __hash__(self) -> int:
            raise AssertionError("__hash__ ran")

        def __eq__(self, other: object) -> bool:
            raise AssertionError("__eq__ ran")

        def __repr__(self) -> str:
            raise AssertionError("__repr__ ran")

    node = Node(id="a").model_copy(update={"id": Hostile("a")})

    with pytest.raises(ValidationError, match="declared twice"):
        WorkflowIR(ir_version="1.0", entry="a", finish="a", nodes=(node, node), edges=())


def test_a_written_duplicate_is_refused_when_it_is_read_back(tmp_path: Path) -> None:
    """The write side is deliberately *not* a second enforcement point, and that is conforming.

    §2.1 words its MUST at loaders, so :func:`~gebra.ir.serialization.write_ir` — which dumps
    a model rather than validating one — writes a model built past validation without
    complaint. What this pins is the consequence: the file it produces is one the loader that
    wrote it refuses, so a duplicate never survives a round trip even though the writer never
    checked. Adding a check to the writer would be a second opinion about a rule the loader
    already owns.
    """
    base = WorkflowIR.model_validate_json(CONFORMING)
    doubled = base.model_copy(update={"nodes": (*base.nodes, base.nodes[0])})
    path = tmp_path / "doubled.ir.yaml"

    write_ir(doubled, path)
    with pytest.raises(ValidationError, match="declared twice"):
        read_ir(path)


# ── Box 2: nothing that conformed before changed ──────────────────────────────────────────


def test_every_corpus_payload_and_committed_golden_still_loads() -> None:
    """The whole document-conformance surface (§1.3), loaded through the model.

    DEC-22's no-digest-moves ruling rests on the corpus being sweep-clean of duplicates, and
    this is that sweep re-run as a standing check: if any vendored payload or committed golden
    declared an id twice, tightening the model would have broken it here.
    """
    blocks = _ir_blocks()
    assert blocks, f"no IR payloads found under {FIXTURES_DIR}"

    for label, block in blocks:
        ids = [node["id"] for node in block["nodes"]]
        assert len(ids) == len(set(ids)), f"{label} declares a node id twice"
        WorkflowIR.model_validate_json(json.dumps(block))

    for path in sorted(GOLDEN_DIR.rglob("*.authored.yaml")):
        read_ir(path)


def test_no_canonical_byte_or_digest_moves() -> None:
    """Acceptance box 2's pin: every corpus payload's and golden's digest, absolutely.

    The table is rendered fresh and fingerprinted; the constant it is compared against was
    captured from this build before the constraint landed. Regenerate deliberately, never to
    make this pass: a move here means either a re-vendored corpus (WA-04, R-05 sign-off) or a
    canonicalization change (WA-05 justification + an ``ir_version`` bump, DEC-09).
    """
    table = _canonical_table()
    rendered = "\n".join(table) + "\n"
    fingerprint = hashlib.sha256(rendered.encode("utf-8")).hexdigest()

    assert len(table) == CANONICAL_ENTRIES
    assert fingerprint == CANONICAL_FINGERPRINT, (
        "a canonical digest or byte length moved for a vendored corpus payload or a "
        "committed golden. IR-07 adds validation only — it touches no field, no "
        f"serialization rule and no hash input. The table as rendered now:\n{rendered}"
    )
