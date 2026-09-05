"""P-02 ``termination-witness`` — witness assembly and verification (PROPERTY-CATALOG-SPEC §2).

**Claim class DEFENSIBLE (witness presence), severity FATAL** (§2.2), with two condition IDs —
``cycle-without-termination-witness`` and ``counter-guard-without-exit-edge`` (distinct per
DEC-05 D4) — both read off the §0.4 registry at emission, never restated here.

What P-02 decides, and the one boundary it never crosses. The question is TERMINATION-WITNESS-
SPEC §1.1's: **does every simple cycle of the label-expanded graph carry a declared bound?**
Witness presence is decidable over the IR and is all this module claims. Semantic termination is
never claimed — guards are opaque Python and that is the halting problem; the attested
components (a variant's decrease, a justification's adequacy, a counter's progress) are
recorded and trusted, never checked (§1.1/§7). Every string this module emits states witness
presence only.

The semantics implemented here are T-W-SPEC §§2–6 as amended by **DEC-23** (2026-08-04,
PD-037 — the VAL-D5 ruling), whose four P-02 rulings this module realizes directly:

* **Q1 — only the gated then-label edge discharges.** A qualifying form-(a) guard puts exactly
  one element into S: the expanded label-edge of its then-label $\\hat{l}$ (§3 R6). The
  else-label is an implicit negation context and any other declared label is not bounded by the
  comparison — neither ever enters S, even when it re-enters the SCC (§4's over-discharge ban).
  The gated edge's own re-entry test stays **SCC-relative** ($\\mathrm{target}(\\hat{l}) \\in
  \\mathrm{SCC}_G(u)$ — the is-it-on-a-cycle test); it does not narrow to the natural loop.
* **Q2 — the R1 near-miss is surfaced, on both result paths.** A recognized guard whose
  counter-ref is absent from keys(Σ) or not integer-compatible emits the structured note
  ``counter-key-not-qualified`` (§4 path 1 — "a misspelled key never silently shrinks
  coverage"), mapped from :class:`~gebra.verify.guards.CounterQualification` through the
  explicit table in :func:`_qualification_note` — never mechanically, since that class's
  ``outcome`` vocabulary is diagnostic, not the note vocabulary. Notes ride
  ``TerminationWitness.notes`` on a pass and the §0.3 ``Failure.notes`` channel
  unconditionally on a fail.
* **Q4 — the D4 exit test is loop-relative.** A qualifying guard discharges only if some
  ``path_map`` label targets outside $\\mathrm{natural\\_loop}_G(g)$ — the back-edge/dominator
  natural loop (Aho, Lam, Sethi, Ullman, *Compilers*, 2nd ed., §9.6) rooted at the header
  dominating the gated re-entry — with the original $\\mathrm{SCC}_G(u)$ test as the required
  fail-closed fallback when no single header dominates (irreducible region). This is what lets
  ``positive-04``'s inner guard discharge (its escape leaves its own 2-node loop while staying
  inside the enclosing 4-node SCC) while ``negative-03`` still fails D4. Soundness never rests
  on the narrowing: $\\mathrm{natural\\_loop}_G(g) \\subseteq \\mathrm{SCC}_G(u)$ always, the
  counter-bound argument carries the discharge, and Lemma 1's residual-acyclicity check runs
  unconditionally afterwards as the global backstop.
* **Q5 — the 640-digit ``int-literal`` bound** ships inside :mod:`gebra.verify.guards`
  (VAL-06) and needs nothing here.

**Coverage is Lemma 1, never enumeration.** Every simple cycle of $G$ contains an element of
$S$ **iff** the element residual $G \\setminus (S_a \\cup S_c)$ is acyclic (T-W-SPEC §5, A7
Lemma 1) — so the verdict is one Tarjan pass over the residual, $O(|N|+|E|)$, with no cycle
enumeration even though $c(G)$ is worst-case super-exponential (§6.4 rejects Johnson's
enumeration as the default on exactly that ground). Each surviving non-trivial SCC reports
**one** representative witness-free cycle (`exhaustive: false`), extracted as the first back
edge of an iterative DFS (A7 Lemma 3); the optional census below is abort-capped and additional,
never the verdict path.

**The census is B-capped Johnson, on the pass path only.** PD-011 (VAL-D4, ratified
2026-07-31) fixes both halves: the abort cap stays at the DEC-11 default $B = 16$, and the
census is **on by default** — §2.4 Step 6 calls it unconditionally on every pass, no flag —
so the witness carries the full simple-cycle list whenever $c(G) \\le B$ and the structured
``cycle-census-capped`` note instead of a partial list otherwise. Self-loops are emitted
directly as length-1 cycles and each vertex-simple cycle counts once per choice of parallel
edge, all against $B$ (§6.3's carried caveat from A7 §5). The abort is taken **during**
enumeration, at circuit $B{+}1$, which is what keeps §6.3's $O((|N|{+}|E|)(B{+}2))$ bound
honest on a graph whose true $c(G)$ is astronomical.

**Strict mode changes the gate, never this record.** §6.1's profile gate has three rows and
the third is ``--gebra-strict``: $S_b$ leaves $S$, so a residual SCC the blanket alone covers
is reported under ``cycle-without-termination-witness`` with ``blanket_only: true`` instead
of passing with a note — the **same** condition ID, "no new condition ID is introduced". That
row belongs to the D-12 gate, not to this module: §2.4's pseudocode takes no strict
parameter, §0.2 names this exact note as promotable "with the report, witness, and note
records unchanged", and DEC-11 item 6 ratified it in those words ("the gate changes, never
the record"). What makes the gate's job a lookup rather than a second analysis is that $S_b$
never participates in residual construction (§6.1): $R$, its surviving SCCs, their
representative cycles and every D4 finding are **profile-invariant**, so the record already
carries exactly the SCCs the strict row reports, each with ``blanket_only: true`` on its
location. :func:`strict_promotions` is that lookup. It returns
:class:`StrictPromotion` values rather than a second
:class:`~gebra.verify.report.PropertyReport`, on purpose: a second report for one property
and one IR would *be* the record changing, whatever produced it.

**The graph is VAL-03's, not this module's.** Label expansion, the sentinel wiring, both
Tarjan passes, the induced subgraphs, the D4 anchor cycle (:meth:`~gebra.verify.graph
.GraphModel.anchor_cycle` *is* §2.4's ``cycle_through``, the catalog says so by name), the
canonical cycle rotation, and the acyclicity certificate (:attr:`~gebra.verify.graph
.GraphModel.worklist_order` over the element residual — "there is no second topological sort
to write"; on the one pass whose element residual is *not* acyclic, the blanket-only case,
the same order is still a §6.2 certificate, since the default-profile $S$ there includes
$S_b = E$ and $G \\setminus S$ is edgeless — recorded in FIDELITY-MATRIX §5) all come from
:mod:`gebra.verify.graph`. What this module contributes is the property
semantics — guard qualification (via :mod:`gebra.verify.guards`, VAL-06), S-assembly, the
residual filter, packaging — plus two P-02-specific analyses no other wedge validator needs,
each reading the shared model rather than building a graph of its own (the P-06
``_structural_retry_regions`` precedent): the iterative Cooper–Harvey–Kennedy dominator pass
behind DEC-23 Q4's natural loops (§2.4 Step 1b), and the abort-capped census.

**The ``dynamic`` edge (ir 1.1 — ratified DEC-28) is §2.4 Step 0's ``elif e.kind == dynamic:
continue`` — "no member of G; a dynamic edge forms no static cycle" — and it is realized in the
shared model, not here.** The builder inserts nothing for it, so a route that closes only through
a dynamic router is not a cycle of $G$, needs no witness, and appears in no census; the form-(a)
scan below reads ``ConditionalEdge`` instances only, and the multigraph key stays the authored
``ir.edges`` index, so a counter guard declared after a ``dynamic`` edge is found where it was
authored. A static cycle beside such an edge is still exactly as witnessed or unwitnessed as it
was: the skip adds no coverage and removes none.

**The P-01-clean precondition, and the hard model boundary on dirty topology.** §0.3 defines
P-02 results only over P-01-clean topology; its named degradation convention is "P-02's
``resolve`` would carry a dangling vertex", which is ``carry_unresolved_references=True`` —
:func:`_model_for` refuses a model built the other way. On P-01-**dirty** topology the results
are best-effort diagnostics, and one consequence is inherited from the envelope rather than
smoothed here: report fields spell node ids under the frozen §5 grammar, so a carried phantom
whose name breaks that grammar has no spelling in a location, a certificate, or a note anchor,
and building the report raises. That is the same hard model boundary
:class:`~gebra.verify.locations.DataflowLocation` documents for P-04 — §0.3 already puts a
single-property run on such topology "outside the defined result surface". On P-01-clean input
every spelled id comes from ``nodes[].id`` (grammar-checked at IR validation) and the boundary
is unreachable.

Nothing here executes a node, calls a model, or opens a network connection (WA-07): the input
is a validated :class:`~gebra.ir.WorkflowIR` and the output is structured values. P-02 reads
``edges[].{kind, from, condition, path_map}`` (through the shared model and the §3 recognizer —
a guard string is matched against a grammar, never parsed as Python, never evaluated),
``state`` (key membership and declared types), ``runtime.recursion_limit`` and
``nodes[].annotations.variant`` — §2.3's field list exactly.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import Final

from gebra.ir import ConditionalEdge, WorkflowIR
from gebra.verify.base import ConditionId, PropertySlug, to_display
from gebra.verify.conditions import emit_co_failure, emit_failure, emittable_condition
from gebra.verify.graph import (
    END_VERTEX,
    SENTINEL_VERTICES,
    START_VERTEX,
    GraphModel,
    build_graph_model,
    canonical_rotation,
    ledger_sort_key,
)
from gebra.verify.guards import CounterQualification, qualify_counter_guard
from gebra.verify.locations import (
    AnyLocation,
    EdgeLocation,
    GuardEdgeLabels,
    NodeLocation,
    P02CycleLocation,
    P02SccLocation,
)
from gebra.verify.registry import register_validator
from gebra.verify.report import CoFailure, PropertyReport
from gebra.verify.witnesses import (
    CounterGuardSource,
    CycleCensus,
    GuardEdgeRef,
    RecursionLimitDecl,
    RecursionLimitSource,
    TerminationWitness,
    VariantDecl,
    VariantSource,
    WitnessInventoryEntry,
    WitnessNote,
    WitnessNoteKind,
)

__all__ = [
    "CENSUS_CAP",
    "COUNTER_GUARD_WITHOUT_EXIT_EDGE",
    "CYCLE_WITHOUT_TERMINATION_WITNESS",
    "PROPERTY_SLUG",
    "StrictPromotion",
    "check_termination_witness",
    "strict_promotions",
]

#: The catalog slug this module answers for (Verification-Properties §1.3).
PROPERTY_SLUG: Final[PropertySlug] = "termination-witness"

#: §0.4 RATIFIED, FATAL, DEFENSIBLE — the base condition (``negative-01/-02/-04``;
#: ``mixed/02/05/08``).
CYCLE_WITHOUT_TERMINATION_WITNESS: Final[ConditionId] = "cycle-without-termination-witness"

#: §0.4 RATIFIED, FATAL, DEFENSIBLE — the distinct D4 wiring defect (DEC-05 D4;
#: ``negative-03``).
COUNTER_GUARD_WITHOUT_EXIT_EDGE: Final[ConditionId] = "counter-guard-without-exit-edge"

#: The census abort cap $B$ — the DEC-11-ratified default, re-pinned against the current
#: corpus (max observed $c(G) = 3$) and ruled on-by-default at PD-011 (VAL-D4). Enumeration
#: stops at circuit $B{+}1$; an aborted census omits the list and notes itself instead.
CENSUS_CAP: Final[int] = 16

#: One P-02 finding before packaging: (anchor-SCC sort key, condition ID, location). §2.3's
#: merged ordering rule — *(sorted node tuple of the finding's anchor SCC, condition ID)* —
#: is applied over D4 and residual findings together before the first fills ``failure``.
_Finding = tuple[tuple[bytes, ...], ConditionId, AnyLocation]


def check_termination_witness(ir: WorkflowIR, *, model: GraphModel | None = None) -> PropertyReport:
    """Check every simple cycle for a declared termination witness (§2.4, DEC-23-amended).

    The steps of the pseudocode, in order: build the label-expanded, sentinel-augmented
    multigraph (Step 0, VAL-03's :func:`~gebra.verify.graph.build_graph_model`); Tarjan pass
    #1 (Step 1, the shared :attr:`~gebra.verify.graph.GraphModel.components`); dominators
    from START for the D4 natural loops (Step 1b, :func:`_dominators` — DEC-23 Q4); assemble
    $S$ per the §4 discharge table (Step 2, :func:`_assemble`); build the element residual
    and run Tarjan pass #2 (Steps 3–4, :func:`_residual`); extract one representative
    witness-free cycle per surviving non-trivial SCC via Lemma 3 (Step 5,
    :func:`_first_back_edge_cycle`), gated by the §2.4 blanket profile; and, on a pass,
    emit the inventory, the acyclicity certificate and the capped census (Step 6).

    This is P-02's **record**, and it is the same record under every gate policy: §2.4 takes
    no strict parameter and §0.2 has promotion change the gate, never the record. §6.1's
    strict row — the one where $S_b$ leaves $S$ — reads this record through
    :func:`strict_promotions`; nothing about the report below depends on a gate policy.

    Args:
        ir: A validated workflow IR. Only the fields §2.3 lists are read.
        model: A pre-built model of the *same* ``ir``, when a caller already has one —
            ``verify()`` builds one model per convention and hands it to every
            topology-facing validator, and two builds of one IR are equal values, so sharing
            changes no result. It must be built with ``carry_unresolved_references=True``,
            which is P-02's own §0.3 degradation convention; a model built the other way is
            P-01's or P-06's and is refused rather than silently mis-analysed.

    Returns:
        One :class:`~gebra.verify.report.PropertyReport`: ``pass`` with a
        :class:`~gebra.verify.witnesses.TerminationWitness` (inventory, certificate, notes,
        census), or ``fail`` with the merged-order-first finding as the primary
        :class:`~gebra.verify.report.Failure`, every further finding as a same-property
        ``co_failure``, and every recorded note riding ``Failure.notes`` unconditionally
        (DEC-23 — a failing P-02 never silently drops a qualification-failure note).

    Raises:
        ValueError: if ``model`` was built without P-02's degradation convention.
    """
    graph = _model_for(ir, model)
    dominators = _dominators(graph)
    assembly = _assemble(ir, graph, dominators)

    residual = _residual(graph, assembly.discharged_edges, assembly.discharged_nodes)
    findings: list[_Finding] = list(assembly.findings)
    notes = list(assembly.notes)

    d4_sources = {location.guard_edge.source for _, _, location in assembly.findings}
    # §2.4 Step 5: "for K in residual ordered by sorted node tuple" — the iteration order is
    # normative for the blanket notes (nothing re-sorts them later) and harmless extra
    # determinism for the findings, which the merged key below orders again.
    surviving = sorted(
        (residual.components.members[index] for index in residual.components.nontrivial),
        key=lambda group: tuple(ledger_sort_key(member) for member in group),
    )
    for members in surviving:
        if any(source in members for source in d4_sources):
            # DEC-05 D2 one-root-cause subsumption, ratified over §4's both-emitted reading
            # (walkthrough #2, DEC-11): the D4 finding owns its SCC's report.
            continue
        representative = _first_back_edge_cycle(residual.subgraph(members))
        location = P02SccLocation(
            kind="scc",
            nodes=members,
            representative_cycle=representative,
            exhaustive=False,
            # §6.1 builds one payload for all three profile rows and fills this member with
            # "<justified (b) present?>" — `true` in the two blanket rows (the default
            # profile's note *and* the strict row's finding are the same $K$), `false` in the
            # third. The `false` is the one spelling not emitted: §2.3's fail shape omits the
            # member, every residual-SCC fixture omits it, and `exclude_none` drops `None`
            # but not `False` — see P02SccLocation, which rules exactly this.
            blanket_only=True if assembly.blanket else None,
        )
        if assembly.blanket:
            notes.append(
                WitnessNote(
                    kind="scc-covered-only-by-recursion-limit",
                    severity="warning",
                    locations=(location,),
                )
            )
        else:
            key = tuple(ledger_sort_key(member) for member in members)
            findings.append((key, CYCLE_WITHOUT_TERMINATION_WITNESS, location))

    if findings:
        findings.sort(key=lambda finding: finding[:2])
        (_, primary_condition, primary_location), *rest = findings
        co_failures: tuple[CoFailure, ...] = tuple(
            emit_co_failure(PROPERTY_SLUG, other_condition, other_location)
            for _, other_condition, other_location in rest
        )
        return PropertyReport.failing(
            PROPERTY_SLUG,
            emit_failure(
                PROPERTY_SLUG,
                primary_condition,
                primary_location,
                co_failures=co_failures or None,
                notes=tuple(notes) or None,
            ),
        )

    census = _capped_census(graph, CENSUS_CAP)
    if census is None:
        notes.append(WitnessNote(kind="cycle-census-capped"))
    return PropertyReport.passing(
        PROPERTY_SLUG,
        TerminationWitness(
            kind="termination",
            inventory=assembly.inventory,
            certificate=tuple(to_display(vertex) for vertex in residual.worklist_order),
            notes=tuple(notes),
            cycles=census,
        ),
    )


# ── §6.1's third row: what a strict gate promotes, and under which name ──────────────────


@dataclass(frozen=True)
class StrictPromotion:
    """One WARNING-grade P-02 record a ``--gebra-strict`` policy naming P-02 selects.

    Deliberately **not** an envelope model, and deliberately not a
    :class:`~gebra.verify.report.PropertyReport`: §0.2 and DEC-11 item 6 keep the record
    unchanged under promotion ("the gate changes, never the record"), so a strict run
    produces no new report — only this, a pointer at a record already in the report plus the
    identity T-W-SPEC §6.1's third row gives it. ``REPORT-FORMAT-SPEC`` §2.3's ``Promotion``
    is the run-level model that carries it into a report, assembled by ``verify()``.

    Attributes:
        note_kind: The promoted record's kind. The record itself is unchanged and stays on
            the report at ``severity: warning`` — that is the whole of §0.2's rule.
        property_condition: The §0.4 ID §6.1's third row reports this promotion under —
            ``cycle-without-termination-witness``, since "the strict promotion reuses the
            same condition ID … no new condition ID is introduced". It names the promoted
            item; it is **not** a finding's grade. The promoted record is the note, and a
            promoted record keeps its own WARNING severity (§0.2), so nothing here enters a
            run's FATAL count — which is what keeps ``gate.snapshot_eligible``
            (``REPORT-FORMAT-SPEC`` §2.5: "promotion moves the gate, not the ladder") true
            under a strict flag.
        location: The residual SCC the blanket alone covers, with its representative cycle
            and ``blanket_only: true`` — §6.1's distinguishing structured field, read off the
            record rather than rebuilt.
    """

    note_kind: WitnessNoteKind
    property_condition: ConditionId
    location: P02SccLocation


#: §6.1's identity rule as an explicit table: which §0.4 condition ID a promoted note is
#: reported under. One row, because §2.3's vocabulary has exactly one WARNING-grade kind.
#: Written out rather than derived, on the :func:`_qualification_note` precedent — note kinds
#: and condition IDs are different vocabularies (§2.3: notes are "deliberately **not** §0.4
#: condition IDs"), and relating them mechanically would let a rename in one silently rewrite
#: the other.
_STRICT_IDENTITY: Final[Mapping[WitnessNoteKind, ConditionId]] = {
    "scc-covered-only-by-recursion-limit": CYCLE_WITHOUT_TERMINATION_WITNESS
}


def strict_promotions(report: PropertyReport) -> tuple[StrictPromotion, ...]:
    """What ``--gebra-strict`` promotes on a P-02 report — §6.1's third row, as a lookup.

    §6.1's profile gate reads: with a justified (b) present, the default profile passes and
    carries each residual SCC the blanket alone covers in the WARNING-grade note, while
    ``--gebra-strict`` excludes $S_b$ from $S$ and reports the same $K$ under
    ``cycle-without-termination-witness`` with ``blanket_only: true``. The two rows describe
    **one** set of SCCs, because $S_b$ never participates in residual construction — so the
    strict row needs no re-analysis and this function does none: it selects the promotable
    records already in ``report`` and attaches §6.1's condition ID to each.

    A caller wanting the gate arithmetic goes to ``REPORT-FORMAT-SPEC`` §2.2: a non-empty
    result here means "at least one WARNING-grade record or note was selected", which is
    exit ``1`` / ``outcome: fail`` under a policy naming this property, with the report,
    witness and note records untouched. Whether the policy names P-02 at all is the run
    level's question (bare ``--gebra-strict`` promotes every WARNING; the per-property form
    promotes only the named slugs), so it is not asked here.

    Selection follows §0.2's reach rather than the note kind: a note is promotable iff it
    carries ``severity: warning``. That is why an aborted census cannot flip a gate — the
    ``cycle-census-capped`` note carries no severity, and neither does any other kind.
    Both carriage paths are swept, since DEC-23 puts notes on ``Failure.notes`` and
    ``CoFailure.notes`` unconditionally on the fail path: promoting there changes no exit
    code (a failing P-02 already carries a FATAL finding), but the promotion is still what
    §6.1's row names, and leaving it out would understate what a strict run selected.

    Args:
        report: A P-02 :class:`~gebra.verify.report.PropertyReport` — this validator's own,
            or one loaded from a fixture through §0.3's loading rule.

    Returns:
        One :class:`StrictPromotion` per promotable location, in the order the record carries
        them (the notes are emitted in §2.4 Step 5's sorted-node-tuple order, and nothing
        re-sorts them). Empty whenever no blanket alone covers a cycle — which is every IR
        with no justified ``recursion_limit``, and every IR whose element witnesses already
        cover it.

    Raises:
        ValueError: if ``report`` is another property's, if it carries a WARNING-grade note
            whose kind has no row above (the promotable vocabulary grew without §6.1's
            identity rule being extended — a WA-03 addendum event, never a silent skip), if a
            WARNING-grade note carries no location at all (§6.1 anchors the promoted item on
            its residual SCC, and a gate the user was owed is never dropped in silence), or
            if the §0.4 registry no longer holds that ID for this property.
        TypeError: if a promotable note anchors on a location that is not a residual SCC,
            which has no ``blanket_only`` for §6.1 to distinguish the promotion on.
    """
    if report.property != PROPERTY_SLUG:
        # A foreign report is a category error, not an empty result: REPORT-FORMAT-SPEC
        # §2.3's reach table matches a note on "the report's own property", and §0.3 scopes
        # `Failure.notes` to same-property notes. Refused rather than answered with `()`, so
        # every way this lookup can be misused fails loudly — `verify()` is the caller that
        # will loop over thirteen reports, where a silent empty tuple reads as "nothing to
        # promote" instead of as the mistake it is.
        raise ValueError(
            f"strict_promotions reads {PROPERTY_SLUG!r} reports; this one is "
            f"{report.property!r}. Each property's promotable records are its own (§0.3)."
        )
    promotions: list[StrictPromotion] = []
    for note in _recorded_notes(report):
        if note.severity != "warning":
            continue
        condition_id = _STRICT_IDENTITY.get(note.kind)
        if condition_id is None:
            raise ValueError(
                f"note kind {note.kind!r} is WARNING-grade but TERMINATION-WITNESS-SPEC "
                "§6.1 fixes no condition ID for promoting it. Extending the promotable "
                "vocabulary is a spec addendum (§0.4 registry discipline), not a local patch."
            )
        entry = emittable_condition(condition_id)
        if entry.property_slug != PROPERTY_SLUG:
            raise ValueError(
                f"{entry.id!r} is held for {entry.property_slug!r} in the §0.4 registry; "
                f"{PROPERTY_SLUG!r} may not report a promotion under it."
            )
        if not note.locations:
            # The third way a promotable note can be un-promotable, closed on the same
            # fail-closed rule as the two above (VAL-11 pre-review, the property-spec pre-review
            # N1): §0.2's reach is severity-based, so this note *is* selected, but §6.1
            # anchors the promoted item on its residual SCC and a note with no location names
            # none. Answering `()` would silently cost the user a gate; T-W-SPEC §2.4's
            # one-note-listing-every-SCC reading — recorded in FIDELITY-MATRIX §5 as a live
            # alternative a future fixture could pin — is the shape most likely to arrive here.
            raise ValueError(
                f"a WARNING-grade {note.kind!r} note carries no location, so TERMINATION-"
                "WITNESS-SPEC §6.1 has no residual SCC to report the promotion on. A note "
                "this shape is a §2.3 vocabulary question (WA-03), never a silent skip."
            )
        for location in note.locations:
            if not isinstance(location, P02SccLocation):
                raise TypeError(
                    f"a {note.kind!r} note anchors on residual SCCs (§2.4 Step 5); this one "
                    f"carries {type(location).__name__}, which has no `blanket_only` to "
                    "distinguish the promotion on (§6.1)."
                )
            promotions.append(StrictPromotion(note.kind, entry.id, location))
    return tuple(promotions)


def _recorded_notes(report: PropertyReport) -> Iterator[WitnessNote]:
    """Every structured note the report carries, on either result path (§2.3 carriage)."""
    if isinstance(report.witness, TerminationWitness):
        yield from report.witness.notes
    if report.failure is not None:
        yield from report.failure.notes or ()
        for co_failure in report.failure.co_failures or ():
            yield from co_failure.notes or ()


def _model_for(ir: WorkflowIR, model: GraphModel | None) -> GraphModel:
    """The graph P-02 runs on — §2.4 Step 0, with §0.3's local degradation convention.

    The guard is P-04's, verbatim in structure, because the two properties share the carry
    convention: what distinguishes the two builds is a non-sentinel reference that was
    recorded and *not* materialized — P-01's and P-06's convention, never P-02's, whose §0.3
    sentence is "P-02's ``resolve`` would carry a dangling vertex" (§2.7 says the same). On
    clean topology ``carried`` is empty under either setting, so the test asks about the
    references rather than about emptiness.
    """
    if model is None:
        return build_graph_model(ir, carry_unresolved_references=True)
    dropped = sorted(
        {
            reference.reference
            for reference in model.unresolved
            if reference.reference not in SENTINEL_VERTICES
        }
        - model.carried
    )
    if dropped:
        raise ValueError(
            "P-02 carries a dangling vertex: that is the degradation convention "
            "PROPERTY-CATALOG-SPEC §0.3 gives it by name (T-W-SPEC §1 drops only the "
            f"label-edge, never silently). This model dropped {dropped!r} instead — build "
            "it with carry_unresolved_references=True (P-01's and P-06's convention is the "
            "other one, and §0.3 does not promise the two agree on ill-formed input)."
        )
    return model


# ── Step 1b — dominators and the D4 natural loop (DEC-23, PD-037 Q4) ─────────────────────


def _dominators(graph: GraphModel) -> dict[str, str]:
    """Immediate dominators from ``__start__`` — iterative Cooper–Harvey–Kennedy.

    The §2.4 Step 1b pass. Only vertices reachable from START have an entry (dominance is
    undefined elsewhere; a gated edge whose endpoints lack entries falls back to the SCC
    test, fail-closed). The root maps to itself. Reverse postorder is computed by an
    iterative DFS with successors in ledger §6 order, so the map is a pure function of the
    model; the intersection walk is Cooper–Harvey–Kennedy's, which needs no bit vectors and
    converges in a handful of passes on reducible graphs.
    """
    postorder: list[str] = []
    seen: set[str] = {START_VERTEX}
    stack: list[tuple[str, int]] = [(START_VERTEX, 0)]
    while stack:
        vertex, cursor = stack[-1]
        successors = graph.successors(vertex)
        descended = False
        for position in range(cursor, len(successors)):
            successor = successors[position]
            if successor not in seen:
                seen.add(successor)
                stack[-1] = (vertex, position + 1)
                stack.append((successor, 0))
                descended = True
                break
        if not descended:
            postorder.append(vertex)
            stack.pop()

    order: dict[str, int] = {vertex: index for index, vertex in enumerate(reversed(postorder))}
    idom: dict[str, str] = {START_VERTEX: START_VERTEX}

    def intersect(one: str, other: str) -> str:
        while one != other:
            while order[one] > order[other]:
                one = idom[one]
            while order[other] > order[one]:
                other = idom[other]
        return one

    changed = True
    while changed:
        changed = False
        for vertex in sorted(seen - {START_VERTEX}, key=lambda member: order[member]):
            candidate: str | None = None
            for predecessor in graph.predecessors(vertex):
                if predecessor in idom:
                    candidate = (
                        predecessor if candidate is None else intersect(predecessor, candidate)
                    )
            if candidate is not None and idom.get(vertex) != candidate:
                idom[vertex] = candidate
                changed = True
    return idom


def _dominates(idom: dict[str, str], upper: str, lower: str) -> bool:
    """Whether ``upper`` dominates ``lower`` — a walk up ``lower``'s idom chain."""
    if upper not in idom or lower not in idom:
        return False
    vertex = lower
    while True:
        if vertex == upper:
            return True
        parent = idom[vertex]
        if parent == vertex:
            return False
        vertex = parent


