"""``runtime.recursion_limit`` at extraction: the two declaration tiers, the binding, the default.

Normative authority: ANNOTATION-API-SPEC §1a, §2, §3, §4, §6 and INTROSPECTION-SPEC §3, §4.1,
§7.1, §8, as DEC-36 re-vendored them (ratified 2026-10-28; PD-064); IR-SPEC §3.5 for the slot;
TERMINATION-WITNESS-SPEC §2.2/§2.4 and PROPERTY-CATALOG-SPEC §P-02 for what P-02 reads off it.

Six claims, one section each. **The surfaces fill the slot** — the graph-level declaration and
the sidecar's ``[runtime]`` table, on the builder, builder-primary compiled and compiled-only
paths, with builder/compiled parity. **The ladder**, pinned by one test per source pair:
graph-level over sidecar, and a binding that corroborates, conflicts or is disclosed and never
fills the slot. **What is rejected** stays absent and warned. **The default is never read.**
**Nothing moves for a source that declares nothing**, and P-02 reads the slot end to end. And
**nothing is invoked**: every read is an instance-dictionary read, pinned against carriers whose
properties, ``__getattribute__``, planted dictionaries, planted keys and values record every call
with the module that made it — and, in a fresh interpreter, under the guard the other extraction
paths use.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import types
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from langchain_core.runnables import RunnableLambda
from langgraph.graph.state import StateGraph
from langgraph.pregel import Pregel
from pydantic import ValidationError

import gebra
from gebra.extraction import (
    BindingOutcome,
    CompiledSurfaces,
    ExtractionDisclosureCode,
    ExtractionEnvelope,
    ExtractionWarningCode,
    RecursionLimitBinding,
    extract,
    to_json,
)
from gebra.extraction.disclosures import (
    DECLARATION_SURFACES,
    NO_WITNESS_FROM_A_BINDING,
    recursion_limit_binding_disclosure,
)
from gebra.ir.models import RecursionLimit
from gebra.verify import PropertyReport, TerminationWitness, run_property, verify
from tests.sample_workflows import sentinel_graph as sg
from tests.sample_workflows import sentinel_runtime as sr
from tests.sample_workflows import sentinel_subgraphs as ss

REPO_ROOT = Path(__file__).resolve().parents[2]

DECLARED = RecursionLimit(value=sr.LIMIT, justification=sr.JUSTIFICATION)
IN_SIDECAR = RecursionLimit(value=sr.SIDECAR_LIMIT, justification=sr.SIDECAR_JUSTIFICATION)

BOUND_ALONE = ExtractionDisclosureCode.RECURSION_LIMIT_BOUND_WITHOUT_JUSTIFICATION


@pytest.fixture(autouse=True)
def _clear_ledgers() -> Iterator[None]:
    """Every test starts with empty ledgers and ends with no sentinel fired and no record
    triggered by anything but the substrate's own drawing."""
    sg.TRIPPED.clear()
    sr.HOOKS.clear()
    sr.CARRIER_READS.clear()
    yield
    assert sg.TRIPPED == [], sg.TRIPPED
    assert sr.outside_the_substrate(sr.HOOKS) == [], sr.HOOKS
    assert sr.outside_the_substrate(sr.CARRIER_READS) == [], sr.CARRIER_READS


@pytest.fixture
def sidecar(tmp_path: Path) -> Path:
    """A ``gebra.toml`` whose ``[runtime]`` table declares :data:`IN_SIDECAR`."""
    path = tmp_path / "gebra.toml"
    path.write_text(sr.SIDECAR_TEXT, encoding="utf-8")
    return path


def _limit(envelope: ExtractionEnvelope) -> RecursionLimit | None:
    runtime = envelope.ir.runtime
    return None if runtime is None else runtime.recursion_limit


def _surfaces(envelope: ExtractionEnvelope) -> CompiledSurfaces:
    surfaces = envelope.extracted_from.compiled
    assert surfaces is not None, "a §4 extraction always records its compiled-level surfaces"
    return surfaces


def _binding(envelope: ExtractionEnvelope) -> tuple[int, BindingOutcome] | None:
    record = _surfaces(envelope).recursion_limit_binding
    return None if record is None else (record.value, record.outcome)


def _graph_level(envelope: ExtractionEnvelope) -> list[tuple[str, str | None]]:
    """The graph-level records: (code, detail rule) for each warning about the slot."""
    return [
        (warning.code.value, warning.detail.get("rule"))
        for warning in envelope.warnings
        if warning.detail.get("slot") == "runtime.recursion_limit"
        or str(warning.detail.get("construct", "")).startswith("recursion-limit")
    ]


# ── The surfaces fill the slot, on every path that reads them ───────────────────────────


def test_a_graph_level_declaration_fills_the_slot_on_the_builder_path() -> None:
    """§1a: the builder's ``__gebra_runtime__``, read from its instance dictionary."""
    envelope = extract(sr.build_declared_loop())

    assert _limit(envelope) == DECLARED
    assert envelope.ir.runtime is not None
    assert envelope.ir.runtime.interrupts is None
    assert envelope.ir.runtime.checkpointer is None  # still absent, never guessed (§7.1)


@pytest.mark.parametrize(
    "factory",
    [sr.compile_declared_loop, sr.bind_declared_loop, sr.declare_on_a_copy],
    ids=["declared-on-compiled", "bound-copy", "declared-on-a-copy"],
)
def test_a_graph_level_declaration_fills_the_slot_on_the_compiled_path(
    factory: Callable[[], Any],
) -> None:
    """§1a: the carrier is the builder every compiled copy shares — declared on the compiled
    graph, through a ``with_config`` copy, or on a copy made before the call."""
    assert _limit(extract(factory())) == DECLARED


def test_the_builder_and_compiled_documents_of_one_declared_source_carry_one_slot() -> None:
    """§6: "the declaration is identical before and after ``.compile()``" — the binding never
    enters the slot, so the two documents carry the same ``runtime.recursion_limit``."""
    builder = sr.build_declared_loop()

    from_builder = extract(builder)
    from_compiled = extract(builder.compile())
    from_bound = extract(builder.compile().with_config(recursion_limit=sr.OTHER_BOUND))

    assert _limit(from_builder) == _limit(from_compiled) == _limit(from_bound) == DECLARED


@pytest.mark.parametrize(
    "factory",
    [sr.declare_pregel, sr.bind_declared_pregel],
    ids=["declared", "bound-then-declared"],
)
def test_a_declaration_on_a_builderless_pregel_fills_the_slot_on_the_compiled_only_path(
    factory: Callable[[], Any],
) -> None:
    """§1a: "only an object with no builder carries the attribute itself", and on the
    compiled-only path extraction reads it "from the object handed in" (§4.3 rule 4)."""
    envelope = extract(factory())

    assert _limit(envelope) == DECLARED
    assert envelope.warnings_of(ExtractionWarningCode.COMPILED_ONLY_EXTRACTION)


@pytest.mark.parametrize(
    "factory",
    [sr.build_undeclared_loop, sr.compile_undeclared_loop, sr.build_review_pregel],
    ids=["builder", "compiled", "compiled-only"],
)
def test_the_sidecar_runtime_table_fills_the_slot_on_every_path_it_reaches(
    factory: Callable[[], Any], sidecar: Path
) -> None:
    """§2: "the table is read on every extraction path the sidecar tier reaches — builder,
    compiled and compiled-only" — the surface for a graph an adopter cannot annotate in code."""
    envelope = extract(factory(), sidecar=sidecar)

    assert _limit(envelope) == IN_SIDECAR
    assert _graph_level(envelope) == []


