"""Canonical serialization + ``graph_version`` — IR-SPEC §6 (DEC-10), PD-004.

Layout mirrors the pipeline: the committed golden vector (§6.5, §1.3), digest sensitivity,
the §6.2 array-ordering rules per class, §6.3 omit-/representation-normalization, the §6.1
step-5 scalar constraints (with the PD-004 adjacent-gap closure), the RFC 8785 emitter
(member sorting, string escaping, ES number formatting), error reporting, and the
corpus-wide recompute-and-compare sweep.

Nothing here executes a workflow, calls an LLM, or opens a connection (WA-07): every input
is hand-written data or a vendored fixture payload, and canonicalization is a pure
function from model to bytes.
"""

from __future__ import annotations

import copy
import json
import re
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
import yaml

from gebra.ir.canonical import (
    I_JSON_MAX_INT,
    I_JSON_MIN_INT,
    CanonicalizationError,
    CanonicalizationErrorReason,
    _at,
    _emit,
    _format_double,
    canonical_bytes,
    graph_version,
    verify_graph_version,
)
from gebra.ir.models import (
    Annotations,
    ConditionalEdge,
    DeterministicSpec,
    Node,
    NormalEdge,
    RecursionLimit,
    Runtime,
    WorkflowIR,
)
from tests.conftest import FIXTURES_DIR

GOLDEN_DIR = Path(__file__).parent / "golden"

#: The OCI digest grammar the §6.1 step-8 rendering must match.
DIGEST_GRAMMAR = re.compile(r"^sha256:[a-f0-9]{64}$")

#: The composed and decomposed spellings of the same text — equal under NFC, unequal as
#: strings. The decomposed form is what the §6.3 NFC constraint refuses.
NFC_NAME = "caf\u00e9"
NON_NFC_NAME = "cafe\u0301"


def load_ir(payload: dict[str, Any]) -> WorkflowIR:
    """JSON-mode ingestion, the §2.5 note-4 route (sequence→tuple under strict-JSON)."""
    return WorkflowIR.model_validate_json(json.dumps(payload))


def minimal(**overrides: Any) -> dict[str, Any]:
    """The smallest valid document, with per-test overrides applied on top."""
    payload: dict[str, Any] = {
        "ir_version": "1.0",
        "entry": "a",
        "finish": "a",
        "nodes": [{"id": "a"}],
        "edges": [],
    }
    payload.update(overrides)
    return payload


def digest_of(payload: dict[str, Any]) -> str:
    return graph_version(load_ir(payload))


def bytes_of(payload: dict[str, Any]) -> bytes:
    return canonical_bytes(load_ir(payload))


# ── Golden vector 001 (IR-SPEC §6.5; §1.3: it MUST ship with the frozen spec) ────────────


def authored_payload() -> dict[str, Any]:
    text = (GOLDEN_DIR / "vector-001.authored.yaml").read_text(encoding="utf-8")
    payload: dict[str, Any] = yaml.safe_load(text)
    return payload


def golden_canonical() -> bytes:
    return (GOLDEN_DIR / "vector-001.canonical.json").read_bytes()


def golden_digest() -> str:
    return (GOLDEN_DIR / "vector-001.digest").read_text(encoding="ascii").strip()


def test_golden_vector_001_reproduces_byte_exactly() -> None:
    """§6.5: 537 canonical bytes; §1.2: a single differing byte is non-conformance.

    The committed canonical file is compared whole, so this also guards the golden file
    itself against a stray trailing newline or an editor touch (WA-05).
    """
    expected = golden_canonical()
    assert len(expected) == 537
    produced = canonical_bytes(load_ir(authored_payload()))
    assert produced == expected


def test_golden_vector_001_digest_matches() -> None:
    """§6.5: ``graph_version = sha256:5db68464…``, rendered per the OCI grammar."""
    digest = graph_version(load_ir(authored_payload()))
    assert digest == golden_digest()
    assert DIGEST_GRAMMAR.match(digest)


def test_verification_is_recompute_and_string_compare() -> None:
    """§6.1 step 9 / §1.2: exact string equality — no case folding, no parsing."""
    ir = load_ir(authored_payload())
    assert verify_graph_version(ir, golden_digest())
    assert not verify_graph_version(ir, golden_digest().upper())
    assert not verify_graph_version(ir, "sha256:" + "0" * 64)


def test_canonical_form_recanonicalizes_to_itself() -> None:
    """§1.2 document conformance: parse the canonical bytes, re-canonicalize, compare.

    The canonical form is itself a valid §2 document (PD-004 finding 4 leans on this), and
    canonicalization is the identity on it — including the tagless re-injection of the
    ``kind`` the normal edge lost to omit-normalization.
    """
    blob = golden_canonical()
    reloaded = WorkflowIR.model_validate_json(blob)
    assert canonical_bytes(reloaded) == blob
    assert graph_version(reloaded) == golden_digest()


def test_python_and_json_ingestion_share_one_digest() -> None:
    """The digest names the document, not its ingestion route."""
    from_json = load_ir(authored_payload())
    by_hand = WorkflowIR(
        ir_version="1.0",
        entry="plan",
        finish="report",
        runtime=Runtime(
            recursion_limit=RecursionLimit(
                value=10, justification="redo loop bounded by review budget"
            )
        ),
        state={"task": "str", "result": "str"},
        nodes=(
            Node(id="plan", annotations=Annotations(pure=True, output=("task",))),
            Node(
                id="act",
                annotations=Annotations(input=("task",), output=("result",), effect=("network",)),
            ),
            Node(id="report", annotations=Annotations(input=("result",))),
        ),
        edges=(
            NormalEdge.model_validate({"kind": "normal", "from": "plan", "to": "act"}),
            ConditionalEdge.model_validate(
                {
                    "kind": "conditional",
                    "from": "act",
                    "condition": "done(result)",
                    "path_map": {"done": "report", "redo": "act"},
                }
            ),
        ),
    )
    assert canonical_bytes(by_hand) == canonical_bytes(from_json)


# ── Digest sensitivity: a single-field mutation changes the digest ───────────────────────

