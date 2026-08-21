"""Mini builder script for ``mixed/07-subgraph-leaked-key-collides-with-parallel-sibling``.

The one cross-property fixture in the designated set. Three constructs it adds: an
``optional: true`` key that **also** carries a reducer (``sources``), a node whose declared
``output`` is empty, and declared writes to ``scratch_notes`` — a key that is not in Σ at all,
carried as written.

The module name is prefixed ``fixture_`` because a ``mixed/`` stem begins with its serial and no
Python module may; :func:`tests.drift.pairs.script_for` states the rule and the suite checks it.
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, Final, TypedDict

from langgraph.graph import END, START, StateGraph

import gebra
from tests.drift.sentinels import trip

FIXTURE: Final = "mixed/07-subgraph-leaked-key-collides-with-parallel-sibling"


class ResearchState(TypedDict):
    """Σ — the whole state schema the fixture declares."""

    question: str
    sources: Annotated[list, operator.add]  # type: ignore[type-arg]  # the fixture's Σ type is the bare `list`, and a Σ type string is digest-bearing
    digest: str


class ResearchInput(TypedDict):
    """The graph's input schema — the fixture's two ``optional: true`` keys."""

    question: str
    sources: Annotated[list, operator.add]  # type: ignore[type-arg]  # the fixture's Σ type is the bare `list`, and a Σ type string is digest-bearing


@gebra.contract(pure=True, reads=["question"], writes=[])
def dispatch(state: ResearchState) -> dict[str, Any]:
    trip("mixed/07.dispatch")


@gebra.effect("network")
@gebra.idempotent(key="question")
@gebra.contract(reads=["question"], writes=["sources", "scratch_notes"])
def web_search(state: ResearchState) -> dict[str, Any]:
    trip("mixed/07.web_search")


@gebra.idempotent(key="question")
@gebra.contract(effects=[], reads=["question"], writes=["sources", "scratch_notes"])
def archive_subgraph(state: ResearchState) -> dict[str, Any]:
    trip("mixed/07.archive_subgraph")


@gebra.contract(pure=True, reads=["sources"], writes=["digest"])
def synthesize(state: ResearchState) -> dict[str, Any]:
    trip("mixed/07.synthesize")


def build() -> Any:
    """dispatch → {web_search, archive_subgraph} → synthesize."""
    builder = StateGraph(ResearchState, input_schema=ResearchInput)
    builder.add_node("dispatch", dispatch)
    builder.add_node("web_search", web_search)
    builder.add_node("archive_subgraph", archive_subgraph)
    builder.add_node("synthesize", synthesize)
    builder.add_edge(START, "dispatch")
    builder.add_edge("dispatch", "web_search")
    builder.add_edge("dispatch", "archive_subgraph")
    builder.add_edge("web_search", "synthesize")
    builder.add_edge("archive_subgraph", "synthesize")
    builder.add_edge("synthesize", END)
    return builder
