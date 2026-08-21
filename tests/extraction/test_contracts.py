"""The resolution seam — ANNOTATION-API-SPEC §3/§6 wired into ``gebra.extract()``.

``tests/annotations/test_resolve.py`` holds the §3 chain itself, over contributions handed to
it. This module holds the half only an extraction can supply: which live object is each tier.

* **§6's wrapper walk**, and the three outcomes it has — the carrier is reached, the carrier
  is invisible because a user decorator dropped the chain, or two carriers disagree and the
  outermost wins wholesale.
* **The tool-carried tier**: a LangChain ``BaseTool``'s author-written ``args_schema``, read
  by pydantic introspection and never by calling the tool.
* **§4's input**: the innermost callable, the graph's own state schema, and the slots the
  higher tiers already took — plus the ``RunnableLambda`` opacity §4 and INTROSPECTION §5
  rule 5 both state.
* **The card's third acceptance box**, at the bottom: extracting the same workflow before and
  after ``.compile()`` yields identical resolved contracts, against a committed golden.

Every graph here is armed. Every node raises if it is called, and the two reads
:mod:`gebra.extraction.contracts` guards with ``except Exception`` are watched by
:data:`~tests.sample_workflows.sentinel_resolution.TRIPPED`, so a sentinel one of those guards
swallowed still fails the run.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from gebra.annotations import NodeContract, Surface
from gebra.extraction import (
    WRAPPER_MEMBERS,
    CarrierRule,
    ExtractionWarningCode,
    SlotGrade,
    extract,
    resolve_node,
    state_schema_of,
    walk,
)
from gebra.extraction.builder import extract_builder
from gebra.extraction.dispatch import classify
from gebra.ir.canonical import canonical_bytes, graph_version
from gebra.ir.models import Annotations
from tests.sample_workflows import sentinel_resolution as sr

if TYPE_CHECKING:
    from gebra.extraction import ExtractionEnvelope, ExtractionWarning

REPO_ROOT = Path(__file__).resolve().parents[2]
GOLDEN_DIR = Path(__file__).parent / "golden"


@pytest.fixture(autouse=True)
def _nothing_was_executed() -> Any:
    """Every test in this file asserts the fixtures were read and not run.

    An autouse fixture rather than a line per test, because the claim is about the *path*
    rather than about any one assertion: the seam guards two reads with ``except Exception``,
    so a sentinel raised inside one of them would otherwise be invisible to a test that only
    checked the extraction succeeded. Recording the read before raising is what makes this
    check possible; :class:`~tests.sample_workflows.sentinel_resolution.ResolutionSentinelError`
    deriving from :class:`BaseException` is what keeps the guard from swallowing it.
    """
    del sr.TRIPPED[:]
    yield
    assert sr.TRIPPED == []


def resolved(envelope: ExtractionEnvelope) -> dict[str, Annotations | None]:
    """The resolved contract per node id."""
    return {node.id: node.annotations for node in envelope.ir.nodes}


def annotation_warnings(envelope: ExtractionEnvelope, node: str) -> list[ExtractionWarning]:
    """The §3/§4 records naming one node, in emission order."""
    annotation = {
        ExtractionWarningCode.CONTRACT_INFERRED,
        ExtractionWarningCode.CONTRACT_DEFAULTED,
        ExtractionWarningCode.ANNOTATION_CONFLICT,
        ExtractionWarningCode.ANNOTATION_INVALID,
    }
    return [warning for warning in envelope.warnings_for(node) if warning.code in annotation]


def sidecar_at(directory: Path, text: str) -> Path:
    """Write a sidecar and return its path."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "gebra.toml"
    path.write_text(text, encoding="utf-8")
    return path


# ── §6: the wrapper walk ─────────────────────────────────────────────────────────────────


def test_a_declaration_reaches_the_ir_at_full_strength() -> None:
    """The ordinary case, and the one everything else is measured against."""
    envelope = extract(sr.build_declared_graph())

    assert resolved(envelope)["declared_step"] == Annotations(
        input=("query",), output=("plan",), effect=("network",)
    )
    for slot in ("input", "output", "effect"):
        assert envelope.slot_grade("declared_step", slot) is SlotGrade.DECLARED
    assert annotation_warnings(envelope, "declared_step") == []


def test_a_carrier_under_a_chain_linking_wrapper_is_reached_by_walking() -> None:
    """§6: extraction "locates the innermost user callable by following ``functools.wraps``
    chains (``__wrapped__``)".

    The wrapper here sets ``__wrapped__`` and copies nothing, so the declaration is reachable
    **only** by walking — which is what makes this a test of the walk rather than of
    ``functools.wraps``'s ``__dict__`` copy.
    """
    envelope = extract(sr.build_wrapper_graph())
    contract = resolved(envelope)["wrapped_step"]

    assert contract is not None
    assert contract.input == ("query",)
    assert contract.output == ("plan",)
    assert envelope.slot_grade("wrapped_step", "input") is SlotGrade.DECLARED


