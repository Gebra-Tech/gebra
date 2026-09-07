"""IR-SPEC §2.5 note 7's ``ir_version`` stamp floor, on the model — the DEC-34 regression (IR-08).

The rule and its history: §2.4 has described kind ``dynamic`` as an ``ir_version`` ≥ 1.1
construct since DEC-28, and §8 told **emitters** to stamp the lowest sufficient minor — but
neither passage named a site that enforced the relation on a document being *read*, and the
§2.5 stub carried no cross-field rule. VAL-14's IR-spec pre-review found the gap and filed it
as PD-055: a hand-authored document stamped ``"1.0"`` that carried a ``dynamic`` edge validated,
canonicalized to a digest differing from its correctly stamped twin's, and was verified under
the dynamic semantics and reported at its own stamp. Ratified 2026-09-06 as **DEC-34, option
1**: the floor is loader validity, over-stamping stays admitted, ``ir_version`` does not bump —
on the DEC-22/IR-07 precedent, because the constraint rejects only documents §2.4 already
described as outside the kind's version and moves no digest byte.

This module is the regression suite for the model half of that ruling. Four claims, matching
the card's acceptance boxes:

1. **An under-stamped document is rejected at model validation**, through every ingestion path
   the package offers, with the stamp, the lowest sufficient minor and the offending edge
   named (:func:`~gebra.ir.models._require_sufficient_ir_version`) — and the loader never
   re-stamps it.
2. **Over-stamping is admitted**, unchanged: a ``"1.1"`` document with no ``dynamic`` edge
   loads, canonicalizes and digests exactly as it did before.
3. **Nothing that conformed before changed.** Every vendored corpus IR payload and every
   committed golden still loads, with canonical byte lengths and digests byte-identical to
   what this build produced before *either* identity constraint landed — pinned absolutely
   against IR-07's pre-constraint capture (:data:`STAMP_FLOOR_FINGERPRINT`), not merely
   recomputed self-consistently.
4. The boundary is *this* rule and no wider one: the floor is a floor and not an equality, it
   is stated generally rather than as a ``dynamic`` special case, and it stays out of
   ``model_json_schema()`` so IR-05's lockstep check still sees the vendored vocabulary.

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
from pydantic import TypeAdapter, ValidationError

from gebra.ir import (
    IR_VERSION,
    IR_VERSION_DYNAMIC_EDGES,
    IR_VERSIONS,
    DynamicEdge,
    Edge,
    IrVersion,
    WorkflowIR,
    canonical_bytes,
    graph_version,
    load_json,
    load_yaml,
    lowest_ir_version,
    read_ir,
    write_ir,
)
from tests.ir.test_node_id_uniqueness import (
    CANONICAL_ENTRIES,
    CANONICAL_FINGERPRINT,
    _canonical_table,
    _ir_blocks,
)

GOLDEN_DIR: Final = Path(__file__).parent / "golden"

#: The document PD-055 reproduced the defect with: the ``dynamic`` edge kind under a ``"1.0"``
#: stamp. Two workers converge on ``collect``; ``plan`` dispatches to them dynamically.
UNDER_STAMPED: Final = json.dumps(
    {
        "ir_version": "1.0",
        "entry": "plan",
        "finish": "collect",
        "nodes": [{"id": "plan"}, {"id": "book_leg"}, {"id": "collect"}],
        "edges": [
            {"kind": "dynamic", "from": "plan", "condition": "route_legs"},
            {"kind": "normal", "from": "book_leg", "to": "collect"},
        ],
    }
)

#: The same document stamped as §8 requires — the "correctly stamped twin" DEC-34 names. It
#: loads, and it is what the under-stamped document was trying to say.
CORRECTLY_STAMPED: Final = json.dumps(
    {**json.loads(UNDER_STAMPED), "ir_version": IR_VERSION_DYNAMIC_EDGES}
)

#: The opposite under-use, admitted by §8's own wording: a stamp above the floor, on a
#: document using no 1.1 construct.
OVER_STAMPED: Final = json.dumps(
    {
        "ir_version": "1.1",
        "entry": "plan",
        "finish": "collect",
        "nodes": [{"id": "plan"}, {"id": "collect"}],
        "edges": [{"kind": "normal", "from": "plan", "to": "collect"}],
    }
)

#: Its minimally stamped twin — the same content at ``"1.0"``.
MINIMALLY_STAMPED: Final = json.dumps({**json.loads(OVER_STAMPED), "ir_version": IR_VERSION})

#: IR-07's absolute no-move pin, re-asserted here rather than re-captured. The table was
#: fingerprinted on this build **before** the DEC-22 constraint landed; DEC-34's constraint is
#: the second validation tightening to leave it untouched, and reusing the one constant says
#: exactly that — a freshly captured baseline could only say "unchanged since a moment ago",
#: and could be quietly re-based. What moves it legitimately is listed at its definition
#: (a re-vendored corpus, a ratified canonicalization change, a golden added to the set).
#:
#: The cost of the reuse, stated rather than hidden: this pin is **not** independent of
#: IR-07's. A legitimate re-base of that constant moves both cards' no-move claims at once,
#: with no second signal — so the justification recorded there has to cover both.
STAMP_FLOOR_FINGERPRINT: Final = CANONICAL_FINGERPRINT

#: The vendored corpus census DEC-34 §4 measured at ratification, as an assertion.
CORPUS_PAYLOADS: Final = 78
CORPUS_FILES: Final = 71


# ── Box 1: an under-stamped document is rejected at model validation ──────────────────────


def test_the_pd055_repro_document_is_rejected_with_the_stamp_and_the_edge_named() -> None:
    """The document PD-055 reproduced, refused where DEC-34 puts the rule.

    The error is an ordinary ``ValidationError`` at ``loc = ("edges",)`` — the array holding
    the construct that raises the floor — and it names all three things the ruling asks for:
    the stamp as declared, the lowest sufficient minor, and which edge is the offender.
    """
    with pytest.raises(ValidationError) as raised:
        WorkflowIR.model_validate_json(UNDER_STAMPED)

    (error,) = raised.value.errors()
    assert error["type"] == "value_error"
    assert error["loc"] == ("edges",)
    assert "ir_version '1.0' is below the lowest minor" in error["msg"]
    assert "edges[0] is of kind 'dynamic'" in error["msg"]
    assert "'1.1' is the lowest sufficient minor" in error["msg"]
    assert "§2.5 note 7" in error["msg"] and "DEC-34" in error["msg"]


def test_every_ingestion_path_refuses_it(tmp_path: Path) -> None:
    """§2.5 note 7's MUST is worded at the *loader*, so every loader this package ships enforces it.

    The constructor, both ``model_validate`` modes, the two format entry points and the
    suffix-dispatching :func:`~gebra.ir.serialization.read_ir` all route through the same
    field validator, so there is one refusal rather than six spellings of one. The Python-mode
    call is spelled with tuples and built models because strict mode admits nothing wider
    there (A6 PC-3; IR-SPEC §2.5 note 4 is why the JSON path exists at all).
    """
    payload = json.loads(UNDER_STAMPED)
    edges = TypeAdapter(tuple[Edge, ...]).validate_python(tuple(payload["edges"]))
    built: dict[str, Any] = {
        "ir_version": "1.0",
        "entry": "plan",
        "finish": "collect",
        "nodes": tuple({"id": node["id"]} for node in payload["nodes"]),
        "edges": edges,
    }

    with pytest.raises(ValidationError, match="below the lowest minor"):
        WorkflowIR(**built)
    with pytest.raises(ValidationError, match="below the lowest minor"):
        WorkflowIR.model_validate(built)
    with pytest.raises(ValidationError, match="below the lowest minor"):
        WorkflowIR.model_validate_json(UNDER_STAMPED)
    with pytest.raises(ValidationError, match="below the lowest minor"):
        load_json(WorkflowIR, UNDER_STAMPED)
    with pytest.raises(ValidationError, match="below the lowest minor"):
        load_yaml(WorkflowIR, yaml.safe_dump(payload))

    document = tmp_path / "under-stamped.ir.yaml"
    document.write_text(yaml.safe_dump(payload), encoding="utf-8")
    with pytest.raises(ValidationError, match="below the lowest minor"):
        read_ir(document)


def test_the_loader_refuses_rather_than_re_stamping() -> None:
    """DEC-34 §3: "The loader refuses; it never re-stamps."

    Re-stamping is the tempting repair and the one the ruling forbids in terms, because
    ``ir_version`` is inside the §6.4 hash scope: a loader that quietly raised ``"1.0"`` to
    ``"1.1"`` would hand back a document with a different ``graph_version`` from the one its
    author wrote and digested.

    The digest claim is deliberately demonstrated on the ``"1.1"``/``"1.0"`` pair that *both*
    load, because the pair a re-stamp would create cannot be measured directly: the
    under-stamped half no longer digests by loading at all. That is the stronger statement of
    the two — the stamp is in the hashed payload, so no two stamps of one content share a
    digest, and a silent repair could therefore never be silent.
    """
    with pytest.raises(ValidationError):
        WorkflowIR.model_validate_json(UNDER_STAMPED)

    twin = WorkflowIR.model_validate_json(CORRECTLY_STAMPED)
    assert twin.ir_version == "1.1"
    assert b'"ir_version":"1.1"' in canonical_bytes(twin)

    over = WorkflowIR.model_validate_json(OVER_STAMPED)
    minimally = WorkflowIR.model_validate_json(MINIMALLY_STAMPED)
    assert graph_version(over) != graph_version(minimally)


def test_the_refusal_is_reported_alongside_other_field_errors() -> None:
    """A field validator, not a model-after one, so one bad field never hides the other.

    A ``model_validator(mode="after")`` runs only once every field has validated, so a
    document that is *also* missing ``nodes`` would report the missing member alone and the
    author would fix one fault to discover the next — IR-07's reason for putting the
    uniqueness MUST on ``nodes`` rather than on the model. Both are reported here.
    """
    with pytest.raises(ValidationError) as raised:
        WorkflowIR.model_validate(
            {
                "ir_version": "1.0",
                "entry": "plan",
                "finish": "collect",
                "edges": TypeAdapter(tuple[Edge, ...]).validate_python(
                    ({"kind": "dynamic", "from": "plan"},)
                ),
            }
        )

    reported = {error["loc"]: error["type"] for error in raised.value.errors()}
    assert reported == {("nodes",): "missing", ("edges",): "value_error"}


def test_a_malformed_stamp_is_reported_on_its_own() -> None:
    """When ``ir_version`` itself fails, the floor check stands down rather than guessing.

    ``info.data`` carries only the members that validated, so a document stamped ``"0.9"``
    has no stamp to compare against. Reporting a second, derived error there would tell the
    author their edges are wrong when the fault is the one pydantic already named.
    """
    with pytest.raises(ValidationError) as raised:
        WorkflowIR.model_validate_json(
            json.dumps({**json.loads(UNDER_STAMPED), "ir_version": "0.9"})
        )

    reported = {error["loc"]: error["type"] for error in raised.value.errors()}
    assert reported == {("ir_version",): "literal_error"}


def test_an_edge_validated_on_its_own_is_untouched_by_the_floor() -> None:
    """The floor is a *document* rule, and an edge outside a document has no stamp to floor.

    ``Edge`` is validatable directly (a ``TypeAdapter``, the tagless-surface note on the
    alias), and that path carries no ``ir_version``. The check reads ``info.data`` and finds
    nothing, so it stands down — a ``dynamic`` edge is still a well-formed edge.
    """
    edge: Edge = TypeAdapter(Edge).validate_python({"kind": "dynamic", "from": "plan"})

    assert isinstance(edge, DynamicEdge)
    assert lowest_ir_version((edge,)) == IR_VERSION_DYNAMIC_EDGES


@pytest.mark.parametrize(
    ("index", "edges"),
    [
        (0, [{"kind": "dynamic", "from": "plan"}, {"kind": "normal", "from": "a", "to": "b"}]),
        (1, [{"kind": "normal", "from": "a", "to": "b"}, {"kind": "dynamic", "from": "plan"}]),
        (
            2,
            [
                {"kind": "normal", "from": "a", "to": "b"},
                {"kind": "send", "from": "b", "to": "a"},
                {"kind": "dynamic", "from": "plan"},
                {"kind": "dynamic", "from": "a"},
            ],
        ),
    ],
    ids=("first", "second", "third-of-two"),
)
def test_the_message_names_the_first_offending_edge_in_authored_order(
    index: int, edges: list[dict[str, Any]]
) -> None:
    """Which offender is reported is the earliest in authored order, deterministically.

    The last row carries two ``dynamic`` edges and the message names the first: a check that
    reported whichever the iteration happened to reach would make the message depend on order
    the author cannot see. Authored order is the one order every ingestion path preserves.
    """
    with pytest.raises(ValidationError) as raised:
        WorkflowIR.model_validate_json(
            json.dumps(
                {
                    "ir_version": "1.0",
                    "entry": "plan",
                    "finish": "plan",
                    "nodes": [{"id": "plan"}, {"id": "a"}, {"id": "b"}],
                    "edges": edges,
                }
            )
        )

    (error,) = raised.value.errors()
    assert f"edges[{index}] is of kind 'dynamic'" in error["msg"]


def test_a_written_under_stamp_is_refused_when_it_is_read_back(tmp_path: Path) -> None:
    """The write side is deliberately *not* a second enforcement point, and that is conforming.

    Note 7 words its MUST at loaders, so :func:`~gebra.ir.serialization.write_ir` — which
    dumps a model rather than validating one — writes a model built past validation without
    complaint. What this pins is the consequence: the file it produces is one the loader that
    wrote it refuses, so an under-stamp never survives a round trip. The same posture IR-07
    recorded for a repeated node id.
    """
    twin = WorkflowIR.model_validate_json(CORRECTLY_STAMPED)
    lowered = twin.model_copy(update={"ir_version": IR_VERSION})
    path = tmp_path / "lowered.ir.yaml"

    write_ir(lowered, path)
    with pytest.raises(ValidationError, match="below the lowest minor"):
        read_ir(path)


# ── Box 2: over-stamping stays admitted ───────────────────────────────────────────────────


def test_an_over_stamped_document_still_loads_and_digests() -> None:
    """DEC-34 §3: "Over-stamping stays admitted."

    §8's minimal-stamping MUST binds emitters, not documents: a ``"1.1"`` document with no
    ``dynamic`` edge uses no construct its loader lacks, so refusing it would make the loader
    police an emitter obligation. Its digest differs from its minimally stamped twin's —
    already true before this card, and the emitter's cost, not the loader's.

    The other two halves of "loads, verifies and records" are where those surfaces live:
    ``tests/verify/test_dynamic_edges.py``'s ``stamped_only`` half runs the same document
    through :func:`gebra.verify.verify` and :func:`gebra.snapshot.record`, and this card left
    it untouched precisely because it is the over-stamp admission.
    """
    over = WorkflowIR.model_validate_json(OVER_STAMPED)
    minimal = WorkflowIR.model_validate_json(MINIMALLY_STAMPED)

    assert over.ir_version == "1.1"
    assert lowest_ir_version(over.edges) == IR_VERSION  # it is over-stamped, and admitted
    assert graph_version(over).startswith("sha256:")
    assert graph_version(over) != graph_version(minimal)


def test_the_floor_admits_every_stamp_at_or_above_it() -> None:
    """The rule is ≥, stated as a table over the whole ``ir_version`` × construct grid.

    Four cells, three admitted and one refused — the asymmetry is the ruling, so it is asserted
    as a grid rather than as two separate happy paths.
    """
    admitted = {
        ("1.0", False),
        ("1.1", False),  # over-stamped
        ("1.1", True),  # minimally stamped for its constructs
    }
    for stamp in IR_VERSIONS:
        for dynamic in (False, True):
            payload: dict[str, Any] = {
                "ir_version": stamp,
                "entry": "plan",
                "finish": "collect",
                "nodes": [{"id": "plan"}, {"id": "collect"}],
                "edges": [{"kind": "normal", "from": "plan", "to": "collect"}],
            }
            if dynamic:
                payload["edges"].append({"kind": "dynamic", "from": "plan"})

            if (stamp, dynamic) in admitted:
                ir = WorkflowIR.model_validate_json(json.dumps(payload))
                assert ir.ir_version == stamp
            else:
                with pytest.raises(ValidationError, match="below the lowest minor"):
                    WorkflowIR.model_validate_json(json.dumps(payload))


def test_a_1_1_document_with_no_dynamic_edge_round_trips(tmp_path: Path) -> None:
    """The admitted over-stamp, through the file path a user actually takes."""
    path = tmp_path / "over-stamped.ir.yaml"
    path.write_text(yaml.safe_dump(json.loads(OVER_STAMPED)), encoding="utf-8")

    ir = read_ir(path)
    assert ir.ir_version == "1.1"

    written = tmp_path / "again.ir.yaml"
    write_ir(ir, written)
    assert read_ir(written) == ir


# ── Box 3: nothing that conformed before changed ──────────────────────────────────────────


def test_every_corpus_payload_and_committed_golden_still_loads() -> None:
    """The whole document-conformance surface (§1.3), loaded through the model.

    DEC-34's no-digest-moves ruling rests on the corpus carrying no ``dynamic`` edge, and this
    is that sweep re-run as a standing check with the census the ruling measured: if any
    vendored payload stamped ``"1.0"`` had carried one, tightening the model would have broken
    it here.
    """
    blocks = _ir_blocks()
    files = {label.split("::")[0] for label, _ in blocks}
    assert (len(blocks), len(files)) == (CORPUS_PAYLOADS, CORPUS_FILES)

    for label, block in blocks:
        kinds = {edge.get("kind", "normal") for edge in block["edges"]}
        assert "dynamic" not in kinds, f"{label} carries a dynamic edge"
        ir = WorkflowIR.model_validate_json(json.dumps(block))
        assert lowest_ir_version(ir.edges) == IR_VERSION

    for path in sorted(GOLDEN_DIR.rglob("*.authored.yaml")):
        read_ir(path)


def test_no_canonical_byte_or_digest_moves() -> None:
    """The no-move pin, absolutely: every corpus payload's and golden's digest.

    The table is rendered fresh and fingerprinted; the constant it is compared against was
    captured from this build before IR-07's constraint landed, and this card is the second
    validation tightening to leave it where it was. Regenerate deliberately, never to make
    this pass: a move here means either a re-vendored corpus (WA-04, R-05 sign-off) or a
    canonicalization change (WA-05 justification + an ``ir_version`` bump, DEC-09) — and
    neither is what a stamp floor is.
    """
    table = _canonical_table()
    rendered = "\n".join(table) + "\n"
    fingerprint = hashlib.sha256(rendered.encode("utf-8")).hexdigest()

    assert len(table) == CANONICAL_ENTRIES
    assert fingerprint == STAMP_FLOOR_FINGERPRINT, (
        "a canonical digest or byte length moved for a vendored corpus payload or a "
        "committed golden. IR-08 adds validation only — it touches no field, no "
        f"serialization rule and no hash input. The table as rendered now:\n{rendered}"
    )


def test_ir_version_did_not_bump() -> None:
    """DEC-34 §4: the constraint carries no bump, and the two constants say so.

    §4's reconciliation is measured rather than asserted: no field is added, renamed, removed,
    retyped or re-semanticized; ``ir_version`` stays REQUIRED with the same two-member domain;
    and the rejected set is the documents §2.4 already described as outside the kind's version.
    """
    assert IR_VERSION == "1.0"
    assert IR_VERSIONS == ("1.0", "1.1")
    assert IrVersion.__args__ == ("1.0", "1.1")  # type: ignore[attr-defined]
    assert WorkflowIR.model_fields["ir_version"].is_required()


# ── Box 4: the boundary — this rule and no wider one ──────────────────────────────────────


def test_the_rule_is_stated_generally_rather_than_as_a_dynamic_special_case() -> None:
    """The construct → minor map lives in one place, so a future *edge* minor inherits the floor.

    DEC-34 §3 states the rule in §8's own phrase — "the lowest sufficient minor" — precisely so
    that a later minor needs no second ruling. The implementation follows: the validator
    compares against :func:`~gebra.ir.lowest_ir_version` over :data:`IR_VERSIONS`' ascending
    order and hardcodes no kind, so teaching that one function a new **edge kind** teaches the
    floor at the same time. This test pins the coupling: the floor the validator enforces on a
    document is exactly what that function returns for its edges.

    The generality has two stated limits, recorded on ``lowest_ir_version`` rather than
    asserted away here: the offender search assumes the floor decomposes per edge, and a minor
    introduced by a non-edge construct — a ``runtime`` sub-slot, an annotation — needs the
    check re-sited rather than that function extended.
    """
    for text in (CORRECTLY_STAMPED, OVER_STAMPED, MINIMALLY_STAMPED):
        ir = WorkflowIR.model_validate_json(text)
        floor = lowest_ir_version(ir.edges)
        assert IR_VERSIONS.index(ir.ir_version) >= IR_VERSIONS.index(floor)

    assert IR_VERSIONS == (IR_VERSION, IR_VERSION_DYNAMIC_EDGES)
    assert lowest_ir_version(()) == IR_VERSION


def test_the_constraint_stays_out_of_the_generated_json_schema() -> None:
    """IR-05's lockstep compares the model's schema against the vendored ``schema.yaml``.

    The rule is a relation between two members, which JSON Schema's vocabulary does not
    express, and the vendored fixture schema (v2.3: ``ir_version`` a bare ``type: string``)
    declares no such rule — the authorized divergence DEC-34 §4 records. An ``AfterValidator``
    leaves the generated schema exactly as it was, the same posture IR-02 took for the §5 id
    grammar and IR-07 for uniqueness.
    """
    schema = WorkflowIR.model_json_schema()
    text = json.dumps(schema)

    assert schema["properties"]["ir_version"]["enum"] == ["1.0", "1.1"]
    assert "dependentRequired" not in text and "dependentSchemas" not in text
    assert "allOf" not in schema["properties"]["edges"]


def test_the_field_order_the_check_depends_on_is_the_specs_own() -> None:
    """``info.data`` carries ``ir_version`` only because §2.1 declares it first.

    That ordering is IR-SPEC §2.1's, not a convenience — but a reordering of the class body
    would silently disable the floor rather than fail loudly, so the dependency is recorded
    here. A future move of ``ir_version`` below ``edges`` fails on this line and not on a
    document nobody wrote.
    """
    order = tuple(WorkflowIR.model_fields)

    assert order.index("ir_version") < order.index("edges")
    assert order == ("ir_version", "entry", "finish", "state", "nodes", "edges", "runtime")


def test_a_model_copy_can_still_build_one_so_the_construct_declines_stay_load_bearing() -> None:
    """Why the engine-level ``dynamic`` declines are kept rather than downgraded.

    DEC-34 §3 records the same boundary DEC-22/IR-07 did: ``model_construct`` is banned on the
    frozen base (A6 PC-6), but ``model_copy(update=...)`` is public pydantic API and skips
    validation by design — so an under-stamped model is still *constructible*, just no longer
    loadable. The construct-keyed declines (``gebra.ir.refuse_dynamic_edges`` in the diff, the
    store, the freshness check and the pytest gate — SD-12) therefore stay in place, and they
    key on the edge kind rather than on the stamp, so they are unmoved either way.
    """
    twin = WorkflowIR.model_validate_json(CORRECTLY_STAMPED)
    lowered = twin.model_copy(update={"ir_version": IR_VERSION})

    assert lowered.ir_version == "1.0"
    assert lowest_ir_version(lowered.edges) == IR_VERSION_DYNAMIC_EDGES
    with pytest.raises(ValidationError, match="below the lowest minor"):
        WorkflowIR.model_validate(lowered.model_dump(by_alias=True))


def test_no_str_subclass_method_runs_while_the_refusal_is_formatted() -> None:
    """WA-07 at the smallest scale: the message calls ``str``'s methods, never an object's.

    The reach is real, and it is on the edge rather than on the stamp. A built ``Edge`` model
    handed to ``edges`` is not re-validated (pydantic's default ``revalidate_instances``), so a
    ``model_copy`` that puts a foreign ``str`` subclass on ``kind`` survives into the message
    the validator formats — and the message would run that subclass's ``__repr__`` or
    ``__format__``. It does not: the kind goes through unbound ``str.__str__``/``str.__repr__``
    first, the same discipline :func:`~gebra.ir.identity.synthetic_segment` and
    :func:`~gebra.ir.models._require_unique_node_ids` use.

    On the stamp the unbound calls are belt-and-braces, but the fact they lean on is not
    decorative: ``ir_version`` is a ``Literal``, so pydantic hands ``info.data`` an exact
    ``str`` even when the input was a subclass — and that coercion is the **only** guard on
    the validator's ``in``/``index`` comparisons, which the unbound calls do not reach (they
    wrap the message, not the comparison). The last assertion here pins it, so a future
    widening of the annotation to a bare ``str`` shows up as a changed fact rather than as a
    silently reachable reflected ``__eq__``.

    ``Hostile`` deliberately leaves ``__hash__`` and ``__eq__`` benign, unlike its IR-07
    sibling in ``tests/ir/test_node_id_uniqueness.py``: pydantic's own tag and literal lookups
    call them *before* this validator runs, so raising there would fail the document with
    ``literal_error`` and this test would assert about pydantic-core rather than about the
    code under review.
    """

    class Hostile(str):
        def __repr__(self) -> str:
            raise AssertionError("__repr__ ran")

        def __format__(self, spec: str) -> str:
            raise AssertionError("__format__ ran")

    twin = WorkflowIR.model_validate_json(CORRECTLY_STAMPED)
    hostile_edge = twin.edges[0].model_copy(update={"kind": Hostile("dynamic")})
    assert type(hostile_edge.kind) is Hostile  # it really is still there

    with pytest.raises(ValidationError, match="below the lowest minor"):
        WorkflowIR(
            ir_version=IR_VERSION,
            entry="plan",
            finish="collect",
            nodes=twin.nodes,
            edges=(hostile_edge,),
        )

    lowered = twin.model_copy(update={"ir_version": Hostile("1.0")})
    assert type(lowered.model_dump(by_alias=True)["ir_version"]) is Hostile
    with pytest.raises(ValidationError, match="below the lowest minor"):
        WorkflowIR.model_validate(lowered.model_dump(by_alias=True))

    # …and the coercion that keeps it belt-and-braces there, stated as the fact it is.
    admitted = WorkflowIR.model_validate(
        {
            "ir_version": Hostile("1.1"),
            "entry": "plan",
            "finish": "collect",
            "nodes": twin.nodes,
            "edges": (),
        }
    )
    assert type(admitted.ir_version) is str