def _natural_loop(
    graph: GraphModel, idom: dict[str, str], source: str, target: str
) -> frozenset[str] | None:
    """$\\mathrm{natural\\_loop}_G(g)$ of the gated re-entry ``source → target``, or ``None``.

    The Aho–Lam–Sethi–Ullman §9.6 construction DEC-23 Q4 names: when the header ``target``
    dominates ``source``, the gated edge is a back edge and its natural loop is
    $\\{h\\} \\cup \\{v : v \\text{ reaches } source \\text{ avoiding } h\\}$, gathered by
    the standard reverse walk from ``source`` that never expands past the header. ``None``
    means no single header dominates the re-entry — an irreducible region — and the caller
    falls back to the $\\mathrm{SCC}_G(u)$ test (fail-closed: the coarser test can only
    refuse a discharge the narrower one would allow, since the loop is always a subset of
    the SCC).

    The walk is restricted to dominator-covered (START-reachable) vertices, the same
    universe the dominance test lives in: on P-01-clean topology every vertex on a cycle
    through ``source`` is reachable, so the restriction changes nothing; on dirty topology
    it keeps the subset-of-SCC property that makes the fallback the *coarser* test.
    """
    if not _dominates(idom, target, source):
        return None
    loop: set[str] = {target, source}
    work: list[str] = [source]
    while work:
        vertex = work.pop()
        for predecessor in graph.predecessors(vertex):
            if predecessor in idom and predecessor not in loop:
                loop.add(predecessor)
                work.append(predecessor)
    return frozenset(loop)