def test_functools_wraps_carries_the_declaration_without_a_warning() -> None:
    """The shape §6 *mandates*, and the false positive it must not produce.

    ``functools.wraps`` copies the wrapped function's ``__dict__``, ``__gebra_contract__``
    included, so a correctly-wrapped node has a carrier at both levels of its chain holding
    one contract. §6's multiple-carrier rule is about ambiguity — "both a wrapper and the
    function it wraps were **independently** decorated" — and there is none here, so warning
    would put every node that followed §6's own instruction outside §8's strict-mode bar.
    """
    envelope = extract(sr.build_wrapper_graph())
    contract = resolved(envelope)["copied_step"]

    assert contract is not None
    assert contract.input == ("query",)
    assert contract.effect == ("billable",)
    assert envelope.warnings_of(ExtractionWarningCode.ANNOTATION_INVALID) == () or all(
        warning.node != "copied_step"
        for warning in envelope.warnings_of(ExtractionWarningCode.ANNOTATION_INVALID)
    )


def test_a_wrapper_that_dropped_the_chain_hides_the_declaration_silently() -> None:
    """§6's warned-about case, asserted as the silence it is.

    "Any user decorator sitting between ``@gebra.contract`` and the function MUST apply
    ``functools.wraps``; otherwise the metadata is invisible and the node falls through to
    sidecar/inference — indistinguishable from 'never annotated', which is exactly why the
    parity test exists." Indistinguishable means exactly that: **no warning**, because nothing
    about the object extraction receives says a contract was ever attached. Emitting one would
    require knowing what is not there.
    """
    envelope = extract(sr.build_wrapper_graph())

    assert resolved(envelope)["hidden_step"] == Annotations(pure=True)
    assert envelope.slot_grade("hidden_step", "pure") is SlotGrade.DEFAULTED
    assert [warning.code for warning in annotation_warnings(envelope, "hidden_step")] == [
        ExtractionWarningCode.CONTRACT_DEFAULTED
    ]


def test_the_outermost_carrier_wins_wholesale_and_both_are_named() -> None:
    """§6's multiple-carrier rule, in both of its halves.

    "The **first contract-bearing callable encountered walking inward from the outermost
    wrapper wins wholesale**; deeper carriers are ignored entirely — no per-slot merge …
    and extraction emits an ``annotation-invalid`` warning naming both carriers." So the
    inner declaration's ``effects=["billable"]`` does **not** survive into the resolved
    contract, which is what "wholesale" and "no per-slot merge" mean, and the record names
    both objects so the ambiguity is visible.
    """
    envelope = extract(sr.build_wrapper_graph())
    contract = resolved(envelope)["two_carrier_step"]

    assert contract is not None
    assert contract.input == ("query",)
    assert contract.output == ("booking_ref",)
    assert contract.effect == ("write",)  # the D-011 floor, not the inner "billable"

    (invalid,) = [
        warning
        for warning in envelope.warnings_for("two_carrier_step")
        if warning.code is ExtractionWarningCode.ANNOTATION_INVALID
    ]
    assert invalid.detail["rule"] == CarrierRule.MULTIPLE_CARRIERS.value
    assert len(invalid.detail["carriers"]) == 2
    assert invalid.detail["kept"] == invalid.detail["carriers"][0]
    assert invalid.detail["ignored"] == invalid.detail["carriers"][1:]


def test_a_foreign_contract_attribute_is_a_warning_not_an_error() -> None:
    """§1 makes this an import-time error; reached from extraction it is warning-grade.

    ``gebra`` owns ``__gebra_contract__`` and the decorators refuse to overwrite something
    they did not attach (§1). But an extraction meets whatever the object already carries, and
    §2/§3 put this whole surface at warning grade — "extraction stays total" — so the tier
    declares nothing and the lower ones stand.
    """
    envelope = extract(sr.build_foreign_carrier_graph())

    (invalid,) = [
        warning
        for warning in envelope.warnings_for("foreign_carrier_step")
        if warning.code is ExtractionWarningCode.ANNOTATION_INVALID
    ]
    assert invalid.detail["rule"] == CarrierRule.CARRIER_UNREADABLE.value
    assert resolved(envelope)["foreign_carrier_step"] == Annotations(pure=True)


def test_an_async_node_is_reached_through_the_member_the_substrate_used() -> None:
    """§6's "known LangGraph/LangChain wrapper attributes", on the async shape.

    An ``async def`` node is held in ``RunnableCallable.afunc`` rather than ``.func``, so a
    walk that only knew one member would find no carrier and no body — and would report the
    node as undeclared rather than as declared. §4 says the patterns "read the async body"
    identically, and this is what makes that reachable.
    """
    envelope = extract(sr.build_async_graph())
    contract = resolved(envelope)["declared_async_step"]

    assert contract is not None
    assert contract.input == ("query",)
    assert envelope.slot_grade("declared_async_step", "input") is SlotGrade.DECLARED


