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
the card's acceptance boxes (IR-08), and a fifth from the 1.2 event (IR-09 — DEC-39 §3.3,
DEC-40 §3.6): the floor is read over the **whole document**, every level included, so a node,
an edge or a ``state`` key can raise it, and the refusal names that one construct:

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
5. **The whole-document floor** (the section at the end): ``"1.2"`` iff a 1.2 construct is
   present at any level, ``"1.1"`` iff a ``dynamic`` edge and nothing newer, else ``"1.0"`` —
   each 1.2 construct refused below ``"1.2"`` through every ingestion path, named as the one
   offender, and restamping lower once it is removed.

Everything here is pure data (WA-07): documents are literals or fixture text read off disk,
and nothing is executed. The corpus is read read-only and never written (WA-04/WA-11).
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
from collections.abc import Callable
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
    Node,
    WorkflowIR,
    canonical_bytes,
    down_project,
    graph_version,
    load_json,
    load_yaml,
    lowest_ir_version,
    read_ir,
    write_ir,
)
from gebra.ir.models import _document_constructs
from tests._corpus import census
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

# The vendored corpus census DEC-34 §4 measured at ratification (78 payloads over 71 files)
# is asserted below as the census ``tests/_corpus.py`` derives from the provenance manifest,
# so a sanctioned re-vendor moves the record and the sweep's expectation follows it.


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

    Three stamps by three construct levels (none, a ``dynamic`` edge, a 1.2 ``barriers`` group
    — which, being a node member, is one the IR-08 edge scan could not see): six cells
    admitted and three refused. The asymmetry is the ruling, so it is asserted as a grid
    rather than as separate happy paths.
    """
    admitted = {
        ("1.0", "none"),
        ("1.1", "none"),  # over-stamped
        ("1.1", "dynamic"),  # minimally stamped for its constructs
        ("1.2", "none"),  # over-stamped
        ("1.2", "dynamic"),  # over-stamped
        ("1.2", "barriers"),  # minimally stamped
    }
    for stamp in IR_VERSIONS:
        for construct in ("none", "dynamic", "barriers"):
            payload: dict[str, Any] = {
                "ir_version": stamp,
                "entry": "plan",
                "finish": "collect",
                "nodes": [{"id": "plan"}, {"id": "draft"}, {"id": "collect"}],
                "edges": [
                    {"kind": "normal", "from": "plan", "to": "collect"},
                    {"kind": "normal", "from": "draft", "to": "collect"},
                ],
            }
            if construct == "dynamic":
                payload["edges"].append({"kind": "dynamic", "from": "plan"})
            if construct == "barriers":
                payload["nodes"][2]["barriers"] = [["draft", "plan"]]

            if (stamp, construct) in admitted:
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
    assert len(blocks) == census().ir_blocks
    assert files == set(census().fixture_ids)

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


def test_the_floor_itself_bumped_nothing_and_the_1_2_event_bumps_once() -> None:
    """DEC-34 §4: the floor carried no bump. The one move of the domain is the 1.2 event's.

    The floor (IR-08) added no field and left the two-member domain where it was; the domain
    moved once afterwards, at IR-09 — the one card DEC-39 and DEC-40 name for the
    ``ir_version`` literal — by appending ``"1.2"``. ``IR_VERSION`` stays ``"1.0"``: it is what
    an ordinary workflow is stamped, and ``ir_version`` stays REQUIRED.
    """
    assert IR_VERSION == "1.0"
    assert IR_VERSIONS == ("1.0", "1.1", "1.2")
    assert IrVersion.__args__ == ("1.0", "1.1", "1.2")  # type: ignore[attr-defined]
    assert WorkflowIR.model_fields["ir_version"].is_required()


# ── Box 4: the boundary — this rule and no wider one ──────────────────────────────────────


def test_the_rule_is_stated_generally_rather_than_as_a_dynamic_special_case() -> None:
    """The construct → minor map lives in one place, so a future minor inherits the floor.

    DEC-34 §3 states the rule in §8's own phrase — "the lowest sufficient minor" — precisely so
    that a later minor needs no second ruling. The implementation follows: the validator
    compares against :func:`~gebra.ir.lowest_ir_version`'s per-construct map over
    :data:`IR_VERSIONS`' ascending order, so teaching that one map a new construct teaches the
    floor at the same time. This test pins the coupling: the floor the validator enforces on a
    document is exactly what that function returns for it.

    IR-08 recorded two limits on the edge-only scan: the search assumed a per-edge
    decomposition, and a minor introduced by a non-edge construct "cannot be taught here at
    all". IR-09 re-sited the scan to the whole document (DEC-39 §3.3, DEC-40 §3.6), which
    lifts the second limit; the first stands, re-stated per construct, on
    ``lowest_ir_version`` itself.
    """
    for text in (CORRECTLY_STAMPED, OVER_STAMPED, MINIMALLY_STAMPED):
        ir = WorkflowIR.model_validate_json(text)
        floor = lowest_ir_version(ir)
        assert IR_VERSIONS.index(ir.ir_version) >= IR_VERSIONS.index(floor)
        assert floor == lowest_ir_version(ir.edges)  # no node or state construct here

    assert IR_VERSIONS == (IR_VERSION, IR_VERSION_DYNAMIC_EDGES, "1.2")
    assert lowest_ir_version(()) == IR_VERSION


def test_the_constraint_stays_out_of_the_generated_json_schema() -> None:
    """IR-05's lockstep compares the model's schema against the vendored ``schema.yaml``.

    The rule is a relation between two members, which JSON Schema's vocabulary does not
    express, and the vendored fixture schema (``ir_version`` a bare ``type: string``, its
    description naming the minors — v2.5) declares no such rule — the authorized divergence
    DEC-34 §4 records. An ``AfterValidator`` leaves the generated schema exactly as it was, the
    same posture IR-02 took for the §5 id grammar and IR-07 for uniqueness.
    """
    schema = WorkflowIR.model_json_schema()
    text = json.dumps(schema)

    assert schema["properties"]["ir_version"]["enum"] == ["1.0", "1.1", "1.2"]
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


def test_a_model_copy_can_still_build_one_so_the_engine_floor_stays_load_bearing() -> None:
    """Why an engine-level floor is kept beside the loader's rather than downgraded.

    DEC-34 §3 records the same boundary DEC-22/IR-07 did: ``model_construct`` is banned on the
    frozen base (A6 PC-6), but ``model_copy(update=...)`` is public pydantic API and skips
    validation by design — so an under-stamped model is still *constructible*, just no longer
    loadable. DEC-34 named the construct-keyed declines (``gebra.ir.refuse_dynamic_edges`` in
    the diff, the store, the freshness check and the pytest gate — SD-12) as the floor that
    reaches such a model; card SD-13 lifted those declines (a ``dynamic`` edge is diffed and
    recorded now — PD-059) and kept the floor, re-keyed on the stamp the loader keys on:
    :func:`gebra.diff.topology.resolve_subject` refuses a model stamped below the minor its
    constructs require, from either side (``tests/diff/test_topology.py``) — read over the whole
    document since IR-09, as the loader reads it. This test holds the
    model half — the document is buildable and not loadable — so that floor stays reachable.
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