# ── Step 2 — S-assembly per the §4 discharge table ───────────────────────────────────────


class _Assembly:
    """What Step 2 hands the verdict: $S$, the inventory, the notes, the D4 findings."""

    __slots__ = (
        "blanket",
        "discharged_edges",
        "discharged_nodes",
        "findings",
        "inventory",
        "notes",
    )

    def __init__(self) -> None:
        self.discharged_edges: set[tuple[int, str]] = set()
        self.discharged_nodes: set[str] = set()
        self.inventory: tuple[WitnessInventoryEntry, ...] = ()
        self.notes: list[WitnessNote] = []
        self.findings: list[tuple[tuple[bytes, ...], ConditionId, P02CycleLocation]] = []
        self.blanket: bool = False


def _assemble(ir: WorkflowIR, graph: GraphModel, idom: dict[str, str]) -> _Assembly:
    """Assemble $S$ per the discharge table — forms (a), (c), (b), in §2.4's own order.

    The inventory lists form-(a) entries in authored edge order, then form-(c) entries in
    authored node order, then the form-(b) blanket — the pseudocode's append order, which is
    what the corpus's ``positive-02`` (a) + (b) inventory pins.
    """
    assembly = _Assembly()
    inventory: list[WitnessInventoryEntry] = []

    for index, edge in enumerate(ir.edges):
        if not isinstance(edge, ConditionalEdge):
            continue
        qualification = qualify_counter_guard(edge.condition, ir.state)
        if qualification.outcome == "opaque":
            continue  # R5 — no partial credit, and no diagnostic for undeclared shapes
        if qualification.guard is None:
            assembly.notes.append(_qualification_note(edge.from_, qualification))
            continue
        guard = qualification.guard
        target = edge.path_map.get(guard.then_label)
        if target is None:
            # The recognized then-label is wired to no path_map entry, so the gated
            # label-edge does not exist: nothing to discharge, and fail-closed like every
            # other v1 exclusion (§3) — the cycle fails as unwitnessed unless covered.
            continue
        resolved = _resolve(target)
        if not graph.components.same_component(edge.from_, resolved):
            # Exit-on-truth wiring: the gated edge lies on no cycle — an explicit
            # no-discharge, no-diagnostic ruling (§4 corollary; DEC-23 Q1 keeps this test
            # SCC-relative). Every resolvable spelling is in the partition under the carry
            # convention — a dangling target is carried, a sentinel spelling is a vertex —
            # and a sentinel-headed edge can never share a non-trivial component (m5).
            continue
        loop = _natural_loop(graph, idom, edge.from_, resolved) or frozenset(
            graph.components.members_of(edge.from_)
        )
        if any(_resolve(label_target) not in loop for label_target in edge.path_map.values()):
            # D4 holds: some label leaves the natural loop (DEC-23 Q4) — discharge the
            # gated label-edge only (DEC-23 Q1).
            assembly.discharged_edges.add((index, guard.then_label))
            inventory.append(
                WitnessInventoryEntry(
                    form="a",
                    element=EdgeLocation(
                        kind="edge",
                        source=edge.from_,
                        target=resolved,
                        label=guard.then_label,
                    ),
                    source=CounterGuardSource(
                        guard_edge=GuardEdgeRef(source=edge.from_, label=guard.then_label),
                        counter_key=guard.counter_key,
                        bound=guard.bound,
                    ),
                    discharges="all-simple-cycles-through-element",
                )
            )
        else:
            # Counter saturation has no wired escape from the loop — the distinct D4
            # wiring defect (DEC-05 D4), emitted during S-construction, independently of
            # residual analysis. The anchor is §2.4's `cycle_through`, which the catalog
            # names as the shared anchor_cycle formulation.
            members = graph.components.members_of(edge.from_)
            assembly.findings.append(
                (
                    tuple(ledger_sort_key(member) for member in members),
                    COUNTER_GUARD_WITHOUT_EXIT_EDGE,
                    P02CycleLocation(
                        kind="cycle",
                        nodes=graph.anchor_cycle(edge.from_),
                        counter_key=guard.counter_key,
                        guard_edge=GuardEdgeLabels(source=edge.from_, labels=tuple(edge.path_map)),
                    ),
                )
            )

    state = ir.state or {}
    for node in ir.nodes:
        variant = node.annotations.variant if node.annotations is not None else None
        if variant is None:
            continue
        if variant.key in state:
            assembly.discharged_nodes.add(node.id)
            on_cycle = graph.components.is_nontrivial(node.id)
            inventory.append(
                WitnessInventoryEntry(
                    form="c",
                    element=NodeLocation(kind="node", node=node.id),
                    source=VariantSource(
                        variant=VariantDecl(key=variant.key, measure=variant.measure)
                    ),
                    # §6.2: a carrier on no cycle stays in the inventory, vacuous — the
                    # explicit empty marker, "a structured empty set, never a string".
                    discharges="all-simple-cycles-through-element" if on_cycle else (),
                )
            )
        else:
            assembly.notes.append(
                WitnessNote(kind="variant-key-not-in-state", node=node.id, key=variant.key)
            )

    limit = ir.runtime.recursion_limit if ir.runtime is not None else None
    if limit is not None:
        if limit.justification:
            assembly.blanket = True
            inventory.append(
                WitnessInventoryEntry(
                    form="b",
                    source=RecursionLimitSource(
                        recursion_limit=RecursionLimitDecl(
                            value=limit.value, justification=limit.justification
                        )
                    ),
                    discharges="blanket",
                )
            )
        else:
            # Schema-invalid at ir 1.0 (§2.2 makes `justification` REQUIRED); the model
            # enforces presence, so the reachable remnant is the empty string — defense in
            # depth per §4 path 3: no witness, note only.
            assembly.notes.append(WitnessNote(kind="recursion-limit-without-justification"))

    assembly.inventory = tuple(inventory)
    return assembly