def test_a_rejected_sidecar_declaration_leaves_the_slot_absent_and_is_warned(
    tmp_path: Path,
) -> None:
    """§2: every rejection leaves the slot "absent — never the substrate default, never a bound
    value", with an ``annotation-invalid`` naming file, key and rule — even beside a binding."""
    path = tmp_path / "gebra.toml"
    path.write_text(
        'schema = "gebra-sidecar-v1"\n[runtime]\nrecursion_limit = { value = true }\n',
        encoding="utf-8",
    )

    envelope = extract(sr.bind_undeclared_loop(), sidecar=path)

    assert _limit(envelope) is None
    (invalid,) = envelope.warnings_of(ExtractionWarningCode.ANNOTATION_INVALID)
    assert invalid.node is None
    assert invalid.slots == ()
    assert invalid.detail["scope"] == "runtime"
    assert invalid.detail["file"] == str(path.resolve())
    assert invalid.detail["key"] == "recursion_limit"
    assert invalid.detail["rule"] == "recursion-limit-invalid"
    assert invalid.detail["violations"] == ("value-not-an-integer", "justification-missing")
    # The binding beside it is still only provenance — and, with no declaration left, disclosed.
    assert _binding(envelope) == (sr.LIMIT, BindingOutcome.DISCLOSED)


def test_the_lcel_path_reads_neither_surface(tmp_path: Path) -> None:
    """DEC-36 rules the declaration's reads on the builder, compiled and compiled-only paths, and
    the owner's ruling at EX-19's pause (PD-075, option (a), 2026-11-13) keeps them there: an LCEL
    fragment's ``runtime`` stays absent (INTROSPECTION-SPEC §5's path). A declaration made on the
    chain changes nothing extraction emits — the envelope is byte-identical before and after."""
    fragment = RunnableLambda(sg.raiser("fragment"))
    absent = tmp_path / "absent.toml"
    before = to_json(extract(fragment, sidecar=absent))

    declared = gebra.recursion_limit(fragment, sr.LIMIT, justification=sr.JUSTIFICATION)
    envelope = extract(declared, sidecar=absent)

    assert envelope.ir.runtime is None
    assert _graph_level(envelope) == []
    assert to_json(envelope) == before


def test_a_valid_runtime_table_is_not_applied_on_the_lcel_path(sidecar: Path) -> None:
    """The same ruling for the sidecar tier: a valid ``[runtime]`` table beside a chain fills no
    slot and adds no record — the chain's warnings, document and ``graph_version`` are exactly
    those it has beside a loaded sidecar that declares nothing, so the table is the only
    difference between the two extractions."""
    fragment = RunnableLambda(sg.raiser("fragment"))
    empty = sidecar.parent / "empty.toml"
    empty.write_text('schema = "gebra-sidecar-v1"\n', encoding="utf-8")

    without = extract(fragment, sidecar=empty)
    beside = extract(fragment, sidecar=sidecar)

    assert beside.ir.runtime is None
    assert _graph_level(beside) == []
    assert beside.warnings == without.warnings
    assert beside.ir == without.ir
    assert beside.graph_version() == without.graph_version()


def test_an_invalid_runtime_table_is_still_warned_on_the_lcel_path(tmp_path: Path) -> None:
    """§2's validation list does not depend on the path: the loader rejects the table and warns,
    on a chain as on a graph, and the chain's ``runtime`` stays absent."""
    path = tmp_path / "gebra.toml"
    path.write_text(
        'schema = "gebra-sidecar-v1"\n[runtime]\n'
        'recursion_limit = { value = 0, justification = " " }\n',
        encoding="utf-8",
    )

    envelope = extract(RunnableLambda(sg.raiser("fragment")), sidecar=path)

    assert envelope.ir.runtime is None
    (invalid,) = envelope.warnings_of(ExtractionWarningCode.ANNOTATION_INVALID)
    assert invalid.detail["scope"] == "runtime"
    assert invalid.detail["rule"] == "recursion-limit-invalid"
    assert invalid.detail["violations"] == ("value-below-one", "justification-blank")


# ── The ladder: one test per source pair ─────────────────────────────────────────────────


def test_graph_level_over_sidecar_identical_objects_are_no_conflict(tmp_path: Path) -> None:
    """§3: "identical objects are not a conflict" — value identity is the canonical JCS bytes."""
    path = tmp_path / "gebra.toml"
    path.write_text(
        'schema = "gebra-sidecar-v1"\n[runtime]\n'
        f'recursion_limit = {{ value = {sr.LIMIT}, justification = "{sr.JUSTIFICATION}" }}\n',
        encoding="utf-8",
    )

    envelope = extract(sr.build_declared_loop(), sidecar=path)

    assert _limit(envelope) == DECLARED
    assert _graph_level(envelope) == []


def test_graph_level_over_sidecar_a_differing_object_is_a_conflict_and_graph_level_is_kept(
    sidecar: Path,
) -> None:
    """§3: "a tier-2 object that differs structurally … from a tier-1 object is a conflict — tier
    1 is kept and ``annotation-conflict`` names the slot, both surfaces … and both values"."""
    envelope = extract(sr.build_declared_loop(), sidecar=sidecar)

    assert _limit(envelope) == DECLARED
    (conflict,) = envelope.warnings_of(ExtractionWarningCode.ANNOTATION_CONFLICT)
    assert conflict.node is None
    assert conflict.slots == ()
    assert conflict.detail["scope"] == "graph"
    assert conflict.detail["slot"] == "runtime.recursion_limit"
    assert conflict.detail["rule"] == "lower-tier-differs"
    assert conflict.detail["surfaces"] == {"kept": "graph-level", "discarded": "sidecar"}
    assert conflict.detail["values"] == {
        "kept": {"value": sr.LIMIT, "justification": sr.JUSTIFICATION},
        "discarded": {"value": sr.SIDECAR_LIMIT, "justification": sr.SIDECAR_JUSTIFICATION},
    }
    assert conflict.detail["file"] == str(sidecar.resolve())


def test_a_justification_alone_differing_is_a_conflict_too(tmp_path: Path) -> None:
    """Resolution is over the whole object, never member by member (§3): same value, different
    justification is two declarations, and the lower tier never fills a member of the higher."""
    path = tmp_path / "gebra.toml"
    path.write_text(
        'schema = "gebra-sidecar-v1"\n[runtime]\n'
        f'recursion_limit = {{ value = {sr.LIMIT}, justification = "another reason" }}\n',
        encoding="utf-8",
    )

    envelope = extract(sr.build_declared_loop(), sidecar=path)

    assert _limit(envelope) == DECLARED
    assert _graph_level(envelope) == [("annotation-conflict", "lower-tier-differs")]


@pytest.mark.parametrize("compiled_path", [True, False], ids=["compiled", "compiled-only"])
def test_graph_level_beside_an_equal_binding_corroborates(compiled_path: bool) -> None:
    """§3: "a bound value equal to the declared one is recorded as corroboration"."""
    workflow = sr.bind_declared_loop() if compiled_path else sr.bind_declared_pregel()

    envelope = extract(workflow)

    assert _limit(envelope) == DECLARED
    assert _binding(envelope) == (sr.LIMIT, BindingOutcome.CORROBORATES)
    assert _graph_level(envelope) == []
    assert envelope.disclosures_of(BOUND_ALONE) == ()


def test_graph_level_beside_a_differing_binding_is_a_conflict_and_the_declaration_is_kept() -> None:
    """§3: "a bound value that differs is recorded and warned — the declaration is kept, because it
    is the attested witness while the binding is what one call site configured"."""
    envelope = extract(sr.bind_declared_loop(sr.OTHER_BOUND))

    assert _limit(envelope) == DECLARED
    assert _binding(envelope) == (sr.OTHER_BOUND, BindingOutcome.CONFLICTS)
    (conflict,) = envelope.warnings_of(ExtractionWarningCode.ANNOTATION_CONFLICT)
    assert conflict.node is None and conflict.slots == ()
    assert conflict.detail["scope"] == "graph"
    assert conflict.detail["slot"] == "runtime.recursion_limit"
    assert conflict.detail["rule"] == "binding-differs"
    assert conflict.detail["surfaces"] == {"declared": "graph-level", "bound": "with_config"}
    assert conflict.detail["values"] == {"declared": sr.LIMIT, "bound": sr.OTHER_BOUND}
    assert conflict.detail["kept"] == "declared"


