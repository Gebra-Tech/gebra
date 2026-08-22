"""Recorded surface inventories + the soft-assertion machinery (VERSION-COMPAT §3).

**What a soft assertion is.** §3: "Where a row says *warning*, that is a paired **soft
assertion** — an exact-set compare against the recorded surface inventory alongside the ⊇
hard assertion; a soft-only failure keeps the cell green, emits a CI annotation, and
auto-opens a version-gap issue. Warnings never live only in logs." This module is the
recorded-inventory half and the collection half of that sentence: :func:`soft_exact_set`
compares an observed member set against the inventory recorded for the *installed*
substrate line and, on any difference, records a :class:`SoftDivergence` — it never raises,
so the test (and therefore the cell) stays green. The package ``conftest.py`` emits every
collected divergence at the end of the run: a ``::warning`` workflow command under GitHub
Actions — which lands in the run's annotations pane, not only the log — and a plain
terminal section everywhere else. Auto-opening the version-gap issue from that annotation
is GOV-07's card; the ``DRIFT-SOFT-DIVERGENCE`` line format below is the stable seam it
consumes.

**What is recorded, and per what key.** One entry per drift-test surface, keyed by the
installed owner distribution's ``(major, minor)`` release line — the granularity A2 §3
observed additive churn at ("additive node-spec fields land in minors"). The recorded sets
were read off each frozen cell's pinned substrate with :func:`member_names` /
:func:`public_instance_attrs` at GOV-05 landing for tests 1-6 and at GOV-06 landing for
tests 7-12 (evidence in each card's artifacts); a set is a *recording of what is*, never a
claim about what should be — the should-claims are the tests' hard ⊇ assertions. An
installed line with **no** recorded entry (a future minor, or the ``--pre`` cell resolving
a new line) is itself a soft divergence: the honest reading of "this substrate line has
never been inventoried", surfaced without blocking anything.

**Document-shaped surfaces ride the same seam.** §3 row 7's soft half is *full-dict
equality* of the rendered jsonschemas — a document, not a member set. Rather than a second
divergence channel, :func:`flatten_documents` encodes a document losslessly as a set of
leaf-path atoms (``input.title="ResearchBrief"``), so document equality **is** atom-set
equality and the ordinary :func:`soft_exact_set` machinery — collection, the stable line,
the gained/lost sentence — applies unchanged. The recorded side is kept as a readable
document literal and flattened at module load.

Updating a recorded set (or adding a line) is the soft half of the §4 ceiling-extension
path: it lands in a commit citing the drift-suite run that observed the new set, beside the
version-gap issue the annotation opened — never as a quiet edit to make an annotation go
away.

WA-07: this module reads type metadata (``dataclasses.fields``, ``_fields``, ``__slots__``,
``vars``) and calls nothing on any substrate object.
"""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from tests import substrate

#: Surface owners — which installed distribution's release line keys the recorded sets.
LANGGRAPH: Final = "langgraph"
LANGCHAIN_CORE: Final = "langchain-core"

#: The stable, machine-readable prefix GOV-07's issue automation greps for.
DIVERGENCE_MARKER: Final = "DRIFT-SOFT-DIVERGENCE"


def member_names(surface: object) -> frozenset[str]:
    """The declared member-name set of a substrate surface object, however it is built.

    One cascade, documented so a recorded set means one thing: dataclass fields, else
    ``NamedTuple._fields``, else ``__slots__`` collected over the MRO, else the public
    instance-``vars`` names. Only metadata is read — nothing on the object is called.
    """
    if dataclasses.is_dataclass(surface) and not isinstance(surface, type):
        return frozenset(field.name for field in dataclasses.fields(surface))
    fields = getattr(type(surface), "_fields", None)
    if fields is not None:
        return frozenset(str(name) for name in fields)
    slots: list[str] = []
    for klass in type(surface).__mro__:
        declared = getattr(klass, "__slots__", ())
        slots.extend((declared,) if isinstance(declared, str) else tuple(declared))
    if slots:
        return frozenset(slots)
    return public_instance_attrs(surface)


