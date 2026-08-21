"""Hand-built IR fixtures for the store tests — SD-01's "no extractor dependency".

Brief D-11's week-2 milestone is the one this card sits on: "snapshot writer/reader: IR →
YAML → IR round-trips on **hand-built IR fixtures** conforming to R-06's IR-SPEC (no live
extraction needed yet)". Everything here is therefore built with the IR model constructors,
and nothing in this module — or in any test that imports it — imports langgraph,
langchain-core, or :mod:`gebra.extraction`. The store's input is an IR *model*; there is no
user object anywhere in reach to invoke (WA-07).

:func:`golden_vector_ir` is IR-SPEC §6.5's worked micro-example, whose digest the spec pins
as **golden vector 001**. Using it as the store's principal fixture means the digest a
snapshot carries is checkable against the frozen spec text rather than against this suite's
own output.
"""

from __future__ import annotations

import hashlib
from typing import Any, Final

from gebra.ir.models import (
    Annotations,
    ConditionalEdge,
    Interrupts,
    Node,
    NormalEdge,
    RecursionLimit,
    Runtime,
    StateField,
    WorkflowIR,
)
from gebra.store import ExtractedFrom, Snapshot

#: The digest IR-SPEC §6.5 pins for :func:`golden_vector_ir` — golden vector 001 of the §1.3
#: conformance suite, computed by hand at the 2026-07-18 fix pass.
GOLDEN_VECTOR_DIGEST: Final = (
    "sha256:5db68464c736069f7213902a1f6cb566c70c623de32a754d42d2d8498e4ba69d"
)

#: Characters that are ordinary text in JSON and line breaks (or a BOM) in YAML 1.1. A
#: snapshot carrying one has to survive a round trip: PyYAML writes them raw inside a
#: single-quoted scalar and reads them back as breaks, which is a silent truncation the IR
#: surface dumper already corrects. The store inherits that correction rather than owning a
#: second copy of it, so this fixture is what holds the inheritance in place.
YAML_BREAK_CHARACTERS: Final = "\x85  ﻿"


def golden_vector_ir() -> WorkflowIR:
    """IR-SPEC §6.5's worked micro-example — three nodes, a witnessed self-loop.

    Its canonical digest is :data:`GOLDEN_VECTOR_DIGEST`.
    """
    return WorkflowIR(
        ir_version="1.0",
        entry="plan",
        finish="report",
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
            NormalEdge(kind="normal", **{"from": "plan"}, to="act"),
            ConditionalEdge(
                kind="conditional",
                **{"from": "act"},
                condition="done(result)",
                path_map={"done": "report", "redo": "act"},
            ),
        ),
        runtime=Runtime(
            recursion_limit=RecursionLimit(
                value=10, justification="redo loop bounded by review budget"
            )
        ),
    )


def minimal_ir() -> WorkflowIR:
    """The smallest thing the §2 model admits: one node, no edges, no state."""
    return WorkflowIR(
        ir_version="1.0",
        entry="only",
        finish="only",
        nodes=(Node(id="only"),),
        edges=(),
    )


def awkward_ir() -> WorkflowIR:
    """Every surface hazard the store has to carry: unicode, YAML break characters, foreign
    JSON Schema content, a collapsed and an object-form state value, a synthetic node id.

    Nothing here is exotic for its own sake — each member is a place where an emitter that
    cut a corner would lose or change content, and where the round trip is the check.
    """
    return WorkflowIR(
        ir_version="1.0",
        entry=("début", "seconde"),
        finish="fin",
        state={
            "résultat": "str",
            "notes": StateField(type="list[str]", reducer="operator.add", optional=True),
        },
        nodes=(
            Node(
                id="début",
                annotations=Annotations(
                    output=("résultat",),
                    args_schema={
                        "type": "object",
                        "properties": {"ville": {"type": "string", "default": None}},
                        "prefixItems": [{"type": "integer"}, {"type": "string"}],
                        "required": [],
                    },
                ),
            ),
            Node(id="seconde", annotations=Annotations(input=("résultat",))),
            Node(id="parent/%map[branche]", annotations=Annotations(pure=True)),
            Node(id="fin", annotations=Annotations(input=("notes",))),
        ),
        edges=(
            NormalEdge(kind="normal", **{"from": "début"}, to="fin"),
            NormalEdge(
                kind="normal",
                **{"from": "seconde"},
                to="fin",
                condition=f"état{YAML_BREAK_CHARACTERS}terminé — «prêt»?",
            ),
            NormalEdge(kind="normal", **{"from": "parent/%map[branche]"}, to="fin"),
        ),
        runtime=Runtime(
            recursion_limit=RecursionLimit(
                value=25, justification=f"borné{YAML_BREAK_CHARACTERS}par le budget"
            ),
            interrupts=Interrupts(before=("fin",)),
        ),
    )


