"""Behaviour tests for the hermetic fixture loader (``gebra.testing.fixtures``).

Two duties are exercised here. Against the **live vendored corpus**: every fixture loads,
every IR block is an ``ir_version`` 1.0 model, and the ``expected:`` blocks that compose into
a PROPERTY-CATALOG-SPEC §0.3 ``PropertyReport`` are exactly the ones the corpus carries in
ratified shape today — pinned, so that a corpus revision in either direction shows up as a diff
rather than silently. Against **temporary documents**: each refusal the loader promises,
including the four things PyYAML's safe constructor set admits and JSON does not.

The vendored corpus is a read-only contract surface (WA-04/WA-11). Nothing here writes to it:
every malformed document is authored under ``tmp_path``.

Nothing here executes a workflow node, calls a model, or opens a socket (WA-07);
``source_snippet`` is asserted inert rather than assumed so — see
``tests/testing/test_hermeticity.py`` for the load path's own tripwire.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest
import yaml

from gebra.ir import IR_VERSION, WorkflowIR
from gebra.testing import (
    FixtureError,
    FixtureErrorReason,
    PropertyFixture,
    fixture_from_document,
    iter_fixture_paths,
    load_corpus,
    load_fixture,
    load_fixture_document,
    yaml_loader,
)
from gebra.verify import PropertyReport, to_data, validate_report
from tests.conftest import FIXTURES_DIR

#: The corpus README's grand total, and the block count the seven evolution pairs imply.
CORPUS_SIZE = 60
IR_BLOCK_COUNT = 67
EVOLUTION_PAIRS = 7

#: Every fixture whose ``expected:`` block composes into a §0.3 ``PropertyReport`` today.
#:
#: This is the same ledger ``tests/verify/test_pc6_dual_duty.py`` keeps from the envelope's
#: side, extended with the three ``mixed/`` fixtures whose owning property that module could
#: not derive ("deriving it from the primary condition ID needs the §0.4 registry, which is
#: its own card") — the registry has since landed, and the loader derives it. Asserted
#: exactly: a fixture that starts composing, or stops, is a corpus or envelope change that
#: must be seen rather than absorbed.
#:
#: It grew 25 → 33 when the corpus reconciliation pass landed (DEC-17, vault ``b2056e9``): the
#: eight wedge negatives whose ``location`` blocks predated their §P-nn.3 subtypes now compose,
#: which is what makes all thirty wedge-directory fixtures composable.
COMPOSING = (
    "dataflow-completeness/negative-01-express-path-skips-writer.yaml",
    "dataflow-completeness/negative-02-writer-downstream-of-reader.yaml",
    "dataflow-completeness/negative-03-fan-in-missing-branch-writer.yaml",
    "dataflow-completeness/positive-01-linear-itinerary-pipeline.yaml",
    "dataflow-completeness/positive-02-conditional-both-branches-write.yaml",
    "dataflow-completeness/positive-03-parallel-fanout-reduced-results.yaml",
    "determinism-replay/negative-01-seedless-deterministic-llm-classifier.yaml",
    "determinism-replay/negative-02-seeded-llm-extractor-hot-temperature.yaml",
    "determinism-replay/positive-01-pinned-seed-zero-temp-classifier.yaml",
    "determinism-replay/positive-02-pure-fare-normalizer.yaml",
    "effect-safety/negative-01-billable-in-unguarded-retry.yaml",
    "effect-safety/negative-02-irreversible-in-refinement-cycle.yaml",
    "effect-safety/negative-03-keyless-idempotent-on-irreversible.yaml",
    "effect-safety/positive-01-keyed-idempotent-billable-retry.yaml",
    "effect-safety/positive-02-irreversible-outside-cycle.yaml",
    "effect-safety/positive-03-compensated-billable-hold-loop.yaml",
    "graph-well-formed/negative-01-unreachable-escalation-node.yaml",
    "graph-well-formed/negative-02-dead-end-review-branch.yaml",
    "graph-well-formed/negative-03-path-map-typo-dangling-target.yaml",
    "graph-well-formed/positive-01-linear-document-pipeline.yaml",
    "graph-well-formed/positive-02-support-triage-branching.yaml",
    "graph-well-formed/positive-03-travel-parent-graph-with-booking-subgraph.yaml",
    "mixed/02-unwitnessed-loop-reading-unwritten-key.yaml",
    "mixed/04-dangling-path-map-target-orphans-downstream-reader.yaml",
    "mixed/08-express-path-skips-gate-writer-and-witnessed-exit.yaml",
    "termination-witness/negative-01-unwitnessed-reflection-loop.yaml",
    "termination-witness/negative-02-nested-scc-outer-only-witness.yaml",
    "termination-witness/negative-03-counter-guard-without-wired-exit.yaml",
    "termination-witness/negative-04-supervisor-delegation-scc-no-witness.yaml",
    "termination-witness/positive-01-counter-guarded-retry-loop.yaml",
    "termination-witness/positive-02-justified-recursion-limit-refinement-loop.yaml",
    "termination-witness/positive-03-shrinking-worklist-hotel-quotes.yaml",
    "termination-witness/positive-04-nested-scc-dual-counter-witnesses.yaml",
)

#: A well-formed single-node fixture — the smallest document that satisfies both contracts.
#: Deep-copied per use so a mutation in one test cannot reach another.
MINIMAL: dict[str, Any] = {
    "property": "graph-well-formed",
    "polarity": "positive",
    "description": "A single-node graph, the smallest document that satisfies both contracts.",
    "ir": {
        "ir_version": IR_VERSION,
        "entry": "only_node",
        "finish": "only_node",
        "nodes": [{"id": "only_node"}],
        "edges": [],
    },
    "expected": {
        "result": "pass",
        "witness": {
            "kind": "well-formedness",
            "reachable_from_start": ["only_node"],
            "terminal_nodes": ["only_node"],
            "orphan_nodes": [],
            "unresolved_targets": [],
        },
    },
}


@pytest.fixture(scope="module")
def corpus() -> tuple[PropertyFixture, ...]:
    return load_corpus(FIXTURES_DIR)


def _write(tmp_path: Path, document: object, name: str = "positive-01-loader-probe.yaml") -> Path:
    path = tmp_path / name
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return path


def _minimal(**overrides: Any) -> dict[str, Any]:
    document = copy.deepcopy(MINIMAL)
    document.update(overrides)
    return document


# ── The live corpus ──────────────────────────────────────────────────────────────────────


def test_every_vendored_fixture_loads(corpus: tuple[PropertyFixture, ...]) -> None:
    """All 60 fixtures become models — the card's first acceptance, on the IR side."""
    assert len(corpus) == CORPUS_SIZE
    for fixture in corpus:
        assert fixture.irs, f"{fixture.fixture_id}: no IR block loaded"
        for ir in fixture.irs:
            assert isinstance(ir, WorkflowIR)
            assert ir.ir_version == IR_VERSION