@pytest.mark.parametrize(
    ("bound", "outcome"),
    [(sr.SIDECAR_LIMIT, BindingOutcome.CORROBORATES), (sr.LIMIT, BindingOutcome.CONFLICTS)],
    ids=["equal", "differs"],
)
def test_sidecar_beside_a_binding_corroborates_or_conflicts(
    sidecar: Path, bound: int, outcome: BindingOutcome
) -> None:
    """The binding against the sidecar tier: the same three outcomes, the sidecar named."""
    envelope = extract(sr.bind_undeclared_loop(bound), sidecar=sidecar)

    assert _limit(envelope) == IN_SIDECAR
    assert _binding(envelope) == (bound, outcome)
    if outcome is BindingOutcome.CONFLICTS:
        (conflict,) = envelope.warnings_of(ExtractionWarningCode.ANNOTATION_CONFLICT)
        assert conflict.detail["surfaces"] == {"declared": "sidecar", "bound": "with_config"}
    else:
        assert _graph_level(envelope) == []


def test_all_three_sources_graph_level_wins_and_both_others_are_measured_against_it(
    sidecar: Path,
) -> None:
    """The ladder resolves first (graph-level over sidecar), then the binding meets the winner."""
    envelope = extract(sr.bind_declared_loop(sr.SIDECAR_LIMIT), sidecar=sidecar)

    assert _limit(envelope) == DECLARED
    assert _binding(envelope) == (sr.SIDECAR_LIMIT, BindingOutcome.CONFLICTS)
    assert _graph_level(envelope) == [
        ("annotation-conflict", "lower-tier-differs"),
        ("annotation-conflict", "binding-differs"),
    ]


# ── A binding alone: never a declaration ─────────────────────────────────────────────────


@pytest.mark.parametrize(
    "factory",
    [sr.bind_undeclared_loop, sr.declare_then_bind_pregel],
    ids=["compiled", "compiled-only-declared-then-bound"],
)
def test_a_binding_with_no_declaration_fills_nothing_and_is_disclosed(
    factory: Callable[[], Any],
) -> None:
    """§3.3: "with no declaration on either surface it fills no slot and is disclosed" — not
    warned. The builderless vector is the one the EX-D3 critique named: declared, then bound, the
    copy carries the binding alone, and the disclosure is what says so."""
    envelope = extract(factory())

    assert _limit(envelope) is None
    assert _binding(envelope) == (sr.LIMIT, BindingOutcome.DISCLOSED)
    assert _graph_level(envelope) == []
    (disclosure,) = envelope.disclosures_of(BOUND_ALONE)
    assert disclosure.node is None
    assert disclosure.detail["bound_value"] == sr.LIMIT
    assert disclosure.detail["declaration_surfaces"] == DECLARATION_SURFACES


def test_the_binding_disclosure_comes_first_beside_the_subgraph_records() -> None:
    """§8's order: "graph-scoped records first, then node-scoped ones in node-id order"."""
    parent = ss.build_direct_mount_parent().compile().with_config(recursion_limit=7)

    envelope = extract(parent)

    codes = [disclosure.code for disclosure in envelope.disclosures]
    assert codes[0] is BOUND_ALONE
    assert set(codes[1:]) == {ExtractionDisclosureCode.SUBGRAPH_READ_AS_ONE_NODE}


@pytest.mark.parametrize(
    "factory",
    [
        lambda: sr.bind_undeclared_loop(True),
        lambda: sr.bind_undeclared_loop("7"),
        lambda: sr.bind_undeclared_loop(-3),
        lambda: sr.bind_undeclared_loop(2**53),
    ],
    ids=["bool", "string", "negative", "too-large"],
)
def test_an_unusable_bound_value_is_unsupported_construct_and_no_binding(
    factory: Callable[[], Any],
) -> None:
    """§4.1: "a bound value is usable only if it is an ``int`` that is not a ``bool``, at least
    ``1`` and within ±(2⁵³−1); any other bound value is ``unsupported-construct`` … and no
    binding" — so no record and no disclosure either."""
    envelope = extract(factory())

    assert _limit(envelope) is None
    assert _binding(envelope) is None
    assert envelope.disclosures_of(BOUND_ALONE) == ()
    (unusable,) = [
        warning
        for warning in envelope.warnings_of(ExtractionWarningCode.UNSUPPORTED_CONSTRUCT)
        if warning.detail["construct"] == "recursion-limit-binding-unusable"
    ]
    assert unusable.detail["ir_partial"] is False
    assert unusable.detail["location"] == {"attribute": "config", "key": "recursion_limit"}


def test_a_config_that_is_not_a_mapping_is_unsupported_construct() -> None:
    """The substrate types ``config`` as a ``RunnableConfig`` mapping; anything else is a known
    field with an unmappable value, read through nothing of its own."""
    compiled = sr.compile_undeclared_loop()
    sr.instance_dictionary(compiled, Pregel)["config"] = sr.RecordingInt(5)
    sr.HOOKS.clear()

    envelope = extract(compiled)

    assert _binding(envelope) is None
    assert ("unsupported-construct", None) in _graph_level(envelope)


def test_a_binding_record_holds_only_a_usable_value() -> None:
    """The provenance model refuses what the read would never record."""
    for bad in (0, -1, 2**53, True):
        with pytest.raises(ValidationError):
            RecursionLimitBinding(value=bad, outcome=BindingOutcome.DISCLOSED)


# ── What is rejected stays absent ────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("carried", "violations"),
    [
        ({"recursion_limit": {"value": 38, "justification": "  "}}, ("justification-blank",)),
        ({"recursion_limit": {"value": True, "justification": "x"}}, ("value-not-an-integer",)),
        ({"recursion_limit": {"value": 0, "justification": "x"}}, ("value-below-one",)),
        ({"recursion_limit": {"justification": "x"}}, ("value-missing",)),
        ("not a declaration", ("not-a-declaration",)),
        ({"recursion_limit": 38}, ("not-an-object",)),
    ],
    ids=["blank", "boolean", "zero", "no-value", "a-string", "a-bare-number"],
)
def test_a_hand_set_attribute_the_call_would_refuse_is_ignored_with_a_graph_scoped_warning(
    carried: object, violations: tuple[str, ...]
) -> None:
    """§1a: an attribute "that is not the declaration's shape, or whose value or justification the
    call-time rules reject … is ignored with an ``annotation-invalid`` warning (scope ``graph``,
    surface ``graph-level``), so a hand-set blank justification or boolean value never reaches the
    IR"."""
    builder = sr.build_review_loop()
    sr.instance_dictionary(builder, StateGraph)["__gebra_runtime__"] = carried

    envelope = extract(builder)

    assert _limit(envelope) is None
    (invalid,) = envelope.warnings_of(ExtractionWarningCode.ANNOTATION_INVALID)
    assert invalid.node is None and invalid.slots == ()
    assert invalid.detail["scope"] == "graph"
    assert invalid.detail["surface"] == "graph-level"
    assert invalid.detail["slot"] == "runtime.recursion_limit"
    assert invalid.detail["attribute"] == "__gebra_runtime__"
    assert invalid.detail["violations"] == violations


def test_an_ignored_hand_set_attribute_declares_nothing_so_the_sidecar_fills_the_slot(
    sidecar: Path,
) -> None:
    """ "Ignored" means the code tier declares nothing — as a carried contract the walk cannot read
    declares nothing for a node — so the sidecar fills the gap (DEC-07: the sidecar fills gaps)."""
    builder = sr.build_review_loop()
    sr.instance_dictionary(builder, StateGraph)["__gebra_runtime__"] = {
        "recursion_limit": {"value": 38, "justification": ""}
    }

    envelope = extract(builder, sidecar=sidecar)

    assert _limit(envelope) == IN_SIDECAR
    assert _graph_level(envelope) == [("annotation-invalid", "recursion-limit-invalid")]


