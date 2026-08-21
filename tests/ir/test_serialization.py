"""YAML/JSON loaders and lossless round-trip — IR-SPEC §2.5 note 4, SOW §2 criterion 6.

Criterion 6 is that *every IR model serializes to YAML and JSON and reloads equal to its
source, golden-tested*. Three layers carry it here, deliberately overlapping:

* the **committed goldens** under ``golden/roundtrip/`` — five authored IRs chosen to cover
  the surface distinctions that a lossless round-trip has to keep (§6.3's collapsible
  representations, the §5 identity grammar, text YAML likes to reinterpret, the foreign
  ``args_schema`` interior, numbers). Each ships with its two committed surface dumps, so a
  styling change is a visible golden diff (WA-05), not a silent one;
* the **vendored corpus** — all 67 embedded IR payloads, the document-conformance surface
  of §1.3, round-tripped through both formats and across them;
* the **per-model table** — one representative instance of every model in the §2.5 surface,
  which is what criterion 6 says literally.

Every round-trip assertion in this module is ``reloaded == source`` on *models* — pydantic
value equality, never string equality of the serialized text. That the assertion can fail
is demonstrated too (:func:`test_model_equality_is_sensitive_to_every_top_level_field`), so
"green" here is not vacuous.

Nothing executes a workflow, a node, an LLM, or a network call (WA-07): every input is
hand-written text, a committed golden, or a vendored fixture payload read as data, and the
loaders are pure functions over that text. Two tripwires pin that the YAML path cannot be
turned into an execution path (:func:`test_the_yaml_loader_refuses_python_object_tags`,
:func:`test_loading_never_imports_a_module_named_in_the_document`) and one pins that no
foreign object's own code runs during a dump.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from gebra.ir import (
    JSON_SUFFIXES,
    YAML_SUFFIXES,
    Annotations,
    Checkpointer,
    Compensation,
    ConditionalEdge,
    DeterministicSpec,
    DynamicEdge,
    IdempotentKey,
    Interrupts,
    IRModel,
    IRSerializationError,
    IRSerializationErrorReason,
    Node,
    NormalEdge,
    RecursionLimit,
    RetryPolicy,
    Runtime,
    SendEdge,
    StateField,
    Variant,
    WorkflowIR,
    canonical_bytes,
    dump_json,
    dump_yaml,
    graph_version,
    load_json,
    load_yaml,
    read_ir,
    write_ir,
)
from tests.conftest import FIXTURES_DIR

GOLDEN_DIR = Path(__file__).parent / "golden" / "roundtrip"

#: The committed round-trip golden set, pinned so that a golden cannot quietly disappear.
GOLDEN_STEMS = (
    "01-minimal",
    "02-annotated-workflow",
    "03-representation-variants",
    "04-identity-and-text",
    "05-scalars-and-foreign-content",
)

#: The smallest legal document, as text — the base every hand-built payload here extends.
MINIMAL_YAML = """
ir_version: "1.0"
entry: only
finish: only
nodes:
  - id: only