def test_the_corpus_carries_the_expected_block_count(corpus: tuple[PropertyFixture, ...]) -> None:
    """60 fixtures, 67 IR blocks: 53 single-snapshot plus 7 evolution pairs."""
    assert sum(len(fixture.irs) for fixture in corpus) == IR_BLOCK_COUNT
    pairs = [fixture for fixture in corpus if fixture.is_pair]
    assert len(pairs) == EVOLUTION_PAIRS
    for fixture in pairs:
        assert fixture.ir is None
        assert isinstance(fixture.ir_before, WorkflowIR)
        assert isinstance(fixture.ir_after, WorkflowIR)
        assert "evolution-safety" in fixture.properties


def test_mixed_fixtures_declare_several_properties(corpus: tuple[PropertyFixture, ...]) -> None:
    """``mixed/`` is the cross-property directory, and nothing else is (README Layout)."""
    for fixture in corpus:
        assert fixture.is_mixed == (fixture.directory == "mixed")
        if not fixture.is_mixed:
            assert fixture.properties == (fixture.directory,)


def test_polarity_and_expected_result_agree(corpus: tuple[PropertyFixture, ...]) -> None:
    """A positive fixture expects a pass and a negative one a fail (schema.yaml ``polarity``)."""
    for fixture in corpus:
        assert (fixture.polarity == "positive") == (fixture.result == "pass")


def test_fixture_id_is_the_corpus_relative_spelling(corpus: tuple[PropertyFixture, ...]) -> None:
    """The ``"<directory>/<file>.yaml"`` form the specs and the fidelity matrix use."""
    for fixture in corpus:
        assert fixture.fixture_id == fixture.path.relative_to(FIXTURES_DIR).as_posix()