# ── Box 5 (IR-09): the whole-document floor — DEC-39 §3.3, DEC-40 §3.6 ───────────────────


def _document(*, stamp: str = "1.2", **members: Any) -> dict[str, Any]:
    """A small, P-01-clean document: ``plan → draft → collect`` plus ``plan → collect``."""
    document: dict[str, Any] = {
        "ir_version": stamp,
        "entry": "plan",
        "finish": "collect",
        "nodes": [{"id": "plan"}, {"id": "draft"}, {"id": "collect"}],
        "edges": [
            {"kind": "normal", "from": "plan", "to": "draft"},
            {"kind": "normal", "from": "draft", "to": "collect"},
            {"kind": "normal", "from": "plan", "to": "collect"},
        ],
    }
    document.update(members)
    return document


def _with_node(document: dict[str, Any], index: int, **members: Any) -> dict[str, Any]:
    nodes = [dict(node) for node in document["nodes"]]
    nodes[index] = {**nodes[index], **members}
    return {**document, "nodes": nodes}


def _child(carrier: str = "draft") -> dict[str, Any]:
    """A one-node child level under ``carrier`` (IR-SPEC §3.8)."""
    return {
        "entry": f"{carrier}/write",
        "finish": f"{carrier}/write",
        "nodes": [{"id": f"{carrier}/write"}],
        "edges": [],
    }