edges: []
"""


def authored(stem: str) -> str:
    """The authored YAML source of golden ``stem``."""
    return (GOLDEN_DIR / f"{stem}.authored.yaml").read_text(encoding="utf-8")


def minimal_payload(**overrides: Any) -> dict[str, Any]:
    """The minimal document as data, with ``overrides`` applied — for hand-built payloads."""
    payload: dict[str, Any] = {
        "ir_version": "1.0",
        "entry": "only",
        "finish": "only",
        "nodes": [{"id": "only"}],
        "edges": [],
    }
    payload.update(overrides)
    return payload


# ── The committed goldens ────────────────────────────────────────────────────────────────


def test_the_golden_set_is_the_committed_one() -> None:
    """Each golden is a triple: the authored source and its two surface dumps."""
    found = {path.name[: -len(".authored.yaml")] for path in GOLDEN_DIR.glob("*.authored.yaml")}
    assert found == set(GOLDEN_STEMS)
    for stem in GOLDEN_STEMS:
        assert (GOLDEN_DIR / f"{stem}.surface.yaml").is_file()
        assert (GOLDEN_DIR / f"{stem}.surface.json").is_file()


@pytest.mark.parametrize("stem", GOLDEN_STEMS)
def test_golden_dumps_to_its_committed_yaml_surface(stem: str) -> None:
    """The committed YAML dump is what ``dump_yaml`` produces, byte for byte.

    This is the dump-styling pin (WA-05): block style, declaration order, non-ASCII kept as
    itself, one trailing newline. A change to any of those shows up as a golden diff.
    """
    ir = load_yaml(WorkflowIR, authored(stem))
    assert dump_yaml(ir) == (GOLDEN_DIR / f"{stem}.surface.yaml").read_text(encoding="utf-8")


@pytest.mark.parametrize("stem", GOLDEN_STEMS)
def test_golden_dumps_to_its_committed_json_surface(stem: str) -> None:
    """The committed JSON dump is what ``dump_json`` produces, byte for byte."""
    ir = load_yaml(WorkflowIR, authored(stem))
    assert dump_json(ir) == (GOLDEN_DIR / f"{stem}.surface.json").read_text(encoding="utf-8")


@pytest.mark.parametrize("stem", GOLDEN_STEMS)
def test_golden_round_trips_through_yaml_by_model_equality(stem: str) -> None:
    """SOW §2 criterion 6, YAML half: ``load_yaml(dump_yaml(m)) == m``."""
    ir = load_yaml(WorkflowIR, authored(stem))
    assert load_yaml(WorkflowIR, dump_yaml(ir)) == ir


@pytest.mark.parametrize("stem", GOLDEN_STEMS)
def test_golden_round_trips_through_json_by_model_equality(stem: str) -> None:
    """SOW §2 criterion 6, JSON half: ``load_json(dump_json(m)) == m``."""
    ir = load_yaml(WorkflowIR, authored(stem))
    assert load_json(WorkflowIR, dump_json(ir)) == ir


@pytest.mark.parametrize("stem", GOLDEN_STEMS)
def test_the_committed_surfaces_reload_to_the_authored_model(stem: str) -> None:
    """The goldens are load-side too: both committed dumps reload to the authored model.

    Text equality is asserted separately above; this is the assertion that survives a
    justified re-dump of the goldens, since it compares models rather than bytes.
    """
    ir = load_yaml(WorkflowIR, authored(stem))
    assert load_yaml(WorkflowIR, (GOLDEN_DIR / f"{stem}.surface.yaml").read_text("utf-8")) == ir
    assert load_json(WorkflowIR, (GOLDEN_DIR / f"{stem}.surface.json").read_text("utf-8")) == ir


@pytest.mark.parametrize("stem", GOLDEN_STEMS)
def test_golden_agrees_across_the_two_formats(stem: str) -> None:
    """The formats are interchangeable: the same document loads to the same model."""
    ir = load_yaml(WorkflowIR, authored(stem))
    assert load_json(WorkflowIR, dump_json(ir)) == load_yaml(WorkflowIR, dump_yaml(ir))


@pytest.mark.parametrize("stem", GOLDEN_STEMS)
def test_the_surface_dumps_are_fixed_points(stem: str) -> None:
    """Re-dumping a reloaded document reproduces the text: no drift under repeated writes."""
    ir = load_yaml(WorkflowIR, authored(stem))
    for dump, load in ((dump_yaml, load_yaml), (dump_json, load_json)):
        text = dump(ir)
        assert dump(load(WorkflowIR, text)) == text


def test_the_authored_sources_carry_yaml_only_noise_the_surface_drops() -> None:
    """The goldens are authored YAML — comments, key order, quoting styles — and the round
    trip is about the *model*, so none of that has to survive (IR-SPEC §6.1 step 1)."""
    source = authored("02-annotated-workflow")
    assert source.lstrip().startswith("#")
    assert "#" not in dump_yaml(load_yaml(WorkflowIR, source))


def test_a_golden_the_surface_carries_and_canonicalization_refuses() -> None:
    """Golden 05 fixes the scope boundary: the loaders are not the hash pipeline.

    Its ``args_schema`` holds integers outside the I-JSON exact range, which the ratified
    IR-D1 ruling (PD-004) makes an IR validity error at hashing time — with the adjacent-gap
    closure reaching into foreign content. The document is still a valid §2 document, so it
    round-trips losslessly; only ``graph_version`` refuses it.
    """
    ir = load_yaml(WorkflowIR, authored("05-scalars-and-foreign-content"))
    assert load_yaml(WorkflowIR, dump_yaml(ir)) == ir
    assert load_json(WorkflowIR, dump_json(ir)) == ir
    with pytest.raises(ValueError, match="I-JSON"):
        graph_version(ir)


# ── The vendored corpus ──────────────────────────────────────────────────────────────────


def corpus_ir_payloads() -> list[tuple[str, dict[str, Any]]]:
    """Every IR payload embedded in the vendored fixture corpus, as (label, block).

    Read as data — the corpus is never imported or executed (WA-07).
    """
    payloads: list[tuple[str, dict[str, Any]]] = []
    for path in sorted(FIXTURES_DIR.rglob("*.yaml")):
        if path.name == "schema.yaml":
            continue
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(document, dict):
            continue
        for key in ("ir", "ir_before", "ir_after"):
            block = document.get(key)
            if isinstance(block, dict):
                payloads.append((f"{path.relative_to(FIXTURES_DIR)}::{key}", block))
    return payloads


def test_every_vendored_corpus_payload_round_trips_in_both_formats() -> None:
    """The corpus samples of the acceptance box: 67 payloads, model equality, both formats.

    Each payload is re-emitted as YAML, loaded, dumped and loaded again in each format, and
    the two formats are cross-checked against each other.
    """
    count = 0
    for label, payload in corpus_ir_payloads():
        source = load_yaml(WorkflowIR, yaml.safe_dump(payload, allow_unicode=True))
        from_yaml = load_yaml(WorkflowIR, dump_yaml(source))
        from_json = load_json(WorkflowIR, dump_json(source))
        assert from_yaml == source, label
        assert from_json == source, label
        assert from_yaml == from_json, label
        count += 1
    assert count == 67


def test_corpus_payloads_load_identically_through_both_entry_points() -> None:
    """``load_yaml`` and ``load_json`` are one validation path behind two parsers: the same
    document, spelled in either format, loads to the same model."""
    for label, payload in corpus_ir_payloads():
        as_yaml = load_yaml(WorkflowIR, yaml.safe_dump(payload, allow_unicode=True))
        as_json = load_json(WorkflowIR, json.dumps(payload))
        assert as_yaml == as_json, label


# ── Every model in the §2.5 surface ──────────────────────────────────────────────────────

#: One representative instance of every model in the IR-SPEC §2.5 surface. SOW §2 criterion
#: 6 is about *every IR model*, not only :class:`WorkflowIR`; the coverage assertion below
#: keeps this table in step with the package.
REPRESENTATIVE_MODELS: tuple[IRModel, ...] = (
    StateField(type="list", reducer="operator.add", optional=True),
    IdempotentKey(key="order_id"),
    DeterministicSpec(seed=7, temperature=0.25),
    RetryPolicy(max_attempts=3, retry_on=("TimeoutError",)),
    Variant(key="budget", measure="decreases"),
    Compensation(hook="refund"),
    Annotations(
        pure=False,
        effect=("payment",),
        idempotent=IdempotentKey(key="order_id"),
        deterministic=DeterministicSpec(seed=7),
        input=("order_id",),
        output=("receipt",),
        source="book_tool",
        map="orders",
        args_schema={"type": "object", "properties": {"q": {"type": "string"}}},
        retry_policy=RetryPolicy(max_attempts=2, retry_on=()),
        variant=Variant(key="budget", measure="decreases"),
        compensation=Compensation(hook="refund"),
        prompt_digest="sha256:" + "a" * 64,
        config_digest="sha256:" + "b" * 64,
    ),
    Node(id="book", annotations=Annotations(pure=True)),
    NormalEdge(kind="normal", **{"from": "plan"}, to="book"),
    ConditionalEdge(kind="conditional", **{"from": "book"}, condition="ok(x)", path_map={"y": "z"}),
    SendEdge(kind="send", **{"from": "book"}, to="report"),
    DynamicEdge(kind="dynamic", **{"from": "book"}, condition="route_legs"),
    RecursionLimit(value=25, justification="bounded by the declared review budget"),
    Interrupts(before=("book",), after=()),
    Checkpointer(present=True),
    Runtime(
        recursion_limit=RecursionLimit(value=25, justification="bounded by the budget"),
        interrupts=Interrupts(before=("book",)),
        checkpointer=Checkpointer(present=False),
    ),
    load_json(WorkflowIR, json.dumps(minimal_payload())),
)

REPRESENTATIVE_IDS = [type(model).__name__ for model in REPRESENTATIVE_MODELS]


def test_the_representative_table_covers_every_exported_model() -> None:
    """Set equality against the package's own model surface, so a new model cannot land
    without a round-trip case (the base :class:`IRModel` is not itself a document shape)."""
    import gebra.ir as ir_package

    exported = {
        value
        for name in ir_package.__all__
        if isinstance(value := getattr(ir_package, name), type)
        and issubclass(value, IRModel)
        and value is not IRModel
    }
    assert {type(model) for model in REPRESENTATIVE_MODELS} == exported


@pytest.mark.parametrize("model", REPRESENTATIVE_MODELS, ids=REPRESENTATIVE_IDS)
def test_every_ir_model_round_trips_through_yaml(model: IRModel) -> None:
    """SOW §2 criterion 6, model by model — YAML."""
    assert load_yaml(type(model), dump_yaml(model)) == model


@pytest.mark.parametrize("model", REPRESENTATIVE_MODELS, ids=REPRESENTATIVE_IDS)
def test_every_ir_model_round_trips_through_json(model: IRModel) -> None:
    """SOW §2 criterion 6, model by model — JSON."""
    assert load_json(type(model), dump_json(model)) == model


@pytest.mark.parametrize("model", REPRESENTATIVE_MODELS, ids=REPRESENTATIVE_IDS)
def test_every_ir_model_agrees_across_the_two_formats(model: IRModel) -> None:
    """The two formats carry the same model, one member at a time."""
    assert load_yaml(type(model), dump_yaml(model)) == load_json(type(model), dump_json(model))


# ── What the round-trip assertion actually asserts ───────────────────────────────────────


def test_the_round_trip_assertion_is_model_equality_not_identity() -> None:
    """The reloaded document is a *different object* that compares equal field by field."""
    source = load_yaml(WorkflowIR, authored("02-annotated-workflow"))
    reloaded = load_json(WorkflowIR, dump_json(source))
    assert reloaded is not source
    assert reloaded == source
    assert reloaded.nodes is not source.nodes
    assert reloaded.nodes == source.nodes
    # Field-by-field, so "equal" is not resting on a single `__eq__` shortcut.
    for name in type(source).model_fields:
        assert getattr(reloaded, name) == getattr(source, name), name


def test_the_round_trip_assertion_is_not_text_equality() -> None:
    """Restyled YAML — reordered members, flow style, different quoting — loads to an equal
    model while the two texts differ. Model equality is what the acceptance box claims."""
    block = "{ir_version: '1.0', edges: [], nodes: [{id: only}], finish: only, entry: only}"
    restyled = load_yaml(WorkflowIR, block)
    plain = load_yaml(WorkflowIR, MINIMAL_YAML)
    assert block != MINIMAL_YAML
    assert restyled == plain


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("ir_version", "1.0"),
        ("entry", "other"),
        ("finish", "other"),
        ("state", {"k": "str"}),
        ("nodes", [{"id": "other"}]),
        ("edges", [{"from": "only", "to": "END"}]),
        ("runtime", {"checkpointer": {"present": True}}),
    ],
)
def test_model_equality_is_sensitive_to_every_top_level_field(field: str, value: Any) -> None:
    """The round-trip assertion is not vacuous: changing any one field breaks equality.

    ``ir_version`` is in the table as the control — it is the one value that cannot differ,
    so it must compare *equal* where the other six compare unequal.
    """
    source = load_json(WorkflowIR, json.dumps(minimal_payload()))
    mutated = load_json(WorkflowIR, json.dumps(minimal_payload(**{field: value})))
    assert (mutated == source) is (field == "ir_version")


def test_representations_that_share_canonical_bytes_are_still_unequal_models() -> None:
    """The sharpest statement of what IR-04 preserves and IR-03 collapses.

    ``entry: only`` and ``entry: [only]`` denote one wired set, so §6.3 gives them one
    canonical form and one ``graph_version`` — and they are *different models*. A round trip
    that normalized them would pass a digest check and fail criterion 6.
    """
    scalar = load_json(WorkflowIR, json.dumps(minimal_payload(entry="only")))
    listed = load_json(WorkflowIR, json.dumps(minimal_payload(entry=["only"])))
    assert scalar != listed
    assert canonical_bytes(scalar) == canonical_bytes(listed)
    assert graph_version(scalar) == graph_version(listed)
    for dump, load in ((dump_yaml, load_yaml), (dump_json, load_json)):
        assert load(WorkflowIR, dump(scalar)) == scalar
        assert load(WorkflowIR, dump(listed)) == listed
        assert load(WorkflowIR, dump(scalar)) != listed


@pytest.mark.parametrize("stem", [stem for stem in GOLDEN_STEMS if not stem.startswith("05")])
def test_the_digest_survives_a_round_trip(stem: str) -> None:
    """What every consumer of the round trip actually depends on: writing a document to a
    file and reading it back does not move its ``graph_version``.

    It follows from model equality — ``canonical_bytes`` is a pure function of the model —
    but it is the property D-11 snapshots and the §6.6 telemetry attribute rest on, so it is
    asserted rather than inferred. Golden 05 is excluded: canonicalization refuses it by
    design (its integers are outside the I-JSON exact range, PD-004).
    """
    ir = load_yaml(WorkflowIR, authored(stem))
    digest = graph_version(ir)
    assert graph_version(load_yaml(WorkflowIR, dump_yaml(ir))) == digest
    assert graph_version(load_json(WorkflowIR, dump_json(ir))) == digest


def test_the_digest_survives_a_round_trip_over_the_whole_corpus() -> None:
    """The same claim over all 67 vendored payloads, in both formats."""
    count = 0
    for label, payload in corpus_ir_payloads():
        ir = load_yaml(WorkflowIR, yaml.safe_dump(payload, allow_unicode=True))
        digest = graph_version(ir)
        assert graph_version(load_yaml(WorkflowIR, dump_yaml(ir))) == digest, label
        assert graph_version(load_json(WorkflowIR, dump_json(ir))) == digest, label
        count += 1
    assert count == 67


def test_an_empty_optional_array_survives_as_itself() -> None:
    """IR-01's carry-forward: ``Interrupts(before=())`` is not ``Interrupts(before=None)``.

    Canonicalization maps the empty array onto absence (§6.3); the surface must not, or the
    document that was authored with an explicit empty list reloads as a different model.
    """
    empty = Interrupts(before=())
    absent = Interrupts(before=None)
    assert empty != absent
    for dump, load in ((dump_yaml, load_yaml), (dump_json, load_json)):
        assert load(Interrupts, dump(empty)) == empty
        assert load(Interrupts, dump(absent)) == absent
    assert "before" in dump_json(empty)
    assert "before" not in dump_json(absent)


def test_the_two_state_surface_forms_stay_distinct() -> None:
    """``{k: str}`` and ``{k: {type: str}}`` collapse to one canonical form (§6.3) and are
    two models; both survive the round trip as authored."""
    bare = load_json(WorkflowIR, json.dumps(minimal_payload(state={"k": "str"})))
    spelled = load_json(WorkflowIR, json.dumps(minimal_payload(state={"k": {"type": "str"}})))
    assert bare != spelled
    assert canonical_bytes(bare) == canonical_bytes(spelled)
    for dump, load in ((dump_yaml, load_yaml), (dump_json, load_json)):
        assert load(WorkflowIR, dump(bare)) == bare
        assert load(WorkflowIR, dump(spelled)) == spelled


def test_a_tagless_edge_reloads_as_the_explicitly_tagged_one() -> None:
    """The §2.5 note 1 injection happens at load, so the tagless and the tagged surface
    forms are one model — and the dump writes the tag it validated."""
    tagless = load_json(
        WorkflowIR, json.dumps(minimal_payload(edges=[{"from": "only", "to": "e"}]))
    )
    tagged = load_json(
        WorkflowIR,
        json.dumps(minimal_payload(edges=[{"kind": "normal", "from": "only", "to": "e"}])),
    )
    assert tagless == tagged
    assert dump_json(tagless) == dump_json(tagged)
    assert '"kind": "normal"' in dump_json(tagless)
    assert load_yaml(WorkflowIR, dump_yaml(tagless)) == tagless


def test_the_alias_is_what_reaches_the_surface() -> None:
    """§2.5 note 2: the member is ``from`` on the wire and ``from_`` in Python."""
    ir = load_json(WorkflowIR, json.dumps(minimal_payload(edges=[{"from": "only", "to": "e"}])))
    assert '"from": "only"' in dump_json(ir)
    assert "from_" not in dump_json(ir)
    assert "from: only" in dump_yaml(ir)


# ── The ingestion path (IR-SPEC §2.5 note 4) ─────────────────────────────────────────────


def test_yaml_sequences_validate_into_tuples_through_json_mode() -> None:
    """Why the SHOULD of §2.5 note 4 is taken: under strict Python-mode validation a
    ``list`` is not a ``tuple``, so the same parsed data that ``model_validate`` refuses is
    exactly what the JSON re-encoding admits — and it admits it as a tuple (A6 PC-2)."""
    parsed = yaml.safe_load(MINIMAL_YAML)
    with pytest.raises(ValidationError) as refused:
        WorkflowIR.model_validate(parsed)
    assert refused.value.errors()[0]["type"] == "tuple_type"

    ir = load_yaml(WorkflowIR, MINIMAL_YAML)
    assert isinstance(ir.nodes, tuple)
    assert isinstance(ir.edges, tuple)


def test_the_yaml_and_json_entry_points_report_the_same_model_error() -> None:
    """One validation path behind two parsers: an invalid document fails the same way."""
    payload = minimal_payload(nodes=[{"id": "__start__"}])
    with pytest.raises(ValidationError) as from_yaml:
        load_yaml(WorkflowIR, yaml.safe_dump(payload))
    with pytest.raises(ValidationError) as from_json:
        load_json(WorkflowIR, json.dumps(payload))
    assert from_yaml.value.errors()[0]["loc"] == from_json.value.errors()[0]["loc"]
    assert from_yaml.value.errors()[0]["loc"] == ("nodes", 0, "id")


def test_an_unknown_member_is_refused_through_both_formats() -> None:
    """``extra="forbid"`` (A6 PC-3) is not softened by either loader."""
    payload = minimal_payload(unexpected="x")
    for load, text in ((load_yaml, yaml.safe_dump(payload)), (load_json, json.dumps(payload))):
        with pytest.raises(ValidationError) as refused:
            load(WorkflowIR, text)
        assert refused.value.errors()[0]["type"] == "extra_forbidden"


def test_bytes_and_text_are_both_accepted() -> None:
    """A file read in binary and one read as text load identically."""
    assert load_yaml(WorkflowIR, MINIMAL_YAML.encode()) == load_yaml(WorkflowIR, MINIMAL_YAML)
    compact = json.dumps(minimal_payload())
    assert load_json(WorkflowIR, compact.encode()) == load_json(WorkflowIR, compact)


def test_a_leading_byte_order_mark_is_not_content() -> None:
    """A UTF-8 BOM is what a Windows editor leaves behind. Handed to a parser it is an
    opaque syntax error, so it is dropped before either parser sees it — and it is dropped
    the same way for both, which PyYAML's own BOM handling would not have been."""
    ir = load_yaml(WorkflowIR, MINIMAL_YAML)
    compact = json.dumps(minimal_payload())
    for source in (MINIMAL_YAML, MINIMAL_YAML.encode("utf-8-sig")):
        assert load_yaml(WorkflowIR, source) == ir
    for source in (compact, compact.encode("utf-8-sig")):
        assert load_json(WorkflowIR, source) == ir