# ── The default is never read ────────────────────────────────────────────────────────────


def test_an_unbound_compiled_graph_records_no_binding_never_a_default() -> None:
    """§3.4: "When no binding exists the provenance record is empty, not 25" — nor 10007, the
    loop's own default at the pins (A1 addendum A1-D39)."""
    envelope = extract(sr.compile_undeclared_loop())

    assert _limit(envelope) is None
    assert _binding(envelope) is None
    assert envelope.disclosures == ()
    assert _graph_level(envelope) == []


def test_no_default_limit_is_read_even_when_the_substrate_constants_move(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Both constants patched to marker values: nothing extraction returns carries either."""
    from langchain_core.runnables import config as core_config
    from langgraph._internal import _config as loop_config

    monkeypatch.setattr(loop_config, "DEFAULT_RECURSION_LIMIT", 4242)
    monkeypatch.setattr(core_config, "DEFAULT_RECURSION_LIMIT", 4343)

    rendered = to_json(extract(sr.compile_undeclared_loop()))

    assert "4242" not in rendered and "4343" not in rendered


def test_no_extraction_module_names_a_default_limit() -> None:
    """The static half: no module under ``src/gebra`` names either default constant."""
    hits = [
        str(path.relative_to(REPO_ROOT))
        for path in sorted((REPO_ROOT / "src" / "gebra").rglob("*.py"))
        if "DEFAULT_RECURSION_LIMIT" in path.read_text(encoding="utf-8")
    ]

    assert hits == []


# ── Nothing moves for a source that declares nothing; P-02 reads the slot ───────────────


@pytest.mark.parametrize(
    "factory",
    [sr.build_undeclared_loop, sr.compile_undeclared_loop, sr.build_review_pregel],
    ids=["builder", "compiled", "compiled-only"],
)
def test_a_source_that_declares_nothing_carries_no_slot_and_no_new_record(
    factory: Callable[[], Any],
) -> None:
    """DEC-36 §3.9: "A source that declares nothing extracts byte-identical" — no slot, no runtime
    record, no warning and no disclosure this card's reads could add. (Every conformance golden's
    bytes are the suite-level half of the claim: ``tests/extraction/test_conformance.py``.)"""
    envelope = extract(factory())

    assert _limit(envelope) is None
    if envelope.extracted_from.compiled is None:
        assert envelope.ir.runtime is None
    else:
        assert _binding(envelope) is None
    assert _graph_level(envelope) == []
    assert envelope.disclosures_of(BOUND_ALONE) == ()


def test_a_declaration_moves_graph_version_and_a_binding_never_does() -> None:
    """A declared slot is inside hash scope and does its job (§3.9); the binding is provenance."""
    undeclared = extract(sr.compile_undeclared_loop()).graph_version()
    declared = extract(sr.compile_declared_loop()).graph_version()
    bound_equal = extract(sr.bind_declared_loop()).graph_version()
    bound_differs = extract(sr.bind_declared_loop(sr.OTHER_BOUND)).graph_version()
    bound_alone = extract(sr.bind_undeclared_loop()).graph_version()

    assert declared != undeclared
    assert declared == bound_equal == bound_differs
    assert bound_alone == undeclared


@pytest.mark.parametrize(
    "factory",
    [sr.build_declared_loop, sr.compile_declared_loop, sr.bind_declared_loop],
    ids=["builder", "compiled", "compiled-and-bound"],
)
def test_p02_passes_a_declared_loop_via_form_b_with_its_warning_grade_note(
    factory: Callable[[], Any],
) -> None:
    """TERMINATION-WITNESS-SPEC §2.2/§2.4: "a justified (b) ALONE … is PASS with a WARNING-grade
    note" — read off an extracted document, not an authored one. A witness-presence verdict:
    the IR carries a justified step budget, nothing more."""
    ir = extract(factory()).ir
    report = run_property("termination-witness", ir)

    assert isinstance(report, PropertyReport)
    assert report.result == "pass"
    assert isinstance(report.witness, TerminationWitness)
    assert [(entry.form, entry.discharges) for entry in report.witness.inventory] == [
        ("b", "blanket")
    ]
    (note,) = report.witness.notes
    assert (note.kind, note.severity) == ("scc-covered-only-by-recursion-limit", "warning")
    assert verify(ir).gate.outcome == "pass-with-notes"


@pytest.mark.parametrize(
    "factory",
    [sr.build_undeclared_loop, sr.compile_undeclared_loop, sr.bind_undeclared_loop],
    ids=["builder", "compiled", "bound-alone"],
)
def test_p02_still_fails_the_loop_with_no_declaration(factory: Callable[[], Any]) -> None:
    """The same graph undeclared — or bound and undeclared — has no witness of any form."""
    report = run_property("termination-witness", extract(factory()).ir)

    assert isinstance(report, PropertyReport)
    assert report.result == "fail"
    assert report.failure is not None
    assert report.failure.property_condition == "cycle-without-termination-witness"


# ── The records ──────────────────────────────────────────────────────────────────────────


def test_the_binding_disclosure_carries_what_its_row_names_and_states_no_more() -> None:
    """§8: "the bound value; the two surfaces that declare the slot; that no witness is read from
    the binding alone" — distinct from, and disjoint with, P-02's note about a present slot."""
    record = recursion_limit_binding_disclosure(9)

    assert record.code is BOUND_ALONE
    assert record.node is None
    assert record.detail == {
        "bound_value": 9,
        "declaration_surfaces": DECLARATION_SURFACES,
        "witness": NO_WITNESS_FROM_A_BINDING,
    }
    for surface in ("gebra.recursion_limit(graph, value, justification=...)", "[runtime]"):
        assert surface in record.message
    assert "runtime.recursion_limit` is absent" in record.message
    assert "recursion-limit-without-justification" not in record.message
    assert not re.search(r"guarantee|bounded|halts|terminates", record.message, re.IGNORECASE)


def test_the_binding_record_round_trips_with_the_envelope() -> None:
    envelope = extract(sr.bind_undeclared_loop())

    reloaded = ExtractionEnvelope.model_validate_json(to_json(envelope))

    assert reloaded == envelope
    assert json.loads(to_json(envelope))["extracted_from"]["compiled"][
        "recursion_limit_binding"
    ] == {"value": sr.LIMIT, "outcome": "disclosed"}


# ── WA-07: every read is an instance-dictionary read ─────────────────────────────────────


def test_an_armed_runtime_property_is_never_run_and_the_planted_declaration_is_read() -> None:
    """DEC-36 §4's first vector: "an armed ``__gebra_runtime__`` property … unreached because the
    reads are instance-dictionary reads" — on the builder and the builder-primary compiled path."""
    builder = sr.build_armed_runtime_loop()

    assert _limit(extract(builder)) == DECLARED
    assert _limit(extract(builder.compile())) == DECLARED
    assert sr.CARRIER_READS == []
    with pytest.raises(sg.SentinelExecutedError):
        builder.__gebra_runtime__  # type: ignore[attr-defined]  # noqa: B018 - the control
    sg.TRIPPED.clear()
    # The recorder's own control: the read above passed through `__getattribute__`, which
    # recorded it — with this module — before the property raised.
    assert sr.CARRIER_READS == [("builder.__gebra_runtime__", __name__)]
    sr.CARRIER_READS.clear()


