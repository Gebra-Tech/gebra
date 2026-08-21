"""What the *installed* substrate can do — the one place the suite branches on a version.

VERSION-COMPAT §3 runs this suite on three frozen langgraph/langchain-core pairs across
four Pythons. A fixture written against a builder API the cell's substrate does not have dies
at construction rather than testing anything, and an expectation written against one cell's
model defaults fails on the other two (PD-038 Findings 2–3). Both are portability
defects in the *suite*, never in the substrate and never in ``gebra`` — the extraction code
reads whatever surface is there.

Every version-conditional fixture, skip and expectation in the suite reads its predicate from
here, so "which minor introduced this?" is answered once, in a table, with the API named.
Each predicate ships a ``…_REASON`` string written to be read in a ``pytest -rs`` skip report:
it names the API and the minor that introduced it, so a skip states which capability is
missing rather than merely that something was skipped.

**No substrate code runs on import.** The versions come from ``importlib.metadata`` — the
installed *metadata*, never the packages themselves — which is how ``gebra.extraction.compat``
reads them too, and which keeps this module usable from fixtures that must stay import-safe
under WA-07.

The boundaries below were bisected for EX-17 over the published wheels of each line — the
stated release is the first sampled one carrying the surface, and the release before it in the
sample does not. ``tests/test_substrate.py`` re-derives every predicate from whatever is
actually installed, so a boundary wrong enough to answer differently on some tested cell fails
a test rather than silently mis-gating a fixture there. A boundary misplaced *between* two
adjacent cells' pins answers identically on all twelve blocking cells and is not falsifiable by
the matrix — which is why the stated minors carry their wheel-grep provenance rather than
standing on the suite alone.
"""

from __future__ import annotations

import re
from importlib import metadata

#: Leading ``major.minor.patch`` of a PEP 440 version, ignoring any pre/post/dev suffix. The
#: ``--pre`` matrix cell installs prereleases (``1.6.0a1``), and a prerelease of a line is
#: that line for gating purposes: it carries the line's APIs.
_RELEASE = re.compile(r"^(\d+)\.(\d+)\.(\d+)")


def _version(distribution: str) -> tuple[int, int, int]:
    """The installed ``distribution``'s release triple, or ``(0, 0, 0)`` if unparsable."""
    match = _RELEASE.match(metadata.version(distribution))
    if match is None:  # pragma: no cover - no published release in range spells otherwise
        return (0, 0, 0)
    return (int(match[1]), int(match[2]), int(match[3]))


#: The installed langgraph release, as a comparable triple.
LANGGRAPH_VERSION: tuple[int, int, int] = _version("langgraph")

#: The installed langchain-core release, as a comparable triple.
LANGCHAIN_CORE_VERSION: tuple[int, int, int] = _version("langchain-core")


# ── langgraph builder surfaces ───────────────────────────────────────────────────────────

#: ``StateGraph.set_node_defaults(...)`` — graph-level node defaults folded in by ``compile()``
#: (INTROSPECTION-SPEC §4.1). Absent from the 1.0 and 1.1 builders: calling it there raises
#: ``AttributeError: 'StateGraph' object has no attribute 'set_node_defaults'``.
HAS_NODE_DEFAULTS: bool = LANGGRAPH_VERSION >= (1, 2, 0)
NODE_DEFAULTS_REASON: str = (
    "needs StateGraph.set_node_defaults(...), introduced in langgraph 1.2.0; "
    f"installed langgraph is {'.'.join(map(str, LANGGRAPH_VERSION))}"
)

#: ``StateGraph.add_node(..., error_handler=...)`` and the compiled
#: ``node_error_handler_map`` it produces (INTROSPECTION-SPEC §4.1). The 1.0/1.1 builders
#: have neither — and, worse for a fixture, ``add_node`` swallows the unknown keyword through
#: its ``**kwargs`` rather than raising, so a graph built there is a plain node wearing the
#: fixture's name. Gate on this rather than on the build succeeding.
HAS_NODE_ERROR_HANDLER: bool = LANGGRAPH_VERSION >= (1, 2, 0)
NODE_ERROR_HANDLER_REASON: str = (
    "needs StateGraph.add_node(..., error_handler=...) and the compiled "
    "node_error_handler_map, introduced in langgraph 1.2.0; installed langgraph is "
    f"{'.'.join(map(str, LANGGRAPH_VERSION))}"
)


# ── langchain-core model surfaces ────────────────────────────────────────────────────────

#: ``BaseChatModel.bind(...)`` answering with ``_ChatModelBinding``, a ``RunnableBinding``
#: **subclass**, rather than a stock ``RunnableBinding``. Below this minor ``bind()`` returns
#: the stock class. Both are now admitted by exact type — INTROSPECTION-SPEC §7.4 (a) as amended
#: by DEC-21, implemented by EX-16 and enumerated in :mod:`gebra.extraction.stock` — so the model
#: is discovered under either, and the node-set difference this predicate used to describe is
#: closed: the same authored ``prompt | model.bind(...)`` now extracts to the same node set on
#: every cell of the matrix.
#:
#: **This predicate gates nothing** — it is a recorded fact with a test. It is what
#: ``tests/extraction/test_stock.py`` compares the resolved enumeration against, so that
#: "``_ChatModelBinding`` exists here" and "the enumeration resolved it here" cannot drift apart;
#: and the fixtures that pin the *decline* still declare their subclass directly rather than
#: reaching for ``bind()``, which no longer produces a declined shape at either end.
CORE_BINDS_TO_A_SUBCLASS: bool = LANGCHAIN_CORE_VERSION >= (1, 4, 0)
CHAT_MODEL_BINDING_REASON: str = (
    "needs BaseChatModel.bind(...) to answer with the _ChatModelBinding subclass, "
    "introduced in langchain-core 1.4.0; installed langchain-core is "
    f"{'.'.join(map(str, LANGCHAIN_CORE_VERSION))}"
)

#: ``BaseChatModel`` filling its ``metadata`` field with ``{"lc_versions": {...}}`` at
#: construction. Below this patch the field's default is ``None``, so INTROSPECTION-SPEC
#: §7.4 (c)'s "omitting ``None``-valued members" drops it from the config form entirely —
#: which is exactly §7.4 (e)'s ruled "a substrate minor release adding a model field with a
#: non-``None`` default moves ``config_digest``", observed from the other side.
CORE_FILLS_LC_VERSIONS_METADATA: bool = LANGCHAIN_CORE_VERSION >= (1, 4, 7)
LC_VERSIONS_METADATA_REASON: str = (
    "needs BaseChatModel to fill its metadata field with lc_versions, introduced in "
    "langchain-core 1.4.7; installed langchain-core is "
    f"{'.'.join(map(str, LANGCHAIN_CORE_VERSION))}"
)

__all__ = [
    "CHAT_MODEL_BINDING_REASON",
    "CORE_BINDS_TO_A_SUBCLASS",
    "CORE_FILLS_LC_VERSIONS_METADATA",
    "HAS_NODE_DEFAULTS",
    "HAS_NODE_ERROR_HANDLER",
    "LANGCHAIN_CORE_VERSION",
    "LANGGRAPH_VERSION",
    "LC_VERSIONS_METADATA_REASON",
    "NODE_DEFAULTS_REASON",
    "NODE_ERROR_HANDLER_REASON",
]