def test_non_utf8_bytes_are_a_value_error() -> None:
    """``bytes`` are UTF-8 in both entry points; anything else is refused, not guessed."""
    for load in (load_yaml, load_json):
        with pytest.raises(UnicodeDecodeError):
            load(WorkflowIR, b"\xff\xfe{}")


def test_a_python_tuple_in_foreign_content_reloads_as_the_list_json_has() -> None:
    """The one documented boundary of the round-trip claim.

    JSON has a single sequence type, so a ``tuple`` is written as an array. Model members
    are tuples by convention (A6 PC-2) and reload as tuples; a tuple can only reach the
    *foreign* ``args_schema`` interior by Python construction, never by loading, and it
    comes back as a ``list``.
    """
    hand_built = Annotations(args_schema={"prefixItems": (1, 2)})
    reloaded = load_json(Annotations, dump_json(hand_built))
    assert reloaded != hand_built
    assert reloaded.args_schema == {"prefixItems": [1, 2]}
    # Loading never produces one, so every model the loaders themselves make round-trips.
    assert load_json(Annotations, dump_json(reloaded)) == reloaded
    assert isinstance(
        load_json(RetryPolicy, '{"max_attempts": 1, "retry_on": ["E"]}').retry_on, tuple
    )


# ── Dump styling ─────────────────────────────────────────────────────────────────────────