def _resolve(target: str) -> str:
    """A ``path_map`` value as a model vertex — the ``"END"`` literal is the exit sentinel (m3)."""
    return END_VERTEX if target == "END" else target


def _qualification_note(source: str, qualification: CounterQualification) -> WitnessNote:
    """The ``counter-key-not-qualified`` note for one §4 path-1 near-miss (DEC-23 Q2).

    This is the explicit reviewed table the card requires between
    :class:`~gebra.verify.guards.CounterQualification`'s **diagnostic** vocabulary and the
    §2.3 note vocabulary — never a mechanical rename, since ``counter-key-not-in-state``
    (diagnostic) sits one word from ``variant-key-not-in-state`` (a real note kind for form
    (c), not for this case). Both near-miss outcomes map onto the one ratified kind:

    ========================================== ============================================
    ``CounterQualification.outcome``           note payload
    ========================================== ============================================
    ``counter-key-not-in-state``               ``identifier`` only — no declared type exists
    ``counter-type-not-integer-compatible``    ``identifier`` + ``declared_type``
    ========================================== ============================================

    (``qualified`` and ``opaque`` never reach this function: the first contributes a witness
    and the second is R5's no-diagnostic case.) The guard edge is the recognized gated
    label-edge — the classification retains the syntactic guard even when qualification
    failed, which is exactly the "same evidence ``CounterQualification`` computes" the §2.3
    amendment names.
    """
    recognized = qualification.classification.guard
    if recognized is None:  # pragma: no cover — unreachable: a near-miss derived the §3 shape
        raise ValueError("a qualification note needs a recognized guard (§4 path 1)")
    return WitnessNote(
        kind="counter-key-not-qualified",
        guard_edge=GuardEdgeRef(source=source, label=recognized.then_label),
        identifier=qualification.unmatched_identifier,
        declared_type=qualification.declared_type,
    )