def test_the_walk_stops_at_shapes_the_spec_sends_to_the_sidecar() -> None:
    """§6 names ``functools.partial`` among the objects the sidecar is the fallback for.

    Following one would also walk into the substrate's own executor trampoline, which is not
    user code at all. The walk therefore descends only into a Python function or method or a
    ``Runnable``, and everything else ends the chain.
    """
    import functools

    def target() -> None:  # pragma: no cover - never called
        return None

    partial = functools.partial(target)

    assert walk(partial).chain == (partial,)
    assert walk(partial).innermost is partial
    assert walk(partial).contract is None
    assert walk("not a callable at all").chain == ("not a callable at all",)
    assert "__wrapped__" in WRAPPER_MEMBERS


def test_the_walk_terminates_on_a_self_referential_chain() -> None:
    """A cycle is a chain that ends, not a ``RecursionError`` out of ``gebra.extract()``."""

    def target() -> None:  # pragma: no cover - never called
        return None

    target.__wrapped__ = target  # type: ignore[attr-defined]

    assert walk(target).chain == (target,)


# ── §3 tier 2: the tool-carried ``args_schema`` ──────────────────────────────────────────


def test_a_tools_args_schema_is_read_as_a_declared_source() -> None:
    """§1: "a LangChain ``BaseTool``'s pydantic ``args_schema`` is read by extraction as a
    declared source (it is author-written schema, not inference) and serialized to JSON
    Schema"."""
    envelope = extract(sr.build_tool_graph())
    contract = resolved(envelope)["search_tool"]

    assert contract is not None
    assert contract.args_schema is not None
    assert contract.args_schema["type"] == "object"
    assert set(contract.args_schema["properties"]) == {"query", "limit"}
    assert envelope.slot_grade("search_tool", "args_schema") is SlotGrade.DECLARED


def test_the_schema_is_asked_for_its_json_schema_and_the_tool_is_never_called() -> None:
    """The one read §1 rule 3 licenses on a caller-supplied class, with its positive control.

    "pydantic model/JSON-schema introspection" is on §1's closed operation list, so this read
    is licensed rather than tolerated — and a seam that stopped performing it would leave the
    tier empty with nothing to show for it. The tool's own implementation is armed, so the
    autouse fixture is what says the tool was not invoked to find its schema.
    """
    del sr.PROBED[:]

    envelope = extract(sr.build_probed_tool_graph())

    assert sr.PROBED == ["ProbedArgs"]  # the one tool whose schema is both readable and probed
    contract = resolved(envelope)["probed_tool"]
    assert contract is not None
    assert contract.args_schema is not None
    assert set(contract.args_schema["properties"]) == {"query"}


@pytest.mark.parametrize(
    ("node", "why"),
    [
        ("refusing_tool", "model_json_schema() raised"),
        ("hostile_tool", "reading args_schema raised"),
        ("foreign_schema_tool", "JSON cannot carry"),
    ],
)
def test_a_schema_this_build_cannot_read_is_a_warning_not_a_failure(node: str, why: str) -> None:
    """What a caller's class does is the caller's business; extraction stays total (§2, §3).

    Three ways the tier can fail, and the same posture for each: the tier declares nothing
    rather than declaring a guess, and the record names the tool and why — which is the
    difference between a diagnosable gap and a silent one. Two of them are *reads* on a
    caller-supplied class (the field, then the JSON schema), which is why the seam guards both
    rather than only the call; the third is a schema object that is not JSON data, which would
    otherwise leave a node with no ``graph_version``.
    """
    envelope = extract(sr.build_probed_tool_graph())

    (invalid,) = [
        warning
        for warning in envelope.warnings_for(node)
        if warning.code is ExtractionWarningCode.ANNOTATION_INVALID
    ]
    assert invalid.detail["rule"] == CarrierRule.TOOL_SCHEMA_UNREADABLE.value
    assert invalid.detail["surface"] == Surface.TOOL.value
    assert why in invalid.detail["why"]
    contract = resolved(envelope)[node]
    assert contract is not None
    assert contract.args_schema is None


def test_a_tool_with_no_schema_declares_nothing_and_warns_about_nothing() -> None:
    """The tier is a *source*, not an obligation: a tool without one is not a defect."""
    envelope = extract(sr.build_probed_tool_graph())
    contract = resolved(envelope)["schemaless_tool"]

    assert contract is not None
    assert contract.args_schema is None
    assert [warning.code for warning in annotation_warnings(envelope, "schemaless_tool")] == [
        ExtractionWarningCode.CONTRACT_DEFAULTED
    ]