def test_json_dump_styling() -> None:
    """Two-space indent, declaration order kept, non-ASCII as itself, one trailing newline."""
    ir = load_yaml(WorkflowIR, authored("04-identity-and-text"))
    text = dump_json(ir)
    assert text.startswith('{\n  "ir_version": "1.0",\n  "entry":')
    assert text.endswith("}\n")
    assert "café/résumé" in text
    assert "\\u00e9" not in text


def test_json_dump_can_be_compact() -> None:
    """``indent=None`` is the single-line form; it reloads to the same model."""
    ir = load_yaml(WorkflowIR, MINIMAL_YAML)
    text = dump_json(ir, indent=None)
    assert text.count("\n") == 1
    assert text.startswith('{"ir_version": "1.0"')
    assert load_json(WorkflowIR, text) == ir


def test_yaml_dump_styling() -> None:
    """Block style, declaration order kept (never alphabetized), non-ASCII as itself."""
    ir = load_yaml(WorkflowIR, authored("04-identity-and-text"))
    text = dump_yaml(ir)
    assert text.startswith("ir_version: '1.0'\nentry:")
    assert text.endswith("\n")
    assert "café/résumé" in text
    assert "{" not in text.splitlines()[0]


@pytest.mark.parametrize(
    ("char", "escape"),
    [("\x85", "\\N"), ("\u2028", "\\L"), ("\u2029", "\\P"), ("\ufeff", "\\uFEFF")],
)
def test_the_yaml_only_line_breaks_are_escaped_rather_than_written_raw(
    char: str, escape: str
) -> None:
    """YAML 1.1 counts NEL, LINE/PARAGRAPH SEPARATOR and the BOM as breaks; JSON counts them
    as ordinary text. Written raw in a single-quoted scalar the parser folds them back —
    ``"\\x85x"`` returns as ``" x"`` — so they are emitted double-quoted and escaped.

    The property tests found this; the pin is here so the diagnosis is named.
    """
    model = RecursionLimit(value=1, justification=f"before{char}after")
    text = dump_yaml(model)
    assert char not in text
    assert escape in text
    assert load_yaml(RecursionLimit, text) == model
    assert load_json(RecursionLimit, dump_json(model)) == model


