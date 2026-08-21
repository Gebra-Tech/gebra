"""Seeded builder-script divergences — the card's negative box.

A drift suite whose pairs are all green proves nothing on its own: a comparison that accepted
everything would look exactly the same. So this module is the same mini builder script as
``tests/drift/builders/graph_well_formed/positive_01_linear_document_pipeline.py`` — the
simplest pair in the designated set — with **one** deliberate edit selectable per build.

:data:`SEEDS` names ten, and between them they touch every top-level IR field a builder can
move: ``entry``, ``finish``, ``state`` (membership, optionality), ``nodes`` (identity,
annotations — three different slots) and ``edges`` (presence, target).

**The baseline is what makes the negatives non-vacuous.** ``build_seeded("none")`` reproduces
the designated pair byte-for-byte, and the suite asserts that first. So each seeded failure is
attributable to its own one edit, and a comparison that had broken in some general way — a
loader that returned the wrong document, a builder that stopped extracting at all — would fail
the baseline rather than pass ten negatives for the wrong reason.

**A seeded divergence is a defect in the *script*, not in the fixture.** That is the direction
D-10's risk row is written in — "hand-written fixtures drift from what ``gebra.extract()``
actually emits" — and both directions of that drift land here as the same red: the fixture is
the fixed point, and anything that moves the extracted document away from it is caught.

WA-07: every body is armed exactly as the designated scripts' are (:mod:`tests.drift.sentinels`).
"""

from __future__ import annotations

from typing import Any, Final, Literal, TypedDict, get_args

from langgraph.graph import END, START, StateGraph

import gebra
from tests.drift.sentinels import trip

#: The fixture the baseline reproduces — the designated pair this module is seeded from.
FIXTURE: Final = "graph-well-formed/positive-01-linear-document-pipeline"

#: One deliberate edit, or ``"none"`` for the baseline.
Seed = Literal[
    "none",
    "moved-entry",
    "widened-finish",
    "dropped-edge",
    "retargeted-edge",
    "renamed-node",
    "dropped-effect-tag",
    "changed-idempotency-key",
    "undeclared-contract",
    "widened-input-schema",
    "extra-state-key",
]

#: Every seed except the baseline — what the negative box quantifies over.
SEEDS: Final[tuple[Seed, ...]] = tuple(seed for seed in get_args(Seed) if seed != "none")

#: Which IR region each seed moves, for the failure message and for the coverage assertion.
SEEDED_REGION: Final[dict[Seed, str]] = {
    "moved-entry": "entry",
    "widened-finish": "finish",
    "dropped-edge": "edges",
    "retargeted-edge": "edges",
    "renamed-node": "nodes",
    "dropped-effect-tag": "nodes",
    "changed-idempotency-key": "nodes",
    "undeclared-contract": "nodes",
    "widened-input-schema": "state",
    "extra-state-key": "state",
}


class DocumentState(TypedDict):
    """Σ — the baseline's state schema."""

    document_url: str
    document: str
    text: str
    summary: str
    archive_id: str


class WidenedState(TypedDict):
    """``extra-state-key``: the same Σ with one key more.

    Σ membership is seeded by **adding** rather than by removing, and the reason is a fact
    about the substrate worth recording: ``StateGraph`` reads a node callable's own parameter
    annotation as a schema too, so dropping a key from the graph's schema while every node
    body still annotates the wide one puts the key straight back and the "edit" is a no-op.
    Adding one is not recoverable that way, so the seed lands.
    """

    document_url: str
    document: str
    text: str
    summary: str
    archive_id: str
    audit_trail: str


class DocumentInput(TypedDict):
    """The baseline's input schema — the one ``optional: true`` key."""

    document_url: str


@gebra.effect("network")
@gebra.idempotent(key="document_url")
@gebra.contract(reads=["document_url"], writes=["document"])
def ingest_document(state: DocumentState) -> dict[str, Any]:
    trip("seeded.ingest_document")


@gebra.idempotent(key="document_url")
@gebra.contract(reads=["document_url"], writes=["document"])
def ingest_document_without_effect(state: DocumentState) -> dict[str, Any]:
    """``dropped-effect-tag``: the same node with its one ``effect`` tag not declared."""
    trip("seeded.ingest_document_without_effect")


@gebra.effect("network")
@gebra.idempotent(key="document")
@gebra.contract(reads=["document_url"], writes=["document"])
def ingest_document_wrong_key(state: DocumentState) -> dict[str, Any]:
    """``changed-idempotency-key``: idempotent on the key it writes, not the one it reads."""
    trip("seeded.ingest_document_wrong_key")


def ingest_document_undeclared(state: DocumentState) -> dict[str, Any]:
    """``undeclared-contract``: no decorator at all, so §4 inference fills the slots."""
    trip("seeded.ingest_document_undeclared")


@gebra.contract(pure=True, reads=["document"], writes=["text"])
def extract_text(state: DocumentState) -> dict[str, Any]:
    trip("seeded.extract_text")


@gebra.idempotent(key="text")
@gebra.contract(effects=[], reads=["text"], writes=["summary"])
def summarize_text(state: DocumentState) -> dict[str, Any]:
    trip("seeded.summarize_text")


@gebra.effect("write")
@gebra.idempotent(key="summary")
@gebra.contract(reads=["summary"], writes=["archive_id"])
def archive_summary(state: DocumentState) -> dict[str, Any]:
    trip("seeded.archive_summary")


def build_seeded(seed: Seed = "none") -> Any:
    """The designated pair's graph with exactly one edit applied — or none, for the baseline."""
    schema: Any = WidenedState if seed == "extra-state-key" else DocumentState
    builder: StateGraph[Any] = (
        StateGraph(schema)
        if seed == "widened-input-schema"
        else StateGraph(schema, input_schema=DocumentInput)
    )

    first = {
        "dropped-effect-tag": ingest_document_without_effect,
        "changed-idempotency-key": ingest_document_wrong_key,
        "undeclared-contract": ingest_document_undeclared,
    }.get(seed, ingest_document)
    entry_node = "fetch_document" if seed == "renamed-node" else "ingest_document"

    builder.add_node(entry_node, first)
    builder.add_node("extract_text", extract_text)
    builder.add_node("summarize_text", summarize_text)
    builder.add_node("archive_summary", archive_summary)

    builder.add_edge(START, "extract_text" if seed == "moved-entry" else entry_node)
    if seed != "dropped-edge":
        builder.add_edge(entry_node, "extract_text")
    builder.add_edge(
        "extract_text", "archive_summary" if seed == "retargeted-edge" else "summarize_text"
    )
    builder.add_edge("summarize_text", "archive_summary")
    builder.add_edge("archive_summary", END)
    if seed == "widened-finish":
        builder.add_edge("summarize_text", END)
    return builder