def test_iter_fixture_paths_is_sorted_and_excludes_the_schema() -> None:
    paths = iter_fixture_paths(FIXTURES_DIR)
    assert list(paths) == sorted(paths)
    assert all(path.name != "schema.yaml" for path in paths)
    assert len(paths) == CORPUS_SIZE


# ── PC-6: the ``expected:`` block and a validator's output are one model ─────────────────


def test_the_composing_set_is_exactly_what_the_corpus_carries_today(
    corpus: tuple[PropertyFixture, ...],
) -> None:
    """The live ledger of what composes, asserted rather than assumed.

    Every fixture that does not compose is one the frozen specs themselves carry as pending,
    under one of three headings:

    1. the eight non-wedge properties' witness shapes, "provisional until their catalog
       sections are drafted" (schema.yaml), and their findings' location shapes;
    2. P-03's three condition IDs, which §0.4 deliberately holds back (DEC-05 D6);
    3. ``mixed/10``'s all-pass block, a run-level wrapper §0.3's scope boundary assigns to
       REPORT-FORMAT-SPEC — not a defect at all.

    A fourth heading has been retired: the wedge negatives (P-04 ×3, P-06 ×3, P-08 ×2) whose
    ``location`` block predated its §P-nn.3 discriminated subtype, which §0.3's *Location
    evidence fields* note sent to "a single corpus pass". That pass landed as DEC-17 and those
    eight now compose, which is what makes all thirty wedge-directory fixtures composable —
    worth naming, because "everything pending is non-wedge" was the convenient summary and it
    was *not* true before. Reconciling 1–2 needs their catalog sections and routes vault-first
    (WA-04) — never a fixture edit here, and never a model relaxed to accommodate a block.
    """
    composing = []
    for fixture in corpus:
        try:
            fixture.expected_report()
        except FixtureError:
            continue
        composing.append(fixture.fixture_id)
    assert tuple(composing) == COMPOSING


def test_expected_report_is_the_section_0_3_composition() -> None:
    """§0.3: ``PropertyReport.model_validate({"property": …, **fixture["expected"]})``."""
    relative = "graph-well-formed/positive-01-linear-document-pipeline.yaml"
    fixture = load_fixture(FIXTURES_DIR / relative)
    document = load_fixture_document(FIXTURES_DIR / relative)
    composed = fixture.expected_report()
    assert composed == validate_report({"property": document["property"], **document["expected"]})
    assert composed.property == "graph-well-formed"
    assert composed.result == "pass"
    assert composed.witness is not None


def test_every_composing_report_round_trips_through_the_pc4_profile(
    corpus: tuple[PropertyFixture, ...],
) -> None:
    """A loaded report re-validates from its own serialization, unchanged (A6 PC-4)."""
    for fixture in corpus:
        if fixture.fixture_id not in COMPOSING:
            continue
        report = fixture.expected_report()
        assert isinstance(report, PropertyReport)
        assert validate_report(to_data(report)) == report


def test_a_mixed_fixture_resolves_its_owning_property_through_the_registry() -> None:
    """A cross-property fixture's owning slug comes off the §0.4 registry, not the document."""
    relative = "mixed/04-dangling-path-map-target-orphans-downstream-reader.yaml"
    fixture = load_fixture(FIXTURES_DIR / relative)
    assert fixture.properties == ("graph-well-formed", "dataflow-completeness")
    assert fixture.owning_property == "graph-well-formed"
    assert fixture.expected_report().property == "graph-well-formed"


def test_a_passing_mixed_fixture_has_no_single_owning_property() -> None:
    """``mixed/10``'s all-pass block is a run-level wrapper — REPORT-FORMAT-SPEC's, not §0.3's."""
    fixture = load_fixture(
        FIXTURES_DIR / "mixed/10-all-properties-pass-healthy-research-pipeline.yaml"
    )
    with pytest.raises(FixtureError) as caught:
        fixture.expected_report()
    assert caught.value.reason is FixtureErrorReason.UNRESOLVED_PROPERTY


def test_an_unregistered_primary_condition_has_no_owning_property() -> None:
    """``mixed/07``'s primary is one of P-03's three strings §0.4 holds back (DEC-05 D6)."""
    fixture = load_fixture(
        FIXTURES_DIR / "mixed/07-subgraph-leaked-key-collides-with-parallel-sibling.yaml"
    )
    failure = fixture.expected_failure
    assert failure is not None
    assert failure["property_condition"] == "write-key-not-in-state-schema"
    with pytest.raises(FixtureError) as caught:
        _ = fixture.owning_property
    assert caught.value.reason is FixtureErrorReason.UNRESOLVED_PROPERTY