def prompt_digest_of(body: bytes) -> str:
    """The ``prompt_digest`` a node bound to ``body`` would carry.

    DEC-10: "``prompt_digest`` = SHA-256 over the exact UTF-8 bytes of the prompt template
    (byte-exact, no normalization)", rendered per IR-SPEC §6.1 step 8. Spelled out here with
    :mod:`hashlib` rather than taken from :mod:`gebra.extraction`, so this fixture depends on
    no extractor: what the store is being shown to do is *carry* a digest, not compute one.
    """
    return "sha256:" + hashlib.sha256(body).hexdigest()


def prompt_bearing_ir(prompt: bytes, *, config: bytes = b"temperature=0") -> WorkflowIR:
    """Two nodes and one edge, with the first node carrying ``prompt``'s digest.

    The topology, the state schema and every other annotation are fixed, so two IRs from this
    function differ in exactly one place: the ``prompt_digest`` string (or, when ``config``
    moves instead, the ``config_digest`` string). That is what makes the D-025
    digest-inclusion demonstration a controlled one — a different ``graph_version`` can only
    have come through the digest that moved.

    ``config``'s digest stands in for INTROSPECTION §7.4's config projection, which is the
    extractor's to compute; as far as the store is concerned both slots are strings that
    ride inside the hash scope (IR-SPEC §6.4).
    """
    return WorkflowIR(
        ir_version="1.0",
        entry="ask",
        finish="answer",
        state={"question": "str", "reply": "str"},
        nodes=(
            Node(
                id="ask",
                annotations=Annotations(
                    input=("question",),
                    output=("reply",),
                    effect=("network",),
                    prompt_digest=prompt_digest_of(prompt),
                    config_digest=prompt_digest_of(config),
                ),
            ),
            Node(id="answer", annotations=Annotations(input=("reply",))),
        ),
        edges=(NormalEdge(kind="normal", **{"from": "ask"}, to="answer"),),
    )


def bodiless_ir() -> WorkflowIR:
    """:func:`prompt_bearing_ir`'s workflow with no digests at all — the opaque-body gap.

    Node bodies are opaque to the IR, so without the §3.6 digest slots two versions of this
    workflow differing only in prompt text are the *same document*. That is the collision
    decision D-025 exists to close, and it is shown rather than asserted:
    ``tests/store/test_store.py`` digests this IR and the one above and compares.
    """
    return WorkflowIR(
        ir_version="1.0",
        entry="ask",
        finish="answer",
        state={"question": "str", "reply": "str"},
        nodes=(
            Node(
                id="ask",
                annotations=Annotations(
                    input=("question",), output=("reply",), effect=("network",)
                ),
            ),
            Node(id="answer", annotations=Annotations(input=("reply",))),
        ),
        edges=(NormalEdge(kind="normal", **{"from": "ask"}, to="answer"),),
    )


def extracted_from(**overrides: Any) -> ExtractedFrom:
    """A fixed provenance record — fixed, because the store's determinism claim is about
    identical input producing identical bytes, and a clock read here would hide it."""
    fields: dict[str, Any] = {
        "source": "tests.store.hand_built:golden_vector_ir",
        "extractor_version": "0.0.1.dev0",
        "extracted_at": "2026-08-04T09:00:00Z",
    }
    fields.update(overrides)
    return ExtractedFrom(**fields)


def snapshot_of(ir: WorkflowIR, version: str = "1.0.0.0", **overrides: Any) -> Snapshot:
    """``ir`` wrapped in the envelope, with the digest computed from it."""
    return Snapshot.of(ir, version=version, extracted_from=extracted_from(**overrides))


#: Every hand-built IR, by the name a test parameterization shows.
ALL_IRS: Final = {
    "golden-vector": golden_vector_ir,
    "minimal": minimal_ir,
    "awkward": awkward_ir,
    "prompt-bearing": lambda: prompt_bearing_ir(b"Be terse."),
    "bodiless": bodiless_ir,
}
