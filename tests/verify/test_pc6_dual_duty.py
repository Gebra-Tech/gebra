"""PC-6 dual duty: a fixture's ``expected:`` block and a validator's output are one model.

Per the R-05 hard requirement and A6 convention PC-6, one set of classes validates both the
validator **output** and the corpus ``expected:`` blocks (§0.3). This module exercises both
duties against the real, vendored, read-only corpus:

* **fixture side** — every ``expected:`` block already in the ratified shape validates into
  the envelope and round-trips through the PC-4 serialization profile;
* **output side** — a report built the way a validator builds one, from the model
  constructors and nothing else, is *equal* to the report loaded from the fixture.

The corpus is a frozen contract surface (WA-04/WA-11): nothing here writes to it, and no
model was relaxed to accommodate a block that predates its §P-nn.3 contract. The single
reconciliation pass DEC-05's closure item and DEC-11 mandated has since landed (DEC-17,
re-vendored from vault ``b2056e9``), so every wedge-directory fixture now validates and
:data:`RECONCILED` names all of them. The blocks that still do not validate are the ones no
ruling has reached yet — the eight non-wedge properties' provisional shapes, P-03's withheld
condition IDs, and ``mixed/10``'s run-level wrapper. :data:`RECONCILED` stays asserted
exactly, so a *future* revision in either direction shows up here as a diff rather than
silently.

Nothing here executes a workflow, a node, or a network call (WA-07): fixtures are read with
PyYAML's safe loader and only their ``expected:`` blocks are validated. The IR blocks are
never built into a graph.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from gebra.verify import (
    END,
    START,
    CoFailure,
    CounterGuardSource,
    CycleCensus,
    DeterminismClaim,
    DeterminismWitness,
    EdgeLocation,
    EffectSafetyWitness,
    Failure,
    GuardEdgeRef,
    NodeLocation,
    P01EdgeLocation,
    P06EffectRecord,
    PropertyReport,
    PropertySlug,
    TerminationWitness,
    WellFormednessWitness,
    Witness,
    WitnessInventoryEntry,
    to_data,
    validate_report,
    validate_witness,
)
from tests.conftest import FIXTURES_DIR

#: Every corpus ``expected:`` block already in its ratified §P-nn.3 shape, by fixture path.
#: Since DEC-17 (the single reconciliation pass, re-vendored from vault ``b2056e9``) that is
#: **every single-property fixture in all five wedge directories**, on both polarities — the
#: eight negatives the pass reconciled joined the fourteen that were already in shape, and
#: the eleven DEC-16 gap fixtures (TE-14, vault ``e6ea366``) were authored directly against
#: the ratified shapes, so they joined on arrival.
RECONCILED: tuple[str, ...] = (
    "dataflow-completeness/negative-01-express-path-skips-writer.yaml",
    "dataflow-completeness/negative-02-writer-downstream-of-reader.yaml",
    "dataflow-completeness/negative-03-fan-in-missing-branch-writer.yaml",
    "dataflow-completeness/negative-04-cycle-entry-at-reader.yaml",
    "dataflow-completeness/positive-01-linear-itinerary-pipeline.yaml",
    "dataflow-completeness/positive-02-conditional-both-branches-write.yaml",
    "dataflow-completeness/positive-03-parallel-fanout-reduced-results.yaml",
    "dataflow-completeness/positive-04-cycle-entry-at-writer.yaml",
    "determinism-replay/negative-01-seedless-deterministic-llm-classifier.yaml",
    "determinism-replay/negative-02-seeded-llm-extractor-hot-temperature.yaml",
    "determinism-replay/negative-03-seeded-llm-temperature-field-absent.yaml",
    "determinism-replay/positive-01-pinned-seed-zero-temp-classifier.yaml",
    "determinism-replay/positive-02-pure-fare-normalizer.yaml",
    "determinism-replay/positive-03-vacuous-pass-no-deterministic-annotation.yaml",
    "effect-safety/negative-01-billable-in-unguarded-retry.yaml",
    "effect-safety/negative-02-irreversible-in-refinement-cycle.yaml",
    "effect-safety/negative-03-keyless-idempotent-on-irreversible.yaml",
    "effect-safety/negative-04-retry-policy-annotation-no-cycle-unprotected.yaml",
    "effect-safety/negative-05-dangling-compensation-hook.yaml",
    "effect-safety/positive-01-keyed-idempotent-billable-retry.yaml",
    "effect-safety/positive-02-irreversible-outside-cycle.yaml",
    "effect-safety/positive-03-compensated-billable-hold-loop.yaml",
    "graph-well-formed/negative-01-unreachable-escalation-node.yaml",
    "graph-well-formed/negative-02-dead-end-review-branch.yaml",
    "graph-well-formed/negative-03-path-map-typo-dangling-target.yaml",
    "graph-well-formed/negative-04-unwired-orphan-node.yaml",
    "graph-well-formed/positive-01-linear-document-pipeline.yaml",
    "graph-well-formed/positive-02-support-triage-branching.yaml",
    "graph-well-formed/positive-03-travel-parent-graph-with-booking-subgraph.yaml",
    "termination-witness/negative-01-unwitnessed-reflection-loop.yaml",
    "termination-witness/negative-02-nested-scc-outer-only-witness.yaml",
    "termination-witness/negative-03-counter-guard-without-wired-exit.yaml",
    "termination-witness/negative-04-supervisor-delegation-scc-no-witness.yaml",
    "termination-witness/negative-05-unwitnessed-self-loop.yaml",
    "termination-witness/positive-01-counter-guarded-retry-loop.yaml",
    "termination-witness/positive-02-justified-recursion-limit-refinement-loop.yaml",
    "termination-witness/positive-03-shrinking-worklist-hotel-quotes.yaml",
    "termination-witness/positive-04-nested-scc-dual-counter-witnesses.yaml",
    "termination-witness/positive-05-recursion-limit-only-scc-note.yaml",
    "termination-witness/positive-06-cycle-census-capped-overflow.yaml",
    "termination-witness/positive-07-acyclic-graph-vacuous-empty-inventory.yaml",
)

#: The mixed fixtures whose ``expected:`` block is in ratified shape, with the property that
#: owns the primary finding. A mixed fixture's top-level ``property:`` is the *list* of
#: properties it exercises, so the owning slug is not readable off the fixture — deriving it
#: from the primary condition ID needs the §0.4 registry, which is its own card. Naming it
#: here keeps this module about the envelope.
RECONCILED_MIXED: tuple[tuple[str, PropertySlug], ...] = (
    ("mixed/02-unwitnessed-loop-reading-unwritten-key.yaml", "termination-witness"),
    ("mixed/04-dangling-path-map-target-orphans-downstream-reader.yaml", "graph-well-formed"),
    ("mixed/08-express-path-skips-gate-writer-and-witnessed-exit.yaml", "dataflow-completeness"),
)


def _load(relative: str) -> dict[str, Any]:
    document = yaml.safe_load((FIXTURES_DIR / relative).read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    return document


def _report(relative: str, slug: PropertySlug | None = None) -> PropertyReport:
    """§0.3's fixture-loading rule: ``expected:`` omits ``property``, the fixture carries it."""
    document = _load(relative)
    return validate_report({"property": slug or document["property"], **document["expected"]})


