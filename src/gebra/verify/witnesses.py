"""The wedge-five witness models and the §0.3 ``Witness`` union.

A witness is what a property returns when it **passes**: structured, re-checkable evidence,
plus the mandatory caveats the claim class demands — never a prose summary and never a bare
pass bit (§0.3). §0 fixes only the pattern (a ``kind``-discriminated union, A6 PC-2) and the
in-corpus ``kind`` vocabulary; each property section's I/O contract declares its own member
and joins the union. The five wedge members are here:

======================== ====================== ==================================
``kind``                 model                  contract
======================== ====================== ==================================
``well-formedness``      P-01                   §1.3 — the 5-key form (DEC-11 pin 1)
``termination``          P-02                   §2.3 + TERMINATION-WITNESS-SPEC §6.2
``dataflow``             P-04                   §4.3
``effect-safety``        P-06                   §6.3
``determinism``          P-08                   §8.3
======================== ====================== ==================================

Membership grows with the catalog: the ``kind`` vocabulary §0.3 records also holds
``signature`` and ``evolution`` for the sections that are not drafted yet, and a new member
joins :data:`Witness` when its §P-nn.3 contract lands.

Honest-claims discipline (Verification-Properties §1.1; TERMINATION-WITNESS-SPEC §7): a
witness records that the *definition* carries what the property asks of it. P-02's witness
records that every simple cycle carries a declared bound — the attested components (a
justification, a variant measure, a counter's progress) are recorded and trusted, never
checked, and no field here means a run halts.
"""

from __future__ import annotations

from typing import Annotated, Literal, TypeAlias

from pydantic import Field, model_validator

from gebra.verify.base import (
    DisplayNodeRef,
    NodeId,
    ReportModel,
    SetCompared,
)
from gebra.verify.locations import AnyLocation, EdgeLocation, NodeLocation

__all__ = [
    "CounterGuardSource",
    "CycleCensus",
    "DataflowCoverage",
    "DataflowWitness",
    "DeterminismClaim",
    "DeterminismWitness",
    "DischargeScope",
    "EffectSafetyWitness",
    "GuardEdgeRef",
    "P06EffectRecord",
    "RecursionLimitDecl",
    "RecursionLimitSource",
    "Region",
    "TerminationWitness",
    "VariantDecl",
    "VariantSource",
    "WellFormednessWitness",
    "Witness",
    "WitnessElement",
    "WitnessInventoryEntry",
    "WitnessNote",
    "WitnessNoteKind",
    "WitnessSource",
]


# ── P-01 graph-well-formed (§1.3) ────────────────────────────────────────────────────────


class WellFormednessWitness(ReportModel):
    """P-01's pass witness — the 5-key form (ratified at walkthrough #2, DEC-11 pin 1).

    The two empty tuples are not padding: they are the re-checkable evidence that
    conditions (iii) and (iv) were evaluated and found clean, which a compact pass bit
    would lose. Both are empty by construction on a pass — a non-empty one would have
    filled ``failure`` instead — so the declared types stay the general ones of the §0.3
    stub rather than an empty-tuple type.
    """

    kind: Literal["well-formedness"]
    #: Sorted, UTF-16 code-unit order (ledger §6).
    reachable_from_start: tuple[NodeId, ...]
    #: Predecessors of ``__end__``, sorted.
    terminal_nodes: tuple[NodeId, ...]
    orphan_nodes: tuple[NodeId, ...]
    unresolved_targets: tuple[str, ...]


# ── P-02 termination-witness (§2.3; TERMINATION-WITNESS-SPEC §6.2/§6.3) ──────────────────


class GuardEdgeRef(ReportModel):
    """One conditional guard's expanded label-edge — the identity is (guard, label)."""

    source: NodeId
    label: str


class CounterGuardSource(ReportModel):
    """Form (a): a bounded counter in Σ plus a conditional exit (T-W-SPEC §2.1)."""

    guard_edge: GuardEdgeRef
    counter_key: str
    bound: int


class RecursionLimitDecl(ReportModel):
    """The graph-level ``runtime.recursion_limit`` slot (ledger §1)."""

    value: int
    justification: str


class RecursionLimitSource(ReportModel):
    """Form (b): a declared, justified ``recursion_limit`` (T-W-SPEC §2.2).

    A blanket witness — a global step budget, not a per-loop bound, and the weakest of the
    three forms (the §2.4 rank rule is (a) > (c) > (b)).
    """

    recursion_limit: RecursionLimitDecl