def test_a_schema_written_directly_as_json_is_taken_as_written() -> None:
    """``args_schema`` may be a JSON Schema object rather than a pydantic class.

    §1 calls the slot "a JSON Schema object" and imposes no algebra on its contents, so a tool
    that carries one directly needs no conversion — and normalizing it through the seam the
    decorator and sidecar share is what keeps the three surfaces landing on one value.
    """
    envelope = extract(sr.build_probed_tool_graph())
    contract = resolved(envelope)["dict_schema_tool"]

    assert contract is not None
    assert contract.args_schema == {"type": "object", "title": "written directly"}


def test_a_sidecar_args_schema_loses_to_the_tool_carried_one_and_is_warned(
    tmp_path: Path,
) -> None:
    """§3's tier-2 rule, in its own words.

    "A sidecar ``args_schema`` differing from the tool-carried schema is a conflict: the
    tool-carried value is kept and an ``annotation-conflict`` warning is emitted (same shape
    as below, surfaces labeled ``tool``/``sidecar``)." The sidecar's *other* slot is unaffected
    — the chain is per slot, so a losing slot does not cost the entry its gaps.
    """
    sidecar = sidecar_at(tmp_path, sr.TOOL_CONFLICT_SIDECAR)

    envelope = extract(sr.build_tool_graph(), sidecar=sidecar)
    contract = resolved(envelope)["search_tool"]

    assert contract is not None
    assert contract.args_schema is not None
    assert contract.args_schema["title"] == "SearchArgs"
    assert contract.pure is True

    (conflict,) = envelope.warnings_of(ExtractionWarningCode.ANNOTATION_CONFLICT)
    assert conflict.node == "search_tool"
    assert conflict.slots == ("args_schema",)
    assert conflict.detail["surfaces"] == {"kept": "tool", "discarded": "sidecar"}


# ── §3 tier 3 and 4, through a live extraction ───────────────────────────────────────────


def test_a_sidecar_fills_the_gaps_and_the_decorator_keeps_its_slots(tmp_path: Path) -> None:
    """DEC-07, end to end: "The decorator wins; the sidecar **fills gaps only**".

    One file, three outcomes at once: a slot the decorator set is kept and the sidecar's
    disagreement is warned, a slot both agree on is silent, and two slots the decorator left
    open are filled at full declared strength.
    """
    sidecar = sidecar_at(tmp_path, sr.CONFLICTING_SIDECAR)

    envelope = extract(sr.build_declared_graph(), sidecar=sidecar)
    contract = resolved(envelope)["declared_step"]

    assert contract is not None
    assert contract.input == ("query",)  # the decorator's, not the sidecar's ["budget"]
    assert contract.output == ("plan",)  # both said the same thing
    assert contract.idempotent is not None  # the sidecar filled a gap
    assert contract.compensation is not None
    assert envelope.slot_grade("declared_step", "idempotent") is SlotGrade.DECLARED

    conflicts = envelope.warnings_of(ExtractionWarningCode.ANNOTATION_CONFLICT)
    assert [warning.slots for warning in conflicts] == [("input",)]
    assert conflicts[0].detail["values"] == {"kept": ("query",), "discarded": ("budget",)}


def test_an_identical_sidecar_declaration_is_not_a_conflict(tmp_path: Path) -> None:
    """§3: "Identical values are not a conflict" — the half that keeps drift reports honest."""
    sidecar = sidecar_at(tmp_path, sr.IDENTICAL_SIDECAR)

    envelope = extract(sr.build_declared_graph(), sidecar=sidecar)

    assert envelope.warnings_of(ExtractionWarningCode.ANNOTATION_CONFLICT) == ()
    assert resolved(envelope)["declared_step"] == Annotations(
        input=("query",), output=("plan",), effect=("network",)
    )


def test_a_cross_surface_contradiction_is_repaired_and_recorded(tmp_path: Path) -> None:
    """§3's resolved-contract pass, reached through two real surfaces.

    ``hidden_step``'s decorator is invisible (its wrapper dropped the chain), so the sidecar's
    ``effects = ["irreversible"]`` is what the node ends up with — and ``plain_step`` gets a
    sidecar ``pure = true`` that closes the D-011 pair. Neither node is a conflict: no slot was
    set twice. The pass is what has to answer for the result.
    """
    sidecar = sidecar_at(tmp_path, sr.PURE_WITH_EFFECTS_SIDECAR)

    envelope = extract(sr.build_wrapper_graph(), sidecar=sidecar)

    assert resolved(envelope)["hidden_step"] == Annotations(effect=("irreversible",))
    assert envelope.slot_grade("hidden_step", "effect") is SlotGrade.DECLARED
    assert envelope.warnings_of(ExtractionWarningCode.ANNOTATION_CONFLICT) == ()