MUTATIONS: dict[str, Callable[[dict[str, Any]], None]] = {
    "recursion_limit.value": lambda p: p["runtime"]["recursion_limit"].update(value=11),
    "recursion_limit.justification": lambda p: p["runtime"]["recursion_limit"].update(
        justification="different words"
    ),
    "state.task type": lambda p: p["state"].update(task="int"),
    "nodes[plan].pure": lambda p: p["nodes"][0]["annotations"].update(pure=False),
    "nodes[act].effect tag": lambda p: p["nodes"][1]["annotations"].update(effect=["billable"]),
    "edges[0].to": lambda p: p["edges"][0].update(to="report"),
    "edges[1].condition": lambda p: p["edges"][1].update(condition="finished(result)"),
    "edges[1].path_map.redo": lambda p: p["edges"][1]["path_map"].update(redo="plan"),
    "entry": lambda p: p.update(entry="act"),
    "nodes[report].prompt_digest added": lambda p: p["nodes"][2]["annotations"].update(
        prompt_digest="sha256:" + "ab" * 32
    ),
}


@pytest.mark.parametrize("field", MUTATIONS)
def test_a_single_field_mutation_changes_the_digest(field: str) -> None:
    """§6.4: the entire core IR is in scope, so any semantic field edit moves the digest."""
    payload = authored_payload()
    MUTATIONS[field](payload)
    assert digest_of(payload) != golden_digest()


def test_the_mutated_digests_are_pairwise_distinct() -> None:
    """Ten one-field variants of one document land on ten distinct digests."""
    digests = set()
    for mutate in MUTATIONS.values():
        payload = authored_payload()
        mutate(payload)
        digests.add(digest_of(payload))
    assert len(digests) == len(MUTATIONS)


# ── §6.2 array-ordering rules, per class ─────────────────────────────────────────────────


def test_nodes_sort_by_id_and_authored_order_is_normalized_away() -> None:
    """§6.2 row 1 + §6.4: authored ``nodes[]`` order is excluded from the digest."""
    payload = authored_payload()
    shuffled = authored_payload()
    shuffled["nodes"] = [shuffled["nodes"][2], shuffled["nodes"][0], shuffled["nodes"][1]]
    assert bytes_of(shuffled) == bytes_of(payload)


def test_nodes_sort_as_utf16_code_units_not_code_points() -> None:
    """§6.2 row 1: the comparator is UTF-16 code units — the same comparator as JCS member
    sorting. U+10000 encodes as the surrogate pair D800 DC00, so it sorts *before*
    U+E000, the reverse of code-point order; a code-point sort is exactly the
    implementation divergence this pins out.
    """
    payload = minimal(nodes=[{"id": "a"}, {"id": ""}, {"id": "\U00010000"}])
    blob = bytes_of(payload).decode("utf-8")
    assert blob.index('"id":"\U00010000"') < blob.index('"id":""')


def test_edges_sort_bytewise_by_their_own_canonical_serialization() -> None:
    """§6.2 row 2: a total, implementation-independent order with no composite key.

    The golden vector already demonstrates the conditional-before-normal case; this pins
    the order *within* one kind and that authored order is normalized away.
    """
    first = {"from": "a", "to": "b"}
    second = {"from": "a", "to": "c"}
    forward = minimal(nodes=[{"id": "a"}, {"id": "b"}, {"id": "c"}], edges=[first, second])
    backward = minimal(nodes=[{"id": "a"}, {"id": "b"}, {"id": "c"}], edges=[second, first])
    assert bytes_of(forward) == bytes_of(backward)
    blob = bytes_of(forward).decode("utf-8")
    assert blob.index('"to":"b"') < blob.index('"to":"c"')


@pytest.mark.parametrize(
    ("label", "payload", "fragment"),
    [
        (
            "entry list form",
            minimal(entry=["b", "a"], nodes=[{"id": "a"}, {"id": "b"}]),
            '"entry":["a","b"]',
        ),
        (
            "finish list form",
            minimal(finish=["b", "a"], nodes=[{"id": "a"}, {"id": "b"}]),
            '"finish":["a","b"]',
        ),
        (
            "effect",
            minimal(nodes=[{"id": "a", "annotations": {"effect": ["network", "billable"]}}]),
            '"effect":["billable","network"]',
        ),
        (
            "input",
            minimal(
                state={"x": "str", "y": "str"},
                nodes=[{"id": "a", "annotations": {"input": ["y", "x"]}}],
            ),
            '"input":["x","y"]',
        ),
        (
            "output",
            minimal(
                state={"x": "str", "y": "str"},
                nodes=[{"id": "a", "annotations": {"output": ["y", "x"]}}],
            ),
            '"output":["x","y"]',
        ),
        (
            "retry_on",
            minimal(
                nodes=[
                    {
                        "id": "a",
                        "annotations": {
                            "retry_policy": {
                                "max_attempts": 3,
                                "retry_on": ["TimeoutError", "OSError"],
                            }
                        },
                    }
                ]
            ),
            '"retry_on":["OSError","TimeoutError"]',
        ),
        (
            "interrupts.before",
            minimal(runtime={"interrupts": {"before": ["b", "a"]}}),
            '"before":["a","b"]',
        ),
        (
            "interrupts.after",
            minimal(runtime={"interrupts": {"after": ["b", "a"]}}),
            '"after":["a","b"]',
        ),
    ],
)
def test_set_valued_string_arrays_sort_in_utf16_order(
    label: str, payload: dict[str, Any], fragment: str
) -> None:
    """§6.2 row 4 — the exhaustive set-valued enumeration, one case per member."""
    assert fragment in bytes_of(payload).decode("utf-8")


def test_set_valued_arrays_sort_but_never_dedupe() -> None:
    """§6.2 fixes their *order*; no §6 rule removes duplicates, so none are removed."""
    payload = minimal(
        state={"x": "str"},
        nodes=[{"id": "a", "annotations": {"input": ["x", "x"]}}],
    )
    assert '"input":["x","x"]' in bytes_of(payload).decode("utf-8")