def public_instance_attrs(surface: object) -> frozenset[str]:
    """The unprefixed instance-attribute names — the conventionally-stable surface (§2)."""
    return frozenset(name for name in vars(surface) if not name.startswith("_"))


def flatten_documents(documents: Mapping[str, object]) -> frozenset[str]:
    """A mapping of JSON-shaped documents as leaf-path atoms — set equality ⇔ doc equality.

    Each top-level key prefixes its document's leaf paths (``input.properties.topic.type``);
    list members carry their index (``input.required[0]``); every leaf value is spelled via
    ``json.dumps``, so ``"true"`` and ``true`` stay distinct; an empty container is itself a
    leaf. Faithful because paths encode position exactly — with the one guard that a mapping
    key containing a path delimiter is refused rather than silently aliased.
    """
    atoms: set[str] = set()
    _flatten_into(atoms, documents)
    return frozenset(atoms)


def _flatten_into(atoms: set[str], node: object, path: str = "") -> None:
    if isinstance(node, Mapping):
        if not node and path:
            atoms.add(f"{path}={{}}")
            return
        for key, value in node.items():
            name = str(key)
            if "." in name or "[" in name or "=" in name:
                raise ValueError(f"unencodable document key {name!r} under {path!r}")
            _flatten_into(atoms, value, f"{path}.{name}" if path else name)
        return
    if isinstance(node, (list, tuple)):
        if not node:
            atoms.add(f"{path}=[]")
            return
        for index, value in enumerate(node):
            _flatten_into(atoms, value, f"{path}[{index}]")
        return
    atoms.add(f"{path}={json.dumps(node, sort_keys=True)}")


@dataclass(frozen=True)
class SurfaceInventory:
    """One drift surface's recorded exact member sets, per owner release line."""

    owner: str
    """Which distribution's release line keys :attr:`recorded` — the surface's owner."""
    recorded: Mapping[tuple[int, int], frozenset[str]]
    """Observed member set per ``(major, minor)`` line of the owner, at recording time."""


#: The full jsonschema document both row-7 getters rendered for the fixture state
#: (``tests.version_drift.workflows.ResearchBrief``) on every frozen line and every tested
#: Python at GOV-06 landing — kept as the readable document; the inventory entry flattens
#: it. Identical for input and output today; a line that renders them apart records two.
_ROW7_RENDERED_SCHEMA: Final[dict[str, object]] = {
    "properties": {
        "attempts": {"title": "Attempts", "type": "integer"},
        "sources": {"items": {"type": "string"}, "title": "Sources", "type": "array"},
        "topic": {"title": "Topic", "type": "string"},
    },
    "required": ["topic", "attempts", "sources"],
    "title": "ResearchBrief",
    "type": "object",
}

#: The compiled Pregel's public instance-attribute set on the 1.0 and 1.1 lines — shared
#: between their entries below; the 1.2 entry is this plus its two additions.
_PREGEL_ATTRS_1_0: Final[frozenset[str]] = frozenset(
    {
        "builder",
        "cache",
        "cache_policy",
        "channels",
        "checkpointer",
        "config",
        "context_schema",
        "debug",
        "input_channels",
        "interrupt_after_nodes",
        "interrupt_before_nodes",
        "name",
        "nodes",
        "output_channels",
        "retry_policy",
        "schema_to_mapper",
        "step_timeout",
        "store",
        "stream_channels",
        "stream_eager",
        "stream_mode",
        "trigger_to_nodes",
    }
)