def test_inference_fills_only_what_the_declaration_tiers_left_open() -> None:
    """§3 tier 4: inference "fills what remains", and every slot it fills is warned (§4).

    Both halves are asserted through §5's own lookup rather than by reading the records: a
    slot is heuristic-grade **iff** a ``contract-inferred``/``contract-defaulted`` warning
    names the (node id, slot) pair, and that is the question a validator asks.
    """
    envelope = extract(sr.build_inference_graph())
    contract = resolved(envelope)["inferring_step"]

    assert contract is not None
    assert contract.input == ("query",)
    assert contract.output == ("plan",)
    assert contract.effect == ("write",)
    assert envelope.slot_grade("inferring_step", "input") is SlotGrade.INFERRED
    assert envelope.slot_grade("inferring_step", "output") is SlotGrade.INFERRED
    assert envelope.slot_grade("inferring_step", "effect") is SlotGrade.DEFAULTED


def test_a_declared_slot_gets_neither_an_inferred_value_nor_a_warning(tmp_path: Path) -> None:
    """A ``contract-inferred`` naming a declared slot would be a false answer to §5's lookup.

    The node's body licenses an ``output`` pattern, and the sidecar declares ``writes``; the
    declaration wins the slot and the record for it must not exist, or every validator would
    read an authored contract as heuristic-grade.
    """
    sidecar = sidecar_at(
        tmp_path, f'{sr.SCHEMA_LINE}\n[nodes.inferring_step]\nwrites = ["booking_ref"]\n'
    )

    envelope = extract(sr.build_inference_graph(), sidecar=sidecar)
    contract = resolved(envelope)["inferring_step"]

    assert contract is not None
    assert contract.output == ("booking_ref",)
    assert envelope.slot_grade("inferring_step", "output") is SlotGrade.DECLARED
    assert envelope.warnings_of(ExtractionWarningCode.ANNOTATION_CONFLICT) == ()


def test_a_declared_output_is_write_evidence_for_the_d011_default() -> None:
    """§4's defaults are written for "an **unannotated** node", and this one is not.

    ``wrapped_step`` declares ``writes=["plan"]`` and its body writes nothing §4's shallow
    patterns can see, so without the author's declaration counting as evidence the D-011
    default would resolve it ``pure: true`` — a gap-filling tier contradicting the declaration
    it was filling around, in the one direction "provably read-only" rules out. It resolves to
    the ``effect: [write]`` floor instead, and the floor is the *defaulted* grade §5 reports.
    """
    envelope = extract(sr.build_wrapper_graph())
    contract = resolved(envelope)["wrapped_step"]

    assert contract is not None
    assert contract.output == ("plan",)
    assert contract.effect == ("write",)
    assert contract.pure is None
    assert envelope.slot_grade("wrapped_step", "effect") is SlotGrade.DEFAULTED


def test_an_inferred_slot_the_ir_cannot_carry_is_dropped_and_unnamed() -> None:
    """§3's carriability pass, on the tier that can produce an uncarriable value by itself.

    §4's pattern (b) reads literal state keys out of source text, and source text can hold a
    lone surrogate — a perfectly good Python string with no UTF-8 encoding, which IR-SPEC §6.1
    step 6 cannot serialize. Emitting it would give the whole document no ``graph_version``,
    so the slot is dropped with an ``annotation-invalid``.

    The second half is the one §5 depends on: the ``contract-inferred`` record that named
    ``input`` is dropped with it. A warning naming a slot the IR does not carry would tell
    §5's lookup that a slot which does not exist is heuristic-grade — the same falsehood the
    seam refused to emit before the chain existed.
    """
    envelope = extract(sr.build_uncarriable_inference_graph())
    contract = resolved(envelope)["surrogate_reader"]

    assert contract is not None
    assert contract.input is None
    assert envelope.graph_version().startswith("sha256:")

    codes = [warning.code for warning in annotation_warnings(envelope, "surrogate_reader")]
    assert ExtractionWarningCode.ANNOTATION_INVALID in codes
    assert ExtractionWarningCode.CONTRACT_INFERRED not in codes
    assert envelope.slot_grade("surrogate_reader", "input") is SlotGrade.DECLARED
    assert envelope.slot_grade("surrogate_reader", "pure") is SlotGrade.DEFAULTED