# ── Steps 3–4 — the element residual ─────────────────────────────────────────────────────


def _residual(
    graph: GraphModel, discharged_edges: set[tuple[int, str]], discharged_nodes: set[str]
) -> GraphModel:
    """$R = G \\setminus (S_a \\cup S_c)$ — delete S-edges alone, S-nodes with incidences.

    Always computed, even when a justified blanket (b) is present: $S_b$ never participates
    in residual construction, since a blanket over $E$ would make Lemma 1 vacuous (§6.1) —
    its effect enters only through the profile gate above.

    A discharged label-edge is identified as ``(ir.edges index, label)`` — the multigraph
    key of §2.4 Step 0 — so a sibling label of the same router, or a byte-identical
    duplicate edge at another ordinal, keeps its own edge (the over-discharge §1's label
    expansion exists to prevent). Filtering the ledger-sorted vertex tuple preserves its
    order, which is what lets the residual be a well-formed :class:`GraphModel` built
    directly.
    """
    kept = tuple(vertex for vertex in graph.vertices if vertex not in discharged_nodes)
    return GraphModel(
        vertices=kept,
        node_ids=graph.node_ids - discharged_nodes,
        edges=tuple(
            edge
            for edge in graph.edges
            if edge.source not in discharged_nodes
            and edge.target not in discharged_nodes
            and not (edge.origin == "edges" and (edge.index, edge.label) in discharged_edges)
        ),
        carried=graph.carried - discharged_nodes,
    )