#: One document per 1.2 construct class, the construct at the top level, with the clause the
#: refusal names it by (DEC-40 §3.6: "one offending node, edge or ``state`` key").
CONSTRUCTS_1_2: Final[dict[str, tuple[dict[str, Any], str]]] = {
    "subgraph": (
        _with_node(_document(), 1, subgraph=_child()),
        "nodes[1] ('draft') carries `subgraph`",
    ),
    "projection": (
        _with_node(_document(), 1, annotations={"projection": {"in": {"q": "q"}, "out": {}}}),
        "nodes[1] ('draft') carries `annotations.projection`",
    ),
    "join_key scalar": (
        _with_node(_document(), 2, annotations={"join_key": "city_code"}),
        "nodes[2] ('collect') carries `annotations.join_key`",
    ),
    "join_key list": (
        _with_node(_document(), 2, annotations={"join_key": ["city_code", "day"]}),
        "nodes[2] ('collect') carries `annotations.join_key`",
    ),
    "barriers": (
        _with_node(_document(), 2, barriers=[["draft", "plan"]]),
        "nodes[2] ('collect') carries `barriers`",
    ),
    "codomain": (
        _document(
            edges=[
                {"kind": "normal", "from": "plan", "to": "draft"},
                {"kind": "normal", "from": "draft", "to": "collect"},
                {
                    "kind": "conditional",
                    "from": "plan",
                    "path_map": {"go": "collect"},
                    "codomain": ["go", "stop"],
                },
            ]
        ),
        "edges[2] carries a `codomain` distinct from its `path_map` keys",
    ),
    "managed": (
        _document(state={"remaining_steps": {"type": "int", "managed": True}}),
        "state['remaining_steps'] carries `managed`",
    ),
    "assign token": (
        _document(
            entry="%seq[0]",
            finish="%seq[1]",
            nodes=[{"id": "%seq[0]"}, {"id": "%seq[1]"}, {"id": "%seq[1]/%assign[context]"}],
            edges=[{"kind": "normal", "from": "%seq[0]", "to": "%seq[1]"}],
        ),
        "nodes[2] ('%seq[1]/%assign[context]') carries a synthetic segment of kind 'assign'",
    ),
    "each token": (
        _document(
            entry="%each[0]",
            finish="%each[0]",
            nodes=[{"id": "%each[0]"}],
            edges=[],
        ),
        "nodes[0] ('%each[0]') carries a synthetic segment of kind 'each'",
    ),
    "leaf token": (
        _document(entry="%leaf[0]", finish="%leaf[0]", nodes=[{"id": "%leaf[0]"}], edges=[]),
        "nodes[0] ('%leaf[0]') carries a synthetic segment of kind 'leaf'",
    ),
}


@pytest.mark.parametrize("name", CONSTRUCTS_1_2)
def test_each_1_2_construct_floors_its_document_at_1_2(name: str) -> None:
    """``"1.2"`` iff a 1.2 construct is present: each class on its own, stamped exactly there."""
    document, _ = CONSTRUCTS_1_2[name]

    ir = WorkflowIR.model_validate_json(json.dumps(document))

    assert lowest_ir_version(ir) == "1.2"
    assert ir.ir_version == "1.2"
    assert canonical_bytes(ir).startswith(b"{")


@pytest.mark.parametrize("name", CONSTRUCTS_1_2)
@pytest.mark.parametrize("stamp", ["1.0", "1.1"])
def test_each_1_2_construct_is_refused_below_1_2_naming_itself(name: str, stamp: str) -> None:
    """Below ``"1.2"`` the document is refused, the one offender named with its own clause."""
    document, clause = CONSTRUCTS_1_2[name]

    with pytest.raises(ValidationError) as raised:
        WorkflowIR.model_validate_json(json.dumps({**document, "ir_version": stamp}))

    (error,) = raised.value.errors()
    assert error["loc"] == ("edges",)
    assert f"ir_version '{stamp}' is below the lowest minor" in error["msg"]
    assert clause in error["msg"]
    assert "'1.2' is the lowest sufficient minor" in error["msg"]
    assert "Stamp the document ir_version '1.2'" in error["msg"]


@pytest.mark.parametrize("name", ["subgraph", "barriers", "codomain", "managed", "assign token"])
def test_every_ingestion_path_refuses_an_under_stamped_1_2_document(
    name: str, tmp_path: Path
) -> None:
    """The constructor, both ``model_validate`` modes, ``load_json``, ``load_yaml``, ``read_ir``.

    One construct per member class — a node member, a node carrying a level, an edge member, a
    ``state`` entry and a token-bearing id — each through every path the package ships. The
    Python-mode calls are spelled from the validated twin's own members (strict mode admits no
    list for a tuple there — IR-SPEC §2.5 note 4), restamped ``"1.1"``.
    """
    document, clause = CONSTRUCTS_1_2[name]
    under = {**document, "ir_version": "1.1"}
    text = json.dumps(under)
    twin = WorkflowIR.model_validate_json(json.dumps(document))
    built: dict[str, Any] = {
        "ir_version": "1.1",
        "entry": twin.entry,
        "finish": twin.finish,
        "state": twin.state,
        "nodes": twin.nodes,
        "edges": twin.edges,
    }

    attempts: tuple[Callable[[], object], ...] = (
        lambda: WorkflowIR(**built),
        lambda: WorkflowIR.model_validate(built),
        lambda: WorkflowIR.model_validate_json(text),
        lambda: load_json(WorkflowIR, text),
        lambda: load_yaml(WorkflowIR, yaml.safe_dump(under)),
    )
    for attempt in attempts:
        with pytest.raises(ValidationError, match="below the lowest minor") as raised:
            attempt()
        assert clause in str(raised.value)

    path = tmp_path / "under-stamped-1-2.ir.yaml"
    path.write_text(yaml.safe_dump(under), encoding="utf-8")
    with pytest.raises(ValidationError, match="below the lowest minor") as raised:
        read_ir(path)
    assert clause in str(raised.value)