#: The recorded inventories, one per drift-test surface. Lines (1, 0)/(1, 1)/(1, 2) for
#: langgraph and (1, 1)/(1, 3)/(1, 5) for langchain-core are the three frozen matrix
#: cells' pins (PD-030 §C3); every set below was observed on that cell's installed
#: substrate at GOV-05 landing (tests 1-6) or GOV-06 landing (tests 7-12).
INVENTORIES: Final[Mapping[str, SurfaceInventory]] = {
    # Test 1 — StateNodeSpec's declared fields (A2 §3: additive churn lands here).
    "state-node-spec-fields": SurfaceInventory(
        owner=LANGGRAPH,
        recorded={
            (1, 0): frozenset(
                {
                    "cache_policy",
                    "defer",
                    "ends",
                    "input_schema",
                    "metadata",
                    "retry_policy",
                    "runnable",
                }
            ),
            (1, 1): frozenset(
                {
                    "cache_policy",
                    "defer",
                    "ends",
                    "input_schema",
                    "metadata",
                    "retry_policy",
                    "runnable",
                }
            ),
            (1, 2): frozenset(
                {
                    "cache_policy",
                    "defer",
                    "ends",
                    "error_handler_node",
                    "input_schema",
                    "is_error_handler",
                    "metadata",
                    "retry_policy",
                    "runnable",
                    "timeout",
                }
            ),
        },
    ),
    # Test 2 — BranchSpec's declared fields.
    "branch-spec-fields": SurfaceInventory(
        owner=LANGGRAPH,
        recorded={
            (1, 0): frozenset({"ends", "input_schema", "path"}),
            (1, 1): frozenset({"ends", "input_schema", "path"}),
            (1, 2): frozenset({"ends", "input_schema", "path"}),
        },
    ),
    # Test 3 — the builder's public instance attributes (the wiring store itself).
    "state-graph-instance-attrs": SurfaceInventory(
        owner=LANGGRAPH,
        recorded={
            (1, 0): frozenset(
                {
                    "branches",
                    "channels",
                    "compiled",
                    "context_schema",
                    "edges",
                    "input_schema",
                    "managed",
                    "nodes",
                    "output_schema",
                    "schemas",
                    "state_schema",
                    "waiting_edges",
                }
            ),
            (1, 1): frozenset(
                {
                    "branches",
                    "channels",
                    "compiled",
                    "context_schema",
                    "edges",
                    "input_schema",
                    "managed",
                    "nodes",
                    "output_schema",
                    "schemas",
                    "state_schema",
                    "waiting_edges",
                }
            ),
            (1, 2): frozenset(
                {
                    "branches",
                    "channels",
                    "compiled",
                    "context_schema",
                    "edges",
                    "input_schema",
                    "managed",
                    "nodes",
                    "output_schema",
                    "schemas",
                    "state_schema",
                    "waiting_edges",
                }
            ),
        },
    ),
    # Test 4 — the drawable Node/Edge shapes (langchain-core's surface, not langgraph's).
    "drawable-node-fields": SurfaceInventory(
        owner=LANGCHAIN_CORE,
        recorded={
            (1, 1): frozenset({"data", "id", "metadata", "name"}),
            (1, 3): frozenset({"data", "id", "metadata", "name"}),
            (1, 5): frozenset({"data", "id", "metadata", "name"}),
        },
    ),
    "drawable-edge-fields": SurfaceInventory(
        owner=LANGCHAIN_CORE,
        recorded={
            (1, 1): frozenset({"conditional", "data", "source", "target"}),
            (1, 3): frozenset({"conditional", "data", "source", "target"}),
            (1, 5): frozenset({"conditional", "data", "source", "target"}),
        },
    ),
    # Test 5 — Send's declared members. A2 §3's "additive `timeout` field, recent" observed
    # exactly: absent through the 1.0/1.1 lines, present from 1.2.
    "send-members": SurfaceInventory(
        owner=LANGGRAPH,
        recorded={
            (1, 0): frozenset({"arg", "node"}),
            (1, 1): frozenset({"arg", "node"}),
            (1, 2): frozenset({"arg", "node", "timeout"}),
        },
    ),
    # Test 6 — RetryPolicy's declared fields (the six; A2 §3 row).
    "retry-policy-fields": SurfaceInventory(
        owner=LANGGRAPH,
        recorded={
            (1, 0): frozenset(
                {
                    "backoff_factor",
                    "initial_interval",
                    "jitter",
                    "max_attempts",
                    "max_interval",
                    "retry_on",
                }
            ),
            (1, 1): frozenset(
                {
                    "backoff_factor",
                    "initial_interval",
                    "jitter",
                    "max_attempts",
                    "max_interval",
                    "retry_on",
                }
            ),
            (1, 2): frozenset(
                {
                    "backoff_factor",
                    "initial_interval",
                    "jitter",
                    "max_attempts",
                    "max_interval",
                    "retry_on",
                }
            ),
        },
    ),
    # Test 7 — the full rendered jsonschema documents (§3 row 7's designated soft half:
    # "full-dict equality"), as flatten_documents atoms. Both getters rendered the same
    # document for the fixture state on every frozen line at GOV-06 landing; the pydantic
    # that renders it is pinned transitively per cell (2.13.4 — no independent axis).
    "input-output-jsonschema": SurfaceInventory(
        owner=LANGGRAPH,
        recorded={
            (1, 0): flatten_documents(
                {"input": _ROW7_RENDERED_SCHEMA, "output": _ROW7_RENDERED_SCHEMA}
            ),
            (1, 1): flatten_documents(
                {"input": _ROW7_RENDERED_SCHEMA, "output": _ROW7_RENDERED_SCHEMA}
            ),
            (1, 2): flatten_documents(
                {"input": _ROW7_RENDERED_SCHEMA, "output": _ROW7_RENDERED_SCHEMA}
            ),
        },
    ),
    # Test 8 — the warning classes the legacy `config_schema=` construction emits. The
    # class is the substrate's own deprecation vocabulary; a rename that stays inside
    # DeprecationWarning keeps the hard half green and lands here as an annotation.
    "config-schema-warning-classes": SurfaceInventory(
        owner=LANGGRAPH,
        recorded={
            (1, 0): frozenset({"LangGraphDeprecatedSinceV10"}),
            (1, 1): frozenset({"LangGraphDeprecatedSinceV10"}),
            (1, 2): frozenset({"LangGraphDeprecatedSinceV10"}),
        },
    ),
    # Test 9 — the two carried channel classes' declared members (slots over the MRO):
    # the reducer channel and the plain-value channel the extractor's Σ read identifies.
    "binop-channel-members": SurfaceInventory(
        owner=LANGGRAPH,
        recorded={
            (1, 0): frozenset({"key", "operator", "typ", "value"}),
            (1, 1): frozenset({"key", "operator", "typ", "value"}),
            (1, 2): frozenset({"key", "operator", "typ", "value"}),
        },
    ),
    "last-value-channel-members": SurfaceInventory(
        owner=LANGGRAPH,
        recorded={
            (1, 0): frozenset({"key", "typ", "value"}),
            (1, 1): frozenset({"key", "typ", "value"}),
            (1, 2): frozenset({"key", "typ", "value"}),
        },
    ),
    # Test 10 — `add_node`'s signature parameter names: the surface the 1.2-era additive
    # kwargs landed on, and the one reading that distinguishes "accepted" from "swallowed
    # through **kwargs" (tests/substrate.py). `self` and `kwargs` are part of the read.
    "add-node-params": SurfaceInventory(
        owner=LANGGRAPH,
        recorded={
            (1, 0): frozenset(
                {
                    "action",
                    "cache_policy",
                    "defer",
                    "destinations",
                    "input_schema",
                    "kwargs",
                    "metadata",
                    "node",
                    "retry_policy",
                    "self",
                }
            ),
            (1, 1): frozenset(
                {
                    "action",
                    "cache_policy",
                    "defer",
                    "destinations",
                    "input_schema",
                    "kwargs",
                    "metadata",
                    "node",
                    "retry_policy",
                    "self",
                }
            ),
            (1, 2): frozenset(
                {
                    "action",
                    "cache_policy",
                    "defer",
                    "destinations",
                    "error_handler",
                    "input_schema",
                    "kwargs",
                    "metadata",
                    "node",
                    "retry_policy",
                    "self",
                    "timeout",
                }
            ),
        },
    ),
    # Test 11 — the RunnableSequence's public instance attributes: the composition members
    # the extractor's LCEL walk reads (langchain-core's surface, the hottest-churn
    # distribution on the matrix).
    "runnable-sequence-instance-attrs": SurfaceInventory(
        owner=LANGCHAIN_CORE,
        recorded={
            (1, 1): frozenset({"first", "last", "middle", "name"}),
            (1, 3): frozenset({"first", "last", "middle", "name"}),
            (1, 5): frozenset({"first", "last", "middle", "name"}),
        },
    ),
    # Test 12 — the compiled Pregel's public instance attributes: the compiled surface the
    # P-13 carrier read lives on. The 1.2 line added `node_error_handler_map` and
    # `stream_transformers`; the set is compile-option-independent (observed identical with
    # and without checkpointer/interrupt gates on every frozen cell).
    "compiled-pregel-instance-attrs": SurfaceInventory(
        owner=LANGGRAPH,
        recorded={
            (1, 0): _PREGEL_ATTRS_1_0,
            (1, 1): _PREGEL_ATTRS_1_0,
            (1, 2): _PREGEL_ATTRS_1_0 | {"node_error_handler_map", "stream_transformers"},
        },
    ),
}