# ── Step 5 — one representative witness-free cycle per residual SCC (A7 Lemma 3) ─────────


def _first_back_edge_cycle(subgraph: GraphModel) -> tuple[str, ...]:
    """Tree-path + first back edge, canonically rotated — §6.1's representative extraction.

    An iterative WHITE/GREY/BLACK DFS over the induced residual SCC, rooted at its
    ledger-least member with successors expanded in ledger order, so the representative is a
    pure function of the residual. The subgraph is strongly connected and non-trivial, so
    the DFS must encounter a back edge (a digraph is acyclic iff DFS yields no back edge —
    CLRS Lemma 22.11, via A7 Lemma 3), and tree-path($v \\leadsto u$) + edge $(u, v)$ is a
    witness-free-by-element simple cycle of $G$ — a concrete counterexample. A self-loop is
    its own back edge and yields the length-1 cycle.

    Stronger than the existence claim, and the reason the retreat arm below is marked
    unreachable: over a strongly connected subgraph the first back edge arrives before any
    vertex is ever popped. Were some vertex the *first* to pop with no back edge found, its
    successors would all be visited (else it descends) and none grey (else a back edge) —
    all black, contradicting that it popped first; and it has successors, since every vertex
    of a strongly connected subgraph with a cycle does. So the walk only descends and
    returns; the retreat code is kept for structural honesty about what a DFS is, not
    because an input can reach it.
    """
    root = subgraph.vertices[0]
    parents: dict[str, str | None] = {root: None}
    grey: set[str] = {root}
    stack: list[tuple[str, int]] = [(root, 0)]
    while stack:
        vertex, cursor = stack[-1]
        successors = subgraph.successors(vertex)
        descended = False
        for position in range(cursor, len(successors)):
            successor = successors[position]
            if successor in grey:
                walk: list[str] = [successor]
                if successor != vertex:
                    step = vertex
                    while step != successor:
                        walk.append(step)
                        parent = parents[step]
                        if parent is None:  # pragma: no cover — grey path runs root ⇝ v ⇝ u
                            raise ValueError("back-edge walk escaped the DFS tree")
                        step = parent
                    walk[1:] = reversed(walk[1:])
                return canonical_rotation(tuple(walk))
            # Not grey ⇒ white: `parents` and `grey` coincide until a pop, and no pop
            # precedes the back edge (docstring) — so there is no black case to test.
            parents[successor] = vertex
            grey.add(successor)
            stack[-1] = (vertex, position + 1)
            stack.append((successor, 0))
            descended = True
            break
        if not descended:  # pragma: no cover — see the docstring: no pop precedes the back edge
            grey.discard(vertex)
            stack.pop()
    raise ValueError(  # pragma: no cover — unreachable: callers pass non-trivial SCCs
        "no back edge found: the subgraph is acyclic (TERMINATION-WITNESS-SPEC §5, Lemma 1)"
    )


