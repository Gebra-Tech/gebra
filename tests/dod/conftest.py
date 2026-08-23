"""The DoD scenario, built once and timed — SD-09's harness spine.

PD-006 R5 fixes the shape this package tests: the DoD scenario is **one** run of
extract → verify → snapshot → evolve → diff → report over the travel-booking agent — the
five seeded-defect variants plus the R4 evolution sequence — and the dedicated CI job that
runs it records, beside its total wall-clock, the non-gating **"gebra-work seconds"**
sub-metric: the summed wall-time of the scenario's own steps, so an infrastructure slowdown
is never misread as a gebra slowdown (R5 amendment, guard 2).

This conftest is both things at once: the scenario as a package-scoped fixture — every leg
executed in R5's order, each leg timed around exactly the gebra calls it makes — and the
sub-metric's reporter, a ``pytest_terminal_summary`` block that prints the per-leg seconds
and appends them to ``$GITHUB_STEP_SUMMARY`` when CI provides one. The metric is
informational by ruling: nothing here asserts a duration, and the <5:00 budget is the CI
job's total clock (enforced by the job's own ``timeout-minutes``), never a pytest verdict.

The evolve leg inherits the boundary SD-08 measured: v1–v6 verify clean and
snapshot-eligible, so they are recorded **through the eligibility gate** (the report handed
to the recorder — CLI-SPEC §4.2's one-resolution flow, one extraction feeding both the gate
and the store); v7–v8 carry the FATAL ``cycle-without-termination-witness``, the recorder
handed their reports refuses them (captured here, asserted in the suite), and they land
only through the engine's documented handed-none-records posture — both halves of PD-006
R4's "every version is snapshotted and re-verified" true, joined by this caller.
"""

from __future__ import annotations

import os
import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Final

import pytest

from gebra import extract
from gebra.audit import export_store, freshness
from gebra.extraction import ExtractionEnvelope
from gebra.lineage import Lineage, compare, dump_lineage, lineage
from gebra.snapshot import SnapshotError, SnapshotOutcome, record
from gebra.store import SnapshotStore
from gebra.verify import RunPolicy, RunReport, StrictPolicy, verify
from gebra.versioning import Component  # noqa: F401  (re-exported for the suite's tables)
from tests.sample_workflows import travel_booking as tb
from tests.sample_workflows import travel_booking_defects as dv
from tests.sample_workflows import travel_booking_evolution as evo

#: The scenario's legs, in PD-006 R5's order. The timing table carries exactly these keys.
LEGS: Final[tuple[str, ...]] = ("extract", "verify", "snapshot", "evolve", "diff", "report")

#: The lineage document's file name in ``.gebra/reports/`` — the PD-047 mitigation artifact.
#: It cannot collide with a per-version report: those always end ``.report.json``.
LINEAGE_EXPORT_NAME: Final[str] = "lineage.json"

#: Per-leg wall seconds of the one scenario build, filled by :func:`_leg` and read by the
#: terminal-summary hook. Module state rather than a fixture so the summary outlives the
#: fixture cache and reports even when a later leg failed.
_TIMINGS: dict[str, float] = {}


@pytest.fixture(autouse=True)
def _nothing_was_executed() -> Iterator[None]:
    """The scenario is read, never run — asserted on entry to and exit from every test.

    The whole fixture family shares one ledger (``travel_booking.TRIPPED``); the one test
    that fires bodies on purpose (the arming test) restores it itself, the TE-05 idiom.
    """
    assert tb.TRIPPED == []
    yield
    assert tb.TRIPPED == []


@contextmanager
def _leg(name: str) -> Iterator[None]:
    """Time one scenario leg into the module table — additive, so re-entry accumulates."""
    started = time.perf_counter()
    try:
        yield
    finally:
        _TIMINGS[name] = _TIMINGS.get(name, 0.0) + (time.perf_counter() - started)


def _instant(index: int) -> datetime:
    """The injected clock — one fixed instant per stage, so the store is a pure function."""
    return datetime(2026, 8, 23, 9, 0, index, tzinfo=timezone.utc)