def test_args_schema_arrays_preserve_authored_order() -> None:
    """§6.2 row 5: array order can be semantic in JSON Schema and is never touched —
    member names inside still sort, because JCS sorts every object's names."""
    schema = {
        "type": "object",
        "required": ["b", "a"],
        "prefixItems": [{"type": "string"}, {"type": "number"}],
        "enum": [3, 1, 2],
    }
    payload = minimal(nodes=[{"id": "a", "annotations": {"args_schema": schema}}])
    blob = bytes_of(payload).decode("utf-8")
    assert '"required":["b","a"]' in blob
    assert '"enum":[3,1,2]' in blob
    assert '"prefixItems":[{"type":"string"},{"type":"number"}]' in blob
    assert blob.index('"enum"') < blob.index('"prefixItems"') < blob.index('"required"')


def test_path_map_needs_no_gebra_rule_because_jcs_sorts_member_names() -> None:
    """§6.2 row 3: ``path_map`` is a JSON object; label order is JCS member order."""
    edge = {"from": "a", "kind": "conditional", "path_map": {"z": "a", "a": "a", "m": "a"}}
    payload = minimal(edges=[edge])
    assert '"path_map":{"a":"a","m":"a","z":"a"}' in bytes_of(payload).decode("utf-8")


# ── §6.3 omit-normalization ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("label", "explicit", "collapsed"),
    [
        (
            "null optional member",
            minimal(nodes=[{"id": "a", "annotations": {"pure": None, "effect": ["x"]}}]),
            minimal(nodes=[{"id": "a", "annotations": {"effect": ["x"]}}]),
        ),
        (
            "kind normal is the schema-declared default",
            minimal(
                nodes=[{"id": "a"}, {"id": "b"}], edges=[{"from": "a", "to": "b", "kind": "normal"}]
            ),
            minimal(nodes=[{"id": "a"}, {"id": "b"}], edges=[{"from": "a", "to": "b"}]),
        ),
        (
            "empty optional array: effect",
            minimal(nodes=[{"id": "a", "annotations": {"effect": [], "pure": True}}]),
            minimal(nodes=[{"id": "a", "annotations": {"pure": True}}]),
        ),
        (
            "empty optional array: interrupts.before",
            minimal(runtime={"interrupts": {"before": []}}),
            minimal(runtime={"interrupts": {}}),
        ),
        (
            "null edge condition",
            minimal(nodes=[{"id": "a"}], edges=[{"from": "a", "to": "a", "condition": None}]),
            minimal(nodes=[{"id": "a"}], edges=[{"from": "a", "to": "a"}]),
        ),
    ],
)
def test_absent_null_and_default_share_one_canonical_form(
    label: str, explicit: dict[str, Any], collapsed: dict[str, Any]
) -> None:
    """§6.3: absent ≡ null ≡ default, and an empty optional array is absent."""
    assert bytes_of(explicit) == bytes_of(collapsed)


def test_required_members_are_never_omitted() -> None:
    """§6.3/§2.5 note 6: omission covers optional members only. ``edges`` is REQUIRED, so
    a workflow with no edges serializes ``"edges":[]``; ``retry_on`` and ``present`` are
    REQUIRED within their objects and keep their empty/false values."""
    blob = bytes_of(
        minimal(
            nodes=[
                {"id": "a", "annotations": {"retry_policy": {"max_attempts": 1, "retry_on": []}}}
            ],
            runtime={"checkpointer": {"present": False}},
        )
    ).decode("utf-8")
    assert '"edges":[]' in blob
    assert '"retry_on":[]' in blob
    assert '"present":false' in blob


def test_checkpointer_present_false_is_distinct_from_slot_absence() -> None:
    """§3.7: ``{present: false}`` is representable and distinct from the slot's absence."""
    with_slot = minimal(runtime={"checkpointer": {"present": False}})
    without = minimal()
    assert digest_of(with_slot) != digest_of(without)


@pytest.mark.parametrize(
    ("label", "payload", "fragment"),
    [
        ("annotations", minimal(nodes=[{"id": "a", "annotations": {}}]), '"annotations":{}'),
        ("runtime", minimal(runtime={}), '"runtime":{}'),
        ("state", minimal(state={}), '"state":{}'),
        (
            "interrupts emptied by its empty arrays",
            minimal(runtime={"interrupts": {"before": [], "after": []}}),
            '"interrupts":{}',
        ),
    ],
)
def test_empty_object_members_are_preserved(
    label: str, payload: dict[str, Any], fragment: str
) -> None:
    """§6.3 removes null members, declared defaults, and empty optional *arrays* — its
    enumerations are exhaustive (DEC-10 fix pass), and ``{}`` is none of the three. An
    authored-empty object therefore serializes, distinct from the member's absence."""
    assert fragment in bytes_of(payload).decode("utf-8")


def test_an_authored_empty_object_is_distinct_from_the_members_absence() -> None:
    """The flip side of preservation: ``annotations: {}`` (and ``runtime``/``state``) do
    not share a canonical form with absence, so the two digest apart."""
    assert digest_of(minimal(nodes=[{"id": "a", "annotations": {}}])) != digest_of(minimal())
    assert digest_of(minimal(runtime={})) != digest_of(minimal())
    assert digest_of(minimal(state={})) != digest_of(minimal())


# ── §6.3 representation-normalization ────────────────────────────────────────────────────


def test_entry_and_finish_collapse_to_a_scalar_iff_the_wired_set_is_a_singleton() -> None:
    """§6.3 (a): the singleton list form and the scalar are one canonical form."""
    scalar = minimal()
    listed = minimal(entry=["a"], finish=["a"])
    assert bytes_of(listed) == bytes_of(scalar)
    assert '"entry":"a"' in bytes_of(listed).decode("utf-8")


def test_entry_serializes_the_wired_set_so_duplicates_collapse() -> None:
    """§4.2 (m1)/(m5): ``["a","a"]`` wires the single edge (START, a), and a tuple's
    canonical surface is unique — so the duplicated singleton lands on the scalar form,
    and a duplicated pair lands on the two-element list."""
    assert bytes_of(minimal(entry=["a", "a"])) == bytes_of(minimal())
    two = minimal(entry=["b", "a", "b"], nodes=[{"id": "a"}, {"id": "b"}])
    assert '"entry":["a","b"]' in bytes_of(two).decode("utf-8")


