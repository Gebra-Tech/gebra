"""Extraction envelopes around hand-built IR — the engine's input, without an extractor.

:func:`~gebra.snapshot.engine.record` takes an
:class:`~gebra.extraction.envelope.ExtractionEnvelope` and reads three things off it: the IR,
the provenance source, and the extractor version. Building one by hand is what lets the policy
table below state *exactly* which component moved between two versions — a live workflow can
be edited into a shape, but a constructed IR pair is the shape.

The IR variants here are deliberately the same vocabulary
``tests/diff/test_workflow.py::CASES`` uses, one deliberate edit apiece, so that what this
suite calls "an F change" is what the diff engine and the version engine call one. The base
document is ``tests/store/hand_built.py``'s golden vector — IR-SPEC §6.5's worked example —
so the digests in play are the ones the frozen spec text pins.

Nothing here imports langgraph or reaches a live workflow object: every IR is built with the
model constructors (WA-07). The engine tests that *do* need a live object use the
travel-booking agent and its guarded child instead.
"""

from __future__ import annotations

from gebra.extraction.base import ObjectFamily
from gebra.extraction.envelope import ExtractedFrom, ExtractionEnvelope
from gebra.ir.models import Annotations, Node, NormalEdge, StateField, WorkflowIR
from tests.store.hand_built import golden_vector_ir

__all__ = [
    "envelope_of",
    "with_escalated_effect",
    "with_extra_node",
    "with_extra_state_key",
    "with_retyped_state_key",
]


def envelope_of(
    ir: WorkflowIR,
    *,
    source: str = "langgraph:StateGraph",
    extractor_version: str = "0.0.1.dev0",
    sidecar: str | None = None,
) -> ExtractionEnvelope:
    """An extraction envelope carrying ``ir`` — what ``gebra.extract()`` would have returned.

    The family is ``BUILDER`` throughout: nothing in the engine reads it (PD-012 fixed the
    store's ``extracted_from`` at four members, and the family is not one of them), and a
    fixture that varied it would suggest otherwise.
    """
    return ExtractionEnvelope(
        ir=ir,
        extracted_from=ExtractedFrom(
            source=source,
            family=ObjectFamily.BUILDER,
            extractor_version=extractor_version,
            sidecar=sidecar,
        ),
    )


def with_extra_node() -> WorkflowIR:
    """The golden vector plus one wired node — the S+F case (a vertex *and* a contract)."""
    base = golden_vector_ir()
    return base.model_copy(
        update={
            "nodes": (*base.nodes, Node(id="audit", annotations=Annotations(input=("result",)))),
            "edges": (
                *base.edges,
                NormalEdge(kind="normal", **{"from": "report"}, to="audit"),
            ),
        }
    )


def with_escalated_effect() -> WorkflowIR:
    """``act``'s effect class escalated — F alone, one of D-11's three canonical cases."""
    base = golden_vector_ir()
    act = next(node for node in base.nodes if node.id == "act")
    escalated = act.model_copy(
        update={
            "annotations": Annotations(
                input=("task",), output=("result",), effect=("billable", "irreversible")
            )
        }
    )
    return base.model_copy(
        update={"nodes": tuple(escalated if node.id == "act" else node for node in base.nodes)}
    )


def with_extra_state_key() -> WorkflowIR:
    """Σ plus one optional key — E alone, D-11's safe-extension case."""
    base = golden_vector_ir()
    return base.model_copy(
        update={"state": {**_state(base), "notes": StateField(type="str", optional=True)}}
    )


def with_retyped_state_key() -> WorkflowIR:
    """``result`` retyped — E alone, D-11's read-key-retype case."""
    base = golden_vector_ir()
    return base.model_copy(update={"state": {**_state(base), "result": "list[str]"}})


def _state(ir: WorkflowIR) -> dict[str, str | StateField]:
    """Σ as a mapping. ``state`` is optional in the model and present in every base here."""
    assert ir.state is not None
    return dict(ir.state)