@dataclass(frozen=True)
class SoftDivergence:
    """One soft-only divergence: an exact-set mismatch that keeps the cell green."""

    test: str
    surface: str
    owner: str
    installed: str
    line: tuple[int, int]
    recorded: frozenset[str] | None
    observed: frozenset[str]

    def message(self) -> str:
        """One line, machine-readable — the GOV-07 seam, stable by contract."""
        recorded = "unrecorded-line" if self.recorded is None else ",".join(sorted(self.recorded))
        observed = ",".join(sorted(self.observed))
        return (
            f"{DIVERGENCE_MARKER} test={self.test} surface={self.surface} "
            f"owner={self.owner} installed={self.installed} "
            f"recorded={recorded} observed={observed}"
        )

    def sentence(self) -> str:
        """The human-readable reading of the same fact."""
        if self.recorded is None:
            return (
                f"{self.surface}: no inventory is recorded for {self.owner} line "
                f"{self.line[0]}.{self.line[1]} (installed {self.installed}) — this line "
                "has never been inventoried"
            )
        gained = sorted(self.observed - self.recorded)
        lost = sorted(self.recorded - self.observed)
        parts: list[str] = []
        if gained:
            parts.append(f"gained {gained}")
        if lost:
            parts.append(f"lost {lost}")
        return (
            f"{self.surface}: the installed {self.owner} {self.installed} "
            f"{' and '.join(parts)} against the recorded line-"
            f"{self.line[0]}.{self.line[1]} inventory"
        )


