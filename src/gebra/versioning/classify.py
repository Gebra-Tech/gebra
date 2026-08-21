"""Which of S, F and E a change to a workflow touches — the comparator half of the engine.

Normative authority: brief D-11 In-Scope 2 states this card's job in one sentence —
"parser, comparator, and bump logic: **compare the working IR against the latest snapshot**
and bump S (topology), F (node/contract), and/or E (state schema) accordingly" — and D-11's
Context is where the three domains are spelled out:

* **S — topology**: "nodes; edges of kind normal | conditional | send; START/END wiring".
* **F — node/contract**: "``@gebra.contract(...)``, ``@gebra.pure``, ``@gebra.effect(...)``,
  ``@gebra.idempotent(key="...")``, ``@gebra.deterministic(seed=...)``" — the ``annotations``
  object of IR-SPEC §2.3 and §3.
* **E — state schema**: "state-schema Σ changes" — IR-SPEC §2.2's ``state`` mapping.

:data:`FIELD_COMPONENTS` is that prose turned into a table over the frozen core-IR field
vocabulary, and :func:`components_for_path` is the lookup. Five of its rows are dispositions
this card had to take, because the frozen text does not decide them:

* **``runtime`` → F.** The graph-level block (``recursion_limit``, ``interrupts``,
  ``checkpointer``) is neither topology nor Σ, and what is left of the three domains is
  contract: it is declared configuration one level up from a node, of the same kind as the
  slots beside it in ``annotations``. (It is *not* a witness-uniformity argument. P-02's
  three witness carriers deliberately do not share one component: form (a) is a
  bounded-counter guard in ``edges[].condition`` → S, form (b) is ``runtime.recursion_limit``
  → F, form (c) is ``nodes[].annotations.variant`` → F. A reader watching for
  witness changes watches S and F, and no single counter can be read as "witnesses".)
* **``nodes[].annotations`` → F sweeps in the six new-in-1.0 §3 slots** — ``args_schema``,
  ``retry_policy``, ``variant``, ``compensation``, ``prompt_digest``, ``config_digest``.
  D-11's F enumeration is the five decorator surfaces, and it predates those slots; they are
  contract content on a node, so they land where the rest of ``annotations`` lands. The
  consequence worth stating: **a prompt-body edit bumps F**, because decision D-025 put
  ``prompt_digest`` inside the hash scope and the digest it moves is a node's.
* **``edges[].condition`` → S**, by the ``edges`` row rather than a row of its own. A guard
  is declared content (IR-SPEC §2.4) and so has a colourable claim to F, but it is what an
  edge *routes on* — rewriting it changes where the workflow goes, which is the reason S
  exists. It is the one member of ``edges`` where this was a choice.
* **``ir_version`` → no component.** IR-SPEC §8: "Two migration regimes, never conflated.
  P-12 ``evolution-safety`` classifies **workflow migrations** … This section governs
  **format migrations** — diffs between IR *schemas*." A V.S.F.E label counts changes to a
  workflow, so an IR-format bump is not one of its business. (In ``ir_version`` 1.0 the
  field is a ``Literal["1.0"]``, so the row is unreachable rather than merely unused.)
* **Bumps are derived from canonical field slices, not "via P-12 diff classes"** — the route
  IR-SPEC §4.1's parenthetical and the field ledger §7 gloss for ``version``. P-12
  ``evolution-safety`` is out of Phase-0 scope (SOW §8), so its classes do not exist to
  derive from; what is decidable without it is which *domain* moved, which is what S, F and
  E are defined over in the first place.

And one overlap in the frozen text, resolved: D-11 lists "nodes" inside S's parenthetical
while naming F "node/contract". The split taken here is **presence and identity → S,
contract → F**, which means adding or removing a node moves *both* counters — the topology
gained a vertex and the contract set gained a member (empty, if the node carries none). An
id rename is the same case, because IR-SPEC §5.3 makes a rename a new identity rather than
a modification ("Renaming a node … is a **new identity**; lineage across such changes is
the job of the V.S.F.E diff layer"). That is why the table maps a path to a *set*: at
``nodes[].id`` the answer is genuinely both.

**The comparison runs on the canonical form, not on the models.** :func:`canonical_view`
parses back what :func:`~gebra.ir.canonical.canonical_bytes` emits, every slice is cut out
of that, and two slices are compared as **bytes through the same emitter**
(:func:`component_bytes`), never as Python values. IR-SPEC §6.2 normalizes authored array
order away and §6.3 normalizes representations (a singleton ``entry`` list to a scalar, a
bare state type-string and its object form onto one shape, an empty optional array onto
absence), so reusing the §6 walk rather than re-deriving it buys the property that matters:
**two IRs with equal ``graph_version`` change no component, and two IRs with different
``graph_version`` change at least one.** A version engine that disagreed with the digest in
the second direction would put two workflow contents under one label — and since PD-012
makes the label a file name, under one file.

That second direction is why the comparison is by bytes. IR-SPEC §1.2 makes the canonical
bytes the identity of content ("a single differing byte in canonical form is
non-conformance"), and Python equality is strictly coarser than it: ``True == 1`` and
``1 == 1.0``. That is not hypothetical here — ``annotations.args_schema`` is a JSON Schema
carried verbatim (``dict[str, Any]``, IR-SPEC §3.1), the one place in ir 1.0 where the JSON
*type* at a path is unconstrained, so editing ``{"const": true}`` to ``{"const": 1}`` moves
the digest while ``==`` sees no change at all.

What this module is *not* is the diff engine. It reports which counters move, and nothing
about what changed: no added/removed/rewired sets, no witnesses, no safe/breaking verdict.
Those belong to :mod:`gebra.diff` — which reports the topology, contract and state-schema
deltas and derives its bump class from them, against this table — and to P-12, which SOW §8
defers out of Phase 0 entirely.

Nothing in this module imports langgraph, opens a socket, or executes anything (WA-07).
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any, Final

from gebra.ir.canonical import canonical_bytes, canonical_foreign_bytes
from gebra.ir.models import WorkflowIR
from gebra.versioning.models import Component, Version

__all__ = [
    "FIELD_COMPONENTS",
    "canonical_view",
    "changed_components",
    "component_bytes",
    "component_slice",
    "components_for_path",
    "next_version",
]

_TOPOLOGY: Final = frozenset({Component.S})
_CONTRACT: Final = frozenset({Component.F})
_SCHEMA: Final = frozenset({Component.E})
_IDENTITY: Final = frozenset({Component.S, Component.F})

#: The S/F/E definition over the frozen core-IR field vocabulary (IR-SPEC §2.1–§3): which
#: components a change at a field moves. Keyed by field path from the document root with
#: array indices left out — ``("nodes", "id")``, never ``("nodes", 0, "id")``. A path is
#: classified by its **longest matching prefix**, so this table stays at the depth where the
#: answer changes: everything under ``edges`` is topology and everything under
#: ``nodes[].annotations`` is contract, neither needing a row per member.
#:
#: The values are *sets* because one path genuinely moves two counters: a node's identity is
#: its presence in the topology **and** the key its contract hangs from, so adding, removing
#: or renaming a node moves S and F together (see the module docstring). An empty set means
#: "no V.S.F.E component" and has exactly one row, ``ir_version``.
FIELD_COMPONENTS: Final[Mapping[tuple[str, ...], frozenset[Component]]] = {
    ("ir_version",): frozenset(),
    ("entry",): _TOPOLOGY,
    ("finish",): _TOPOLOGY,
    ("edges",): _TOPOLOGY,
    # The array itself — a node arriving or leaving — and the id that is its identity. Both
    # rows carry the same answer; the second is kept because it is where the S half of it
    # comes from, and a reader looking up `nodes[].id` should not have to infer that.
    ("nodes",): _IDENTITY,
    ("nodes", "id"): _IDENTITY,
    ("nodes", "annotations"): _CONTRACT,
    ("state",): _SCHEMA,
    ("runtime",): _CONTRACT,
}


def components_for_path(path: Sequence[str]) -> frozenset[Component]:
    """The V.S.F.E components a change at a core-IR field moves — possibly none, possibly two.

    ``path`` is a field path from the document root with array indices omitted, matched by
    longest prefix against :data:`FIELD_COMPONENTS`::

        components_for_path(("edges", "condition"))            # {S}
        components_for_path(("nodes", "id"))                   # {S, F}
        components_for_path(("nodes", "annotations", "pure"))  # {F}
        components_for_path(("state",))                        # {E}
        components_for_path(("ir_version",))                   # frozenset()

    This is the surface :mod:`gebra.diff` reads when it maps a diff delta onto a bump class:
    one table, consulted, rather than two implementations of the same three sentences.

    Raises:
        KeyError: if no prefix of ``path`` is a core-IR field — including the empty path,
            which names the whole document rather than a field. The ``ir_version`` 1.0
            field set is closed (IR-SPEC §2.1, frozen by DEC-09), so an unknown path is a
            caller's mistake and not a document's.
    """
    for stop in range(len(path), 0, -1):
        prefix = tuple(path[:stop])
        if prefix in FIELD_COMPONENTS:
            return FIELD_COMPONENTS[prefix]
    raise KeyError(
        f"{tuple(path)!r} is not a core-IR field path; the ir_version 1.0 field set is "
        f"{sorted({name for (name, *_rest) in FIELD_COMPONENTS})}"
    )


def canonical_view(ir: WorkflowIR) -> dict[str, Any]:
    """``ir``'s canonical form as a JSON tree — IR-SPEC §6.1 steps 2–6, parsed back.

    The document this returns is the one the ``graph_version`` digest is taken over, so
    anything §6.2/§6.3 normalizes away (authored array order, a singleton ``entry`` list, a
    state value's object-versus-scalar surface) is already gone. Going through the emitted
    bytes rather than re-walking the models is deliberate: there is one canonical walk in
    this package, and a comparator that used a second one would be a second opinion about
    what counts as a change.

    A parsed tree is a place to *cut slices*, not a place to compare them —
    :func:`component_bytes` is what compares. Typed as a plain JSON object rather than as
    :data:`~gebra.ir.canonical.Json`, because that is what it is on the way back in — a tree
    whose shape comes from the emitter that produced it rather than from this signature.

    Raises:
        CanonicalizationError: if ``ir`` carries a value the canonical form refuses (a
            non-NFC identifier, a non-finite number, an integer outside ±(2⁵³−1)). Such a
            document has no digest, so it has no version either.
    """
    view: dict[str, Any] = json.loads(canonical_bytes(ir))
    return view


def component_slice(view: Mapping[str, Any], component: Component) -> dict[str, Any]:
    """The part of a canonical ``view`` that ``component`` counts changes to.

    The three slices between them determine the whole canonical document except
    ``ir_version``; ``nodes[].id`` appears in two of them, which is the "presence → S,
    contract → F" split of the module docstring showing through — an added node is a change
    to both.

    Compare slices with :func:`component_bytes`, not with ``==``: this is a tree of parsed
    JSON, and Python equality does not distinguish ``true`` from ``1``.

    Raises:
        ValueError: for :attr:`Component.V`, which no workflow change derives.
    """
    nodes: list[Any] = view.get("nodes", [])
    if component is Component.S:
        return {
            "entry": view.get("entry"),
            "finish": view.get("finish"),
            "edges": view.get("edges"),
            "nodes": [node.get("id") for node in nodes],
        }
    if component is Component.F:
        return {
            "nodes": [[node.get("id"), node.get("annotations")] for node in nodes],
            "runtime": view.get("runtime"),
        }
    if component is Component.E:
        return {"state": view.get("state")}
    raise ValueError(
        "V is not derived from a workflow change: the frozen package defines S, F and E "
        "and leaves V to the caller (SOW §1; brief D-11 In-Scope 2)"
    )


def component_bytes(view: Mapping[str, Any], component: Component) -> bytes:
    """A component's slice of ``view``, serialized — the value the comparison compares.

    Through :func:`~gebra.ir.canonical.canonical_foreign_bytes`, the same RFC 8785 emitter
    the digest goes through, so two slices are equal exactly when their canonical bytes are
    — the identity IR-SPEC §1.2 uses, rather than the coarser one Python's ``==`` offers
    (``True == 1``; see the module docstring on ``args_schema``).

    An absent member is spelled ``None`` in a slice and is dropped by the emitter's
    null-normalization, which keeps it distinct from an *empty* one: a workflow with no
    ``runtime`` block serializes to ``{}`` where one with an empty block serializes to
    ``{"runtime":{}}``.

    Raises:
        ValueError: for :attr:`Component.V`, as :func:`component_slice`.
    """
    return canonical_foreign_bytes(component_slice(view, component))


def changed_components(before: WorkflowIR, after: WorkflowIR) -> frozenset[Component]:
    """Which of S, F and E differ between two IRs — the bump-category selection.

    The comparison is by canonical content, so it answers "did this domain change", not
    "was this document authored differently"::

        changed_components(v1, v1_with_nodes_listed_in_another_order)  # frozenset()
        changed_components(v1, v1_with_a_new_edge)                     # {S}
        changed_components(v1, v1_with_a_node_marked_pure)             # {F}
        changed_components(v1, v1_with_a_new_state_key)                # {E}
        changed_components(v1, v1_with_a_node_added)                   # {S, F}

    :attr:`Component.V` is never in the result — see the module docstring.

    Raises:
        CanonicalizationError: if either document has no canonical form (and therefore no
            digest to be a version of).
    """
    before_view = canonical_view(before)
    after_view = canonical_view(after)
    return frozenset(
        component
        for component in Component.derived()
        if component_bytes(before_view, component) != component_bytes(after_view, component)
    )


def next_version(current: Version, before: WorkflowIR, after: WorkflowIR) -> Version:
    """``current``, bumped for every component that differs between ``before`` and ``after``.

    The engine's one-call surface: ``current`` is the label of the snapshot being compared
    against — the store's *current* version, for :mod:`gebra.snapshot`, which SD-01's index
    does not require to be the newest row — ``before`` is that snapshot's IR and ``after`` is
    the working one. An unchanged workflow
    comes back with the same version — whether it is re-snapshot at all is
    :mod:`gebra.snapshot`'s idempotency policy, and whether it is written under a fresh label
    is the caller's.

    Raises:
        CanonicalizationError: as for :func:`changed_components`.
        VersionFormatError: with reason ``TOO_LONG`` if the bumped label could no longer be
            a snapshot's file name.
    """
    return current.bump(*changed_components(before, after))