def _source(stage: evo.EvolutionStage) -> str:
    """The CLI-SPEC §2.1-shaped subject reference for a recorded stage."""
    return f"{stage.build.__module__}:{stage.build.__qualname__}"


#: The per-property promotion R2 rules for the defect-3 catch — the API spelling of
#: ``--gebra-strict=determinism-replay``.
STRICT_DETERMINISM: Final[StrictPolicy] = StrictPolicy(
    mode="per-property", properties=("determinism-replay",)
)


@dataclass(frozen=True)
class DodScenario:
    """Everything one run of the DoD scenario produced, leg by leg.

    Attributes:
        stage_envelopes: One extraction per evolution stage, v1 first — each stage's single
            resolution, feeding verify, the eligibility gate and the store alike.
        stage_reports: ``verify()`` over each stage's IR, default policy.
        defect_envelopes: One extraction per seeded-defect variant, keyed by variant name.
        defect_reports: ``verify()`` over each variant's IR, default policy.
        defect_strict_reports: The R2 strict leg — ``verify()`` under the
            ``determinism-replay`` per-property promotion — for every variant, so the suite
            can also assert the promotion moves no other variant's gate.
        healthy_strict_report: The same strict policy over healthy v1 — the negative
            harness's control (no finding to promote, so the gate must stay 0).
        store: The scenario's ``.gebra/`` store, all eight versions recorded.
        outcomes: The eight recording outcomes, in sequence order.
        refusals: Stage name → the ``SnapshotErrorReason`` the recorder answered when a
            FATAL-bearing stage was offered **with** its eligibility report (v7 and v8).
        listing: ``lineage(store)`` after the evolve leg.
        pair_diffs: ``compare(store, previous, version)`` per consecutive pair — the diff
            leg re-derived from the store's own files, not from the in-memory IRs.
        exports: ``export_store(store)`` — one audit report per stored version.
        lineage_path: Where the report leg wrote the lineage document (PD-047 mitigation).
        lineage_text: The exact text written there.
        freshness_outcome: The freshness check over the final stage's IR — the CI-check
            surface, green when the working definition matches the store's current.
        timings: The per-leg seconds table (live view of the module accumulator).
    """

    stage_envelopes: tuple[ExtractionEnvelope, ...]
    stage_reports: tuple[RunReport, ...]
    defect_envelopes: Mapping[str, ExtractionEnvelope]
    defect_reports: Mapping[str, RunReport]
    defect_strict_reports: Mapping[str, RunReport]
    healthy_strict_report: RunReport
    store: SnapshotStore
    outcomes: tuple[SnapshotOutcome, ...]
    refusals: Mapping[str, Any]
    listing: Lineage
    pair_diffs: tuple[Any, ...]
    exports: tuple[Any, ...]
    lineage_path: Path
    lineage_text: str
    freshness_outcome: Any
    timings: Mapping[str, float]