@pytest.mark.parametrize(
    ("factory", "recorder"),
    [(sr.build_armed_config_compiled, "compiled"), (sr.build_armed_config_pregel, "pregel")],
    ids=["compiled", "compiled-only"],
)
def test_an_armed_config_property_is_never_read_by_gebra(
    factory: Callable[[], Any], recorder: str
) -> None:
    """DEC-36 §4's second vector, with its residue measured rather than hidden: the binding is
    read from the instance dictionary, and the property refuses any read gebra's own code makes —
    while LangGraph's ``get_graph()``, which the cross-check and the compiled-only path both run,
    reads ``self.config`` through the object's own access once per drawing
    (``langgraph/pregel/main.py``). That substrate read predates this card; it is pinned here."""
    workflow = factory()

    envelope = extract(workflow)

    assert _limit(envelope) == DECLARED
    assert _binding(envelope) == (sr.LIMIT, BindingOutcome.CORROBORATES)
    assert sr.CARRIER_READS == [("config", "langgraph.pregel.main")]
    # The control: the same attribute read, made from a frame whose module is gebra's, raises.
    with pytest.raises(sg.SentinelExecutedError):
        _as_gebra_module(_read_config)(workflow)
    sg.TRIPPED.clear()
    # The recorder's own control: a watched read made here is recorded, with this module.
    sr.CARRIER_READS.clear()
    workflow.__dict__  # noqa: B018 - the control
    assert sr.CARRIER_READS == [(f"{recorder}.__dict__", __name__)]
    sr.CARRIER_READS.clear()


def _read_config(workflow: Any) -> Any:
    return workflow.config


def _as_gebra_module(function: Callable[..., Any]) -> Callable[..., Any]:
    """``function`` rebound to a namespace named as a gebra module — what an attribute read made by
    gebra's own code looks like to the armed property's caller check."""
    return types.FunctionType(function.__code__, {"__name__": "gebra.extraction.probe"})


def test_a_recording_getattribute_sees_none_of_the_reads() -> None:
    """The builder whose ``__getattribute__`` records ``__gebra_runtime__``, ``config`` and
    ``__dict__``: extracting it, and its compiled form, records nothing."""
    builder = sr.build_armed_runtime_loop()

    extract(builder)
    extract(builder.compile())

    assert sr.CARRIER_READS == []
    # The recorder's own control: the watched reads, made here, are recorded with this module.
    builder.__dict__  # noqa: B018 - the control
    getattr(builder, "config", None)
    assert sr.CARRIER_READS == [("builder.__dict__", __name__), ("builder.config", __name__)]
    sr.CARRIER_READS.clear()


@pytest.mark.parametrize(
    ("factory", "limit"),
    [
        (sr.build_planted_dict_builder, DECLARED),
        (sr.build_planted_key_builder, None),
        (sr.build_hand_set_recording_declaration, DECLARED),
    ],
    ids=["planted-dict", "planted-key", "recording-declaration"],
)
def test_planted_dictionaries_keys_and_values_run_nothing_on_the_builder_path(
    factory: Callable[[], Any], limit: RecursionLimit | None
) -> None:
    """DEC-38 §3.2's read, applied: a planted ``dict`` subclass as the instance dictionary, a
    ``str``-subclass key spelled ``__gebra_runtime__`` (never the declaration: only an exact
    ``str`` key counts) and a declaration of recording ``dict``/``int``/``str`` subclasses — no
    hook of any of them runs, from any module, since nothing but gebra reads these."""
    envelope = extract(factory())

    assert _limit(envelope) == limit
    assert sr.HOOKS == []


@pytest.mark.parametrize(
    ("factory", "binding"),
    [
        (sr.build_planted_config_compiled, (sr.OTHER_BOUND, BindingOutcome.DISCLOSED)),
        (sr.build_planted_config_key_compiled, None),
        (sr.build_planted_config_attribute_key_compiled, None),
    ],
    ids=["recording-config", "planted-recursion-limit-key", "planted-config-key"],
)
def test_planted_config_objects_are_never_run_by_gebra(
    factory: Callable[[], Any], binding: tuple[int, BindingOutcome] | None
) -> None:
    """The binding read takes ``config`` and ``recursion_limit`` by exact-``str`` key through
    ``dict.items`` and the value through ``int.__index__``: that read triggers no hook. LangGraph's
    own drawing does — it merges ``self.config`` (``merge_configs``) and looks ``config`` up by
    hashing — and every such hook is attributed to a ``langgraph`` module."""
    envelope = extract(factory())

    assert _binding(envelope) == binding
    assert sr.outside_the_substrate(sr.HOOKS) == [], sr.HOOKS


@pytest.mark.parametrize(
    ("factory", "limit"),
    [
        (lambda: sr.build_planted_dict_builder().compile(), DECLARED),
        (lambda: sr.build_planted_key_builder().compile(), None),
        (lambda: sr.build_hand_set_recording_declaration().compile(), DECLARED),
        (sr.build_planted_dict_pregel, DECLARED),
        (sr.build_planted_key_pregel, None),
        (sr.build_recording_declaration_pregel, DECLARED),
    ],
    ids=[
        "compiled-planted-dict",
        "compiled-planted-key",
        "compiled-recording-declaration",
        "compiled-only-planted-dict",
        "compiled-only-planted-key",
        "compiled-only-recording-declaration",
    ],
)
def test_planted_dictionaries_keys_and_values_run_nothing_on_the_compiled_paths(
    factory: Callable[[], Any], limit: RecursionLimit | None
) -> None:
    """The same vectors on the builder-primary compiled path (the builder's dictionary, read
    through ``StateGraph``'s descriptor) and on the compiled-only path (the ``Pregel``'s own,
    read through the descriptor its MRO carries): no hook runs, from any module at all."""
    workflow = factory()
    sr.HOOKS.clear()

    envelope = extract(workflow)

    assert _limit(envelope) == limit
    assert sr.HOOKS == []


def test_an_armed_runtime_property_on_a_builderless_pregel_is_never_run() -> None:
    """DEC-36 §4's first vector on the compiled-only path: the declaration planted in the
    ``Pregel``'s own dictionary is read, its raising class property never answers, and the only
    watched read is the substrate drawing's ``config``."""
    pregel = sr.build_armed_runtime_pregel()

    envelope = extract(pregel)

    assert _limit(envelope) == DECLARED
    assert sr.CARRIER_READS == [("pregel.config", "langgraph.pregel.main")]
    sr.CARRIER_READS.clear()
    with pytest.raises(sg.SentinelExecutedError):
        pregel.__gebra_runtime__  # type: ignore[attr-defined]  # noqa: B018 - the control
    sg.TRIPPED.clear()
    # The recorder's own control: the read above was recorded, with this module, before the
    # property raised.
    assert sr.CARRIER_READS == [("pregel.__gebra_runtime__", __name__)]
    sr.CARRIER_READS.clear()