class VariantDecl(ReportModel):
    """The node-level ``variant`` annotation slot (ledger §3)."""

    key: str
    measure: str


class VariantSource(ReportModel):
    """Form (c): an annotated loop variant on the carrier node (T-W-SPEC §2.3).

    Attested, not decided: the declared well-founded measure is recorded and trusted.
    """

    variant: VariantDecl


#: Which form supplied an inventory entry's evidence, resolved by its required fields.
WitnessSource: TypeAlias = Annotated[
    CounterGuardSource | RecursionLimitSource | VariantSource,
    Field(union_mode="left_to_right"),
]

#: The S-element an entry discharges: an expanded label-edge for form (a), the carrier node
#: for form (c). Form (b) has none — it is a blanket over E.
WitnessElement: TypeAlias = Annotated[EdgeLocation | NodeLocation, Field(discriminator="kind")]

#: What an entry discharges (T-W-SPEC §6.2). The empty tuple is the spec's explicit empty
#: marker — "a structured empty set, never a string" — for a **vacuous** element: a form-(c)
#: carrier annotated on a node that lies on no cycle. Declared content is surfaced; no
#: finding of any severity follows from it.
DischargeScope: TypeAlias = Literal["all-simple-cycles-through-element", "blanket"] | tuple[()]

#: The closed note vocabulary of §2.3 — structured, display-adjacent, and deliberately
#: **not** §0.4 condition IDs. ``scc-covered-only-by-recursion-limit`` is the WARNING-grade
#: one: it is promotable at the gate under ``--gebra-strict=termination-witness``, and the
#: record is unchanged by promotion (§0.2). ``counter-key-not-qualified`` is the fifth
#: member, ratified at DEC-23 (2026-08-04, PD-037 Q2): the §4 path-1 R1 near-miss — a
#: recognized guard whose counter-ref is absent from keys(Σ) or not integer-compatible.
WitnessNoteKind: TypeAlias = Literal[
    "scc-covered-only-by-recursion-limit",
    "recursion-limit-without-justification",
    "variant-key-not-in-state",
    "counter-key-not-qualified",
    "cycle-census-capped",
]


class WitnessNote(ReportModel):
    """A structured P-02 advisory — §2.3's closed note vocabulary, on either result path.

    ``kind`` is normative — §2.3 closes the vocabulary to the five members above (the fifth,
    ``counter-key-not-qualified``, ratified at DEC-23). So is the carriage: notes ride
    :attr:`TerminationWitness.notes` on the pass path and, unconditionally, the §0.3
    ``Failure.notes``/``CoFailure.notes`` channel whenever the P-02 result is ``fail``
    (DEC-23, PD-037 Q2) — a failing P-02 never silently drops a qualification-failure note.

    ``severity`` is ``warning`` or absent, never wider: §2.3 makes notes "never
    gate-bearing" and §0.2 describes only WARNING-grade notes reaching strict promotion, so
    a FATAL note is not a shape the catalog has. Carrying it per record — rather than
    leaving a consumer to know which kinds are WARNING-grade — mirrors how §0.3 pins
    :class:`~gebra.verify.report.Advisory`.

    The evidence fields are per kind, each the §2.3/§2.4 payload for its note and absent on
    every other kind:

    * ``locations`` — ``scc-covered-only-by-recursion-limit``: the residual non-trivial
      SCCs that only the blanket form covers, each with its representative cycle (§2.4's
      "a structured value listing every residual non-trivial SCC").
    * ``guard_edge``/``identifier``/``declared_type`` — ``counter-key-not-qualified``: the
      near-missed guard's gated label-edge, the unmatched counter-ref and, for the
      wrong-type case only, the declared type expression — "the same evidence
      ``CounterQualification`` computes" (§2.3, DEC-23).
    * ``node``/``key`` — ``variant-key-not-in-state``: the carrier node and the missing key
      (T-W-SPEC §4 path 4).
    * ``recursion-limit-without-justification`` and ``cycle-census-capped`` carry no
      payload: the kind is the whole statement (the census note's overflow wording is
      VAL-08's `decisions_to_implementer`, per PD-011).
    """

    kind: WitnessNoteKind
    severity: Literal["warning"] | None = None
    locations: tuple[AnyLocation, ...] | None = None
    #: ``counter-key-not-qualified``: the recognized guard's gated label-edge (DEC-23).
    guard_edge: GuardEdgeRef | None = None
    #: ``counter-key-not-qualified``: the counter-ref that failed to qualify (§4 path 1).
    identifier: str | None = None
    #: ``counter-key-not-qualified``, wrong-type case only: the declared type expression.
    declared_type: str | None = None
    #: ``variant-key-not-in-state``: the carrier node (§4 path 4).
    node: NodeId | None = None
    #: ``variant-key-not-in-state``: the ``variant.key`` absent from keys(Σ).
    key: str | None = None