def test_the_dump_omits_null_members_but_keeps_foreign_nulls() -> None:
    """Absence and ``null`` reload identically for a model member, so the dump drops it; a
    ``null`` inside the foreign ``args_schema`` object is content and is carried."""
    ir = load_json(
        WorkflowIR,
        json.dumps(
            minimal_payload(nodes=[{"id": "only", "annotations": {"args_schema": {"c": None}}}])
        ),
    )
    text = dump_json(ir)
    assert '"c": null' in text
    assert '"pure"' not in text
    assert '"retry_policy"' not in text
    assert load_json(WorkflowIR, text) == ir


def test_an_explicit_null_member_and_an_absent_one_reload_the_same() -> None:
    """Which is why dropping ``null`` members costs nothing under model equality."""
    spelled = load_json(WorkflowIR, json.dumps(minimal_payload(state=None, runtime=None)))
    absent = load_json(WorkflowIR, json.dumps(minimal_payload()))
    assert spelled == absent


# ── Files ────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("suffix", [".yaml", ".yml", ".json", ".YAML", ".JSON"])
def test_a_file_round_trips_through_write_and_read(suffix: str, tmp_path: Path) -> None:
    """Format by suffix, case-insensitively; the file reloads equal to the model written."""
    ir = load_yaml(WorkflowIR, authored("02-annotated-workflow"))
    path = tmp_path / f"workflow{suffix}"
    write_ir(ir, path)
    assert read_ir(path) == ir
    assert path.read_bytes().endswith(b"\n")
    assert b"\r\n" not in path.read_bytes()


def test_a_written_file_is_utf8_and_matches_the_dump(tmp_path: Path) -> None:
    """``write_ir`` writes exactly what ``dump_*`` returns, encoded as UTF-8."""
    ir = load_yaml(WorkflowIR, authored("04-identity-and-text"))
    for suffix, dump in ((".yaml", dump_yaml), (".json", dump_json)):
        path = tmp_path / f"workflow{suffix}"
        write_ir(ir, path)
        assert path.read_text(encoding="utf-8") == dump(ir)
        assert "café".encode() in path.read_bytes()


def test_read_ir_accepts_a_path_as_a_string(tmp_path: Path) -> None:
    """``str`` and ``Path`` are both path-likes here."""
    ir = load_yaml(WorkflowIR, MINIMAL_YAML)
    path = tmp_path / "workflow.json"
    write_ir(ir, str(path))
    assert read_ir(str(path)) == ir


@pytest.mark.parametrize("name", ["workflow.txt", "workflow", "workflow.yaml.bak"])
def test_an_unrecognized_suffix_is_refused_by_both_file_entry_points(
    name: str, tmp_path: Path
) -> None:
    """The suffix names the format; nothing sniffs content, and nothing guesses."""
    ir = load_yaml(WorkflowIR, MINIMAL_YAML)
    path = tmp_path / name
    path.write_text(MINIMAL_YAML, encoding="utf-8")
    for call in (lambda: read_ir(path), lambda: write_ir(ir, path)):
        with pytest.raises(IRSerializationError) as refused:
            call()
        assert refused.value.reason is IRSerializationErrorReason.UNKNOWN_SUFFIX
    assert set(YAML_SUFFIXES) == {".yaml", ".yml"}
    assert set(JSON_SUFFIXES) == {".json"}