def test_state_values_collapse_iff_no_reducer_and_no_optional_flag() -> None:
    """§6.3 (b), including the null-reducer form, which drops to bare before collapsing."""
    bare = minimal(state={"x": "str"})
    objected = minimal(state={"x": {"type": "str"}})
    nulled = minimal(state={"x": {"type": "str", "reducer": None}})
    assert bytes_of(objected) == bytes_of(bare)
    assert bytes_of(nulled) == bytes_of(bare)
    assert '"state":{"x":"str"}' in bytes_of(bare).decode("utf-8")


def test_a_carried_state_flag_keeps_the_object_form() -> None:
    """An explicit ``optional: false`` is a carried flag — the schema default is null, and
    §6.3's complete non-null default list is ``edges[].kind`` alone — so the object form
    stays, distinct from the bare string."""
    flagged = minimal(state={"x": {"type": "str", "optional": False}})
    blob = bytes_of(flagged).decode("utf-8")
    assert '"state":{"x":{"optional":false,"type":"str"}}' in blob
    assert digest_of(flagged) != digest_of(minimal(state={"x": "str"}))
    reduced = minimal(state={"x": {"type": "list", "reducer": "operator.add"}})
    assert '{"reducer":"operator.add","type":"list"}' in bytes_of(reduced).decode("utf-8")


# ── §6.1 step 5: scalar constraints (PD-004: IR validity, pre-hash, never stringified) ───


def seed_payload(value: int) -> dict[str, Any]:
    return minimal(
        nodes=[{"id": "a", "annotations": {"deterministic": {"seed": value}}}],
    )


def attempts_payload(value: int) -> dict[str, Any]:
    return minimal(
        nodes=[
            {"id": "a", "annotations": {"retry_policy": {"max_attempts": value, "retry_on": []}}}
        ],
    )


def limit_payload(value: int) -> dict[str, Any]:
    return minimal(runtime={"recursion_limit": {"value": value, "justification": "j"}})


INTEGER_FIELDS: dict[str, tuple[Callable[[int], dict[str, Any]], tuple[str | int, ...]]] = {
    "deterministic.seed": (
        seed_payload,
        ("nodes", 0, "annotations", "deterministic", "seed"),
    ),
    "retry_policy.max_attempts": (
        attempts_payload,
        ("nodes", 0, "annotations", "retry_policy", "max_attempts"),
    ),
    "runtime.recursion_limit.value": (
        limit_payload,
        ("runtime", "recursion_limit", "value"),
    ),
}


@pytest.mark.parametrize("field", INTEGER_FIELDS)
def test_the_three_integer_fields_admit_the_full_i_json_range(field: str) -> None:
    """PD-004 decision item 1: the boundary values ±(2⁵³−1) are inclusive."""
    build, _ = INTEGER_FIELDS[field]
    assert DIGEST_GRAMMAR.match(digest_of(build(I_JSON_MAX_INT)))
    assert DIGEST_GRAMMAR.match(digest_of(build(I_JSON_MIN_INT)))
    assert str(I_JSON_MAX_INT) in bytes_of(build(I_JSON_MAX_INT)).decode("utf-8")


@pytest.mark.parametrize("field", INTEGER_FIELDS)
@pytest.mark.parametrize("value", [I_JSON_MAX_INT + 1, I_JSON_MIN_INT - 1, 2**63 - 1])
def test_an_out_of_range_integer_is_a_validity_error_never_a_string(field: str, value: int) -> None:
    """PD-004 decision items 1–3: outside ±(2⁵³−1) is an IR validity error raised before
    any bytes or digest exist — the document is refused, not stringified."""
    build, path = INTEGER_FIELDS[field]
    with pytest.raises(CanonicalizationError) as caught:
        canonical_bytes(load_ir(build(value)))
    assert caught.value.reason is CanonicalizationErrorReason.INTEGER_OUT_OF_RANGE
    assert caught.value.path == path
    assert caught.value.value == value


def test_interior_wide_integers_are_the_same_validity_error() -> None:
    """PD-004 adjacent-gap closure (ratified un-struck; IR-01 review recorded IR-03 carries
    it whole): the step-5 constraints apply to every JSON number serialized, ``args_schema``
    interiors included — e.g. an int64 bound in a generated tool schema."""
    schema = {"properties": {"n": {"type": "integer", "maximum": 9223372036854775807}}}
    payload = minimal(nodes=[{"id": "a", "annotations": {"args_schema": schema}}])
    with pytest.raises(CanonicalizationError) as caught:
        canonical_bytes(load_ir(payload))
    assert caught.value.reason is CanonicalizationErrorReason.INTEGER_OUT_OF_RANGE
    assert caught.value.path == (
        "nodes",
        0,
        "annotations",
        "args_schema",
        "properties",
        "n",
        "maximum",
    )


def test_a_wide_integer_inside_a_foreign_array_is_caught_with_its_index() -> None:
    schema = {"enum": [1, 2**53]}
    payload = minimal(nodes=[{"id": "a", "annotations": {"args_schema": schema}}])
    with pytest.raises(CanonicalizationError) as caught:
        canonical_bytes(load_ir(payload))
    assert caught.value.path == ("nodes", 0, "annotations", "args_schema", "enum", 1)


def test_wide_doubles_are_not_integers_and_serialize_fine() -> None:
    """The range constraint is about exact integers; a finite double always has one JCS
    rendering, however large — the PD-004 hazard is ints an IEEE double cannot carry."""
    schema = {"maximum": 1e300, "exclusiveMaximum": 9007199254740992.0}
    payload = minimal(nodes=[{"id": "a", "annotations": {"args_schema": schema}}])
    blob = bytes_of(payload).decode("utf-8")
    assert '"maximum":1e+300' in blob
    assert '"exclusiveMaximum":9007199254740992' in blob