def test_a_runnable_lambda_body_is_opaque_and_takes_the_floor() -> None:
    """§4: "opaque nodes (``RunnableLambda`` bodies …) skip inference entirely and go
    straight to defaults"; INTROSPECTION §5 rule 5 says the same in the other spec.

    The floor is ``effect: [write]``, never ``pure`` — D-011's own words are "provably
    read-only", and a body nobody looked at is not that. So opacity can only cost precision.

    **No ``opaque-lambda`` is emitted here**, and the absence is deliberate. INTROSPECTION §8
    scopes that record to *stitched* lambdas (§5 fragment stitching), and a lambda bound as a
    ``StateGraph`` node is not stitched — the §5 path stitches an LCEL object handed to
    ``extract()``, and nothing on the §3 path calls it. The node is still graded correctly by
    ANNOTATION §5's lookup, which names exactly ``contract-inferred``/``contract-defaulted``;
    ``tests/extraction/test_lcel.py`` is where the stitched half of the same rule lives.
    """
    envelope = extract(sr.build_opaque_graph())

    assert resolved(envelope)["opaque_step"] == Annotations(effect=("write",))
    assert envelope.slot_grade("opaque_step", "effect") is SlotGrade.DEFAULTED
    assert envelope.warnings_of(ExtractionWarningCode.OPAQUE_LAMBDA) == ()


def test_the_graphs_own_schema_is_what_the_full_state_exclusion_reads() -> None:
    """§4's exclusion is about the *graph's* schema, not every schema a builder registered.

    ``builder.schemas`` accumulates one entry per node input schema, so a node annotated with
    a projection puts that projection in it — and reading the exclusion off that set would
    exclude exactly the annotations §4's ``input`` pattern (a) exists to license. The three
    graph-level attributes are what §4 means, and this is the assertion that says so.
    """
    builder = sr.build_inference_graph()

    schema = state_schema_of(builder)

    assert schema.is_full_state(sr.ParityState)
    assert not schema.is_full_state(sr.Reads)
    assert sr.Reads in builder.schemas


def test_resolving_a_node_directly_returns_the_whole_record() -> None:
    """The seam's own surface, for a caller that needs the tier per slot."""
    builder = sr.build_declared_graph()

    record = resolve_node(
        "declared_step",
        builder.nodes["declared_step"].runnable,
        state_schema=state_schema_of(builder),
    )

    assert record.contract.input == ("query",)
    assert record.resolution.surfaces["input"] is Surface.DECORATOR
    assert record.inference is not None
    assert record.warnings == ()


def test_a_node_the_sidecar_does_not_key_is_untouched_by_it(tmp_path: Path) -> None:
    """One entry annotates one node: the chain runs per node, with no shared state."""
    sidecar = sidecar_at(tmp_path, sr.CONFLICTING_SIDECAR)

    with_file = extract(sr.build_declared_graph(), sidecar=sidecar)
    without = extract(sr.build_declared_graph(), sidecar=tmp_path / "absent.toml")

    assert resolved(with_file)["plain_step"] == resolved(without)["plain_step"]
    assert resolved(with_file)["declared_step"] != resolved(without)["declared_step"]


@pytest.mark.parametrize("name", sorted(sr.RESOLUTION_BUILDERS))
def test_every_shape_extracts_to_an_ir_with_a_digest(name: str) -> None:
    """Extraction stays total *and* digestible, over every §3/§6 shape.

    The second half is the one §3's carriability pass exists for: an IR that INTROSPECTION §2
    requires to exist and that raises the moment anyone asks it for a ``graph_version`` would
    be extraction total in name only.
    """
    envelope = extract(sr.RESOLUTION_BUILDERS[name]())

    assert envelope.graph_version().startswith("sha256:")
    assert envelope.ir.nodes


@pytest.mark.parametrize("name", sorted(sr.RESOLUTION_BUILDERS))
def test_every_shape_extracts_to_the_same_value_twice(name: str) -> None:
    """Resolution is a function of the object, not of the run.

    Not a truism here: the chain reads a per-extraction source cache, a sidecar reading and a
    schema tuple, and any of the three leaking state between nodes or between runs would show
    up as two unequal envelopes for one unchanged builder.
    """
    factory = sr.RESOLUTION_BUILDERS[name]

    assert extract(factory()) == extract(factory())


# ── The card's third acceptance box: builder-vs-compiled parity, golden-tested ───────────


def golden(name: str) -> bytes:
    """One committed golden file's bytes."""
    return (GOLDEN_DIR / name).read_bytes()


def test_the_parity_workflow_reproduces_its_golden_canonical_form() -> None:
    """The committed golden for the §6 parity workflow (WA-05 lifecycle).

    Compared whole rather than field by field, so this also guards the golden file itself:
    a resolution that changed by one byte fails here, and changing the file is a commit that
    has to say why.
    """
    envelope = extract(sr.build_parity_graph())

    assert canonical_bytes(envelope.ir) == golden("parity.canonical.json")
    assert envelope.graph_version() == golden("parity.digest").decode().strip()