def test_a_condition_held_for_an_undeclared_property_is_refused(tmp_path: Path) -> None:
    """§0.4 holds each name for one property; a fixture may not borrow another's."""
    document = _minimal(
        property=["graph-well-formed", "determinism-replay"],
        polarity="negative",
        expected={
            "result": "fail",
            "failure": {
                "property_condition": "unprotected-effect-in-cycle",
                "location": {"kind": "node", "node": "only_node"},
                "severity": "error",
                "claim_class": "defensible-a",
            },
        },
    )
    path = _write(tmp_path, document, name="01-borrowed-condition.yaml")
    with pytest.raises(FixtureError) as caught:
        load_fixture(path).expected_report()
    assert caught.value.reason is FixtureErrorReason.UNRESOLVED_PROPERTY
    assert "effect-safety" in str(caught.value)


def test_the_expected_sub_block_accessors_read_the_parsed_document(tmp_path: Path) -> None:
    fixture = load_fixture(_write(tmp_path, _minimal()))
    witness = fixture.expected_witness
    assert witness is not None
    assert witness["kind"] == "well-formedness"
    assert fixture.expected_failure is None


def test_a_pending_witness_shape_is_reported_not_absorbed() -> None:
    """A non-wedge witness ``kind`` is an ``expected-invalid``, never a relaxed model."""
    fixture = load_fixture(
        FIXTURES_DIR / "signature-soundness/positive-01-linear-booking-declared-io.yaml"
    )
    with pytest.raises(FixtureError) as caught:
        fixture.expected_report()
    assert caught.value.reason is FixtureErrorReason.EXPECTED_INVALID
    assert caught.value.key == "expected"
    assert "witness" in str(caught.value)


# ── Refusals: the document faults the loader promises to name ────────────────────────────


def test_a_document_that_is_not_a_mapping_is_refused(tmp_path: Path) -> None:
    path = _write(tmp_path, ["not", "a", "fixture"])
    with pytest.raises(FixtureError) as caught:
        load_fixture(path)
    assert caught.value.reason is FixtureErrorReason.NOT_A_MAPPING


def test_a_yaml_syntax_error_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "positive-01-broken.yaml"
    path.write_text("property: [unclosed\n", encoding="utf-8")
    with pytest.raises(FixtureError) as caught:
        load_fixture(path)
    assert caught.value.reason is FixtureErrorReason.YAML_SYNTAX


def test_a_non_string_mapping_key_is_refused_rather_than_coerced(tmp_path: Path) -> None:
    """``{1: "str"}`` inside ``state`` would become ``{"1": "str"}`` under ``json.dumps``."""
    document = _minimal()
    document["ir"]["state"] = {1: "str"}
    path = _write(tmp_path, document)
    with pytest.raises(FixtureError) as caught:
        load_fixture(path)
    assert caught.value.reason is FixtureErrorReason.NON_JSON_VALUE
    assert "non-string key" in str(caught.value)


def test_a_yaml_timestamp_is_refused(tmp_path: Path) -> None:
    """A YAML scalar JSON has no form for is named, not silently stringified."""
    path = tmp_path / "positive-01-timestamp.yaml"
    path.write_text(
        yaml.safe_dump(_minimal(), sort_keys=False) + "notes: 2026-07-31\n", encoding="utf-8"
    )
    with pytest.raises(FixtureError) as caught:
        load_fixture(path)
    assert caught.value.reason is FixtureErrorReason.NON_JSON_VALUE


def test_a_recursive_anchor_is_refused(tmp_path: Path) -> None:
    """A JSON document is a tree; a self-referential anchor cannot be re-encoded."""
    path = tmp_path / "positive-01-recursive.yaml"
    path.write_text("&loop\nproperty: graph-well-formed\nnotes: *loop\n", encoding="utf-8")
    with pytest.raises(FixtureError) as caught:
        load_fixture(path)
    assert caught.value.reason is FixtureErrorReason.NON_JSON_VALUE