#: The constructs the format-migration down-projection removes — the extraction-populated ones
#: (IR-SPEC §8); the declared slots and the root tokens it never touches.
DOWN_PROJECTED: Final = frozenset({"subgraph", "barriers", "codomain", "managed", "assign token"})


def _without_by_hand(name: str, document: dict[str, Any]) -> dict[str, Any]:
    """The document with a never-down-projected construct taken out by hand."""
    stripped: dict[str, Any] = json.loads(json.dumps(document))
    if name in {"projection", "join_key scalar", "join_key list"}:
        for node in stripped["nodes"]:
            node.pop("annotations", None)
        return stripped
    # A root `each`/`leaf` document: the same one-node shape under a 1.0 token.
    return {**stripped, "entry": "%seq[0]", "finish": "%seq[0]", "nodes": [{"id": "%seq[0]"}]}


@pytest.mark.parametrize("name", CONSTRUCTS_1_2)
def test_removing_the_construct_restamps_the_document_lower(name: str) -> None:
    """The "iff": with its one 1.2 construct removed, the same document floors at ``"1.0"``.

    Removed by :func:`~gebra.ir.down_project` where the construct is extraction-populated, and by
    hand where it is declared or a root token (which the down-projection never touches).
    """
    document, _ = CONSTRUCTS_1_2[name]
    ir = WorkflowIR.model_validate_json(json.dumps(document))

    if name in DOWN_PROJECTED:
        lowered = down_project(ir, "1.1")
    else:
        lowered = WorkflowIR.model_validate_json(json.dumps(_without_by_hand(name, document)))

    assert lowest_ir_version(lowered) == IR_VERSION
    restamped = lowered.model_dump(by_alias=True, exclude_none=True)
    restamped["ir_version"] = IR_VERSION
    assert WorkflowIR.model_validate_json(json.dumps(restamped)).ir_version == IR_VERSION


def test_1_1_iff_a_dynamic_edge_and_nothing_newer() -> None:
    """A ``dynamic`` edge beside a 1.2 construct floors the document at ``"1.2"``, not ``"1.1"``.

    And the offender named is the construct whose own minor *is* the floor: a message naming the
    ``dynamic`` edge would call ``"1.1"`` the lowest sufficient minor, which is false.
    """
    dynamic = {"kind": "dynamic", "from": "plan"}
    only_dynamic = _document(stamp="1.1", edges=[*_document()["edges"], dynamic])
    both = _with_node({**only_dynamic, "ir_version": "1.2"}, 1, subgraph=_child())

    assert lowest_ir_version(WorkflowIR.model_validate_json(json.dumps(only_dynamic))) == "1.1"
    assert lowest_ir_version(WorkflowIR.model_validate_json(json.dumps(both))) == "1.2"
    for stamp in ("1.0", "1.1"):
        with pytest.raises(ValidationError) as raised:
            WorkflowIR.model_validate_json(json.dumps({**both, "ir_version": stamp}))
        message = raised.value.errors()[0]["msg"]
        assert "nodes[1] ('draft') carries `subgraph`" in message
        assert "'1.2' is the lowest sufficient minor" in message
        assert "kind 'dynamic'" not in message


def test_an_agreeing_or_empty_codomain_is_absent_and_floors_nothing() -> None:
    """ "Present in canonical form": non-empty and, after NFC, distinct from ``keys(path_map)``.

    An agreeing set collapses to absence (§6.3), so a ``"1.1"``-stamped document carrying one is
    not under-stamped and loads (DEC-40 §3.6). The comparison is after NFC: a decomposed label
    agrees with its composed key (canonicalization then refuses the non-NFC member — a separate
    rule, §6.1 step 5 — but loading does not).
    """
    decomposed = unicodedata.normalize("NFD", "é")
    for codomain in ([], ["go"], [decomposed]):
        path_map = {"é" if codomain == [decomposed] else "go": "collect"}
        document = _document(
            stamp="1.0",
            edges=[
                {"kind": "normal", "from": "plan", "to": "draft"},
                {"kind": "normal", "from": "draft", "to": "collect"},
                {"kind": "conditional", "from": "plan", "path_map": path_map, "codomain": codomain},
            ],
        )
        ir = WorkflowIR.model_validate_json(json.dumps(document))
        assert lowest_ir_version(ir) == IR_VERSION
        assert lowest_ir_version(ir.edges) == IR_VERSION