@pytest.fixture(scope="package")
def dod(tmp_path_factory: pytest.TempPathFactory) -> DodScenario:
    """The scenario, run once in R5's leg order — the store every test in this suite reads."""
    # extract — one resolution per subject: eight stages, five defect variants.
    with _leg("extract"):
        stage_envelopes = tuple(extract(stage.build()) for stage in evo.EVOLUTION)
        defect_envelopes = {defect.name: extract(defect.build()) for defect in dv.DEFECTS}

    # verify — every subject answered under the default policy; the R2 strict leg beside it.
    with _leg("verify"):
        stage_reports = tuple(verify(envelope.ir) for envelope in stage_envelopes)
        defect_reports = {name: verify(envelope.ir) for name, envelope in defect_envelopes.items()}
        strict_policy = RunPolicy(strict=STRICT_DETERMINISM)
        defect_strict_reports = {
            name: verify(envelope.ir, strict_policy) for name, envelope in defect_envelopes.items()
        }
        healthy_strict_report = verify(stage_envelopes[0].ir, strict_policy)

    # snapshot — v1 through the eligibility gate: the digest the gate saw is the digest
    # stored (CLI-SPEC §4.2's one-resolution rule, which is why `record` exists).
    store = SnapshotStore.for_project(tmp_path_factory.mktemp("dod"))
    with _leg("snapshot"):
        outcomes = [
            record(
                stage_envelopes[0],
                store=store,
                source=_source(evo.EVOLUTION[0]),
                extracted_at=_instant(0),
                eligibility=stage_reports[0],
            )
        ]

    # evolve — v2..v8 under the SD-08 boundary: eligible stages through the gate; the two
    # FATAL-bearing stages refused with their reports, then recorded handed-none.
    refusals: dict[str, Any] = {}
    with _leg("evolve"):
        for index, stage in enumerate(evo.EVOLUTION[1:], start=1):
            envelope, report = stage_envelopes[index], stage_reports[index]
            if report.gate.snapshot_eligible:
                outcomes.append(
                    record(
                        envelope,
                        store=store,
                        source=_source(stage),
                        extracted_at=_instant(index),
                        eligibility=report,
                    )
                )
                continue
            try:
                record(
                    envelope,
                    store=store,
                    source=_source(stage),
                    extracted_at=_instant(index),
                    eligibility=report,
                )
            except SnapshotError as refusal:
                refusals[stage.name] = refusal.reason
            outcomes.append(
                record(
                    envelope,
                    store=store,
                    source=_source(stage),
                    extracted_at=_instant(index),
                    eligibility=None,
                )
            )

    # diff — the consecutive pairs re-derived from the store's own files.
    with _leg("diff"):
        listing = lineage(store)
        versions = tuple(entry.version for entry in listing.entries)
        pair_diffs = tuple(
            compare(store, versions[index - 1], versions[index])
            for index in range(1, len(versions))
        )

    # report — the audit export for every stored version, plus the PD-047 lineage document
    # beside them, plus the freshness check over the final working definition.
    with _leg("report"):
        exports = export_store(store)
        lineage_path = exports[0].path.parent / LINEAGE_EXPORT_NAME
        lineage_text = dump_lineage(lineage(store))
        lineage_path.write_text(lineage_text, encoding="utf-8")
        freshness_outcome = freshness(stage_envelopes[-1].ir, store=store)

    return DodScenario(
        stage_envelopes=stage_envelopes,
        stage_reports=stage_reports,
        defect_envelopes=defect_envelopes,
        defect_reports=defect_reports,
        defect_strict_reports=defect_strict_reports,
        healthy_strict_report=healthy_strict_report,
        store=store,
        outcomes=tuple(outcomes),
        refusals=refusals,
        listing=listing,
        pair_diffs=pair_diffs,
        exports=exports,
        lineage_path=lineage_path,
        lineage_text=lineage_text,
        freshness_outcome=freshness_outcome,
        timings=_TIMINGS,
    )


def pytest_terminal_summary(terminalreporter: object) -> None:
    """Report the R5 sub-metric: per-leg and summed gebra-work seconds, non-gating.

    Printed whenever the scenario ran in this session; appended to
    ``$GITHUB_STEP_SUMMARY`` when CI provides one, so the DoD job's summary page carries
    the setup-vs-scenario split beside the job's own total wall-clock.
    """
    if not _TIMINGS:
        return
    write = getattr(terminalreporter, "write_line", print)
    total = sum(_TIMINGS.values())
    parts = ", ".join(f"{leg} {_TIMINGS[leg]:.2f}s" for leg in LEGS if leg in _TIMINGS)
    write(f"gebra-work seconds (PD-006 R5 sub-metric, non-gating): {total:.2f}s — {parts}")

    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        lines = ["### gebra-work seconds (PD-006 R5 sub-metric, non-gating)", ""]
        lines += ["| leg | seconds |", "|---|---|"]
        lines += [f"| {leg} | {_TIMINGS[leg]:.2f} |" for leg in LEGS if leg in _TIMINGS]
        lines += [f"| **total** | **{total:.2f}** |", ""]
        with open(summary, "a", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")