#: Armed controls for the recording fixtures: each hook, fired by the one operation it guards.
#: A recorder nobody shows recording proves nothing — every strict ``HOOKS == []`` above and
#: below would pass just as well against a hook that never fires.
RECORDER_CONTROLS: tuple[tuple[str, Callable[[], Any], Callable[[Any], object]], ...] = (
    ("dict.__getitem__", lambda: sr.RecordingDict(a=1), lambda held: held["a"]),
    ("dict.get", lambda: sr.RecordingDict(a=1), lambda held: held.get("a")),
    ("dict.__contains__", lambda: sr.RecordingDict(a=1), lambda held: "a" in held),
    ("dict.__iter__", lambda: sr.RecordingDict(a=1), iter),
    ("dict.__len__", lambda: sr.RecordingDict(a=1), len),
    ("dict.keys", lambda: sr.RecordingDict(a=1), lambda held: held.keys()),
    ("dict.values", lambda: sr.RecordingDict(a=1), lambda held: held.values()),
    ("dict.items", lambda: sr.RecordingDict(a=1), lambda held: held.items()),
    ("dict.copy", lambda: sr.RecordingDict(a=1), lambda held: held.copy()),
    ("dict.__repr__", lambda: sr.RecordingDict(a=1), repr),
    ("key.__hash__", lambda: sr.RecordingKey("k"), hash),
    ("key.__eq__", lambda: sr.RecordingKey("k"), lambda held: held == "k"),
    ("key.__ne__", lambda: sr.RecordingKey("k"), lambda held: held != "k"),
    ("key.__repr__", lambda: sr.RecordingKey("k"), repr),
    ("key.__str__", lambda: sr.RecordingKey("k"), str),
    ("key.__format__", lambda: sr.RecordingKey("k"), lambda held: f"{held}"),
    ("key.__iter__", lambda: sr.RecordingKey("k"), iter),
    ("key.__len__", lambda: sr.RecordingKey("k"), len),
    ("key.partition", lambda: sr.RecordingKey("k"), lambda held: held.partition(".")),
    ("key.__getitem__", lambda: sr.RecordingKey("k"), lambda held: held[0]),
    ("key.__contains__", lambda: sr.RecordingKey("k"), lambda held: "k" in held),
    ("key.__lt__", lambda: sr.RecordingKey("k"), lambda held: held < "z"),
    # The interpreter's own index protocol returns an `int` instance without calling an override
    # (`PyNumber_Index`), so only a direct call reaches this hook.
    ("int.__index__", lambda: sr.RecordingInt(3), lambda held: held.__index__()),
    ("int.__int__", lambda: sr.RecordingInt(3), int),
    ("int.__eq__", lambda: sr.RecordingInt(3), lambda held: held == 3),
    ("int.__hash__", lambda: sr.RecordingInt(3), hash),
    ("int.__lt__", lambda: sr.RecordingInt(3), lambda held: held < 4),
    ("int.__gt__", lambda: sr.RecordingInt(3), lambda held: held > 1),
    ("int.__le__", lambda: sr.RecordingInt(3), lambda held: held <= 3),
    ("int.__ge__", lambda: sr.RecordingInt(3), lambda held: held >= 3),
    ("int.__bool__", lambda: sr.RecordingInt(3), bool),
    ("int.__repr__", lambda: sr.RecordingInt(3), repr),
    ("int.__str__", lambda: sr.RecordingInt(3), str),
    ("int.__format__", lambda: sr.RecordingInt(3), lambda held: f"{held}"),
    ("text.strip", lambda: sr.RecordingText(" t "), lambda held: held.strip()),
    ("text.encode", lambda: sr.RecordingText("t"), lambda held: held.encode()),
    ("text.__str__", lambda: sr.RecordingText("t"), str),
    ("text.__repr__", lambda: sr.RecordingText("t"), repr),
    ("text.__eq__", lambda: sr.RecordingText("t"), lambda held: held == "t"),
    ("text.__hash__", lambda: sr.RecordingText("t"), hash),
    ("text.__len__", lambda: sr.RecordingText("t"), len),
    ("text.__bool__", lambda: sr.RecordingText("t"), bool),
    ("text.__format__", lambda: sr.RecordingText("t"), lambda held: f"{held}"),
    ("text.__iter__", lambda: sr.RecordingText("t"), iter),
    ("text.__getitem__", lambda: sr.RecordingText("t"), lambda held: held[0]),
    ("text.__contains__", lambda: sr.RecordingText("t"), lambda held: "t" in held),
    ("text.partition", lambda: sr.RecordingText("t"), lambda held: held.partition(".")),
)


@pytest.mark.parametrize(
    ("entry", "factory", "operation"),
    RECORDER_CONTROLS,
    ids=[entry for entry, _, _ in RECORDER_CONTROLS],
)
def test_every_recorder_the_runtime_fixtures_use_does_record(
    entry: str, factory: Callable[[], Any], operation: Callable[[Any], object]
) -> None:
    """Armed controls: each recording hook writes ``HOOKS`` when its operation runs. Each object
    is built first and the ledger cleared, so the entry asserted is the operation's own."""
    held = factory()
    sr.HOOKS.clear()

    operation(held)

    assert entry in [name for name, _ in sr.HOOKS]
    sr.HOOKS.clear()  # a control's own records come from this module, by construction


#: The seven positions a rejected value's type is named from, as the fixture builds them.
_POSITIONS = tuple(sr.hostile_positions(object()))


@pytest.mark.parametrize("route", sorted(sr.HOSTILE_NAMED))
@pytest.mark.parametrize("position", _POSITIONS)
def test_a_rejected_values_type_is_named_without_running_any_of_its_name(
    route: str, position: str
) -> None:
    """Every position at which a rejected value's type is named — a hand-set attribute, the
    declaration object under its key, that object's ``value``, its ``justification``, a member
    key, a ``config`` that is not a mapping, an unusable bound value — holding an instance of a
    class whose ``__module__`` is a ``str``
    subclass or not a string at all, whose ``__qualname__`` is a ``str`` subclass, or whose
    namespace holds a key that hashes as ``__module__``: the type is named, and none of the four
    routes runs (no hashing lookup, no format, no partition, no attribute read of the module
    object). The record still serializes."""
    workflow = sr.hostile_positions(sr.HOSTILE_NAMED[route]())[position]()
    sr.HOOKS.clear()

    envelope = extract(workflow)

    assert _limit(envelope) is None
    assert _graph_level(envelope) != []
    assert sr.HOOKS == []
    to_json(envelope).encode("utf-8")


@pytest.mark.parametrize(
    "carried",
    [
        {"recursion_limit": {"value": 38, "justification": "lone \ud800 surrogate"}},
        {"recursion_limit": {"value": 10**5000, "justification": "a reason"}},
        {"recursion_limit": {"value": -(10**5000), "justification": "a reason"}},
        {"recursion_limit": {"value": 38, "justification": "x", "lone \ud800": 1}},
        "lone \ud800 surrogate",
        {"recursion_limit": {"value": sr.QualnameHoldsASurrogate(), "justification": "x"}},
        {"recursion_limit": {"value": sr.ModuleHoldsASurrogate(), "justification": "x"}},
        sr.QualnameHoldsASurrogate(),
        sr.ModuleHoldsASurrogate(),
    ],
    ids=[
        "surrogate",
        "huge",
        "huge-negative",
        "surrogate-member",
        "surrogate-attribute",
        "surrogate-qualname-value",
        "surrogate-module-value",
        "surrogate-qualname-attribute",
        "surrogate-module-attribute",
    ],
)
def test_a_rejected_hand_set_declaration_always_serializes(carried: object) -> None:
    """A warning is a reported record: a lone surrogate — in a value, or in the name of a value's
    type — or a number past the interpreter's integer-string limit is named, never carried, so
    the envelope still encodes as UTF-8 JSON and reloads equal — and extraction stays total."""
    builder = sr.build_review_loop()
    sr.instance_dictionary(builder, StateGraph)["__gebra_runtime__"] = carried

    envelope = extract(builder)

    assert _limit(envelope) is None
    rendered = to_json(envelope)
    rendered.encode("utf-8")
    assert ExtractionEnvelope.model_validate_json(rendered) == envelope


@pytest.mark.parametrize(
    "bound",
    [
        "lone \ud800 surrogate",
        10**5000,
        -(10**5000),
        sr.QualnameHoldsASurrogate(),
        sr.ModuleHoldsASurrogate(),
    ],
    ids=["surrogate", "huge", "huge-negative", "surrogate-qualname", "surrogate-module"],
)
def test_an_unusable_bound_value_always_serializes(bound: object) -> None:
    """The same for a bound value: ``unsupported-construct``, no binding, and a record that
    serializes — whatever the binding held."""
    compiled = sr.compile_undeclared_loop()
    sr.instance_dictionary(compiled, Pregel)["config"] = {"recursion_limit": bound}

    envelope = extract(compiled)

    assert _binding(envelope) is None
    rendered = to_json(envelope)
    rendered.encode("utf-8")
    assert ExtractionEnvelope.model_validate_json(rendered) == envelope