def test_an_alias_bomb_is_refused_before_it_expands(tmp_path: Path) -> None:
    """A YAML alias is one shared object when parsed and a full copy once re-encoded.

    The classic "billion laughs" document is a few hundred bytes and expands past every
    ceiling on the way to JSON, so the walk is budgeted rather than trusting the file size.
    """
    levels = ["a: &a [x, x, x, x, x, x, x, x, x]"]
    for index in range(1, 7):
        previous, current = chr(ord("a") + index - 1), chr(ord("a") + index)
        levels.append(f"{current}: &{current} [" + ", ".join([f"*{previous}"] * 9) + "]")
    path = tmp_path / "positive-01-alias-bomb.yaml"
    path.write_text("\n".join(levels) + "\n", encoding="utf-8")
    with pytest.raises(FixtureError) as caught:
        load_fixture(path)
    assert caught.value.reason is FixtureErrorReason.NON_JSON_VALUE
    assert "expands to more than" in str(caught.value)


def test_a_document_nested_past_the_ceiling_is_refused(tmp_path: Path) -> None:
    """Deeper than any fixture, and shallower than the RecursionError it would otherwise be."""
    path = tmp_path / "positive-01-deep.yaml"
    path.write_text(
        "property: graph-well-formed\nir: " + "{a: " * 120 + "1" + "}" * 120 + "\n",
        encoding="utf-8",
    )
    with pytest.raises(FixtureError) as caught:
        load_fixture(path)
    assert caught.value.reason is FixtureErrorReason.NON_JSON_VALUE
    assert "levels deep" in str(caught.value)


def test_a_refusal_names_where_in_the_document_it_sits(tmp_path: Path) -> None:
    """The position is rendered in authored shape — member names and array indexes."""
    document = _minimal()
    document["ir"]["nodes"][0]["annotations"] = {"args_schema": {"properties": {1: "x"}}}
    path = _write(tmp_path, document)
    with pytest.raises(FixtureError) as caught:
        load_fixture(path)
    assert caught.value.key == "ir.nodes[0].annotations.args_schema.properties"


def test_a_non_finite_number_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "positive-01-nan.yaml"
    path.write_text(yaml.safe_dump(_minimal(), sort_keys=False) + "notes: .nan\n", encoding="utf-8")
    with pytest.raises(FixtureError) as caught:
        load_fixture(path)
    assert caught.value.reason is FixtureErrorReason.NON_JSON_VALUE


@pytest.mark.parametrize(
    "mutation",
    [
        pytest.param({"ir_before": {}, "ir_after": {}}, id="all-three"),
        pytest.param({"ir": None}, id="none"),
    ],
)
def test_only_one_ir_shape_is_admitted(tmp_path: Path, mutation: dict[str, Any]) -> None:
    document = _minimal()
    for key, value in mutation.items():
        if value is None:
            del document[key]
        else:
            document[key] = value
    path = _write(tmp_path, document)
    with pytest.raises(FixtureError) as caught:
        load_fixture(path)
    assert caught.value.reason is FixtureErrorReason.IR_SHAPE


def test_an_ir_block_that_is_not_1_0_is_refused(tmp_path: Path) -> None:
    document = _minimal()
    document["ir"]["ir_version"] = "0.1"
    path = _write(tmp_path, document)
    with pytest.raises(FixtureError) as caught:
        load_fixture(path)
    assert caught.value.reason is FixtureErrorReason.IR_INVALID
    assert caught.value.key == "ir"


def test_an_ir_block_with_an_unknown_member_is_refused(tmp_path: Path) -> None:
    """``WorkflowIR`` is ``extra="forbid"``, which is how "conforms to schema.yaml" is spelled."""
    document = _minimal()
    document["ir"]["invented_member"] = True
    path = _write(tmp_path, document)
    with pytest.raises(FixtureError) as caught:
        load_fixture(path)
    assert caught.value.reason is FixtureErrorReason.IR_INVALID


@pytest.mark.parametrize("key", ["property", "polarity", "description", "expected"])
def test_a_missing_required_member_is_refused(tmp_path: Path, key: str) -> None:
    document = _minimal()
    del document[key]
    path = _write(tmp_path, document)
    with pytest.raises(FixtureError) as caught:
        load_fixture(path)
    assert caught.value.reason is FixtureErrorReason.MISSING_KEY
    assert caught.value.key == key