def _fixture_files() -> list[Path]:
    return sorted(p for p in FIXTURES_DIR.rglob("*.yaml") if p.name != "schema.yaml")


# ── Duty one: the fixture side ───────────────────────────────────────────────────────────


@pytest.mark.parametrize("relative", RECONCILED)
def test_expected_block_validates_into_the_envelope(relative: str) -> None:
    report = _report(relative)
    document = _load(relative)
    assert report.property == document["property"]
    assert report.result == ("pass" if document["polarity"] == "positive" else "fail")


@pytest.mark.parametrize("relative", RECONCILED)
def test_expected_block_round_trips(relative: str) -> None:
    report = _report(relative)
    assert validate_report(to_data(report)) == report


@pytest.mark.parametrize(("relative", "slug"), RECONCILED_MIXED)
def test_mixed_expected_block_validates_and_round_trips(relative: str, slug: PropertySlug) -> None:
    """The cross-property carriage rules, on the fixtures that pinned them."""
    report = _report(relative, slug)
    assert report.result == "fail"
    assert validate_report(to_data(report)) == report


def test_mixed_04_pins_the_subsumption_precedent() -> None:
    """DEC-05 D2: the orphaned read is owned by P-01, not counted a second time by P-04."""
    report = _report(RECONCILED_MIXED[1][0], "graph-well-formed")
    assert report.failure is not None
    assert isinstance(report.failure.location, P01EdgeLocation)
    assert report.failure.co_failures is not None
    subsumed = [co for co in report.failure.co_failures if co.subsumed_by is not None]
    assert [(co.property, co.subsumed_by) for co in subsumed] == [("dataflow-completeness", "P-01")]