def test_nan_and_infinity_are_forbidden_in_model_fields() -> None:
    """§6.1 step 5. JSON cannot author these, so the Python construction route is the one
    that needs the tripwire."""
    ir = WorkflowIR(
        ir_version="1.0",
        entry="a",
        finish="a",
        nodes=(
            Node(
                id="a",
                annotations=Annotations(
                    deterministic=DeterministicSpec(seed=1, temperature=float("nan"))
                ),
            ),
        ),
        edges=(),
    )
    with pytest.raises(CanonicalizationError) as caught:
        graph_version(ir)
    assert caught.value.reason is CanonicalizationErrorReason.NON_FINITE_NUMBER
    assert caught.value.path == ("nodes", 0, "annotations", "deterministic", "temperature")


def test_nan_and_infinity_are_forbidden_inside_foreign_content() -> None:
    for bad in (float("inf"), float("-inf"), float("nan")):
        ir = WorkflowIR(
            ir_version="1.0",
            entry="a",
            finish="a",
            nodes=(Node(id="a", annotations=Annotations(args_schema={"x": bad})),),
            edges=(),
        )
        with pytest.raises(CanonicalizationError) as caught:
            canonical_bytes(ir)
        assert caught.value.reason is CanonicalizationErrorReason.NON_FINITE_NUMBER


@pytest.mark.parametrize(
    ("site", "payload", "path"),
    [
        (
            "state key",
            minimal(state={NON_NFC_NAME: "str"}),
            ("state", NON_NFC_NAME),
        ),
        (
            "input entry",
            minimal(nodes=[{"id": "a", "annotations": {"input": [NON_NFC_NAME]}}]),
            ("nodes", 0, "annotations", "input", 0),
        ),
        (
            "output entry",
            minimal(nodes=[{"id": "a", "annotations": {"output": [NON_NFC_NAME]}}]),
            ("nodes", 0, "annotations", "output", 0),
        ),
        (
            "idempotent.key",
            minimal(nodes=[{"id": "a", "annotations": {"idempotent": {"key": NON_NFC_NAME}}}]),
            ("nodes", 0, "annotations", "idempotent", "key"),
        ),
        (
            "variant.key",
            minimal(
                nodes=[
                    {"id": "a", "annotations": {"variant": {"key": NON_NFC_NAME, "measure": "m"}}}
                ]
            ),
            ("nodes", 0, "annotations", "variant", "key"),
        ),
        (
            "path_map label",
            minimal(edges=[{"from": "a", "kind": "conditional", "path_map": {NON_NFC_NAME: "a"}}]),
            ("edges", 0, "path_map", NON_NFC_NAME),
        ),
    ],
)
def test_state_key_role_strings_must_be_nfc(
    site: str, payload: dict[str, Any], path: tuple[str | int, ...]
) -> None:
    """§6.3: NFC applies to state keys, the state-key references, and path_map labels —
    checked verbatim, since these carry no escaping grammar. IR-02 covered ``nodes[].id``
    at model validation; this sweep is the rest of the enumeration."""
    with pytest.raises(CanonicalizationError) as caught:
        canonical_bytes(load_ir(payload))
    assert caught.value.reason is CanonicalizationErrorReason.IDENTIFIER_NOT_NFC
    assert caught.value.path == path


@pytest.mark.parametrize(
    ("site", "payload", "path"),
    [
        ("entry", minimal(entry=NON_NFC_NAME), ("entry",)),
        (
            "finish list item",
            minimal(finish=[NON_NFC_NAME, "a"]),
            ("finish", 0),
        ),
        (
            "edge from",
            minimal(edges=[{"from": NON_NFC_NAME, "to": "a"}]),
            ("edges", 0, "from"),
        ),
        (
            "edge to",
            minimal(edges=[{"from": "a", "to": NON_NFC_NAME}]),
            ("edges", 0, "to"),
        ),
        (
            "path_map value",
            minimal(edges=[{"from": "a", "kind": "conditional", "path_map": {"go": NON_NFC_NAME}}]),
            ("edges", 0, "path_map", "go"),
        ),
        (
            "interrupts.before entry",
            minimal(runtime={"interrupts": {"before": [NON_NFC_NAME]}}),
            ("runtime", "interrupts", "before", 0),
        ),
        (
            "compensation.hook",
            minimal(nodes=[{"id": "a", "annotations": {"compensation": {"hook": NON_NFC_NAME}}}]),
            ("nodes", 0, "annotations", "compensation", "hook"),
        ),
        (
            "synthetic selector in a reference",
            minimal(edges=[{"from": "a", "to": f"%map[{NON_NFC_NAME}]"}]),
            ("edges", 0, "to"),
        ),
    ],
)
def test_node_id_role_references_must_be_nfc_on_the_decoded_form(
    site: str, payload: dict[str, Any], path: tuple[str | int, ...]
) -> None:
    """§6.3 names "node-id segments (§5.1)" as identifier-role; the IR-02 review recorded
    that the step-5 test must run on the *decoded* segment and left every node-id-role
    reference to this sweep. The check parses per §5, so a selector's escapes decode
    before the NFC test."""
    with pytest.raises(CanonicalizationError) as caught:
        canonical_bytes(load_ir(payload))
    assert caught.value.reason is CanonicalizationErrorReason.IDENTIFIER_NOT_NFC
    assert caught.value.path == path


@pytest.mark.parametrize("reference", ["100%", "a//b", "__start__", "%zip[0]"])
def test_a_reference_the_grammar_does_not_admit_is_byte_preserved(reference: str) -> None:
    """The step-5 string constraint is NFC, nothing more: a malformed or reserved
    *reference* is opaque content, byte-preserved, and digests fine — whether it resolves
    is the reporting stage's question (P-01's), not canonicalization's. The definition
    site is different: a ``nodes[].id`` like this never loads (IR-02)."""
    payload = minimal(edges=[{"from": "a", "to": reference}])
    blob = bytes_of(payload).decode("utf-8")
    assert f'"to":{json.dumps(reference)}' in blob
    assert DIGEST_GRAMMAR.match(digest_of(payload))


def test_the_end_literal_is_an_ordinary_segment_under_the_sweep() -> None:
    """§4.2: ``to`` and ``path_map`` values may use ``"END"``; it satisfies §5.1 as an
    ordinary user segment, so the sweep needs no special case."""
    payload = minimal(
        edges=[
            {"from": "a", "to": "END"},
            {"from": "a", "kind": "conditional", "path_map": {"done": "END"}},
        ]
    )
    assert DIGEST_GRAMMAR.match(digest_of(payload))


