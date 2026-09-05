"""Witness evidence, rendered — REPORT-FORMAT-SPEC §4.3, as label/value lines.

§4.3 gives every member of the §0.3 ``Witness`` union, and every substructure under it, a row
saying which facts a rendering must carry. This module is that column: one function per
witness kind, each returning the lines a human surface prints. Nothing here projects to
SARIF — §4.3's SARIF column reads *does not project* for every witness row, because "SARIF
has no witness structure" (A.1 loss 1), and a witness smuggled through a property bag would
be exactly what that loss refuses.

**Witness-presence wording only** (§4.6 rule 2). P-02's lines say that a cycle carries a
*declared bound*, that a variant measure is *declared and trusted*, that the acyclicity
certificate is *present and re-checkable*. They never say a workflow halts, terminates, or is
safe to run — the subject is the definition, and gebra observes no run (§4.6 rule 3).

Two rows are load-bearing negatives and are written as statements rather than omissions: P-01's
two empty tuples are the evidence that conditions (iii) and (iv) were evaluated and found
clean, and a ``cycle-census-capped`` note says enumeration stopped at the cap — never "no
cycles". P-06's ``none_required`` protection reads as *no obligation arose here*, never as
*protected*, and P-08's empty claim list reads as *nothing declared determinism*, never as
*all deterministic*.

Nothing here imports langgraph, executes anything, or opens a socket (WA-07).
"""

from __future__ import annotations

from collections import Counter

from gebra.report.anchors import location_lines
from gebra.verify.locations import NodeLocation
from gebra.verify.witnesses import (
    CounterGuardSource,
    CycleCensus,
    DataflowCoverage,
    DataflowWitness,
    DeterminismClaim,
    DeterminismWitness,
    EffectSafetyWitness,
    P06EffectRecord,
    RecursionLimitSource,
    TerminationWitness,
    VariantSource,
    WellFormednessWitness,
    Witness,
    WitnessInventoryEntry,
    WitnessNote,
)

__all__ = ["note_lines", "witness_lines", "witness_summary"]

_START: str = "START"


def _listed(values: tuple[str, ...], *, empty: str = "(none)") -> str:
    return ", ".join(values) if values else empty


def _plural(count: int, singular: str, plural: str | None = None) -> str:
    if count == 1:
        return f"{count} {singular}"
    return f"{count} {plural if plural is not None else singular + 's'}"


def _walk(nodes: tuple[str, ...]) -> str:
    return " -> ".join(nodes)


def _closed_walk(nodes: tuple[str, ...]) -> str:
    return _walk((*nodes, nodes[0])) if nodes else ""


# ── P-01 (§4.3 well-formedness row) ──────────────────────────────────────────────────────


def _well_formedness_lines(witness: WellFormednessWitness) -> list[tuple[str, str]]:
    lines = [
        (
            "reachable from START",
            (
                f"{_plural(len(witness.reachable_from_start), 'node')}: "
                f"{_listed(witness.reachable_from_start)}"
            ),
        ),
        ("terminal nodes", _listed(witness.terminal_nodes)),
        (
            "orphan check",
            "evaluated — no node stands outside every edge"
            if not witness.orphan_nodes
            else f"evaluated — {_listed(witness.orphan_nodes)}",
        ),
        (
            "reference check",
            "evaluated — every edge and path_map target resolves"
            if not witness.unresolved_targets
            else f"evaluated — unresolved: {_listed(witness.unresolved_targets)}",
        ),
    ]
    if witness.dynamic_dependent:
        # §4.3's `dynamic_dependent` row (DEC-28 clause 1): the nodes condition (i) did not name
        # because a reachable `dynamic` edge may dispatch to them. The line states its relation
        # to the list above it, claims neither reachability nor unreachability (gebra observes
        # no dispatch), and scopes the coverage gap to what DEC-28 prices — condition (i) and
        # P-04's obligations — rather than to "every analysis".
        lines.append(
            (
                "dynamic-dependent",
                (
                    f"of these, {_plural(len(witness.dynamic_dependent), 'node')} depend on a "
                    "dynamic router: no declared START-path reaches them, so their reachability "
                    "is neither claimed nor denied here, and P-04 generates no obligation for "
                    f"their reads: {_listed(witness.dynamic_dependent)}"
                ),
            )
        )
    return lines