# ── Step 6 — the abort-capped census (§6.3; PD-011) ──────────────────────────────────────


def _capped_census(graph: GraphModel, cap: int) -> CycleCensus | None:
    """Every simple cycle of $G$, or ``None`` when the count exceeds ``cap`` (§6.3).

    Johnson's algorithm with an abort counter — stop at circuit $B{+}1$, worst case
    $O((|N|{+}|E|)(B{+}2))$ regardless of the true count — with the two A7 §5 caveats the
    spec carries: Johnson's definitions exclude self-loops and parallel edges, so self-loops
    are emitted directly as length-1 cycles (one per parallel self-loop edge) and each
    vertex-simple cycle is expanded per choice of parallel edge, all counting against the
    cap. The completed list is canonically rotated and ordered shortest-first, ties by the
    ledger §6 comparator — a repo-authored ordering (no spec fixes one; the census order in
    ``positive-04`` pins shortest-first), recorded in FIDELITY-MATRIX §5.

    The abort bound holds because every enumeration root is the least member of a
    multi-vertex SCC of the remaining subgraph, and strong connectivity puts at least one
    circuit through every such root — so at most $B{+}1$ roots are ever processed, each
    O(|N|+|E|), before the census either completes or aborts.
    """
    census: list[tuple[str, ...]] = []
    count = 0
    for vertex in graph.vertices:
        for edge in graph.out_edges(vertex):
            if edge.target == vertex:
                count += 1
                if count > cap:
                    return None
                census.append((vertex,))

    remaining = set(graph.vertices)
    while True:
        subgraph = graph.subgraph(remaining)
        components = [group for group in subgraph.components.members if len(group) >= 2]
        if not components:
            break
        group = min(components, key=lambda members: ledger_sort_key(members[0]))
        root = group[0]
        # Collecting cap - count + 1 vertex-circuits already proves overflow (each stands
        # for at least one cycle), so the blocked search stops there rather than
        # enumerating an unbounded tail — the abort is *during* enumeration, which is what
        # keeps the §6.3 bound honest on a graph with super-exponentially many circuits.
        for walk in _circuits_through(subgraph.subgraph(group), root, cap - count + 1):
            multiplicity = _parallel_expansion(graph, walk)
            count += multiplicity
            if count > cap:
                return None
            census.extend((canonical_rotation(walk),) * multiplicity)
        remaining.discard(root)

    census.sort(key=lambda cycle: (len(cycle), tuple(ledger_sort_key(member) for member in cycle)))
    return CycleCensus(exhaustive=True, cycles=tuple(census))