def test_mixed_10_per_property_witness_blocks_are_wedge_witnesses() -> None:
    """``mixed/10``'s all-pass block is a *run-level* wrapper — REPORT-FORMAT-SPEC's to own.

    Its per-property members are per-property witnesses, and the four wedge properties whose
    shapes have landed validate into this envelope directly.
    """
    document = _load("mixed/10-all-properties-pass-healthy-research-pipeline.yaml")
    blocks: dict[str, Any] = document["expected"]["witness"]["properties"]
    validated: dict[str, Witness] = {}
    for slug in ("graph-well-formed", "termination-witness", "effect-safety", "determinism-replay"):
        witness = validate_witness(blocks[slug])
        assert validate_witness(to_data(witness)) == witness
        validated[slug] = witness
    assert isinstance(validated["graph-well-formed"], WellFormednessWitness)
    assert isinstance(validated["termination-witness"], TerminationWitness)
    assert isinstance(validated["effect-safety"], EffectSafetyWitness)
    assert isinstance(validated["determinism-replay"], DeterminismWitness)


# ── Duty two: the output side — the same model, built as a validator builds it ───────────


def test_a_constructed_pass_report_equals_the_fixture() -> None:
    """``graph-well-formed/positive-01``: the DEC-11 5-key witness, built field by field."""
    built = PropertyReport.passing(
        "graph-well-formed",
        WellFormednessWitness(
            kind="well-formedness",
            reachable_from_start=(
                "archive_summary",
                "extract_text",
                "ingest_document",
                "summarize_text",
            ),
            terminal_nodes=("archive_summary",),
            orphan_nodes=(),
            unresolved_targets=(),
        ),
    )
    assert built == _report("graph-well-formed/positive-01-linear-document-pipeline.yaml")


def test_a_constructed_fail_report_with_a_cascade_equals_the_fixture() -> None:
    """``graph-well-formed/negative-03``: the (iv) primary and its (i) cascade as co_failures."""
    loaded = _report("graph-well-formed/negative-03-path-map-typo-dangling-target.yaml")
    built = PropertyReport.failing(
        "graph-well-formed",
        Failure(
            property_condition="path-map-target-undefined",
            location=P01EdgeLocation(
                kind="edge",
                source="review_booking",
                label="confirm",
                undefined_target="send_confirmatoin",
            ),
            severity="fatal",
            claim_class="defensible",
            co_failures=(
                CoFailure(
                    property="graph-well-formed",
                    property_condition="node-unreachable-from-start",
                    location=NodeLocation(kind="node", node="send_confirmation"),
                    severity="fatal",
                    claim_class="defensible",
                ),
            ),
        ),
    )
    assert built == loaded