# ── P-02 (§4.3 termination rows, TERMINATION-WITNESS-SPEC §6.2/§6.3) ─────────────────────


def _inventory_entry_line(entry: WitnessInventoryEntry) -> str:
    """One S-element of the witness inventory — the form fixes what the line says (§4.3)."""
    source = entry.source
    if isinstance(source, CounterGuardSource):
        guard = source.guard_edge
        return (
            f"form (a) — guard edge {guard.source} --{guard.label}--> | "
            f"counter key {source.counter_key} | declared bound {source.bound} | "
            f"discharges {_discharges(entry)}"
        )
    if isinstance(source, RecursionLimitSource):
        limit = source.recursion_limit
        return (
            f"form (b) — the cover is the graph-level recursion_limit {limit.value}, "
            f"declared justification: {limit.justification} | a blanket over the edge set, "
            "not a per-loop bound"
        )
    if isinstance(source, VariantSource):
        element = entry.element
        carrier = element.node if isinstance(element, NodeLocation) else "(no element)"
        variant = source.variant
        return (
            f"form (c) — carrier node {carrier} | variant key {variant.key} | "
            f"declared measure {variant.measure} | the measure is declared and trusted, not "
            f"checked | discharges {_discharges(entry)}"
        )
    raise AssertionError(f"no §4.3 rendering for witness source {type(source).__name__}")


def _discharges(entry: WitnessInventoryEntry) -> str:
    """What a form-(a) or form-(c) entry discharges — with the vacuous empty set spelled out.

    Form (b) never reaches here: its ``discharges`` reads ``blanket``, and its own line says so
    in words ("a blanket over the edge set, not a per-loop bound") because that is the fact
    §4.3 asks a form-(b) rendering to carry.
    """
    if entry.discharges == ():
        return (
            "nothing — the annotation is declared on a node lying on no cycle; declared "
            "content, and no finding of any severity follows from it"
        )
    return "all simple cycles through the element"


def note_lines(note: WitnessNote) -> list[tuple[str, str]]:
    """One structured witness note — §4.3's five note rows (§2.3's closed vocabulary)."""
    severity = note.severity or "no severity carried"
    lines: list[tuple[str, str]] = [("note", f"{note.kind} ({severity})")]
    if note.kind == "scc-covered-only-by-recursion-limit":
        # §4.5's fact sets are not scoped to the failure side: a `P02SccLocation` riding a note
        # still owes its representative cycle, its `exhaustive: false` and its `blanket_only`,
        # so the note renders its locations through the same function a finding does.
        for location in note.locations or ():
            lines.extend(location_lines(location))
        lines.append(
            (
                "promotion",
                (
                    "promotable under a strict flag naming termination-witness; the record "
                    "itself is unchanged by promotion"
                ),
            )
        )
    elif note.kind == "counter-key-not-qualified":
        if note.guard_edge is not None:
            lines.append(("guard edge", f"{note.guard_edge.source} --{note.guard_edge.label}-->"))
        if note.identifier is not None:
            lines.append(("identifier", f"{note.identifier} — unmatched"))
        if note.declared_type is not None:
            lines.append(("declared type", note.declared_type))
    elif note.kind == "variant-key-not-in-state":
        if note.node is not None:
            lines.append(("carrier node", note.node))
        if note.key is not None:
            lines.append(("missing key", note.key))
    elif note.kind == "cycle-census-capped":
        lines.append(
            (
                "census",
                (
                    "enumeration stopped at the cap, so no cycle list is carried — this is "
                    "not a statement that the graph has no cycles"
                ),
            )
        )
    return lines


def _census_lines(census: CycleCensus) -> list[tuple[str, str]]:
    return [
        (
            "census",
            f"exhaustive under the cap — {_plural(len(census.cycles), 'simple cycle')}",
        ),
        *(("cycle", _closed_walk(cycle)) for cycle in census.cycles),
    ]