def test_a_lone_surrogate_is_refused_wherever_it_sits() -> None:
    """§6.1 step 6 serializes UTF-8; a surrogate code point has no encoding. JSON-mode
    input cannot smuggle one past pydantic-core, so the Python route is the tripwire."""
    sites: list[tuple[WorkflowIR, tuple[str | int, ...]]] = [
        (
            WorkflowIR(
                ir_version="1.0",
                entry="a",
                finish="a",
                nodes=(Node(id="a"),),
                edges=(
                    NormalEdge.model_validate(
                        {"kind": "normal", "from": "a", "to": "a", "condition": "\ud800"}
                    ),
                ),
            ),
            ("edges", 0, "condition"),
        ),
        (
            WorkflowIR(
                ir_version="1.0",
                entry="a",
                finish="a",
                state={"\ud800": "str"},
                nodes=(Node(id="a"),),
                edges=(),
            ),
            ("state", "\ud800"),
        ),
        (
            WorkflowIR(
                ir_version="1.0",
                entry="a",
                finish="a",
                nodes=(Node(id="a", annotations=Annotations(args_schema={"x": "\udfff"})),),
                edges=(),
            ),
            ("nodes", 0, "annotations", "args_schema", "x"),
        ),
    ]
    for ir, path in sites:
        with pytest.raises(CanonicalizationError) as caught:
            canonical_bytes(ir)
        assert caught.value.reason is CanonicalizationErrorReason.NOT_A_SCALAR_VALUE
        assert caught.value.path == path


def test_foreign_null_members_drop_and_null_items_stay() -> None:
    """§6.3's null rule is not one of the Gebra-model-specific steps §3.6 exempts for
    foreign objects, so a null-valued *member* inside ``args_schema`` never serializes;
    array *items* are not members, and ``enum: [null, …]`` keeps its null."""
    with_null = minimal(
        nodes=[{"id": "a", "annotations": {"args_schema": {"default": None, "x": 1}}}]
    )
    without = minimal(nodes=[{"id": "a", "annotations": {"args_schema": {"x": 1}}}])
    assert bytes_of(with_null) == bytes_of(without)
    items = minimal(nodes=[{"id": "a", "annotations": {"args_schema": {"enum": [None, 1]}}}])
    assert '"enum":[null,1]' in bytes_of(items).decode("utf-8")


def test_a_non_string_foreign_key_is_refused_not_coerced() -> None:
    ir = WorkflowIR(
        ir_version="1.0",
        entry="a",
        finish="a",
        nodes=(Node(id="a", annotations=Annotations(args_schema={"x": {1: "one"}})),),
        edges=(),
    )
    with pytest.raises(CanonicalizationError) as caught:
        canonical_bytes(ir)
    assert caught.value.reason is CanonicalizationErrorReason.NON_STRING_KEY
    assert caught.value.value == 1
    assert "1" in str(caught.value)
    foreign = WorkflowIR(
        ir_version="1.0",
        entry="a",
        finish="a",
        nodes=(Node(id="a", annotations=Annotations(args_schema={"x": {(1,): "t"}})),),
        edges=(),
    )
    with pytest.raises(CanonicalizationError) as caught:
        canonical_bytes(foreign)
    assert "tuple" in str(caught.value)


def test_a_non_json_foreign_value_is_refused_not_coerced() -> None:
    ir = WorkflowIR(
        ir_version="1.0",
        entry="a",
        finish="a",
        nodes=(Node(id="a", annotations=Annotations(args_schema={"x": {"y": object()}})),),
        edges=(),
    )
    with pytest.raises(CanonicalizationError) as caught:
        canonical_bytes(ir)
    assert caught.value.reason is CanonicalizationErrorReason.UNSUPPORTED_TYPE
    assert caught.value.path == ("nodes", 0, "annotations", "args_schema", "x", "y")


def test_the_remaining_annotation_slots_are_byte_preserved_verbatim() -> None:
    """§6.3: ``source``, ``map``, and the digest strings are not identifier-role — they
    ride byte-preserved, and both digest slots are in hash scope (§6.4: digests, not
    bodies)."""
    payload = minimal(
        nodes=[
            {
                "id": "a",
                "annotations": {
                    "source": "@SOURCE(catalog)",
                    "map": "@MAP(row)",
                    "config_digest": "sha256:" + "cd" * 32,
                },
            }
        ]
    )
    blob = bytes_of(payload).decode("utf-8")
    assert '"source":"@SOURCE(catalog)"' in blob
    assert '"map":"@MAP(row)"' in blob
    assert '"config_digest":"sha256:' + "cd" * 32 + '"' in blob
    assert digest_of(payload) != digest_of(minimal())


def test_the_path_renderer_names_the_document_root() -> None:
    """No walk error carries an empty path today; the renderer's contract still pins the
    root spelling rather than leaving it to chance."""
    assert _at(()) == "the document"
    assert _at(("nodes", 0, "id")) == "nodes[0].id"


def test_a_python_tuple_inside_foreign_content_serializes_as_an_array() -> None:
    ir = WorkflowIR(
        ir_version="1.0",
        entry="a",
        finish="a",
        nodes=(Node(id="a", annotations=Annotations(args_schema={"enum": (1, 2)})),),
        edges=(),
    )
    assert b'"enum":[1,2]' in canonical_bytes(ir)


# ── Error reporting ──────────────────────────────────────────────────────────────────────


def test_the_error_message_renders_the_authored_path() -> None:
    payload = minimal(nodes=[{"id": "a", "annotations": {"args_schema": {"maximum": 2**53}}}])
    with pytest.raises(CanonicalizationError) as caught:
        canonical_bytes(load_ir(payload))
    assert "nodes[0].annotations.args_schema.maximum" in str(caught.value)
    assert "I-JSON" in str(caught.value)