@pytest.mark.parametrize("route", sorted(sr.UNENCODABLE_NAMED))
@pytest.mark.parametrize("position", _POSITIONS)
def test_a_type_whose_name_utf8_cannot_encode_still_gives_a_record_that_encodes(
    route: str, position: str
) -> None:
    """Every position a rejected value's type is named from, holding an instance of a class whose
    ``__module__`` or ``__qualname__`` was assigned a lone surrogate: the record names the type
    without that string, so extraction stays total and the envelope reloads equal."""
    workflow = sr.hostile_positions(sr.UNENCODABLE_NAMED[route]())[position]()

    envelope = extract(workflow)

    assert _limit(envelope) is None
    assert _graph_level(envelope) != []
    rendered = to_json(envelope)
    rendered.encode("utf-8")
    assert ExtractionEnvelope.model_validate_json(rendered) == envelope


#: A TOML hexadecimal literal of 3,700 digits: ``tomllib`` applies the interpreter's 4300-digit
#: limit to decimal literals only, so this parses — into an integer no report could render.
_HEX_PAST_THE_DIGIT_LIMIT = "0x" + "f" * 3700


@pytest.mark.parametrize(
    ("body", "rule", "path"),
    [
        (
            (
                "[runtime]\n"
                f"recursion_limit = {{ value = {_HEX_PAST_THE_DIGIT_LIMIT}, "
                'justification = "x" }\n'
            ),
            "recursion-limit-invalid",
            ("declared", "value"),
        ),
        (
            f"[runtime]\nrecursion_limit = {_HEX_PAST_THE_DIGIT_LIMIT}\n",
            "recursion-limit-invalid",
            ("declared",),
        ),
        (f"[runtime]\nlaps = {_HEX_PAST_THE_DIGIT_LIMIT}\n", "runtime-key-unknown", ("value",)),
        (f"runtime = {_HEX_PAST_THE_DIGIT_LIMIT}\n", "runtime-table-invalid", ("value",)),
    ],
    ids=["member", "not-a-table", "unknown-key", "runtime-not-a-table"],
)
def test_a_runtime_integer_past_the_digit_limit_is_named_not_carried(
    tmp_path: Path, body: str, rule: str, path: tuple[str, ...]
) -> None:
    """Each ``[runtime]`` record names such an integer as the code surface does — "outside the
    I-JSON exact range" — rather than carrying it, so the envelope encodes and reloads equal."""
    sidecar = tmp_path / "gebra.toml"
    sidecar.write_text(f'schema = "gebra-sidecar-v1"\n{body}', encoding="utf-8")

    envelope = extract(sr.build_review_loop(), sidecar=sidecar)

    assert _limit(envelope) is None
    (record,) = [warning for warning in envelope.warnings if warning.detail.get("rule") == rule]
    carried: Any = record.detail
    for key in path:
        carried = carried[key]
    assert carried == "an integer outside the I-JSON exact range ±(2**53−1)"
    rendered = to_json(envelope)
    rendered.encode("utf-8")
    assert ExtractionEnvelope.model_validate_json(rendered) == envelope


def test_an_unknown_member_is_named_in_the_records_detail() -> None:
    """ANNOTATION-API-SPEC §2: the record carries "the value(s) found" — the members the slot's
    shape does not carry are named in ``detail["unknown_members"]``."""
    builder = sr.build_review_loop()
    sr.instance_dictionary(builder, StateGraph)["__gebra_runtime__"] = {
        "recursion_limit": {"value": 38, "justification": "x", "note": "y", 7: "z"}
    }

    (invalid,) = extract(builder).warnings_of(ExtractionWarningCode.ANNOTATION_INVALID)

    assert invalid.detail["violations"] == ("member-unknown",)
    assert invalid.detail["unknown_members"] == ("note", "a builtins:int key")


# ── WA-07: every shape, in a guarded interpreter ─────────────────────────────────────────

#: Per family and shape, with and without the sidecar: the expected declared value. Written out,
#: so the guarded child's count is the fixtures' and not the code's.
EXPECTED_LIMITS: dict[str, dict[str, tuple[int | None, int | None]]] = {
    "builders": {
        "undeclared": (None, sr.SIDECAR_LIMIT),
        "declared": (sr.LIMIT, sr.LIMIT),
        "armed-runtime": (sr.LIMIT, sr.LIMIT),
        "planted-dict": (sr.LIMIT, sr.LIMIT),
        "planted-key": (None, sr.SIDECAR_LIMIT),
        "hand-set-recording": (sr.LIMIT, sr.LIMIT),
    },
    "compiled": {
        "undeclared": (None, sr.SIDECAR_LIMIT),
        "declared": (sr.LIMIT, sr.LIMIT),
        "bound-equal": (sr.LIMIT, sr.LIMIT),
        "bound-differs": (sr.LIMIT, sr.LIMIT),
        "bound-undeclared": (None, sr.SIDECAR_LIMIT),
        "bound-bool": (None, sr.SIDECAR_LIMIT),
        "bound-string": (None, sr.SIDECAR_LIMIT),
        "bound-negative": (None, sr.SIDECAR_LIMIT),
        "bound-too-large": (None, sr.SIDECAR_LIMIT),
        "declared-on-a-copy": (sr.LIMIT, sr.LIMIT),
        "armed-config": (sr.LIMIT, sr.LIMIT),
        "planted-config": (None, sr.SIDECAR_LIMIT),
        "planted-config-key": (None, sr.SIDECAR_LIMIT),
        "planted-config-attribute-key": (None, sr.SIDECAR_LIMIT),
    },
    "pregels": {
        "undeclared": (None, sr.SIDECAR_LIMIT),
        "declared": (sr.LIMIT, sr.LIMIT),
        "bound-and-declared": (sr.LIMIT, sr.LIMIT),
        "declared-then-bound": (None, sr.SIDECAR_LIMIT),
        "armed-config": (sr.LIMIT, sr.LIMIT),
        "armed-runtime": (sr.LIMIT, sr.LIMIT),
        "planted-dict": (sr.LIMIT, sr.LIMIT),
        "planted-key": (None, sr.SIDECAR_LIMIT),
        "hand-set-recording": (sr.LIMIT, sr.LIMIT),
    },
}


def _workflows() -> dict[str, dict[str, Callable[[], Any]]]:
    return {"builders": sr.BUILDERS, "compiled": sr.COMPILED, "pregels": sr.PREGELS}


def test_the_expectations_cover_every_registered_shape() -> None:
    """The table above and the fixture registries cannot drift apart."""
    assert {family: set(table) for family, table in EXPECTED_LIMITS.items()} == {
        family: set(table) for family, table in _workflows().items()
    }


@pytest.mark.parametrize("with_sidecar", [False, True], ids=["no-sidecar", "sidecar"])
@pytest.mark.parametrize(
    ("family", "name"),
    [(family, name) for family, table in EXPECTED_LIMITS.items() for name in table],
)
def test_every_registered_shape_declares_what_the_table_says(
    family: str, name: str, with_sidecar: bool, sidecar: Path
) -> None:
    """In process, the table the guarded child counts against — one shape, one path at a time."""
    workflow = _workflows()[family][name]()
    sr.HOOKS.clear()
    sr.CARRIER_READS.clear()

    envelope = extract(workflow, sidecar=sidecar if with_sidecar else None)

    limit = _limit(envelope)
    assert (None if limit is None else limit.value) == EXPECTED_LIMITS[family][name][with_sidecar]