def _termination_lines(witness: TerminationWitness) -> list[tuple[str, str]]:
    forms = Counter(entry.form for entry in witness.inventory)
    breakdown = ", ".join(f"{count} form ({form})" for form, count in sorted(forms.items()))
    lines: list[tuple[str, str]] = [
        (
            "inventory",
            f"{_plural(len(witness.inventory), 'entry', 'entries')}"
            + (f": {breakdown}" if breakdown else ""),
        ),
        *(("entry", _inventory_entry_line(entry)) for entry in witness.inventory),
        (
            "certificate",
            (
                "present and re-checkable — a topological order of the graph with the "
                f"witnessed elements removed, over "
                f"{_plural(len(witness.certificate), 'vertex', 'vertices')}: {_walk(witness.certificate)}"
            ),
        ),
    ]
    for note in witness.notes:
        lines.extend(note_lines(note))
    if witness.cycles is not None:
        lines.extend(_census_lines(witness.cycles))
    return lines


# ── P-04 (§4.3 dataflow rows) ────────────────────────────────────────────────────────────


def _coverage_line(coverage: DataflowCoverage) -> str:
    writers = ", ".join(
        f"{writer} (boundary source)" if writer == _START else writer
        for writer in coverage.satisfied_by
    )
    return f"{coverage.node} reads {coverage.key} <- covered by {writers or '(nothing)'}"


def _dataflow_lines(witness: DataflowWitness) -> list[tuple[str, str]]:
    lines = [
        (
            "coverage",
            f"{_plural(len(witness.coverage), '(reader, key) obligation')} covered",
        ),
        *(("covered", _coverage_line(coverage)) for coverage in witness.coverage),
    ]
    if witness.outside_static_coverage:
        lines.append(
            (
                "outside static coverage",
                _outside_static_coverage_phrase(witness.outside_static_coverage),
            )
        )
    return lines


def _outside_static_coverage_phrase(readers: tuple[str, ...]) -> str:
    """§4.3's `outside_static_coverage` row (DEC-28 clause 2), on the pass witness.

    The same fact rides a failing P-04 report's primary finding as evidence (§4.4), where
    :func:`gebra.report.human._evidence_label` words it; the two spellings say one thing —
    these readers' declared reads were covered by no analysis in this run, and the pass above
    them is a statement about the static graph only.
    """
    return (
        f"{_plural(len(readers), 'node')} with declared reads that no START-path of the static "
        "graph reaches — reachable only through a dynamic router, so no analysis in this run "
        f"covers those reads: {_listed(readers)}"
    )


# ── P-06 (§4.3 effect-safety rows) ───────────────────────────────────────────────────────


def _protection_phrase(record: P06EffectRecord) -> str:
    if record.protection == "idempotency_key":
        return f"protected by idempotency key {record.key}"
    if record.protection == "compensation_hook":
        return f"protected by compensation hook {record.hook}"
    return f"no protection obligation arose here — {record.region} region"


def _effect_record_line(record: P06EffectRecord) -> str:
    cycle = f" | anchor cycle {_closed_walk(record.cycle)}" if record.cycle is not None else ""
    return (
        f"{record.node} [{_listed(record.effect)}] in a {record.region} region{cycle} | "
        f"{_protection_phrase(record)}"
    )


def _effect_safety_lines(witness: EffectSafetyWitness) -> list[tuple[str, str]]:
    lines: list[tuple[str, str]] = [("cycle inventory", _plural(len(witness.cycles), "cycle"))]
    lines.extend(("cycle", _closed_walk(cycle)) for cycle in witness.cycles)
    lines.extend(("effect", _effect_record_line(record)) for record in witness.effects)
    if not witness.effects:
        lines.append(("effect", "no node declares a trigger effect tag"))
    return lines


# ── P-08 (§4.3 determinism rows) ─────────────────────────────────────────────────────────


def _claim_line(claim: DeterminismClaim) -> str:
    if claim.llm_backed:
        parts = [f"{claim.node} — LLM-backed"]
        if claim.seed is not None:
            parts.append(f"pinned seed {claim.seed}")
        if claim.temperature is not None:
            parts.append(f"pinned temperature {claim.temperature}")
        if claim.divergence_handling is not None:
            parts.append(f"divergence handling {claim.divergence_handling}")
        return " | ".join(parts)
    basis = claim.basis or "(none declared)"
    return f"{claim.node} — not LLM-backed | declared basis {basis} | no pinning was required"