def test_no_bytes_and_no_digest_exist_for_a_refused_document() -> None:
    """PD-004 decision item 2: the error always precedes any digest. The public surface
    offers no partial output to observe — every entry point raises."""
    payload = seed_payload(2**53)
    ir = load_ir(payload)
    for operation in (canonical_bytes, graph_version):
        with pytest.raises(CanonicalizationError):
            operation(ir)
    with pytest.raises(CanonicalizationError):
        verify_graph_version(ir, "sha256:" + "0" * 64)


#: The P-01 rows of the PROPERTY-CATALOG-SPEC §0.4 condition-ID registry, transcribed only
#: to keep the reason vocabulary disjoint from it (the same pin test_identity carries).
P01_CONDITION_IDS = (
    "node-unreachable-from-start",
    "dead-end-node-not-wired-to-end",
    "path-map-target-undefined",
    "orphan-node",
    "edge-target-undefined",
)


def test_the_reason_codes_are_not_condition_ids() -> None:
    """Canonicalization errors are IR-validity errors; no verification envelope carries
    them, and the §0.4 registry neither contains nor needs them (exit code 2 is the
    catalog's home for IR validation failing before any property runs)."""
    reasons = {reason.value for reason in CanonicalizationErrorReason}
    assert reasons.isdisjoint(P01_CONDITION_IDS)


# ── RFC 8785 emitter: member sorting, string escaping, ES numbers ────────────────────────


def test_member_names_sort_as_utf16_code_units() -> None:
    """RFC 8785 §3.2.3. U+1F602 (D83D DE02) sorts before U+FB33 (FB33 > D83D) — the
    surrogate-range inversion that separates UTF-16 order from code-point order."""
    blob = _emit({"דּ": 1, "\U0001f602": 2, "€": 3, "1": 4, "A": 5, "a": 6})
    decoded = blob.decode("utf-8")
    order = [decoded.index(ch) for ch in ("1", "A", "a", "€", "\U0001f602", "דּ")]
    assert order == sorted(order)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("plain", b'"plain"'),
        ('say "hi"', b'"say \\"hi\\""'),
        ("back\\slash", b'"back\\\\slash"'),
        ("\b\f\n\r\t", b'"\\b\\f\\n\\r\\t"'),
        ("\x00", b'"\\u0000"'),
        ("\x1f", b'"\\u001f"'),
        ("\x7f", b'"\x7f"'),
        ("café", '"café"'.encode()),
        ("\U0001f602", '"\U0001f602"'.encode()),
    ],
)
def test_string_escaping_follows_rfc_8785(value: str, expected: bytes) -> None:
    """§3.2.2.2: the two mandatory escapes, short forms for the named controls, lowercase
    ``\\u00xx`` for the rest of C0 — and nothing else escaped (DEL and non-ASCII ride as
    literal UTF-8)."""
    assert _emit(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0.0, "0"),
        (-0.0, "0"),
        (1.0, "1"),
        (10.0, "10"),
        (0.5, "0.5"),
        (-2.5, "-2.5"),
        (0.05, "0.05"),
        (123.456, "123.456"),
        (9007199254740992.0, "9007199254740992"),
        (1e16, "10000000000000000"),
        (1e20, "100000000000000000000"),
        (1e21, "1e+21"),
        (0.00001, "0.00001"),
        (0.000001, "0.000001"),
        (1e-7, "1e-7"),
        (1.5e-7, "1.5e-7"),
        (-1e-7, "-1e-7"),
        (5e-324, "5e-324"),
        (1.7976931348623157e308, "1.7976931348623157e+308"),
    ],
)
def test_number_formatting_follows_ecmascript_rules(value: float, expected: str) -> None:
    """RFC 8785 §3.2.2.3: shortest round-trip digits under the ES rendering rules —
    positional between 10⁻⁶ and 10²¹, exponent form beyond, ``-0`` as ``"0"``, and never
    a trailing ``.0``. These pins include both boundary flips (10²⁰/10²¹ and 10⁻⁶/10⁻⁷)
    and the extremes of the double range."""
    assert _format_double(value) == expected


def test_the_emitter_refuses_a_non_tree_value_as_a_programming_error() -> None:
    """Step-5 vetting happens in the walk; handing the emitter anything else is misuse."""
    with pytest.raises(TypeError):
        _emit({"x": {1, 2}})


# ── The vendored corpus: reproducibility at scale ────────────────────────────────────────


def corpus_ir_payloads() -> Iterator[tuple[str, dict[str, Any]]]:
    for path in sorted(FIXTURES_DIR.rglob("*.yaml")):
        if path.name == "schema.yaml":
            continue
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        for key in ("ir", "ir_before", "ir_after"):
            if key in data:
                yield f"{path.relative_to(FIXTURES_DIR)}::{key}", data[key]


def test_every_vendored_corpus_payload_canonicalizes_reproducibly() -> None:
    """§1.3 layer 1: the corpus is the document-conformance surface. Every embedded IR
    canonicalizes, its canonical bytes are valid JSON and a valid §2 document, and
    re-canonicalizing the reloaded document reproduces the bytes and the digest —
    recompute-and-compare (§1.2) across all 67 payloads."""
    count = 0
    for label, payload in corpus_ir_payloads():
        ir = load_ir(payload)
        blob = canonical_bytes(ir)
        digest = graph_version(ir)
        assert DIGEST_GRAMMAR.match(digest), label
        assert json.loads(blob) is not None, label
        reloaded = WorkflowIR.model_validate_json(blob)
        assert canonical_bytes(reloaded) == blob, label
        assert verify_graph_version(reloaded, digest), label
        count += 1
    assert count == 78


def test_authored_yaml_noise_never_reaches_the_digest() -> None:
    """§6.1 step 1 + DEC-10: surface bytes are never hashed. Restyling the authored YAML
    (key order, flow vs block, quoting) leaves the digest untouched."""
    restyled = yaml.safe_load(
        """
        edges:
          - {to: act, from: plan}
          - path_map: {redo: act, done: report}
            condition: done(result)
            kind: conditional
            from: act
        nodes:
          - {id: report, annotations: {input: [result]}}
          - {id: act, annotations: {effect: [network], output: [result], input: [task]}}
          - {id: plan, annotations: {output: [task], pure: true}}
        state: {result: str, task: str}
        runtime: {recursion_limit: {justification: redo loop bounded by review budget, value: 10}}
        finish: report
        entry: plan
        ir_version: "1.0"
        """
    )
    assert digest_of(restyled) == golden_digest()