#: The guarded child — the guard prologue the other extraction paths use, plus
#: ``Pregel.invoke``/``stream`` (a compiled graph is what must never be run) and
#: ``Pregel.with_config`` (extraction reads a binding; it never makes one). The fixtures are built,
#: compiled and bound before the guard goes up — the fixtures' step, never extraction's.
#: ``ChannelWrite.invoke`` stays allow-listed and counted: the compiled path's cross-check drawing
#: runs LangGraph's own, as ``test_compiled`` records.
_TRIPWIRE = """
import pathlib, socket, sys, tempfile

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
        raise AssertionError("a socket was created on the runtime path")


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
from tests.sample_workflows import sentinel_runtime as sr

workflows = [factory() for factory in sr.BUILDERS.values()]
workflows += [factory().compile() for factory in sr.BUILDERS.values()]
workflows += [factory() for factory in sr.COMPILED.values()]
workflows += [factory() for factory in sr.PREGELS.values()]
workflows += [
    build()
    for cls in sr.HOSTILE_NAMED.values()
    for build in sr.hostile_positions(cls()).values()
]
home = pathlib.Path(tempfile.mkdtemp())
(home / ".git").mkdir()
sidecar = home / "gebra.toml"
sidecar.write_text(sr.SIDECAR_TEXT, encoding="utf-8")
sg.TRIPPED.clear()
del sr.HOOKS[:]
del sr.CARRIER_READS[:]

assert attempts == [], attempts
socket.socket = _TripSocket
StateGraph.compile = _record("StateGraph.compile")
Pregel.invoke = _record("Pregel.invoke")
Pregel.stream = _record("Pregel.stream")
Pregel.with_config = _record("Pregel.with_config")

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

declared = 0
for workflow in workflows:
    for path in (home / "absent.toml", sidecar):
        envelope = gebra.extract(workflow, sidecar=path)
        envelope.graph_version()          # canonicalize and digest, still under the guard
        runtime = envelope.ir.runtime
        declared += runtime is not None and runtime.recursion_limit is not None

assert declared == %d, declared


def _claims():
    # The run's end-of-run claims, in one place so the controls re-run the very assertions.
    assert channelwrite_invokes, "no ChannelWrite.invoke ran — the cross-check drawing never ran"
    remote = [m for m in sys.modules if m == "langgraph.pregel.remote"]
    assert not remote, "remote module imported: " + repr(remote)
    assert sg.TRIPPED == [], "tripped ledger: " + repr(sg.TRIPPED)
    outside = sr.outside_the_substrate(sr.HOOKS)
    assert outside == [], "hooks outside the substrate: " + repr(outside)
    outside = sr.outside_the_substrate(sr.CARRIER_READS)
    assert outside == [], "reads outside the substrate: " + repr(outside)


_claims()
"""

_REPORT = "print(attempts)\n"


def _expected_declared() -> int:
    """How many extractions in the guarded run carry a declared slot — the table, with the
    builders counted twice (builder path and builder-primary compiled path), plus every hostile
    position, which declares nothing of its own and so takes the sidecar's declaration."""
    count = 0
    for family, table in EXPECTED_LIMITS.items():
        weight = 2 if family == "builders" else 1
        count += weight * sum(value is not None for pair in table.values() for value in pair)
    return count + len(sr.HOSTILE_NAMED) * len(sr.hostile_positions(object()))


def _run_guarded(probe: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", _TRIPWIRE % _expected_declared() + probe + _REPORT],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )


def test_every_runtime_shape_extracts_without_invoking_anything() -> None:
    """The WA-07 claim for the ``runtime.recursion_limit`` reads, in a fresh interpreter.

    Every shape — builder, builder-primary compiled, compiled-only, every adversarial carrier —
    with and without the sidecar, under a guard where name resolution, socket construction,
    ``compile()``, ``Runnable.invoke`` (``ChannelWrite`` allow-listed and counted),
    ``Pregel.invoke``/``stream`` and ``Pregel.with_config`` all raise. The child asserts the
    number of extractions that carried a declaration, so a run that stopped reaching the shapes
    fails; that no sentinel fired; that every recording hook and every watched read came from a
    ``langgraph`` module — the substrate's own drawing, never gebra's code nor a standard-library
    frame it called through; and that ``langgraph.pregel.remote`` was never imported.
    """
    result = _run_guarded()

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "[]", result.stdout
    assert "WA07-TRIP" not in result.stderr, result.stderr


#: Indices into the child's ``workflows`` list: the first compiled graph (the undeclared loop
#: compiled), the armed-runtime builder, and the armed-config compiled graph — all built before
#: the guard goes up, so a control reaches its raiser rather than a fixture step.
_FIRST_COMPILED = len(sr.BUILDERS)
_ARMED_RUNTIME = list(sr.BUILDERS).index("armed-runtime")
_ARMED_CONFIG = 2 * len(sr.BUILDERS) + list(sr.COMPILED).index("armed-config")


@pytest.mark.parametrize(
    ("probe", "expected"),
    [
        ("sr.build_review_loop().compile()\n", "StateGraph.compile was reached"),
        (f"workflows[{_FIRST_COMPILED}].invoke({{}})\n", "Pregel.invoke was reached"),
        (f"workflows[{_FIRST_COMPILED}].stream({{}})\n", "Pregel.stream was reached"),
        (
            f"workflows[{_FIRST_COMPILED}].with_config(recursion_limit=1)\n",
            "Pregel.with_config was reached",
        ),
        ("socket.socket()\n", "a socket was created"),
        ("socket.getaddrinfo('example.invalid', 80)\n", "getaddrinfo was reached"),
        ("socket.gethostbyname('example.invalid')\n", "gethostbyname was reached"),
        ("socket.create_connection(('example.invalid', 80))\n", "create_connection was reached"),
        (
            "workflows[0].nodes['draft'].runnable.invoke({})\n",
            "reached a non-ChannelWrite",
        ),
        (
            f"Runnable.invoke(workflows[{_FIRST_COMPILED}], {{}})\n",
            "Runnable.invoke reached: ",
        ),
        ("sg.SentinelExecutedError('a probe sentinel')\n_claims()\n", "tripped ledger"),
        (
            "sr.HOOKS.append(('dict.get', 'gebra.extraction.runtime'))\n_claims()\n",
            "hooks outside the substrate",
        ),
        (
            "sr.HOOKS.append(('dict.items', 'json.encoder'))\n_claims()\n",
            "hooks outside the substrate",
        ),
        (
            "sr.CARRIER_READS.append(('config', 'gebra.extraction.runtime'))\n_claims()\n",
            "reads outside the substrate",
        ),
        ("sys.modules['langgraph.pregel.remote'] = sys\n_claims()\n", "remote module imported"),
        (
            f"workflows[{_ARMED_RUNTIME}].__gebra_runtime__\n",
            "the __gebra_runtime__ property ran",
        ),
        (
            (
                "exec('w.config', {'__name__': 'gebra.extraction.probe', "
                f"'w': workflows[{_ARMED_CONFIG}]}})\n"
            ),
            "read `config` through the object's own access",
        ),
    ],
    ids=[
        "compile",
        "pregel-invoke",
        "pregel-stream",
        "pregel-with-config",
        "socket",
        "getaddrinfo",
        "gethostbyname",
        "create_connection",
        "runnable-invoke",
        "runnable-invoke-backstop",
        "tripped-ledger",
        "hook-ledger",
        "hook-ledger-stdlib-frame",
        "read-ledger",
        "remote-module",
        "armed-runtime-property",
        "armed-config-property",
    ],
)
def test_each_raiser_in_the_guarded_child_is_armed(probe: str, expected: str) -> None:
    """A tripwire nobody trips proves nothing: each raiser of the child gets a control, run after
    the child's own assertions so it proves the raiser was live at the end of that run; each
    ledger and module claim gets one that seeds its event and re-runs the child's ``_claims()``;
    and the two armed properties get one each, so a property that stopped raising fails here."""
    result = _run_guarded(probe)

    assert result.returncode != 0
    assert expected in result.stderr
