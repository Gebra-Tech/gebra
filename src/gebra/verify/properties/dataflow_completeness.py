"""P-04 ``dataflow-completeness`` — the must-write analysis (PROPERTY-CATALOG-SPEC §4).

**Claim class DEFENSIBLE-A, severity FATAL, always** (§4.3): both are read off the §0.4
registry at emission, never restated here. DEFENSIBLE-A rather than DEFENSIBLE because the
reads and writes are the *declared* ``annotations.input``/``output`` (D-010) and their
truthfulness is trusted the way a type annotation is (§4.2 "Trust").

What P-04 decides, in one sentence (the catalog statement, authoritative): for every node
$n$ and every key $k \\in \\mathrm{reads}(n)$, on **every** path from ``START`` to $n$ some
predecessor writes $k$ — or $k$ is a declared graph-input key, which §4.2 treats as written
at ``START`` (the boundary set $I_0$).

**The interpretation rules, all §4.2's.** Conditional edges are label-expanded and *every*
labelled successor is admitted, because which label fires at runtime is P-05's business
(VAL-03 does the expansion). A key with ``optional: true`` in ``state`` is in $I_0$.
First-arrival semantics: ``IN[v]`` is the state *before* $v$ runs, so a node's own write never
satisfies its own read — which is the runtime fact that the first iteration of an
entry-at-reader loop sees the key unwritten.

**Scope is `START`-paths only (DEC-05 D2).** An unreachable node generates **no** P-04
obligation and its reads are P-01's findings exclusively — one root cause, one report, no
double-blame; where a run-level report surfaces the interaction it does so with
``subsumed_by: "P-01"`` on the record (``mixed/04`` is the pinned precedent). ⊤-initialization
plus the reachable-only obligation loop of :func:`_obligations` is what mechanizes that
(memo A8 T4): the reads of an unreachable node are never enumerated, so there is nothing for
this validator to package.

**The ``dynamic`` edge (ir 1.1 — ratified DEC-28, 2026-08-09) contributes no path** — §4.4
Step 0's ``elif e.kind == dynamic: continue``, realized once in the shared model (§0.3's one
convention for every graph builder). The quantification stays over START→n paths of the
*static* graph, so a node reachable only through dynamic dispatch generates no obligation, and
because P-01's condition (i) is over-approximation-silenced on such a document (DEC-28 clause
1) no analysis covers its reads. DEC-28 clause 2 rules that this absence must never be
silent: the report gains the optional ``outside_static_coverage`` diagnostic — the nodes with
declared reads outside the static START closure, on a document with a reachable ``dynamic``
edge — emitted only when non-empty (DEC-11 discipline), never verdict-bearing, on the pass
witness and on the primary failure alike (:func:`_outside_static_coverage`).

**The algorithm is the MFP fixpoint** of §4.4 Step 3 — the gen-only, ⊤-initialized,
∩-meet forward framework of §4.1, whose iterative solution equals the meet-over-all-paths
solution because the framework is distributive (A8 T1), and whose walk-quantification
collapses to the simple-path quantification the catalog statement uses (A8 T2). §4.4 says the
per-key writer-avoiding reachability form of A8 §7.2 is "provably interchangeable" and that
D-09 "may implement either"; this module runs the fixpoint for the *verdict* and the
reachability form for the *attribution* (:func:`_offending_path`, one breadth-first search per
key over the graph with that key's writers removed), so A8 T5 — violation $(v,k)$ iff
``START`` reaches $v$ avoiding $W_k \\setminus \\{v\\}$ — is the bridge the two halves meet on
rather than a claim taken on trust. ``tests/verify/test_dataflow_completeness.py`` runs both
forms over the whole corpus and asserts they agree key for key.

**SCCs are never collapsed** (§4.1's warning, and this module's sharpest correctness point).
Condensation supplies **iteration order only**: collapsing a component into a supernode with
unioned writes is unsound, because the union is a may-eventually-write summary while P-04
needs must-write-*before-first-read*, which is order-sensitive inside the component (A8 T3);
the dual collapse, ignoring intra-SCC writes, is incomplete. The node-level equations of
:func:`_fixpoint` are the semantics, and the order they are evaluated in — VAL-03's
:attr:`~gebra.verify.graph.GraphModel.worklist_order`, which is §4.4 Step 3's
``[v for scc in topological_sort(condensation(G)) for v in members(scc)]`` verbatim — is a
schedule that cannot change the answer. The tests hold that two ways: the A8 §8.4 cycle-entry
pair (entry-at-reader fails, entry-at-writer passes — the two verdicts a collapse in either
direction gets wrong), which §4.6 records as a corpus gap; and an order-independence check
that re-runs the fixpoint under a deliberately hostile order and gets the same solution.

**The graph is VAL-03's** (§4.4 Step 0 is :func:`~gebra.verify.graph.build_graph_model`'s
job): sentinel wiring, label expansion and the unresolved-reference records all come from
:mod:`gebra.verify.graph`, so P-01, P-02, P-04 and P-06 agree on the graph by construction.
One divergence from §4.4 Step 0 is inherited from there rather than chosen here, and is named
so a later reader does not take it for an oversight: Step 0's ``resolve`` reads the literal
``"END"`` as the exit sentinel wherever it appears, but ledger §1/§4 bless that spelling in a
``path_map`` value only, and PD-007 Q2 (ratified 2026-07-24) kept it that way — so ``to:
"END"`` on a ``normal``/``send`` edge is looked up in $V$ like any other target and recorded
as an unresolved reference. No corpus fixture writes that shape, so it is unobservable here;
reopening it is IR-D3's, not this card's.

**The degradation convention is P-04's own** (§0.3's P-01-clean precondition): "P-04 carries
the phantom vertex with an empty contract", so the model is built with
``carry_unresolved_references=True`` and §4.4 Step 0's own comment applies — a reference
naming no node "is P-01's finding — the vertex is still carried, with empty contract ⇒ zero
P-04 obligations". §0.3 states plainly that these conventions are local, that
"cross-validator agreement on ill-formed input is NOT promised", and that a
single-property-scoped run on P-01-dirty topology is "outside the defined result surface";
P-01's convention is the opposite one, and :func:`_model_for` refuses a model built the other
way rather than analysing it silently.

Nothing here executes a node, calls a model, or opens a network connection (WA-07): the input
is a validated :class:`~gebra.ir.WorkflowIR` and the output is structured values. P-04 reads
``entry``, ``finish``, ``state``, ``nodes[].id``, ``nodes[].annotations.input``/``output`` and
``edges[].{from,to,kind,path_map}`` (§4.3) and nothing else. A fixture's illustrative builder
snippet is never read, let alone run; a router's declared guard string is P-05's and P-02's,
never this module's; and ``runtime`` is P-02's.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Final

from gebra.ir import WorkflowIR
from gebra.verify.base import ConditionId, PropertySlug, to_display
from gebra.verify.conditions import emit_co_failure, emit_failure
from gebra.verify.graph import (
    SENTINEL_VERTICES,
    START_VERTEX,
    GraphModel,
    build_graph_model,
    ledger_sort_key,
)
from gebra.verify.locations import DataflowLocation
from gebra.verify.registry import register_validator
from gebra.verify.report import CoFailure, P04Failure, PropertyReport
from gebra.verify.witnesses import DataflowCoverage, DataflowWitness

__all__ = [
    "PROPERTY_SLUG",
    "READ_KEY_NEVER_WRITTEN_ON_PATH",
    "check_dataflow_completeness",
]

#: The catalog slug this module answers for (Verification-Properties §1.3).
PROPERTY_SLUG: Final[PropertySlug] = "dataflow-completeness"

#: P-04's one condition — §0.4 RATIFIED (``dataflow-completeness/negative-01..03``;
#: ``mixed/02/04/05/08``). §4.3: "exactly one".
READ_KEY_NEVER_WRITTEN_ON_PATH: Final[ConditionId] = "read-key-never-written-on-path"


# ── Step 1's contracts, as bitsets over Σ ────────────────────────────────────────────────


@dataclass(frozen=True)
class _Contracts:
    """§4.4 Step 1's ``K``/``reads``/``writes``/``I0``/``W`` — the lattice, materialized.

    The representation is §4.5's own: "bitsets over K … AND/OR", with a Python ``int`` as the
    bitset, so a meet is one ``&`` and a transfer one ``|``, each $O(\\lceil|\\Sigma|/w\\rceil)$
    machine words. The key → bit assignment is ``sorted(K)`` under :func:`ledger_sort_key`,
    which makes the whole analysis a pure function of the IR: nothing depends on ``dict``
    insertion order or on ``hash`` randomization.

    Attributes:
        keys: $\\Sigma$, in :func:`ledger_sort_key` order — the bit assignment.
        bit: Key → its single-bit mask. Membership in this mapping *is* membership in
            $\\Sigma$, which is the ``k ∉ K: continue`` test of §4.4 Step 4 ("Σ-membership is
            P-03's finding", never P-04's).
        universe: $\\top = \\Sigma$ — the ⊤-initialization value, and the empty meet.
        boundary: $I_0$ — the keys ``state`` declares ``optional: true`` (§4.2 "Graph
            inputs"), treated as written at ``START``.
        reads: Vertex → its declared reads, deduplicated and ordered. Sentinels and carried
            phantoms are absent, which is their empty contract.
        writes: Vertex → its declared writes as a bitset, $\\Sigma$-restricted. ``__start__``
            carries :attr:`boundary`; every other sentinel and every phantom carries nothing.
        writers: Key → $W_k$, the vertices that write it. ``__start__`` is a member exactly
            when the key is in $I_0$ (§4.4 Step 1).
    """

    keys: tuple[str, ...]
    bit: Mapping[str, int]
    universe: int
    boundary: int
    reads: Mapping[str, tuple[str, ...]]
    writes: Mapping[str, int]
    writers: Mapping[str, frozenset[str]]


def _contracts(ir: WorkflowIR, graph: GraphModel) -> _Contracts:
    """Read §4.4 Step 1 off the IR (ledger §2–§3).

    ``reads(v) := set(v.annotations.input or [])`` and the same for ``output`` — "absent ≡ ∅
    (omit-normalized)", so a node with no annotations at all has an empty contract rather than
    an undefined one. A declared read or write naming a key outside $\\Sigma$ is P-03's
    finding: it is kept in :attr:`_Contracts.reads` so §4.4 Step 4's ``continue`` is a visible
    step rather than a silent filter, and it is dropped from the write bitsets, where it could
    only ever be a bit with no key.
    """
    declared = ir.state or {}
    keys = tuple(sorted(declared, key=ledger_sort_key))
    bit = {key: 1 << index for index, key in enumerate(keys)}
    universe = (1 << len(keys)) - 1
    boundary = 0
    for key, field in declared.items():
        if not isinstance(field, str) and field.optional:
            boundary |= bit[key]

    reads: dict[str, tuple[str, ...]] = {}
    writes: dict[str, int] = {START_VERTEX: boundary}
    writers: dict[str, set[str]] = {key: set() for key in keys}
    for key in keys:
        if boundary & bit[key]:
            writers[key].add(START_VERTEX)
    for node in ir.nodes:
        annotations = node.annotations
        declared_reads = frozenset(annotations.input or ()) if annotations else frozenset()
        declared_writes = frozenset(annotations.output or ()) if annotations else frozenset()
        reads[node.id] = tuple(sorted(declared_reads, key=ledger_sort_key))
        written = 0
        for key in declared_writes:
            mask = bit.get(key)
            if mask is not None:
                written |= mask
                writers[key].add(node.id)
        writes[node.id] = written

    # Every vertex the graph carries but `ir.nodes` does not — the sentinels and any phantom
    # materialized under the §0.3 degradation convention — gets the empty contract §4.4
    # Step 0/Step 1 give it.
    for vertex in graph.vertices:
        reads.setdefault(vertex, ())
        writes.setdefault(vertex, 0)

    return _Contracts(
        keys=keys,
        bit=bit,
        universe=universe,
        boundary=boundary,
        reads=reads,
        writes=writes,
        writers={key: frozenset(group) for key, group in writers.items()},
    )


# ── The check (§4.4) ─────────────────────────────────────────────────────────────────────


def check_dataflow_completeness(
    ir: WorkflowIR, *, model: GraphModel | None = None
) -> PropertyReport:
    """Check every reachable node's declared reads against §4's every-path rule (§4.4).

    The five steps of the pseudocode, in order: build the label-expanded, sentinel-augmented
    graph (Step 0, VAL-03's :func:`~gebra.verify.graph.build_graph_model`); read the contracts
    and the boundary set off the IR (Step 1, :func:`_contracts`); take the ``START`` closure
    that scopes the obligations (Step 2, DEC-05 D2); run the must-write fixpoint (Step 3,
    :func:`_fixpoint`); and enumerate the obligations with their attribution (Step 4,
    :func:`_obligations`), packaged by §0.3's same-property rule.

    Args:
        ir: A validated workflow IR. Only the fields §4.3 lists are read.
        model: A pre-built model of the *same* ``ir``, when a caller already has one —
            ``verify()`` builds one model per convention and hands it to every topology-facing
            validator, and two builds of one IR are equal values, so sharing changes no result.
            It must be built with ``carry_unresolved_references=True``, which is P-04's own
            §0.3 degradation convention; a model built the other way is P-01's or P-06's and is
            refused rather than silently mis-analysed.

    Returns:
        One :class:`~gebra.verify.report.PropertyReport`: ``pass`` with a
        :class:`~gebra.verify.witnesses.DataflowWitness` carrying one coverage entry per
        (reachable reader, read key), or ``fail`` with the ledger-§6-first finding as the
        primary :class:`~gebra.verify.report.P04Failure` and every further finding as a
        same-property ``co_failure`` (§0.3 packaging; findings are never dropped). On a
        document with a statically reachable ``dynamic`` edge either carries the optional
        ``outside_static_coverage`` diagnostic when it is non-empty (DEC-28 clause 2).

    Raises:
        ValueError: if ``model`` was built without P-04's degradation convention.
    """
    graph = _model_for(ir, model)
    contracts = _contracts(ir, graph)

    # Step 2 — D2 scope. The union is not decoration: `descendants` excludes its own source
    # (VAL-03 mirrors `nx.descendants` there), and START is a member of its own closure here.
    reach = graph.descendants(START_VERTEX) | {START_VERTEX}
    outside = _outside_static_coverage(graph, reach, contracts)

    inn = _fixpoint(graph, reach, contracts)
    coverage, findings = _obligations(graph, reach, contracts, inn)

    if findings:
        primary, *rest = findings
        co_failures: tuple[CoFailure, ...] = tuple(
            emit_co_failure(PROPERTY_SLUG, READ_KEY_NEVER_WRITTEN_ON_PATH, other.location)
            for other in rest
        )
        return PropertyReport.failing(
            PROPERTY_SLUG,
            emit_failure(
                PROPERTY_SLUG,
                READ_KEY_NEVER_WRITTEN_ON_PATH,
                primary.location,
                model=P04Failure,
                # "Emitted only when non-empty" (§4.3); the PC-4 profile drops the `None`, so a
                # finding carrying no diagnostic equals the corpus's expected block rather
                # than a decorated variant of it.
                writers_on_other_paths=primary.writers_on_other_paths or None,
                downstream_writers=primary.downstream_writers or None,
                # DEC-28 clause 2's report-level diagnostic rides the primary — the one carrier
                # a failing report has — beside the two per-finding ones (see `P04Failure`).
                outside_static_coverage=outside or None,
                co_failures=co_failures or None,
            ),
        )

    return PropertyReport.passing(
        PROPERTY_SLUG,
        DataflowWitness(
            kind="dataflow", coverage=tuple(coverage), outside_static_coverage=outside or None
        ),
    )


def _outside_static_coverage(
    graph: GraphModel, reach: frozenset[str] | set[str], contracts: _Contracts
) -> tuple[str, ...]:
    """DEC-28 clause 2's diagnostic: readers no analysis covers on a dynamic-bearing document.

    §4.4 Step 0's ``dynamic`` branch, in its own words: P-04's "quantification stays over
    START→n paths of the STATIC graph; nodes reachable only via dynamic dispatch generate no
    P-04 obligations — and with (i) over-approximation-silenced, no analysis covers their
    reads. NEVER silent". So, exactly when a ``dynamic`` edge's source is statically reachable
    (the same trigger P-01 §1.4 Step 3 keys on — :meth:`GraphModel.reachable_dynamic_sources`),
    every declared node outside ``Reach`` that declares at least one read is named, in ledger
    §6 order and report-side spelling. "Declared reads" is ``annotations.input`` as declared,
    Σ-membership aside: a read of a key outside Σ is P-03's finding, but it is still a read
    nothing here covers.

    When no dispatcher is reachable the list is empty and the unreachable reader is P-01's
    finding alone (DEC-05 D2) — the D2 scope in :func:`_obligations` is untouched either way;
    this function adds a diagnostic, never an obligation. Empty on every ir 1.0 document.
    """
    if not graph.reachable_dynamic_sources():
        return ()
    return tuple(
        to_display(vertex)
        for vertex in graph.vertices
        if vertex in graph.node_ids and vertex not in reach and contracts.reads[vertex]
    )


def _model_for(ir: WorkflowIR, model: GraphModel | None) -> GraphModel:
    """The graph P-04 runs on — §4.4 Step 0, with §0.3's local degradation convention.

    Building it here rather than taking one is the default because a validator handed no model
    must still work; taking one is what lets ``verify()`` pay for the build once.

    The guard is the mirror of P-01's and is deliberately stated as a question about the
    *references*, not about :attr:`~gebra.verify.graph.GraphModel.carried`: on clean topology
    ``carried`` is empty under either setting, so an emptiness test would reject nothing and
    protect nothing. What distinguishes the two builds is a non-sentinel reference that was
    recorded and *not* materialized — which is exactly P-01's convention and never P-04's. A
    reference spelling a reserved sentinel segment is never carried under either setting
    (it would break IR-SPEC §4.1 (m5)), so it is excluded from the test rather than
    misreported as the wrong convention.
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
            "P-04 carries the phantom vertex with an empty contract: that is the degradation "
            "convention PROPERTY-CATALOG-SPEC §0.3 gives it by name, and §4.4 Step 0 spells "
            "out why — an unresolved reference 'is P-01's finding … the vertex is still "
            f"carried, with empty contract ⇒ zero P-04 obligations'. This model dropped "
            f"{dropped!r} instead — build it with carry_unresolved_references=True (P-01's "
            "and P-06's convention is the other one, and §0.3 does not promise the two agree "
            "on ill-formed input)."
        )
    return model


# ── Step 3 — the must-write MFP fixpoint ─────────────────────────────────────────────────


def _fixpoint(
    graph: GraphModel, reach: frozenset[str] | set[str], contracts: _Contracts
) -> Mapping[str, int]:
    """Solve ``IN[v] = ⋂ OUT[u]``, ``OUT[v] = IN[v] ∪ writes(v)`` (§4.4 Step 3).

    ⊤-initialization everywhere, ``OUT[START] := I0``, round-robin in
    :attr:`~gebra.verify.graph.GraphModel.worklist_order` until nothing changes. The framework
    is gen-only — **no kill, ever** — so both maps are monotonically decreasing from ⊤ in a
    lattice of finite height, and the loop terminates at the greatest fixpoint, which is the
    MFP solution (A8 T1; Kildall 1973, Kam & Ullman 1977). §4.5's bound is ≤ depth + 2 passes
    in reverse postorder (Aho et al. 2006 §9.6.7), an expectation about loop-nesting depth and
    not a worst case; the loop below asks the lattice rather than counting passes.

    Two details are load-bearing rather than incidental. **``START`` is excluded from the
    update set**, because its ``OUT`` is the boundary set and re-deriving it from an empty meet
    would hand back ⊤ — (m5) gives ``__start__`` no in-edges, so the empty-meet rule would
    otherwise overwrite $I_0$ with $\\Sigma$ on the first pass and pass every graph. **Vertices
    outside ``Reach`` are never updated**, so they keep ⊤ and contribute nothing to any meet
    they appear in: an unreachable predecessor of a reachable node is neutral, which is right,
    because no ``START``-path runs through it.

    The meet is taken over :meth:`~gebra.verify.graph.GraphModel.predecessors` — the
    de-duplicated view — because ``∩`` is idempotent and two parallel edges from one
    predecessor say nothing a single edge does not. (The multigraph view matters to P-02,
    where a discharged label-edge must not discharge its sibling; here it would only cost
    time.)
    """
    inn = dict.fromkeys(graph.vertices, contracts.universe)
    out = dict.fromkeys(graph.vertices, contracts.universe)
    out[START_VERTEX] = contracts.boundary
    order = tuple(
        vertex for vertex in graph.worklist_order if vertex in reach and vertex != START_VERTEX
    )
    while _sweep(graph, order, contracts, inn, out):
        pass
    return inn


def _sweep(
    graph: GraphModel,
    order: Iterable[str],
    contracts: _Contracts,
    inn: dict[str, int],
    out: dict[str, int],
) -> bool:
    """One round-robin pass of :func:`_fixpoint`; ``True`` if anything moved."""
    changed = False
    for vertex in order:
        meet = contracts.universe  # the empty meet is ⊤ = K (neutral), §4.4 Step 3
        for predecessor in graph.predecessors(vertex):
            meet &= out[predecessor]
        produced = meet | contracts.writes[vertex]  # gen-only; no kill ever
        if meet != inn[vertex] or produced != out[vertex]:
            inn[vertex] = meet
            out[vertex] = produced
            changed = True
    return changed


# ── Step 4 — obligations and attribution ─────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class _Finding:
    """One violated obligation, before §0.3 packaging decides which one is the primary.

    Deliberately not a :class:`~gebra.verify.report.P04Failure` yet: the primary carries
    ``co_failures`` and the others do not, and the two diagnostics ride the primary alone —
    §4.4's packaging builds every further finding as a plain ``CoFailure``, which has no
    field for them. Building the models only after the order is fixed keeps every emission on
    the one :mod:`~gebra.verify.conditions` surface, with no post-hoc mutation of a frozen
    model.
    """

    location: DataflowLocation
    writers_on_other_paths: tuple[str, ...]
    downstream_writers: tuple[str, ...]


def _obligations(
    graph: GraphModel,
    reach: frozenset[str] | set[str],
    contracts: _Contracts,
    inn: Mapping[str, int],
) -> tuple[list[DataflowCoverage], list[_Finding]]:
    """Enumerate every (reachable reader, read key) obligation and decide it (§4.4 Step 4).

    The outer loop is ``ir.nodes`` restricted to ``Reach`` in the ledger §6 comparator, which
    is what fixes the primary finding under §0.3's packaging rule; the inner loop is
    ``sorted(reads(v))``. A Σ key is not a node id, so ledger §6 does not literally reach it —
    the same comparator is used anyway, for one determinism rule rather than two, and the two
    orders differ only for strings mixing non-BMP characters with U+E000..U+FFFF.

    It iterates the vertex **set** (``graph.vertices`` filtered to ``node_ids``, already in that
    comparator's order) rather than the ``nodes`` list, which matters only for an IR carrying a
    repeated id: Step 1 keys ``reads`` and ``writes`` by id, so two such entries are already
    indistinguishable here, and "ordered by the ledger-§6 id comparator" has no meaning over a
    list holding one id twice. One obligation, not two.

    The **unreachable reader is skipped here, and that skip is the whole of the subsumption**
    (DEC-05 D2; A8 T4): its reads are never enumerated, so P-04 emits nothing about them and
    the P-01 ``node-unreachable-from-start`` finding owns the root cause alone. Nothing else in
    this module knows about P-01.
    """
    coverage: list[DataflowCoverage] = []
    findings: list[_Finding] = []
    trees: dict[frozenset[str], _SearchTree] = {}
    for vertex in graph.vertices:
        if vertex not in graph.node_ids or vertex not in reach:
            continue
        for key in contracts.reads[vertex]:
            mask = contracts.bit.get(key)
            if mask is None:  # Σ-membership is P-03's finding, never P-04's
                continue
            upstream = _upstream_writers(graph, reach, contracts, vertex, key)
            if inn[vertex] & mask:
                coverage.append(
                    DataflowCoverage(
                        node=to_display(vertex),
                        key=key,
                        satisfied_by=_display_sorted(
                            ({START_VERTEX} if contracts.boundary & mask else set()) | set(upstream)
                        ),
                    )
                )
            else:
                findings.append(_finding(graph, contracts, vertex, key, upstream, trees))
    return coverage, findings


def _upstream_writers(
    graph: GraphModel,
    reach: frozenset[str] | set[str],
    contracts: _Contracts,
    vertex: str,
    key: str,
) -> tuple[str, ...]:
    """``{w ∈ W[k] ∖ {v, START} : w ∈ Reach and v ∈ descendants(w)}`` (§4.4 Step 4).

    One set, two duties, exactly as the pseudocode has it: on the covered branch it is the
    non-boundary half of ``satisfied_by``, and on the violated branch it is the
    ``writers_on_other_paths`` diagnostic — "upstream writers that cover *other* paths"
    (§4.3). ``START`` is excluded by the pseudocode's own ``∖ {v, START}`` and carries the
    display sentinel separately, which is also what keeps the diagnostic's declared
    ``tuple[NodeId, ...]`` honest: :data:`~gebra.verify.base.NodeId` admits no sentinel.
    """
    return tuple(
        sorted(
            (
                writer
                for writer in contracts.writers[key] - {vertex, START_VERTEX}
                if writer in reach and vertex in graph.descendants(writer)
            ),
            key=ledger_sort_key,
        )
    )


def _finding(
    graph: GraphModel,
    contracts: _Contracts,
    vertex: str,
    key: str,
    upstream: tuple[str, ...],
    trees: dict[frozenset[str], _SearchTree],
) -> _Finding:
    """One violated obligation as its §4.3 location and its two DEC-11 diagnostics.

    ``downstream_writers`` is §4.4's ``W[k] ∩ descendants(G, v)`` — "writers wired *after* the
    reader" (§4.3), the ``negative-02`` precedent. The intersection is with
    :meth:`~gebra.verify.graph.GraphModel.descendants`, which excludes its own source, so a
    self-writing reader on a cycle is not its own downstream writer — the same first-arrival
    reading the endpoint exemption makes on the other side.

    Neither list is projected through :func:`to_display`: both are declared
    ``tuple[NodeId, ...]``, which admits no sentinel, and neither can hold one — ``__start__``
    is excluded from ``upstream`` by §4.4's own ``∖ {v, START}`` and can never be a
    *descendant* of anything, since (m5) gives it no in-edge.
    """
    downstream = tuple(
        sorted(contracts.writers[key] & graph.descendants(vertex), key=ledger_sort_key)
    )
    return _Finding(
        location=DataflowLocation(
            kind="state-key",
            key=key,
            node=to_display(vertex),
            # DEC-26 phantom-leak rule (§0.3): a phantom vertex carried under the
            # degradation convention is walk-internal, never report evidence — no
            # location field may name a vertex absent from ``ir.nodes``. The path is
            # emitted with phantoms elided; sentinels keep their §0 display spelling.
            path=_display(
                step
                for step in _offending_path(graph, contracts, vertex, key, trees)
                if step in graph.node_ids or step in SENTINEL_VERTICES
            ),
        ),
        writers_on_other_paths=upstream,
        downstream_writers=downstream,
    )


def _offending_path(
    graph: GraphModel,
    contracts: _Contracts,
    vertex: str,
    key: str,
    trees: dict[frozenset[str], _SearchTree],
) -> tuple[str, ...]:
    """The shortest ``START`` → ``vertex`` path avoiding $W_k \\setminus \\{v\\}$ (§4.4 Step 4).

    This is A8 T5 read as a constructor: a violation $(v, k)$ holds **iff** ``START`` reaches
    $v$ in that restricted graph, so the path exists whenever the fixpoint says the obligation
    is violated, and finding it is the independent second opinion on the verdict — the
    reachability reference form of A8 §7.2, which §4.4 declares interchangeable with the
    fixpoint and which runs here as the attribution half of the same analysis.

    The **endpoint exemption** ``∖ {v}`` is first-arrival semantics in graph form: a
    self-writing reader's own write never feeds its own first read, so $v$ stays in the graph
    even when it writes $k$ (A8 §3, the T5 refinement). Mind the polarity when reading §4.4's
    ``nx.restricted_view(G, nodes = W[k] ∖ {v})`` — that call *removes* those nodes, which is
    :meth:`~gebra.verify.graph.GraphModel.subgraph` over the complement.

    **One tree per key, not one per finding**, which is the difference between §4.5's two
    stated bounds. Read literally, "one $O(|V|+|E|)$ BFS per finding" is quadratic in the
    input: a workflow whose nodes each read many unwritten keys has $|V| \\cdot |\\Sigma|$
    findings, and rebuilding the restricted graph for each one costs $O(|V|+|E|)$ again —
    measured at 4 s for 12 800 findings on 160 nodes, on input a user authors. What is used
    instead is §4.5's *other* bound, the one it gives this very algorithm: "$|\\Sigma|$
    independent reachability problems, $O(|\\Sigma| \\cdot (|V|+|E|))$ total".

    Reaching that bound takes one observation, because the naive memo does **not**: keying the
    cache on $W_k \\setminus \\{v\\}$ makes it depend on $v$ as well as $k$ for every
    self-writing reader, so a graph of readers that write what they read defeats it completely
    — one tree per finding again, and now *retained* rather than transient (measured at 102 400
    trees, 54 s and 2.8 GB on a 1.9 MB document). So the cache is keyed on $W_k$ alone, and the
    exemption is applied when the path is read out instead:

    * a reader $v \\notin W_k$ is in that tree, and its path is read off directly;
    * a reader $v \\in W_k$ is absent from it, and its path is ``walk(u) + (v,)`` for the
      predecessor $u$ of $v$ that the tree discovered **earliest**.

    The second case is exact, not an approximation. A simple path ending at $v$ has no interior
    $v$, so its interior avoids $W_k$ entirely and lies inside the shared tree; and a BFS over
    $G \\setminus (W_k \\setminus \\{v\\})$ discovers $v$ from the first predecessor it pops,
    which — since a BFS pops in discovery order, and discovery order is non-decreasing in depth
    — is exactly the earliest-discovered predecessor of $v$ in the tree over $G \\setminus W_k$.
    Every vertex discovered before $v$ is reached without passing through $v$, so the two BFS
    runs agree on all of them. The emitted path is byte-identical to the per-finding search this
    replaces, which is why the fixture paths pinned in ``tests/verify`` did not move.

    The search is a plain BFS expanding successors in ledger §6 order, so "shortest" is
    resolved to one deterministic answer among the shortest.
    """
    removed = contracts.writers[key]
    tree = trees.get(removed)
    if tree is None:
        tree = _shortest_path_tree(graph.subgraph(graph.vertex_set - removed))
        trees[removed] = tree
    if vertex in tree.parents:
        return _walk(tree, vertex)
    entry = min(
        (u for u in graph.predecessors(vertex) if u in tree.parents),
        key=lambda u: tree.discovered[u],
        default=None,
    )
    if entry is None:  # pragma: no cover - excluded by A8 T5; see below
        raise AssertionError(
            f"P-04 internal invariant: the fixpoint reports {key!r} unwritten on some "
            f"START-path to {vertex!r}, but no such path survives removing its other writers. "
            "A8 T5 makes the two equivalent, so this is a defect in this module, not in the "
            "input — please file it against VAL-09 with the IR that produced it."
        )
    return (*_walk(tree, entry), vertex)


@dataclass(frozen=True, slots=True)
class _SearchTree:
    """A breadth-first search from ``__start__`` over one restricted graph.

    Attributes:
        parents: Vertex → its BFS parent; ``__start__`` maps to ``None``, which terminates the
            walk-back. A vertex absent from the mapping is unreachable in this restriction.
        discovered: Vertex → the order it was dequeued into the tree. This is what lets the
            endpoint exemption be applied at read-out rather than by rebuilding the tree: a BFS
            pops in exactly this order, so "the first predecessor to be popped" is "the
            predecessor with the least index here".
    """

    parents: Mapping[str, str | None]
    discovered: Mapping[str, int]


def _walk(tree: _SearchTree, vertex: str) -> tuple[str, ...]:
    """``__start__`` → ``vertex``, read off ``tree`` by following parents back."""
    walk: list[str] = []
    cursor: str | None = vertex
    while cursor is not None:
        walk.append(cursor)
        cursor = tree.parents[cursor]
    walk.reverse()
    return tuple(walk)


def _shortest_path_tree(graph: GraphModel) -> _SearchTree:
    """Breadth-first search from ``__start__`` over ``graph``.

    The guard is for a case A8 T5 excludes rather than one that arises: a boundary key is in
    ``OUT[START]`` and gen-only transfers never remove it, so $k \\in I_0$ is covered at every
    reachable node and no finding for it can reach this function. Were one to, ``__start__``
    would have been removed with the writers and the empty tree routes it to the invariant
    error in :func:`_offending_path` instead of a ``KeyError`` three frames away.
    """
    if START_VERTEX not in graph.vertex_set:  # pragma: no cover - excluded by A8 T5
        return _SearchTree(parents={}, discovered={})
    parents: dict[str, str | None] = {START_VERTEX: None}
    discovered: dict[str, int] = {START_VERTEX: 0}
    queue: deque[str] = deque([START_VERTEX])
    while queue:
        current = queue.popleft()
        for successor in graph.successors(current):
            if successor not in parents:
                parents[successor] = current
                discovered[successor] = len(discovered)
                queue.append(successor)
    return _SearchTree(parents=parents, discovered=discovered)


# ── Helpers ──────────────────────────────────────────────────────────────────────────────


def _display(vertices: Iterable[str]) -> tuple[str, ...]:
    """Graph-side vertex ids in their report-side spelling, order preserved (§0.3)."""
    return tuple(to_display(vertex) for vertex in vertices)


def _display_sorted(vertices: Iterable[str]) -> tuple[str, ...]:
    """The same projection, then the ledger §6 order — a report-level writer list.

    Sorting the *display* spellings rather than the graph-side ids is deliberate: the order is
    a property of the emitted list, and ``"START"`` and ``"__start__"`` do not sort to the same
    place. §4.3 fixes no order for ``satisfied_by``, and it is not a
    :class:`~gebra.verify.base.SetCompared` field, so one has to be chosen and stated; this is
    the comparator every other list in a report already carries.
    """
    return tuple(sorted(_display(vertices), key=ledger_sort_key))


# Registration is what dispatch runs on, so it happens once, at import (see P-01's note).
register_validator(PROPERTY_SLUG, check_dataflow_completeness)