def test_canonicalization_does_not_mutate_its_input() -> None:
    """The pipeline is a pure function: same model in, same bytes out, input untouched."""
    payload = authored_payload()
    ir = load_ir(payload)
    before = copy.deepcopy(payload)
    first = canonical_bytes(ir)
    second = canonical_bytes(ir)
    assert first == second
    assert payload == before
    assert ir == load_ir(before)


# ── The ir 1.1 `dynamic` kind, and the invariance it was ratified on (DEC-28) ─────────────


def _ir_blocks() -> list[tuple[str, dict[str, Any]]]:
    """Every IR document the repo vendors or commits, as (label, payload).

    The vendored property corpus (WA-04, read-only) plus golden vector 001 — everything whose
    canonical bytes are a contract this repo already made.
    """
    blocks: list[tuple[str, dict[str, Any]]] = [("golden/vector-001", authored_payload())]
    for path in sorted(FIXTURES_DIR.rglob("*.yaml")):
        if path.name == "schema.yaml":
            continue
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(document, dict):  # pragma: no cover - the corpus gate refuses these
            continue
        for key in ("ir", "ir_before", "ir_after"):
            block = document.get(key)
            if isinstance(block, dict):
                blocks.append((f"{path.relative_to(FIXTURES_DIR)}:{key}", block))
    return blocks


def test_a_dynamic_edge_canonicalizes_to_from_kind_and_its_guard() -> None:
    """IR-SPEC §2.4 as amended: "kind ``dynamic`` carries neither ``to`` nor ``path_map``".

    The member set is asserted whole rather than as two absences, so a target member added to
    the branch in passing fails here — and the ``kind`` is present, unlike ``normal``'s, because
    it is a discriminating value rather than the one omit-normalized default (§6.3).
    """
    payload = minimal(
        nodes=[{"id": "a"}],
        edges=[{"kind": "dynamic", "from": "a", "condition": "route_legs"}],
    )
    edge = json.loads(bytes_of(payload))["edges"][0]

    assert edge == {"condition": "route_legs", "from": "a", "kind": "dynamic"}
    assert list(edge) == ["condition", "from", "kind"]  # JCS member order, still by name
    assert digest_of(payload).startswith("sha256:")


def test_a_dynamic_edge_omits_a_guard_it_does_not_have() -> None:
    """``condition`` is OPTIONAL on the kind, and absence is absence (§6.3 omit-normalization)."""
    payload = minimal(edges=[{"kind": "dynamic", "from": "a"}])

    assert json.loads(bytes_of(payload))["edges"][0] == {"from": "a", "kind": "dynamic"}


def test_a_dynamic_edge_sorts_with_the_others_by_its_own_canonical_bytes() -> None:
    """§6.2 sorts ``edges[]`` bytewise over each edge's own normalized serialization.

    The fourth kind is no exception and needed no rule of its own: ``"dynamic"`` sorts before
    ``"conditional"``? No — the sort key is the whole edge object, so the answer is decided by
    ``from`` first (``"condition"`` and ``"from"`` precede ``"kind"`` by name), which is why the
    order below is by source and not by kind. Pinned because it is inside the digest.
    """
    payload = minimal(
        nodes=[{"id": "a"}, {"id": "b"}, {"id": "c"}],
        edges=[
            {"kind": "dynamic", "from": "c"},
            {"from": "a", "to": "b"},
            {"kind": "send", "from": "b", "to": "c"},
            {"kind": "dynamic", "from": "a"},
        ],
    )
    edges = json.loads(bytes_of(payload))["edges"]

    assert [(edge["from"], edge.get("kind", "normal")) for edge in edges] == [
        ("a", "dynamic"),
        ("a", "normal"),
        ("b", "send"),
        ("c", "dynamic"),
    ]


def test_no_document_this_repo_already_committed_carries_a_dynamic_edge() -> None:
    """The first half of DEC-28's digest-invariance ruling, machine-checked.

    "No existing document contains a ``dynamic`` edge and the three 1.0 kinds' serialization
    rules are untouched" — §6.3's additive-optional corollary is deliberately *not* the citation,
    because it covers new defaulted optional slots and this is a new union member. So the
    argument rests on this: quantified over the whole vendored corpus and the committed golden,
    every edge is one of the three 1.0 kinds and every document stamps ``"1.0"``.

    Durable rather than a one-off: the day a corpus revision introduces a ``dynamic`` edge is the
    day the invariance argument stops holding for that document, and this is what says so.
    """
    blocks = _ir_blocks()
    assert len(blocks) >= 60

    for label, payload in blocks:
        assert payload.get("ir_version") == "1.0", label
        for edge in payload.get("edges") or ():
            assert edge.get("kind", "normal") in {"normal", "conditional", "send"}, label


def test_the_dynamic_branch_moves_no_existing_documents_canonical_bytes() -> None:
    """The second half — the byte-diff DEC-28 mandates at EX-03 implementation time.

    Mechanical, and quantified over every document the repo commits: appending a ``dynamic`` edge
    changes the canonical bytes (so the branch is not a no-op), and removing it again reproduces
    the original bytes **exactly** (so the branch adds a member and disturbs nothing else — no
    resorting, no member of another edge moved, no top-level change beyond the one array entry).

    Golden vector 001 is in the quantification and is also checked whole against its committed
    file by :func:`test_golden_vector_001_reproduces_byte_exactly`, so between them the claim
    covers both "unchanged against the record" and "unchanged under the new branch".
    """
    for label, payload in _ir_blocks():
        original = bytes_of(payload)
        source = (payload.get("nodes") or [{"id": "a"}])[0]["id"]
        widened = {
            **payload,
            "ir_version": "1.1",
            "edges": [*(payload.get("edges") or ()), {"kind": "dynamic", "from": source}],
        }

        assert bytes_of(widened) != original, label
        narrowed = {**widened, "ir_version": "1.0", "edges": list(payload.get("edges") or ())}
        assert bytes_of(narrowed) == original, label