# ── Surface faults: refused, never coerced ───────────────────────────────────────────────


def test_malformed_yaml_is_a_serialization_error() -> None:
    """A YAML syntax error is a surface fault, so it is not dressed up as a model error."""
    with pytest.raises(IRSerializationError) as refused:
        load_yaml(WorkflowIR, "ir_version: '1.0'\n  entry: [oops\n")
    assert refused.value.reason is IRSerializationErrorReason.YAML_SYNTAX
    assert refused.value.path == ()


def test_malformed_json_is_a_serialization_error() -> None:
    """Symmetrically with YAML: a syntax error is a surface fault in either format."""
    with pytest.raises(IRSerializationError) as refused:
        load_json(WorkflowIR, "{oops")
    assert refused.value.reason is IRSerializationErrorReason.JSON_SYNTAX
    assert refused.value.path == ()


@pytest.mark.parametrize("literal", ["Infinity", "-Infinity", "NaN"])
def test_the_non_standard_json_number_literals_are_refused(literal: str) -> None:
    """Python's JSON parser and pydantic's both accept ``Infinity``/``NaN``; RFC 8259 has
    neither, and IR-SPEC §6.3 forbids them in an IR document. Accepting one would load a
    document that could not be written back out — the YAML half already refuses ``.inf``,
    and the two entry points answer alike."""
    with pytest.raises(IRSerializationError) as refused:
        load_json(DeterministicSpec, f'{{"seed": 1, "temperature": {literal}}}')
    assert refused.value.reason is IRSerializationErrorReason.NON_FINITE_NUMBER
    assert refused.value.path == ("temperature",)


def test_a_non_string_mapping_key_is_refused_not_stringified() -> None:
    """YAML admits ``1: x``; JSON does not, and ``json.dumps`` would silently make it
    ``"1"`` — a document that no longer says what it said."""
    source = MINIMAL_YAML.replace(
        "  - id: only",
        "  - id: only\n    annotations: {args_schema: {properties: {1: {type: string}}}}",
    )
    with pytest.raises(IRSerializationError) as refused:
        load_yaml(WorkflowIR, source)
    assert refused.value.reason is IRSerializationErrorReason.NON_STRING_KEY
    assert refused.value.value == 1
    assert "nodes[0].annotations.args_schema.properties" in str(refused.value)


@pytest.mark.parametrize("literal", [".inf", "-.inf", ".nan"])
def test_a_non_finite_number_is_refused_on_the_way_in(literal: str) -> None:
    """YAML has ``.inf`` and ``.nan``; JSON has no form for either, and IR-SPEC §6.3 forbids
    them in an IR document."""
    source = MINIMAL_YAML.replace(
        "  - id: only",
        f"  - id: only\n    annotations: {{args_schema: {{maximum: {literal}}}}}",
    )
    with pytest.raises(IRSerializationError) as refused:
        load_yaml(WorkflowIR, source)
    assert refused.value.reason is IRSerializationErrorReason.NON_FINITE_NUMBER
    assert "nodes[0].annotations.args_schema.maximum" in str(refused.value)


def test_a_non_finite_number_is_refused_on_the_way_out() -> None:
    """Dumping refuses it too, rather than writing ``Infinity`` (which no JSON parser reads)
    or ``null`` (which pydantic's own JSON-mode dump would silently substitute)."""
    model = Annotations(args_schema={"maximum": float("inf")})
    for dump in (dump_json, dump_yaml):
        with pytest.raises(IRSerializationError) as refused:
            dump(model)
        assert refused.value.reason is IRSerializationErrorReason.NON_FINITE_NUMBER
    assert "args_schema.maximum" in str(refused.value)


def test_an_alias_bomb_is_refused_by_name() -> None:
    """``safe_load`` returns a compact object graph — an alias is one shared object — and the
    JSON re-encoding writes every reference out in full. A few hundred bytes of nested
    aliases therefore expand without bound, so the expansion is bounded and named."""
    levels = "\n".join(
        f"        l{n}: &l{n} [{', '.join([f'*l{n - 1}'] * 9)}]" for n in range(1, 8)
    )
    source = MINIMAL_YAML.replace(
        "  - id: only",
        f"  - id: only\n    annotations:\n      args_schema:\n        l0: &l0 x\n{levels}",
    )
    assert len(source) < 1500
    with pytest.raises(IRSerializationError) as refused:
        load_yaml(WorkflowIR, source)
    assert refused.value.reason is IRSerializationErrorReason.TOO_COMPLEX
    assert "expands to more than" in str(refused.value)


def test_a_document_nested_past_the_depth_ceiling_is_refused() -> None:
    """Depth is bounded for the same reason, and so that the answer is a reason code rather
    than a ``RecursionError`` from whichever parser runs out of stack first."""
    deep: Any = "leaf"
    for _ in range(400):
        deep = {"n": deep}
    payload = minimal_payload(nodes=[{"id": "only", "annotations": {"args_schema": deep}}])
    with pytest.raises(IRSerializationError) as refused:
        load_json(WorkflowIR, json.dumps(payload))
    assert refused.value.reason is IRSerializationErrorReason.TOO_COMPLEX
    assert "nested more than" in str(refused.value)


@pytest.mark.parametrize("load", [load_yaml, load_json])
def test_a_parser_that_runs_out_of_stack_is_a_reason_coded_refusal(load: Any) -> None:
    """Both parsers recurse, and both give up before this module's depth ceiling is reached
    on a document this deep. A ``RecursionError`` reaching the caller would be a hole in the
    documented contract, so it is translated."""
    source = "[" * 20_000 + "]" * 20_000
    with pytest.raises(IRSerializationError) as refused:
        load(WorkflowIR, source)
    assert refused.value.reason is IRSerializationErrorReason.TOO_COMPLEX
    assert "too deeply" in str(refused.value)