def _determinism_lines(witness: DeterminismWitness) -> list[tuple[str, str]]:
    lines: list[tuple[str, str]] = [("claim class", f"{witness.claim_class} (carried in-band)")]
    if not witness.claims:
        lines.append(
            (
                "claims",
                (
                    "no node declared determinism, so nothing was checked — this is not a "
                    "statement that every node is deterministic"
                ),
            )
        )
    else:
        lines.append(("claims", _plural(len(witness.claims), "declared claim")))
        lines.extend(("claim", _claim_line(claim)) for claim in witness.claims)
    if witness.caveat is not None:
        lines.append(("caveat", witness.caveat))
    return lines


# ── The union ────────────────────────────────────────────────────────────────────────────


def witness_lines(witness: Witness) -> tuple[tuple[str, str], ...]:
    """The facts §4.3 requires a human rendering of ``witness`` to carry.

    Raises:
        AssertionError: if the §0.3 witness union grows a member with no §4.3 rendering —
            the loud failure REPORT-FORMAT-SPEC Appendix B OI-5 asks for, rather than a
            variant that renders as nothing.
    """
    if isinstance(witness, WellFormednessWitness):
        return tuple(_well_formedness_lines(witness))
    if isinstance(witness, TerminationWitness):
        return tuple(_termination_lines(witness))
    if isinstance(witness, DataflowWitness):
        return tuple(_dataflow_lines(witness))
    if isinstance(witness, EffectSafetyWitness):
        return tuple(_effect_safety_lines(witness))
    if isinstance(witness, DeterminismWitness):
        return tuple(_determinism_lines(witness))
    raise AssertionError(f"no §4.3 rendering for witness kind {witness.kind!r}")


def witness_summary(witness: Witness) -> str:
    """One line naming what the witness records — §5.1 rule 4's "witness summary"."""
    if isinstance(witness, WellFormednessWitness):
        # Read, never asserted: both tuples are empty on any pass `verify()` produces, and §0.1
        # still has every fact shown read off the report rather than known in advance.
        orphans = (
            "no orphan nodes"
            if not witness.orphan_nodes
            else _plural(len(witness.orphan_nodes), "orphan node")
        )
        unresolved = (
            "no unresolved targets"
            if not witness.unresolved_targets
            else _plural(len(witness.unresolved_targets), "unresolved target")
        )
        dynamic = (
            f" | {_plural(len(witness.dynamic_dependent), 'dynamic-dependent node')}"
            if witness.dynamic_dependent
            else ""
        )
        return (
            f"{_plural(len(witness.reachable_from_start), 'node')} reachable from START | "
            f"{_plural(len(witness.terminal_nodes), 'terminal node')} | {orphans} | "
            f"{unresolved}{dynamic}"
        )
    if isinstance(witness, TerminationWitness):
        notes = f" | {_plural(len(witness.notes), 'note')}" if witness.notes else ""
        return (
            f"{_plural(len(witness.inventory), 'declared witness', 'declared witnesses')} in the inventory | "
            f"acyclicity certificate present{notes}"
        )
    if isinstance(witness, DataflowWitness):
        outside = (
            f" | {_plural(len(witness.outside_static_coverage), 'reader')} outside static coverage"
            if witness.outside_static_coverage
            else ""
        )
        return f"{_plural(len(witness.coverage), '(reader, key) obligation')} covered{outside}"
    if isinstance(witness, EffectSafetyWitness):
        return (
            f"{_plural(len(witness.cycles), 'cycle')} | "
            f"{_plural(len(witness.effects), 'effect-tagged node')} recorded"
        )
    if isinstance(witness, DeterminismWitness):
        caveat = " | provider caveat carried" if witness.caveat is not None else ""
        return f"{_plural(len(witness.claims), 'declared determinism claim')}{caveat}"
    raise AssertionError(f"no §4.3 summary for witness kind {witness.kind!r}")