@pytest.mark.parametrize(
    ("overrides", "key"),
    [
        pytest.param({"property": "not-a-catalog-property"}, "property", id="slug"),
        pytest.param({"property": [17]}, "property", id="slug-type"),
        pytest.param({"property": []}, "property", id="slug-empty"),
        pytest.param({"polarity": "sideways"}, "polarity", id="polarity"),
        pytest.param({"description": 17}, "description", id="description"),
        pytest.param({"axiom_basis": "transitivity"}, "axiom_basis", id="axiom-basis"),
        pytest.param({"notes": ["a", "list"]}, "notes", id="notes"),
    ],
)
def test_a_malformed_member_is_refused(tmp_path: Path, overrides: dict[str, Any], key: str) -> None:
    path = _write(tmp_path, _minimal(**overrides))
    with pytest.raises(FixtureError) as caught:
        load_fixture(path)
    assert caught.value.reason is FixtureErrorReason.MALFORMED_KEY
    assert caught.value.key == key


def test_an_expected_block_without_a_result_is_refused(tmp_path: Path) -> None:
    path = _write(tmp_path, _minimal(expected={"witness": {"kind": "well-formedness"}}))
    with pytest.raises(FixtureError) as caught:
        load_fixture(path)
    assert caught.value.reason is FixtureErrorReason.MISSING_KEY
    assert caught.value.key == "expected.result"


def test_an_expected_result_outside_the_enum_is_refused(tmp_path: Path) -> None:
    path = _write(tmp_path, _minimal(expected={"result": "maybe"}))
    with pytest.raises(FixtureError) as caught:
        load_fixture(path)
    assert caught.value.reason is FixtureErrorReason.MALFORMED_KEY


# ── Hermeticity of the parse itself ──────────────────────────────────────────────────────


def test_source_snippet_is_carried_inert(tmp_path: Path) -> None:
    """schema.yaml: "NEVER executed — documentation for human readers only"."""
    snippet = "raise SystemExit('a fixture loader must never run this')\n"
    path = _write(tmp_path, _minimal(source_snippet=snippet))
    fixture = load_fixture(path)
    assert fixture.source_snippet == snippet
    assert isinstance(fixture.source_snippet, str)


def test_the_process_wide_safe_loader_cannot_change_what_a_fixture_means(tmp_path: Path) -> None:
    """A tag registered on ``yaml.SafeLoader`` after the snapshot never reaches a fixture.

    ``yaml.safe_load`` uses the shared ``SafeLoader``, and ``add_constructor`` mutates it
    process-wide. Fixtures parse through a private subclass whose constructor tables are
    snapshotted, so a document that would mean something else under a mutated ``SafeLoader``
    is still refused here.

    The snapshot is taken on the first call to :func:`~gebra.testing.yaml_loader`, so this
    warms it *before* registering the tag — which is exactly the guarantee the loader
    documents, stated in the order it holds. Warming first also makes the test deterministic
    in isolation: registered first, the tag would be inherited into the snapshot and the
    hostile document would parse.
    """

    def _explode(loader: object, node: object) -> str:  # pragma: no cover - never reached
        return "injected"

    yaml_loader()
    path = _write(tmp_path, _minimal(notes="!injected placeholder"))
    yaml.SafeLoader.add_constructor("!injected", _explode)
    try:
        assert "!injected" not in yaml_loader().yaml_constructors
        assert load_fixture(path).notes == "!injected placeholder"
        hostile = tmp_path / "positive-02-tagged.yaml"
        hostile.write_text(
            yaml.safe_dump(_minimal(), sort_keys=False) + "notes: !injected x\n", encoding="utf-8"
        )
        with pytest.raises(FixtureError) as caught:
            load_fixture(hostile)
        assert caught.value.reason is FixtureErrorReason.YAML_SYNTAX
    finally:
        del yaml.SafeLoader.yaml_constructors["!injected"]


def test_the_hardened_loader_is_not_the_shared_safe_loader() -> None:
    """The parser fixtures and the vendored schema both go through, in one place."""
    loader = yaml_loader()
    assert loader is not yaml.SafeLoader
    assert issubclass(loader, yaml.SafeLoader)
    # Snapshotted, not inherited: mutating the shared tables must not reach these.
    assert loader.yaml_constructors is not yaml.SafeLoader.yaml_constructors
    assert loader.yaml_multi_constructors is not yaml.SafeLoader.yaml_multi_constructors


def test_fixture_from_document_reads_nothing_from_disk(tmp_path: Path) -> None:
    """The parse and the model build are separable — the lint depends on it."""
    fixture = fixture_from_document(_minimal(), tmp_path / "mixed" / "01-never-written.yaml")
    assert not (tmp_path / "mixed").exists()
    assert fixture.fixture_id == "mixed/01-never-written.yaml"
    assert fixture.directory == "mixed"