@pytest.mark.parametrize("load", [load_yaml, load_json])
def test_an_integer_past_the_interpreter_digit_limit_is_a_reason_coded_refusal(
    load: Any,
) -> None:
    """CPython caps int↔str conversion (``sys.set_int_max_str_digits``, 4300 by default), so
    a wide enough integer cannot be parsed or written at all. That is a refusal with a
    reason, not a bare ``ValueError``."""
    source = f"seed: {'9' * 5000}"
    with pytest.raises(IRSerializationError) as refused:
        load(DeterministicSpec, source if load is load_yaml else '{"seed": %s}' % ("9" * 5000))
    assert refused.value.reason is IRSerializationErrorReason.TOO_COMPLEX


def test_an_integer_past_the_digit_limit_is_refused_on_the_way_out() -> None:
    """The same limit on the dump side, in both formats: a model can be constructed in
    Python with an integer no writer can render."""
    model = DeterministicSpec(seed=10**5000)  # built without ever writing it as digits
    for dump in (dump_json, dump_yaml):
        with pytest.raises(IRSerializationError) as refused:
            dump(model)
        assert refused.value.reason is IRSerializationErrorReason.TOO_COMPLEX


def test_a_document_within_the_ceilings_is_untouched_by_them() -> None:
    """The ceilings are set far above any real IR: a document an order of magnitude larger
    than the whole vendored corpus still loads."""
    nodes = [{"id": f"n{index}", "annotations": {"input": [f"k{index}"]}} for index in range(500)]
    payload = minimal_payload(entry="n0", finish="n0", nodes=nodes)
    ir = load_json(WorkflowIR, json.dumps(payload))
    assert len(ir.nodes) == 500
    assert load_yaml(WorkflowIR, dump_yaml(ir)) == ir


def test_a_fault_in_the_document_root_is_reported_as_the_document() -> None:
    """A whole-document fault has no member path to name, so the message says so."""
    with pytest.raises(IRSerializationError) as refused:
        load_yaml(WorkflowIR, ".nan\n")
    assert refused.value.reason is IRSerializationErrorReason.NON_FINITE_NUMBER
    assert refused.value.path == ()
    assert "the document is nan" in str(refused.value)


def test_a_yaml_scalar_with_no_json_form_is_refused() -> None:
    """An unquoted date is a ``datetime.date`` after ``safe_load``. JSON has no date, and
    turning it into text would be this loader inventing content."""
    source = MINIMAL_YAML.replace(
        "  - id: only",
        "  - id: only\n    annotations: {args_schema: {released: 2026-07-30}}",
    )
    with pytest.raises(IRSerializationError) as refused:
        load_yaml(WorkflowIR, source)
    assert refused.value.reason is IRSerializationErrorReason.UNSUPPORTED_TYPE
    assert "date" in str(refused.value)


def test_a_recursive_anchor_is_refused_by_name() -> None:
    """A YAML anchor may refer to its own container. JSON is a tree, so the re-encoding says
    so — rather than recursing until the interpreter gives up."""
    source = MINIMAL_YAML.replace(
        "  - id: only",
        "  - id: only\n    annotations: {args_schema: &loop {self: *loop}}",
    )
    with pytest.raises(IRSerializationError) as refused:
        load_yaml(WorkflowIR, source)
    assert refused.value.reason is IRSerializationErrorReason.CIRCULAR_REFERENCE


def test_a_non_recursive_anchor_is_ordinary_shared_content() -> None:
    """Sharing is not recursion: the same anchor used twice is two equal members."""
    source = MINIMAL_YAML.replace(
        "  - id: only",
        "  - id: only\n    annotations: {args_schema: {a: &shape {type: string}, b: *shape}}",
    )
    ir = load_yaml(WorkflowIR, source)
    assert ir.nodes[0].annotations is not None
    assert ir.nodes[0].annotations.args_schema == {"a": {"type": "string"}, "b": {"type": "string"}}
    assert load_yaml(WorkflowIR, dump_yaml(ir)) == ir


def test_the_error_carries_a_reason_a_path_and_the_value() -> None:
    """Consumers branch on the code, not on message text."""
    with pytest.raises(IRSerializationError) as refused:
        load_yaml(WorkflowIR, "!!python/name:os.system {}")
    error = refused.value
    assert isinstance(error, ValueError)
    assert isinstance(error.reason, IRSerializationErrorReason)
    assert error.reason.value == "yaml-syntax"


#: The P-01 rows of the PROPERTY-CATALOG-SPEC §0.4 condition-ID registry, transcribed only
#: to keep the reason vocabulary disjoint from it (the pin test_identity and test_canonical
#: both carry). P-01's rows are the ones a document-shaped fault could plausibly collide
#: with; the WA-08 pre-review checked the six codes against the whole catalog.
P01_CONDITION_IDS = (
    "node-unreachable-from-start",
    "dead-end-node-not-wired-to-end",
    "path-map-target-undefined",
    "orphan-node",
    "edge-target-undefined",
)


def test_the_reason_codes_are_not_condition_ids() -> None:
    """These are IR-validity codes: no verification envelope reports one, and the §0.4
    registry neither contains nor needs them."""
    reasons = {reason.value for reason in IRSerializationErrorReason}
    assert reasons.isdisjoint(P01_CONDITION_IDS)


# ── WA-07: the loader is not an execution path ───────────────────────────────────────────


@pytest.mark.parametrize(
    "tag",
    [
        "!!python/object/apply:os.system ['exit 1']",
        "!!python/name:os.system {}",
        "!!python/module:this {}",
        "!!python/object:tests.sample_workflows.sentinel_graph.SentinelExecutedError {}",
    ],
)
def test_the_yaml_loader_refuses_python_object_tags(tag: str) -> None:
    """Only PyYAML's safe constructor set parses here, so no document can name a callable, a
    module or a class and have it constructed (WA-07).

    ``!!python/name:os.system`` is the discriminating row: it is the one tag that even
    PyYAML's *FullLoader* constructs, so this case fails if the parser is ever widened,
    while the others are refused by both and only pin the current behavior.
    """
    with pytest.raises(IRSerializationError) as refused:
        load_yaml(WorkflowIR, tag)
    assert refused.value.reason is IRSerializationErrorReason.YAML_SYNTAX