#: Every soft divergence this run observed, in observation order. The package
#: ``conftest.py`` reports them at terminal-summary time; tests never read this.
DIVERGENCES: list[SoftDivergence] = []


def _installed(owner: str) -> tuple[tuple[int, int], str]:
    """The installed release line and full version string of ``owner``."""
    version = (
        substrate.LANGGRAPH_VERSION if owner == LANGGRAPH else substrate.LANGCHAIN_CORE_VERSION
    )
    return (version[0], version[1]), ".".join(map(str, version))


def soft_documents_exact(test: str, surface: str, documents: Mapping[str, object]) -> None:
    """The document-shaped soft compare: flatten, then the ordinary exact-set collect.

    An observed document the atom encoding cannot represent (a mapping key carrying a path
    delimiter — see :func:`flatten_documents`) is itself **recorded as a divergence**
    rather than raised: §3 designates this compare soft, so no rendering shape a future
    substrate produces may harden it into a cell failure. The strict raise stays on
    :func:`flatten_documents` itself, where it guards *our* recorded literals at module
    load.
    """
    try:
        observed = flatten_documents(documents)
    except ValueError as error:
        observed = frozenset({f"unencodable-document={error}"})
    soft_exact_set(test, surface, observed)


def soft_exact_set(test: str, surface: str, observed: frozenset[str]) -> None:
    """The paired soft assertion: exact-set compare, collected — never raised (§3).

    A mismatch (or an installed line with no recorded inventory) records a divergence and
    returns; the calling test stays green. The hard assertions beside this call are the
    ones allowed to fail the cell.
    """
    entry = INVENTORIES[surface]
    line, installed = _installed(entry.owner)
    recorded = entry.recorded.get(line)
    if recorded is not None and observed == recorded:
        return
    DIVERGENCES.append(
        SoftDivergence(
            test=test,
            surface=surface,
            owner=entry.owner,
            installed=installed,
            line=line,
            recorded=recorded,
            observed=observed,
        )
    )