def test_over_stamping_at_1_2_stays_admitted() -> None:
    """A ``"1.2"`` stamp on a document with no 1.2 construct loads, as the 1.1 over-stamp does."""
    for document in (_document(), _document(edges=[{"kind": "dynamic", "from": "plan"}])):
        ir = WorkflowIR.model_validate_json(json.dumps(document))
        assert ir.ir_version == "1.2"
        assert IR_VERSIONS.index(lowest_ir_version(ir)) < IR_VERSIONS.index("1.2")


def test_the_floor_reads_every_level_and_names_the_construct_with_its_level() -> None:
    """The scan walks into each carrier's ``subgraph`` level (IR-SPEC §2.5 note 7).

    At 1.2 a carrier itself already requires ``"1.2"``, so a construct inside a child never
    *raises* the floor above its carrier's — but it is read, with a path that locates its level
    (``nodes[1].subgraph.edges[0]``), which is what a later minor carried inside a child will
    lean on. Asserted on the per-construct stream the floor and the refusal share.
    """
    child = {
        **_child(),
        "state": {"budget": {"type": "int", "managed": True}},
        "nodes": [{"id": "draft/write"}, {"id": "draft/check"}],
        "edges": [{"kind": "dynamic", "from": "draft/write"}],
    }
    ir = WorkflowIR.model_validate_json(json.dumps(_with_node(_document(), 1, subgraph=child)))

    located = [(minor, where) for minor, where, _ in _document_constructs(ir)]

    assert located == [
        ("1.2", "nodes[1]"),
        ("1.2", "nodes[1].subgraph.state['budget']"),
        ("1.1", "nodes[1].subgraph.edges[0]"),
    ]
    assert lowest_ir_version(ir) == "1.2"


def test_the_whole_document_floor_is_one_function_with_the_edge_scan_inside_it() -> None:
    """``lowest_ir_version`` takes a document or, as before, an edge set (IR-08's call form).

    An emitter that stamps before it builds the document passes its edges; the floor of the
    edges alone is the document's whenever no node or ``state`` construct of a later minor is
    present — and a node construct is exactly what the edge form cannot see.
    """
    plain = WorkflowIR.model_validate_json(json.dumps(_document()))
    barriered, _ = CONSTRUCTS_1_2["barriers"]
    with_barrier = WorkflowIR.model_validate_json(json.dumps(barriered))

    assert lowest_ir_version(plain) == lowest_ir_version(plain.edges) == IR_VERSION
    assert lowest_ir_version(with_barrier) == "1.2"
    assert lowest_ir_version(with_barrier.edges) == IR_VERSION
    assert lowest_ir_version(iter(with_barrier.edges)) == IR_VERSION  # consumed once


def test_no_str_subclass_method_runs_while_a_node_offender_is_formatted() -> None:
    """WA-07 for the node half of the scan: a ``model_copy``'d id is read through ``str`` only.

    A built ``Node`` handed to the constructor is not re-validated, so a ``model_copy`` can put a
    foreign ``str`` subclass on ``id``; the token scan, the uniqueness walk and the message all
    take an exact copy first, so none of its methods runs.
    """

    class Hostile(str):
        def __repr__(self) -> str:
            raise AssertionError("__repr__ ran")

        def __format__(self, spec: str) -> str:
            raise AssertionError("__format__ ran")

        def __hash__(self) -> int:
            raise AssertionError("__hash__ ran")

        def __eq__(self, other: object) -> bool:
            raise AssertionError("__eq__ ran")

        def startswith(self, *args: Any) -> bool:
            raise AssertionError("startswith ran")

        def split(self, *args: Any) -> list[str]:
            raise AssertionError("split ran")

    hostile = Node(id="%leaf[0]").model_copy(update={"id": Hostile("%leaf[0]")})
    assert type(hostile.id) is Hostile

    with pytest.raises(ValidationError, match="kind 'leaf'"):
        WorkflowIR(
            ir_version="1.1", entry="%leaf[0]", finish="%leaf[0]", nodes=(hostile,), edges=()
        )