def test_loading_never_imports_a_module_named_in_the_document() -> None:
    """A side-effect tripwire rather than a return-value one: ``this`` prints on import, so
    an unsafe-loader regression is caught by the import having happened, whether or not the
    document's value came back.

    It does not subsume the previous test: PyYAML's FullLoader resolves only modules already
    imported, so a widening to *that* loader would leave ``sys.modules`` untouched and be
    caught by ``!!python/name:os.system`` above instead.
    """
    assert "this" not in sys.modules
    for text in ("!!python/module:this {}", "!!python/name:this.c {}"):
        with pytest.raises(IRSerializationError):
            load_yaml(WorkflowIR, text)
    assert "this" not in sys.modules


def test_the_ir_loader_is_a_private_subclass_of_the_safe_loader() -> None:
    """``yaml.safe_load`` uses the process-wide ``SafeLoader``, whose constructor table any
    library in the same interpreter can add to. This package's ingestion semantics are its
    own: the subclass snapshots the safe tables, and nothing is registered on it."""
    from gebra.ir.serialization import _surface_loader

    loader = _surface_loader()
    assert issubclass(loader, yaml.SafeLoader)
    assert loader is not yaml.SafeLoader
    # Its own tables, not the inherited ones — a bare subclass would still see later edits.
    assert "yaml_constructors" in loader.__dict__
    assert loader.yaml_constructors == yaml.SafeLoader.yaml_constructors


def test_a_tag_registered_on_the_global_safe_loader_never_reaches_the_ir_loader() -> None:
    """The hazard in one test: a third party registering an ``!include``-shaped constructor
    would otherwise change what a gebra document means — and such constructors open files
    named *in the document* (WA-07)."""
    load_yaml(WorkflowIR, MINIMAL_YAML)  # the loader's tables snapshot on first use

    def construct(loader: object, node: object) -> str:  # pragma: no cover - never called
        raise AssertionError("a foreign constructor ran inside the IR loader")

    yaml.SafeLoader.add_constructor("!injected", construct)
    try:
        assert "!injected" in yaml.SafeLoader.yaml_constructors
        with pytest.raises(IRSerializationError) as refused:
            load_yaml(WorkflowIR, "!injected {}")
        assert refused.value.reason is IRSerializationErrorReason.YAML_SYNTAX
    finally:
        del yaml.SafeLoader.yaml_constructors["!injected"]


def test_the_yaml_dumper_is_still_the_safe_dumper() -> None:
    """The one thing corrected in the dumper is a string's quoting style; it stays a
    ``SafeDumper`` subclass, so no Python object can be *written* as a tag either."""
    from gebra.ir.serialization import _surface_dumper

    dumper = _surface_dumper()
    assert issubclass(dumper, yaml.SafeDumper)
    with pytest.raises(yaml.YAMLError):
        yaml.dump(object(), Dumper=dumper)


def test_dumping_never_runs_foreign_code() -> None:
    """``args_schema`` is ``Any``-typed, so a Python-constructed model can hold an arbitrary
    object. It is named by type and refused; none of its own code runs (the discipline
    canonicalization's foreign walk follows).

    ``__getattr__`` traps the whole explicit-attribute surface rather than three names, so
    a probe for ``keys``, ``items``, ``read`` or anything else is caught too.
    """
    tripped: list[str] = []

    class Hostile:
        def __getattr__(self, name: str) -> object:
            tripped.append(name)
            raise AttributeError(name)

        def __str__(self) -> str:
            tripped.append("__str__")
            return "escaped"

        def __repr__(self) -> str:
            tripped.append("__repr__")
            return "escaped"

    model = Annotations(args_schema={"schema": Hostile()})
    for dump in (dump_json, dump_yaml):
        with pytest.raises(IRSerializationError) as refused:
            dump(model)
        assert refused.value.reason is IRSerializationErrorReason.UNSUPPORTED_TYPE
    assert "Hostile" in str(refused.value)
    # Pydantic's serializer asks the value whether it is a model or a dataclass before this
    # module's walk ever sees it; those two probes are its own. Nothing else is touched — no
    # ``__str__``, no ``__repr__``, and nothing an ordinary duck-typing walk reaches for.
    assert set(tripped) == {"__pydantic_serializer__", "__dataclass_fields__"}


def test_a_hostile_mapping_key_is_named_not_rendered() -> None:
    """The same discipline on the key side: a non-string key is described by type."""
    tripped: list[str] = []

    class HostileKey:
        def __hash__(self) -> int:
            return 0

        def __repr__(self) -> str:  # pragma: no cover - calling this is the failure
            tripped.append("__repr__")
            return "escaped"

    model = Annotations(args_schema={"schema": {HostileKey(): "x"}})
    with pytest.raises(IRSerializationError) as refused:
        dump_json(model)
    assert refused.value.reason is IRSerializationErrorReason.NON_STRING_KEY
    assert "HostileKey" in str(refused.value)
    assert tripped == []


def test_a_string_subclass_never_reaches_the_surface_as_itself() -> None:
    """Foreign scalars are copied through their exact built-in accessor, so a subclass with
    an overridden ``__str__`` cannot change what is written."""

    class Sneaky(str):
        def __str__(self) -> str:  # pragma: no cover - calling this is the failure
            return "replaced"

    model = Annotations(args_schema={"title": Sneaky("original")})
    assert '"title": "original"' in dump_json(model)


# ── PyYAML is imported on use ────────────────────────────────────────────────────────────


def test_the_json_half_needs_no_yaml(monkeypatch: pytest.MonkeyPatch) -> None:
    """JSON loading and dumping work in an environment without PyYAML."""
    monkeypatch.setitem(sys.modules, "yaml", None)
    ir = load_json(WorkflowIR, json.dumps(minimal_payload()))
    assert load_json(WorkflowIR, dump_json(ir)) == ir


def test_a_missing_pyyaml_names_the_fix(monkeypatch: pytest.MonkeyPatch) -> None:
    """The YAML half fails with one actionable sentence, at the call rather than at import."""
    monkeypatch.setitem(sys.modules, "yaml", None)
    ir = load_json(WorkflowIR, json.dumps(minimal_payload()))
    for call in (lambda: load_yaml(WorkflowIR, MINIMAL_YAML), lambda: dump_yaml(ir)):
        with pytest.raises(ImportError, match="requires PyYAML"):
            call()