def test_extracting_before_and_after_compile_yields_identical_resolved_contracts() -> None:
    """§6: "Annotations MUST survive ``gebra.extract()`` on **compiled** graphs: extracting
    the same workflow before and after ``.compile()`` yields identical resolved contracts".

    Literally that: one builder, extracted, then compiled, then extracted again. The claim is
    not vacuous — ``.compile()`` is the moment LangGraph is free to rewrap the node callables
    it was given, and §6's whole normative discipline (one namespaced attribute, attached
    without wrapping) exists so that it cannot strip the metadata by replacing a wrapper gebra
    never added.
    """
    builder = sr.build_parity_graph()

    before = extract(builder)
    builder.compile()
    after = extract(builder)

    assert resolved(after) == resolved(before)
    assert canonical_bytes(after.ir) == golden("parity.canonical.json")
    assert after.graph_version() == before.graph_version()


def test_the_compiled_objects_builder_resolves_to_the_same_contracts() -> None:
    """The other half of §6's parity, read off the *compiled object* rather than the builder.

    The §3 rule set is applied directly to the compiled object's ``.builder`` backreference,
    which is the route §4.3 rule 1 makes authoritative ("builder-authoritative-when-available")
    and is what the registered §4 path itself calls. Going through it here rather than through
    ``gebra.extract()`` keeps this a statement about §3 and §6 alone: the resolved contracts and
    the canonical bytes are the same document. The compiled-only surfaces the §4 path layers on
    top (interrupts, checkpointer, the cross-check) are ``tests/extraction/test_compiled.py``'s,
    and nothing here claims anything about them — which is also why this envelope carries no
    ``runtime`` block while an ``extract()`` of the same object does.
    """
    compiled = sr.compile_parity_graph()
    dispatch = classify(compiled)

    from gebra.annotations.sidecar import SidecarReading

    envelope = extract_builder(dispatch, sidecar=SidecarReading())

    assert resolved(envelope) == resolved(extract(sr.build_parity_graph()))
    assert canonical_bytes(envelope.ir) == golden("parity.canonical.json")
    assert envelope.graph_version() == graph_version(envelope.ir)


def test_a_sidecar_pinned_extraction_survives_compilation_too(tmp_path: Path) -> None:
    """Parity is about the *resolved* contract, so the tier that came from a file is in it."""
    sidecar = sidecar_at(tmp_path, sr.CONFLICTING_SIDECAR)
    builder = sr.build_parity_graph()

    before = extract(builder, sidecar=sidecar)
    builder.compile()
    after = extract(builder, sidecar=sidecar)

    assert resolved(after) == resolved(before)
    assert after.graph_version() == before.graph_version()
    assert resolved(after)["declared_step"] != resolved(extract(builder))["declared_step"]


def test_the_golden_covers_every_tier_of_the_chain() -> None:
    """A golden is only worth what it spans, so what it spans is asserted rather than assumed.

    One node per §3 tier plus the two §4 outcomes: a decorator declaration, a declaration
    reached through §6's walk, a tool-carried ``args_schema``, an opaque body at the D-011
    floor, and an undeclared node at the other D-011 default.
    """
    contracts = resolved(extract(sr.build_parity_graph()))

    assert contracts["declared_step"] == Annotations(
        input=("query",), output=("plan",), effect=("network",)
    )
    assert contracts["wrapped_step"] == Annotations(
        input=("query",), output=("plan",), effect=("write",)
    )
    assert contracts["search_tool"] is not None
    assert contracts["search_tool"].args_schema is not None
    assert contracts["opaque_step"] == Annotations(effect=("write",))
    assert contracts["plain_step"] == Annotations(pure=True)


def test_the_golden_is_the_canonical_form_of_the_ir_it_claims_to_be() -> None:
    """The committed bytes parse as JSON and carry the resolved contracts, not only a hash."""
    document = json.loads(golden("parity.canonical.json"))

    assert document["ir_version"] == "1.0"
    assert [node["id"] for node in document["nodes"]] == [
        "declared_step",
        "opaque_step",
        "plain_step",
        "search_tool",
        "wrapped_step",
    ]
    assert document["nodes"][0]["annotations"]["input"] == ["query"]


# ── WA-07 — the tripwire for the path this card lands ────────────────────────────────────

#: The guarded child. Network primitives raise from the first line, socket construction is
#: only counted until the imports are done (extraction must import the substrate to read its
#: classes), and then ``StateGraph.compile`` is taken away and every §3/§6 shape is resolved.
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
        raise AssertionError("a socket was created on the resolution path")


socket.socket = _CountSocket
socket.getaddrinfo = _record("getaddrinfo")
socket.gethostbyname = _record("gethostbyname")
socket.create_connection = _record("create_connection")

import gebra
from langgraph.graph.state import StateGraph
from tests.sample_workflows import sentinel_resolution as sr

graphs = {name: factory() for name, factory in sr.RESOLUTION_BUILDERS.items()}

assert attempts == [], attempts
assert sr.TRIPPED == [], sr.TRIPPED
socket.socket = _TripSocket
StateGraph.compile = _record("StateGraph.compile")

resolved = 0
for name, builder in graphs.items():
    envelope = gebra.extract(builder)
    assert envelope.ir.nodes, name
    envelope.graph_version()          # canonicalize and digest, still under the guard
    resolved += 1

