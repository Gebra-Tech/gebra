"""Per-condition rule copy — REPORT-FORMAT-SPEC Appendix A.3, written by CLI-03.

A.3 fixes the *shape* of the SARIF ``rules[]`` catalog (the emittable §0.4 registry entries,
in registry order, each with a level, a rank, the property bags and a ``shortDescription``)
and hands the prose itself here: "Rule copy is repo-authored prose and is held to §4.6: it
describes the condition, never a behavioral claim about a running agent. Writing it is
CLI-03's, under these constraints."

Three strings per condition, each with its own job and its own ≤1024-character budget:

* :attr:`RuleCopy.short_description` — A.3's own table cell, byte-for-byte. It is *not*
  re-invented here: ``tests/report/test_rules.py`` parses the table out of the spec and holds
  this module equal to it, so a divergence fails a test rather than shipping.
* :attr:`RuleCopy.full_description` — the owning property section's statement of the
  condition, as PROPERTY-CATALOG-SPEC states it, with the section named.
* :attr:`RuleCopy.help_text` — the remediation the owning section fixes, plus the pointer to
  that section (the shape Appendix C's worked example uses).

The copy rules of §4.6 bind every string here. In particular the P-02 and P-08 texts describe
what the *definition declares* — a bounded counter guard, a declared and justified
``recursion_limit``, an annotated variant, a pinned seed — and never what a run does; the
claim class never appears in a rule's prose, because A.2 keeps claim language out of
``message.text`` and in the property bag.

Nothing here imports langgraph, executes anything, or opens a socket (WA-07): this module is
a frozen table of strings plus lookups over it.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

from gebra.verify.base import ConditionId
from gebra.verify.conditions import CONDITION_REGISTRY, ConditionEntry

__all__ = [
    "MAX_RULE_TEXT",
    "RULE_COPY",
    "SARIF_RULE_ENTRIES",
    "RuleCopy",
    "rule_copy",
]

#: Appendix C's per-string copy budget ("≤ 1024 characters each — catalog copy budget per
#: condition"), restated by A.3 for ``fullDescription`` and ``help``. Enforced at import.
MAX_RULE_TEXT: Final = 1024


@dataclass(frozen=True)
class RuleCopy:
    """The three prose strings one SARIF rule carries (A.3)."""

    #: A.3's table cell, verbatim.
    short_description: str
    #: The owning property section's statement of the condition.
    full_description: str
    #: The remediation that section fixes, plus a pointer to it.
    help_text: str


_COPY: Final[Mapping[ConditionId, RuleCopy]] = MappingProxyType(
    {
        "node-unreachable-from-start": RuleCopy(
            short_description="Node unreachable from START",
            full_description=(
                "P-01 graph-well-formed, condition (i): every node of the workflow definition "
                "is reachable from START in the sentinel-augmented graph. This node is not, so "
                "nothing in the definition routes into it."
            ),
            help_text=(
                "Wire an edge — or a conditional path_map label — into the node, or remove the "
                "node from the definition. See PROPERTY-CATALOG-SPEC §P-01."
            ),
        ),
        "dead-end-node-not-wired-to-end": RuleCopy(
            short_description="Dead-end node is not wired to END",
            full_description=(
                "P-01 graph-well-formed, condition (ii): a node with no outgoing edge is wired "
                "to END through the definition's `finish` set. This node has neither an "
                "outgoing edge nor that wiring."
            ),
            help_text=(
                "Add an outgoing edge, or list the node in `finish` so its wiring to END is "
                "declared. See PROPERTY-CATALOG-SPEC §P-01."
            ),
        ),
        "path-map-target-undefined": RuleCopy(
            short_description="Conditional path_map names an undefined target",
            full_description=(
                "P-01 graph-well-formed, condition (iv): every target a conditional edge's "
                "path_map names resolves to a node of the definition or to the END sentinel. "
                "This label resolves to neither."
            ),
            help_text=(
                "Point the label at an existing node id (or at END), or add the node it names. "
                "See PROPERTY-CATALOG-SPEC §P-01."
            ),
        ),
        "cycle-without-termination-witness": RuleCopy(
            short_description="Simple cycle carries no declared termination witness",
            full_description=(
                "P-02 termination-witness, §2.1: every simple cycle of the definition carries a "
                "declared bound — a bounded counter guard with an exit edge (form a), a "
                "declared and justified graph-level recursion_limit (form b), or an annotated "
                "loop variant on a node of the cycle (form c). No simple cycle in this "
                "component carries one — or, under a strict policy naming the property, the "
                "component is covered only by the blanket form (b), which the location marks "
                "with `blanket_only: true` (TERMINATION-WITNESS-SPEC §6.1). The property "
                "records the presence of a declared witness in the definition; it observes no "
                "run."
            ),
            help_text=(
                "Declare a bounded counter guard whose exit label leaves the loop it gates, "
                "annotate a loop variant on a node of the cycle, or declare a justified "
                "runtime.recursion_limit. See PROPERTY-CATALOG-SPEC §P-02 and "
                "TERMINATION-WITNESS-SPEC §2."
            ),
        ),
        "counter-guard-without-exit-edge": RuleCopy(
            short_description="Bounded-counter guard has no exit edge out of its component",
            full_description=(
                "P-02 termination-witness, §2.1 form (a): a bounded counter guard discharges "
                "the cycles it gates only when one of its labels leaves the loop it gates — "
                "the gated back edge's natural loop, with the enclosing component as the "
                "fail-closed fallback where none is identified (DEC-23). None of this guard's "
                "labels does, so the bound it declares is never escaped."
            ),
            help_text=(
                "Wire one of the guard's path_map labels to a node outside the loop it "
                "gates, or to END. See PROPERTY-CATALOG-SPEC §P-02 and "
                "TERMINATION-WITNESS-SPEC §2.1."
            ),
        ),
        "read-key-never-written-on-path": RuleCopy(
            short_description="State key is read on a path where nothing writes it",
            full_description=(
                "P-04 dataflow-completeness, §4.1: every (reachable reader, read key) "
                "obligation is covered on every START→node path, either by the boundary state "
                "the path starts with or by an upstream writer on that path. On the path this "
                "finding anchors, neither covers the key."
            ),
            help_text=(
                "Write the key on the offending path, or declare it in the boundary state so "
                "every path starts covered. See PROPERTY-CATALOG-SPEC §P-04."
            ),
        ),
        "unprotected-effect-in-cycle": RuleCopy(
            short_description="Effect-carrying node in a cycle without binding protection",
            full_description=(
                "P-06 effect-safety, §6.1: a node declaring a trigger effect tag (`billable` or "
                "`irreversible`) that lies on a cycle declares binding protection — an "
                "idempotency key drawn from the node's declared reads, or a compensation hook "
                "naming a node of the definition. This node declares neither."
            ),
            help_text=(
                "Declare an idempotency key among the node's declared reads, or a compensation "
                "hook naming an existing node. See PROPERTY-CATALOG-SPEC §P-06."
            ),
        ),
        "unprotected-effect-in-retry-region": RuleCopy(
            short_description="Effect-carrying node in a retry region without binding protection",
            full_description=(
                "P-06 effect-safety, §6.1: a node declaring a trigger effect tag (`billable` "
                "or `irreversible`) that sits in a retry region declares binding protection — "
                "an idempotency key drawn from the node's declared reads, or a compensation "
                "hook naming a node of the definition. A retry region is either a declared "
                "node-level retry_policy or structural re-entry: the node lies on a cycle and "
                "is re-entered by a conditional label-edge, together with the `send` "
                "re-dispatch unit that edge reaches (§P-06.4 Phase 3, DEC-13). This node "
                "declares neither protection."
            ),
            help_text=(
                "Declare an idempotency key among the node's declared reads, or a "
                "compensation hook naming an existing node — or remove what puts the node in "
                "a retry region: its retry_policy, or the conditional label that re-enters it. "
                "See PROPERTY-CATALOG-SPEC §P-06."
            ),
        ),
        "irreversible-with-keyless-idempotent": RuleCopy(
            short_description="Irreversible effect declared idempotent without a key",
            full_description=(
                "P-06 effect-safety, §6.1: a node tagged `irreversible` that declares "
                "idempotence in the keyless boolean form names nothing to deduplicate on, so "
                "the declaration carries no key a replay could match. The condition is "
                "cycle-independent — it holds wherever the node sits."
            ),
            help_text=(
                "Replace `idempotent: true` with the keyed form naming a key among the node's "
                "declared reads, or drop the `irreversible` tag where it does not apply. See "
                "PROPERTY-CATALOG-SPEC §P-06."
            ),
        ),
        "deterministic-llm-seed-unpinned": RuleCopy(
            short_description="Determinism declared on an LLM-backed node with no pinned seed",
            full_description=(
                "P-08 determinism-replay, Appendix B §B.2 C-2: an LLM-backed node that declares "
                "determinism uses the object form with a pinned seed. This node declares the "
                "bare boolean form, so the declaration pins nothing. What is read is the "
                "declaration in the definition; a provider may answer differently on replay."
            ),
            help_text=(
                "Replace `deterministic: true` with `deterministic: {seed: <n>, temperature: "
                "0}` on the node's annotation. See PROPERTY-CATALOG-SPEC §P-08."
            ),
        ),
        "deterministic-llm-temperature-unpinned": RuleCopy(
            short_description="Determinism declared with a seed but no pinned temperature",
            full_description=(
                "P-08 determinism-replay, Appendix B §B.2 C-3: the object form of a determinism "
                "declaration carries `temperature: 0` beside its seed. This declaration omits "
                "the temperature or sets it nonzero, so the pinning is incomplete."
            ),
            help_text=(
                "Set `temperature: 0` beside the pinned seed on the node's annotation. See "
                "PROPERTY-CATALOG-SPEC §P-08."
            ),
        ),
        "orphan-node": RuleCopy(
            short_description="Node participates in no edge",
            full_description=(
                "P-01 graph-well-formed, condition (iii), reading A: every node participates in "
                "at least one edge, where membership in `entry` or `finish` counts as "
                "participation through the implicit sentinel wiring. This node participates in "
                "none of them."
            ),
            help_text=(
                "Wire the node into the graph, list it in `entry` or `finish`, or remove it. "
                "See PROPERTY-CATALOG-SPEC §P-01."
            ),
        ),
        "edge-target-undefined": RuleCopy(
            short_description="Edge endpoint names a node that does not exist",
            full_description=(
                "P-01 graph-well-formed, condition (iv): every `from` and `to` endpoint of a "
                "normal or send edge, and every `entry`/`finish` reference, resolves to a node "
                "of the definition. This reference resolves to none, and nothing is "
                "auto-created for it."
            ),
            help_text=(
                "Correct the endpoint to an existing node id, or add the node it names. See "
                "PROPERTY-CATALOG-SPEC §P-01."
            ),
        ),
    }
)

#: The rule copy, by condition ID. Keyed on the emittable §0.4 entries and no others — a rule
#: for a name no validator may emit "would advertise a check that does not exist" (A.3).
RULE_COPY: Final[Mapping[ConditionId, RuleCopy]] = _COPY

#: The §0.4 registry entries the catalog is built from: emittable only, in registry order
#: (A.3), "whether or not a given rule produced a result in this run".
SARIF_RULE_ENTRIES: Final[tuple[ConditionEntry, ...]] = tuple(
    entry for entry in CONDITION_REGISTRY.values() if entry.emittable
)


def rule_copy(condition: ConditionId) -> RuleCopy:
    """The three prose strings for ``condition``.

    Raises:
        KeyError: if ``condition`` is registered but not emittable, so no rule exists for it.
    """
    return RULE_COPY[condition]


def _check_table() -> None:
    """Hold the table to A.3 at import: one entry per emittable ID, every string in budget."""
    emittable = {entry.id for entry in SARIF_RULE_ENTRIES}
    if set(RULE_COPY) != emittable:
        missing = sorted(emittable - set(RULE_COPY))
        extra = sorted(set(RULE_COPY) - emittable)
        raise RuntimeError(
            "the SARIF rule catalog must carry exactly the emittable §0.4 condition IDs "
            f"(A.3); missing {missing}, non-emittable {extra}"
        )
    for condition, copy in RULE_COPY.items():
        for label, text in (
            ("shortDescription", copy.short_description),
            ("fullDescription", copy.full_description),
            ("help", copy.help_text),
        ):
            if not text or len(text) > MAX_RULE_TEXT:
                raise RuntimeError(
                    f"{condition}: {label} must be non-empty and at most {MAX_RULE_TEXT} "
                    f"characters (Appendix C copy budget); it is {len(text)}"
                )


_check_table()