class CycleCensus(ReportModel):
    """The optional full simple-cycle list (§2.5; T-W-SPEC §6.3).

    Present **only** when the census completed under the abort cap B — enumeration stops at
    circuit B+1, and an aborted census omits the list and reports itself as the
    ``cycle-census-capped`` note instead. So ``exhaustive`` is ``True`` wherever a census
    exists at all; there is no partial census.
    """

    exhaustive: Literal[True]
    cycles: tuple[tuple[NodeId, ...], ...]


class WitnessInventoryEntry(ReportModel):
    """One S-element of the witness inventory (T-W-SPEC §6.2).

    The form fixes the rest of the entry, so the mapping is enforced rather than
    documented: form (a) discharges an expanded label-edge from a counter guard, form (c)
    discharges its carrier node from a variant annotation, and form (b) is a blanket with
    no element at all.
    """

    form: Literal["a", "b", "c"]
    element: WitnessElement | None = None
    source: WitnessSource
    discharges: DischargeScope

    @model_validator(mode="after")
    def _form_fixes_element_and_source(self) -> WitnessInventoryEntry:
        expected: dict[str, tuple[type[ReportModel] | None, type[ReportModel]]] = {
            "a": (EdgeLocation, CounterGuardSource),
            "b": (None, RecursionLimitSource),
            "c": (NodeLocation, VariantSource),
        }
        element_type, source_type = expected[self.form]
        if element_type is None:
            if self.element is not None:
                raise ValueError(
                    "form (b) is a blanket witness over E and discharges no element; "
                    "drop `element` (TERMINATION-WITNESS-SPEC §6.2)"
                )
        elif not isinstance(self.element, element_type):
            raise ValueError(
                f"form ({self.form}) discharges an element of type {element_type.__name__}, "
                f"not {type(self.element).__name__} (TERMINATION-WITNESS-SPEC §6.2)"
            )
        if not isinstance(self.source, source_type):
            # ValueError, not TypeError (TRY004): pydantic converts a ValueError raised in a
            # model validator into a ValidationError, and lets a TypeError escape as itself.
            raise ValueError(  # noqa: TRY004
                f"form ({self.form}) is sourced from a {source_type.__name__}, not "
                f"{type(self.source).__name__} (TERMINATION-WITNESS-SPEC §2.1-§2.3)"
            )
        if (self.discharges == "blanket") != (self.form == "b"):
            raise ValueError(
                "`discharges` reads 'blanket' for form (b) and names the element's simple "
                "cycles for forms (a) and (c) (TERMINATION-WITNESS-SPEC §6.2)"
            )
        if self.discharges == () and self.form != "c":
            raise ValueError(
                "only a form-(c) carrier can be vacuous: a form-(a) element always lies on "
                "a cycle, since its gated edge runs within an SCC "
                "(TERMINATION-WITNESS-SPEC §6.2, §4)"
            )
        return self


class TerminationWitness(ReportModel):
    """P-02's pass witness — the inventory and the acyclicity certificate (T-W-SPEC §6.2).

    Those two are the whole mandatory output: a cycle census is never required to pass, and
    ``cycles`` carries one only when the capped enumeration completed (§6.3).

    The certificate is a topological order of ``G \\ S``: any consumer re-checks it in
    O(|N|+|E|) with no trust in the checker, which is what makes this witness evidence
    rather than an assertion. It carries the display sentinels START/END like every other
    report-level path list (§0.3).

    What is claimed: every simple cycle of the graph carries a **declared bound**, recorded
    per S-element in ``inventory``. Semantic termination is not claimed — the guards are
    opaque Python (T-W-SPEC §1.1/§7).
    """

    kind: Literal["termination"]
    inventory: tuple[WitnessInventoryEntry, ...]
    certificate: tuple[DisplayNodeRef, ...]
    notes: tuple[WitnessNote, ...] = ()
    cycles: CycleCensus | None = None