assert resolved == %d, resolved
# Every armed surface: no node body, no wrapper, no tool implementation and no schema hook
# was reached — including the two the seam guards with `except Exception`, which is what this
# list exists to make visible.
assert sr.TRIPPED == [], sr.TRIPPED
# The one read §1 rule 3 licenses *is* performed: a schema that recorded being asked was.
assert sr.PROBED == ["ProbedArgs"], sr.PROBED
"""

_REPORT = "print(attempts)\n"


def _run_guarded(probe: str = "") -> subprocess.CompletedProcess[str]:
    body = _TRIPWIRE % len(sr.RESOLUTION_BUILDERS)
    return subprocess.run(
        [sys.executable, "-c", body + probe + _REPORT],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_contract_resolution_invokes_nothing_and_compiles_nothing() -> None:
    """The WA-07 claim for the path this card lands, in a fresh interpreter.

    This path is the first one that reads ``StateNodeSpec.runnable``, so it is the first that
    touches the *user's own callables* rather than the builder's declarative record — a
    wrapper chain, a tool's schema class, a function's ``__annotations__``. Four claims at
    once: nothing in any of those is called; ``StateGraph.compile`` is taken away before the
    first extraction, so §1 rule 2 is checked rather than reviewed; no name is resolved and no
    connection opened at any point; and no socket is even constructed while resolving.

    The child asserts its own counts and its own sentinel log, so a resolution pass that
    quietly stopped reaching the fixtures fails here rather than passing with nothing to prove.
    """
    result = _run_guarded()

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "[]", result.stdout
    assert "WA07-TRIP" not in result.stderr, result.stderr


@pytest.mark.parametrize(
    ("probe", "expected"),
    [
        ("sr.build_parity_graph().compile()\n", "StateGraph.compile was reached"),
        ("socket.socket()\n", "a socket was created"),
        ("socket.getaddrinfo('example.invalid', 80)\n", "getaddrinfo was reached"),
        ("socket.gethostbyname('example.invalid')\n", "gethostbyname was reached"),
        ("socket.create_connection(('example.invalid', 80))\n", "create_connection was reached"),
        ("sr.declared_step({})\n", "was invoked"),
        ("sr.search_tool.func('q')\n", "was invoked"),
        ("sr.RefusingArgs.model_json_schema()\n", "declines to describe itself"),
    ],
    ids=[
        "compile",
        "socket",
        "getaddrinfo",
        "gethostbyname",
        "create_connection",
        "node",
        "tool-impl",
        "refusing-schema",
    ],
)
def test_each_raiser_is_armed(probe: str, expected: str) -> None:
    """A tripwire nobody trips proves nothing — so every raiser gets its own control.

    All eight, and the last three are what this card adds: the node bodies, the tool
    implementation behind an ``args_schema``, and the schema hook whose *legitimate* refusal
    the seam catches. The controls run after the child's own assertions, so each one proves
    the raiser was live at the end of the very run that made the claim.
    """
    result = _run_guarded(probe)

    assert result.returncode != 0
    assert expected in result.stderr


def test_the_tripwire_covers_the_shapes_this_path_handles() -> None:
    """The claim above is only as wide as the table it quantifies over."""
    assert len(sr.RESOLUTION_BUILDERS) >= 8


def test_every_node_in_every_shape_fixture_is_armed() -> None:
    """All of them, not a sample: an unarmed fixture is a hole where the claim is strongest.

    An ``async def`` node is called through :func:`asyncio.run`, because calling one without
    awaiting it builds a coroutine and runs nothing — which would leave exactly those two
    fixtures unarmed while this test stayed green.
    """
    checked = 0

    for factory in sr.RESOLUTION_BUILDERS.values():
        for spec in factory().nodes.values():
            innermost = walk(spec.runnable).innermost
            target = getattr(innermost, "func", innermost)
            assert callable(target)
            with pytest.raises(sr.ResolutionSentinelError):
                if inspect.iscoroutinefunction(target):
                    asyncio.run(target({}))
                else:
                    target({})
            checked += 1

    assert checked >= 10
    del sr.TRIPPED[:]  # the calls above are the point; the autouse guard asserts on the rest


def test_the_contract_a_node_carries_is_never_rebuilt_by_the_walk() -> None:
    """§1's identity property, read from the other end: the walk returns what was attached.

    ``@gebra.contract`` "returns the function unchanged", and the resolution reads the value
    that decoration attached rather than reconstructing one — which is why a contract compares
    identical, not merely equal, across the walk.
    """
    declarations = walk(sr.build_declared_graph().nodes["declared_step"].runnable)

    assert declarations.contract is sr.declared_step.__gebra_contract__  # type: ignore[attr-defined]
    assert isinstance(declarations.contract, NodeContract)