def _circuits_through(subgraph: GraphModel, root: str, limit: int) -> list[tuple[str, ...]]:
    """Vertex-simple circuits through ``root`` in ``subgraph`` — Johnson's blocked DFS.

    The CIRCUIT/UNBLOCK procedure of Johnson (1975), iterative with an explicit frame stack
    (deep agent graphs would exhaust the interpreter limit — the §2.4 closing note makes
    that a requirement). Self-loops are excluded from the successor lists; the caller counts
    them directly. Circuits are emitted as vertex walks starting at ``root``, and the search
    stops as soon as ``limit`` of them are collected — the caller sizes ``limit`` so that
    reaching it already proves the census exceeds the cap. A return below ``limit`` is a
    completed enumeration.
    """
    successors = {
        vertex: tuple(successor for successor in subgraph.successors(vertex) if successor != vertex)
        for vertex in subgraph.vertices
    }
    blocked: dict[str, bool] = dict.fromkeys(subgraph.vertices, False)
    pending: dict[str, set[str]] = {vertex: set() for vertex in subgraph.vertices}
    circuits: list[tuple[str, ...]] = []

    path: list[str] = [root]
    blocked[root] = True
    frames: list[tuple[str, int]] = [(root, 0)]
    found: list[bool] = [False]
    while frames:
        vertex, cursor = frames[-1]
        options = successors[vertex]
        descended = False
        for position in range(cursor, len(options)):
            successor = options[position]
            frames[-1] = (vertex, position + 1)
            if successor == root:
                circuits.append(tuple(path))
                found[-1] = True
                if len(circuits) >= limit:
                    return circuits
            elif not blocked[successor]:
                path.append(successor)
                blocked[successor] = True
                frames.append((successor, 0))
                found.append(False)
                descended = True
                break
        if descended:
            continue
        frames.pop()
        fruitful = found.pop()
        if fruitful:
            _unblock(vertex, blocked, pending)
        else:
            for successor in options:
                pending[successor].add(vertex)
        path.pop()
        if frames and fruitful:
            found[-1] = True
    return circuits


def _unblock(vertex: str, blocked: dict[str, bool], pending: dict[str, set[str]]) -> None:
    """Johnson's UNBLOCK, iterative: unblock ``vertex`` and everything waiting on it."""
    work: list[str] = [vertex]
    while work:
        current = work.pop()
        if not blocked[current]:
            continue
        blocked[current] = False
        waiting = pending[current]
        pending[current] = set()
        work.extend(waiting)


def _parallel_expansion(graph: GraphModel, walk: tuple[str, ...]) -> int:
    """How many edge-simple cycles the vertex walk stands for — ∏ parallel multiplicities.

    T-W-SPEC §1 fixes cycles as **edge sequences**: two parallel edges $u \\to v$ yield two
    distinct simple cycles over the same vertices, so a vertex-simple circuit counts once
    per choice of parallel edge along it (§6.3). Counted off the full model, whose subgraphs
    keep parallels — the walk's consecutive pairs, closing back to the start.
    """
    multiplicity = 1
    for position, source in enumerate(walk):
        target = walk[(position + 1) % len(walk)]
        multiplicity *= sum(1 for edge in graph.out_edges(source) if edge.target == target)
    return multiplicity


register_validator(PROPERTY_SLUG, check_termination_witness)