# ── P-04 dataflow-completeness (§4.3) ────────────────────────────────────────────────────


class DataflowCoverage(ReportModel):
    """One (reachable reader, read key) obligation and the writers that cover it.

    ``satisfied_by`` carries the display sentinel START exactly when the key is in the
    boundary set I₀; every START→node simple path contains at least one member.
    """

    node: NodeId
    key: str
    satisfied_by: tuple[DisplayNodeRef, ...]


class DataflowWitness(ReportModel):
    """P-04's pass witness — one coverage entry per reachable (reader, read key)."""

    kind: Literal["dataflow"]
    coverage: Annotated[
        tuple[DataflowCoverage, ...],
        SetCompared("PROPERTY-CATALOG-SPEC §4.3: coverage order is not normative"),
    ]


# ── P-06 effect-safety (§6.3) ────────────────────────────────────────────────────────────

#: Where an effect-carrying node sits, for the protection lattice (§6.3).
Region: TypeAlias = Literal["retry", "cycle", "acyclic"]


class P06EffectRecord(ReportModel):
    """One trigger-tagged node, its region, and how it is protected there (§6.3).

    Protection is **binding**, not mere presence: an idempotency key that is not among the
    node's declared inputs, and a compensation hook that names no node, are not protection.
    A record therefore names the key or the hook it was satisfied by.
    """

    node: NodeId
    effect: Annotated[
        tuple[str, ...],
        SetCompared("PROPERTY-CATALOG-SPEC §6.3: `effect` tuples are set-compared"),
    ]
    region: Region
    #: The anchor cycle; absent iff the node lies on no cycle.
    cycle: tuple[NodeId, ...] | None = None
    protection: Literal["idempotency_key", "compensation_hook", "none_required"]
    #: Present iff ``protection == "idempotency_key"``.
    key: str | None = None
    #: Present iff ``protection == "compensation_hook"``.
    hook: NodeId | None = None


class EffectSafetyWitness(ReportModel):
    """P-06's pass witness — the cycle inventory and one record per trigger-tagged node."""

    kind: Literal["effect-safety"]
    #: One canonical anchor per non-trivial SCC.
    cycles: tuple[tuple[NodeId, ...], ...]
    #: One record per trigger-tagged node, by node id.
    effects: tuple[P06EffectRecord, ...]


# ── P-08 determinism-replay (§8.3) ───────────────────────────────────────────────────────


class DeterminismClaim(ReportModel):
    """One node's declared determinism claim and the evidence for it (§8.3)."""

    node: NodeId
    llm_backed: bool
    #: LLM-backed claims: the pinned seed.
    seed: int | None = None
    #: LLM-backed claims: always 0.
    temperature: float | None = None
    #: LLM-backed claims: the D-013 policy echo.
    divergence_handling: Literal["logged"] | None = None
    #: Non-LLM claims.
    basis: Literal["pure-local-computation"] | None = None
    #: Non-LLM claims.
    pinning_required: Literal[False] | None = None


class DeterminismWitness(ReportModel):
    """P-08's pass witness — the per-node claims, with the mandatory provider caveat.

    The caveat is required exactly when some claim is LLM-backed and forbidden otherwise
    (§8.3). That conditional is the honest-claims boundary in model form: a pinned seed and
    a pinned temperature are what the *definition* declares, and a provider is free to
    return something else on replay (Appendix B §B.1).
    """

    kind: Literal["determinism"]
    #: Canonical node order; may be empty (a vacuous pass).
    claims: tuple[DeterminismClaim, ...]
    caveat: Literal["provider-seed-reproducibility-not-guaranteed"] | None = None
    claim_class: Literal["heuristic"]

    @model_validator(mode="after")
    def _caveat_iff_llm_backed(self) -> DeterminismWitness:
        if any(claim.llm_backed for claim in self.claims) != (self.caveat is not None):
            raise ValueError(
                "caveat present iff some claim is llm_backed (PROPERTY-CATALOG-SPEC §8.3)"
            )
        return self


# ── The §0.3 witness union ───────────────────────────────────────────────────────────────

#: The five wedge members, discriminated on ``kind`` (A6 PC-2; §0.3).
Witness: TypeAlias = Annotated[
    WellFormednessWitness
    | TerminationWitness
    | DataflowWitness
    | EffectSafetyWitness
    | DeterminismWitness,
    Field(discriminator="kind"),
]