def test_a_constructed_termination_witness_equals_the_fixture() -> None:
    """``termination-witness/positive-01``: inventory, certificate and the capped census."""
    built = PropertyReport.passing(
        "termination-witness",
        TerminationWitness(
            kind="termination",
            inventory=(
                WitnessInventoryEntry(
                    form="a",
                    element=EdgeLocation(
                        kind="edge", source="check_response", target="call_service", label="retry"
                    ),
                    source=CounterGuardSource(
                        guard_edge=GuardEdgeRef(source="check_response", label="retry"),
                        counter_key="retry_count",
                        bound=3,
                    ),
                    discharges="all-simple-cycles-through-element",
                ),
            ),
            certificate=(
                START,
                "submit_request",
                "call_service",
                "check_response",
                "compile_result",
                END,
            ),
            cycles=CycleCensus(exhaustive=True, cycles=(("call_service", "check_response"),)),
        ),
    )
    assert built == _report("termination-witness/positive-01-counter-guarded-retry-loop.yaml")


def test_a_constructed_determinism_witness_equals_the_fixture() -> None:
    """``determinism-replay/positive-01``: the caveat a pinned LLM-backed claim requires."""
    built = PropertyReport.passing(
        "determinism-replay",
        DeterminismWitness(
            kind="determinism",
            claims=(
                DeterminismClaim(
                    node="classify_request",
                    llm_backed=True,
                    seed=42,
                    temperature=0,
                    divergence_handling="logged",
                ),
            ),
            caveat="provider-seed-reproducibility-not-guaranteed",
            claim_class="heuristic",
        ),
    )
    assert built == _report("determinism-replay/positive-01-pinned-seed-zero-temp-classifier.yaml")


def test_a_constructed_effect_witness_equals_the_fixture() -> None:
    """``effect-safety/positive-03``: compensation as protection (DEC-05 D7, DEC-11 item 8).

    The anchor is written in §0.3's least-id-first canonical rotation, which is what §6.4's
    ``anchor_cycle`` returns and what the fixture carries since DEC-17 — before that pass it
    was authored in traversal order starting at ``propose_dates``.
    """
    cycle = ("place_hotel_hold", "review_hold", "release_hotel_hold", "propose_dates")
    built = PropertyReport.passing(
        "effect-safety",
        EffectSafetyWitness(
            kind="effect-safety",
            cycles=(cycle,),
            effects=(
                P06EffectRecord(
                    node="place_hotel_hold",
                    effect=("billable",),
                    region="cycle",
                    cycle=cycle,
                    protection="compensation_hook",
                    hook="release_hotel_hold",
                ),
            ),
        ),
    )
    assert built == _report("effect-safety/positive-03-compensated-billable-hold-loop.yaml")


# ── The reconciliation ledger ────────────────────────────────────────────────────────────


def test_reconciled_set_is_exactly_what_validates_today() -> None:
    """The live record of the corpus reconciliation pass, asserted rather than assumed.

    A fixture that starts validating (or stops) is a corpus or envelope change that must be
    seen: the reconciliation pass is a WA-04-routed revision, and an unannounced drift in
    either direction is exactly what the fidelity matrix exists to catch.
    """
    validates = tuple(
        relative
        for relative in (path.relative_to(FIXTURES_DIR).as_posix() for path in _fixture_files())
        # A mixed fixture's `property:` is the list of properties it exercises, so its owning
        # slug is not readable off the fixture; RECONCILED_MIXED covers those separately.
        if isinstance(_load(relative).get("property"), str) and _in_ratified_shape(relative)
    )
    assert validates == RECONCILED


def _in_ratified_shape(relative: str) -> bool:
    """Whether this fixture's ``expected:`` block validates into the envelope as it stands."""
    document = _load(relative)
    try:
        validate_report({"property": document["property"], **document["expected"]})
    except ValidationError:
        return False
    return True


def test_the_corpus_is_read_only_here() -> None:
    """WA-04: the fixture corpus is a vendored contract surface, never edited to fit a model."""
    assert FIXTURES_DIR.is_dir()
    assert len(_fixture_files()) >= 60
