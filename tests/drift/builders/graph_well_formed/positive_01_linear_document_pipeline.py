"""Mini builder script for ``graph-well-formed/positive-01-linear-document-pipeline``.

The minimal well-formed topology: a strictly linear four-node chain, normal edges only, one
graph-input key. ``summarize_text`` declares ``effects=[]`` rather than leaving the slot open —
the fixture's node carries neither ``effect`` nor ``pure``, and an open slot is what §4 shallow
inference fills.
"""

from __future__ import annotations

from typing import Any, Final, TypedDict

from langgraph.graph import END, START, StateGraph

import gebra
from tests.drift.sentinels import trip

FIXTURE: Final = "graph-well-formed/positive-01-linear-document-pipeline"


class DocumentState(TypedDict):
    """Σ — the whole state schema the fixture declares."""

    document_url: str
    document: str
    text: str
    summary: str
    archive_id: str


class DocumentInput(TypedDict):
    """The graph's input schema — exactly the fixture's one ``optional: true`` key."""

    document_url: str


@gebra.effect("network")
@gebra.idempotent(key="document_url")
@gebra.contract(reads=["document_url"], writes=["document"])
def ingest_document(state: DocumentState) -> dict[str, Any]:
    trip("graph-well-formed/positive-01.ingest_document")


@gebra.contract(pure=True, reads=["document"], writes=["text"])
def extract_text(state: DocumentState) -> dict[str, Any]:
    trip("graph-well-formed/positive-01.extract_text")


@gebra.idempotent(key="text")
@gebra.contract(effects=[], reads=["text"], writes=["summary"])
def summarize_text(state: DocumentState) -> dict[str, Any]:
    trip("graph-well-formed/positive-01.summarize_text")


@gebra.effect("write")
@gebra.idempotent(key="summary")
@gebra.contract(reads=["summary"], writes=["archive_id"])
def archive_summary(state: DocumentState) -> dict[str, Any]:
    trip("graph-well-formed/positive-01.archive_summary")


def build() -> Any:
    """ingest → extract → summarize → archive."""
    builder = StateGraph(DocumentState, input_schema=DocumentInput)
    builder.add_node("ingest_document", ingest_document)
    builder.add_node("extract_text", extract_text)
    builder.add_node("summarize_text", summarize_text)
    builder.add_node("archive_summary", archive_summary)
    builder.add_edge(START, "ingest_document")
    builder.add_edge("ingest_document", "extract_text")
    builder.add_edge("extract_text", "summarize_text")
    builder.add_edge("summarize_text", "archive_summary")
    builder.add_edge("archive_summary", END)
    return builder
