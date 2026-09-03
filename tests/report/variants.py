"""The variant catalog — one run report per REPORT-FORMAT-SPEC §4 rendering row.

CLI-03's first acceptance box is "every wedge witness/failure variant renders without error
(golden-tested)". A test that renders a handful of corpus fixtures would not show that: the
corpus does not carry every variant (no tool error, no strict promotion, no capped census, no
vacuous form-(c) carrier), and "every variant" has to be checked against the envelope rather
than against a sample. So this module builds a catalog of run reports that between them touch
every §4.2–§4.5 row, and ``test_coverage.py`` proves the coverage against the live models —
every concrete envelope class and every closed vocabulary member — instead of trusting the
list below to be complete.

**The reports are real, not hand-assembled.** Each case stubs the five wedge validators with
functions that return the canned reports, then calls :func:`gebra.verify.verify`, so the
thirteen outcomes, the marker filling, the §2.2 gate derivation, the §2.3 promotions and
``best_effort`` are VAL-11's own — never restated here. What a case chooses is the *records*;
what the run makes of them is the aggregation's.

Never-invokes (WA-07): the stub validators ignore the IR and return values; nothing here
imports langgraph, executes a workflow node, calls a model or opens a socket.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Final

from gebra import __version__
from gebra.ir import WorkflowIR
from gebra.verify import (
    WEDGE_SLUGS,
    Advisory,
    CoFailure,
    CounterGuardSource,
    CycleCensus,
    CycleLocation,
    DataflowCoverage,
    DataflowLocation,
    DataflowWitness,
    DeterminismClaim,
    DeterminismNodeLocation,
    DeterminismWitness,
    EdgeLocation,
    EffectSafetyWitness,
    Failure,
    GuardEdgeLabels,
    GuardEdgeRef,
    NodeLocation,
    P01EdgeLocation,
    P02CycleLocation,
    P02SccLocation,
    P04Failure,
    P06EffectRecord,
    P06NodeLocation,
    PathLocation,
    PropertyReport,
    PropertySlug,
    RecursionLimitDecl,
    RecursionLimitSource,
    RunPolicy,
    RunReport,
    SccLocation,
    StateKeyLocation,
    StrictPolicy,
    SubjectRef,
    TerminationWitness,
    VariantDecl,
    VariantSource,
    WellFormednessWitness,
    WitnessInventoryEntry,
    WitnessNote,
    not_implemented,
    register_validator,
    unregister_validator,
    validator_for,
    verify,
)
from gebra.verify.base import to_data

__all__ = ["CASES", "Case", "case_report", "stub_wedge"]

#: A minimal IR the stub validators ignore. It exists because ``verify()`` takes one and
#: computes the subject's digest from it — not because any variant depends on its shape.
_IR_DOCUMENT: Final[dict[str, Any]] = {
    "ir_version": "1.0",
    "entry": "check_availability",
    "finish": "send_confirmation",
    "state": {"booking_id": "str"},
    "nodes": [
        {"id": "check_availability"},
        {"id": "book_flight"},
        {"id": "send_confirmation"},
    ],
    "edges": [
        {"kind": "normal", "from": "check_availability", "to": "book_flight"},
        {"kind": "normal", "from": "book_flight", "to": "send_confirmation"},
    ],
}


def _ir() -> WorkflowIR:
    # The IR models are strict (IR-SPEC §2.5 note 4), so parsed document data validates in
    # JSON mode — the same ingestion path the loaders use.
    return WorkflowIR.model_validate_json(json.dumps(_IR_DOCUMENT))


IR: Final[WorkflowIR] = _ir()


@contextmanager
def stub_wedge(reports: dict[PropertySlug, PropertyReport]) -> Iterator[None]:
    """Register stub validators for the wedge five, restoring the real ones afterwards.

    A slug with no canned report answers with a vacuous pass, so ``verify()`` always finds all
    five registered — §1.4 rule 2 makes a missing wedge validator a tool error, and a case that
    wanted a verdict would get an exit 2 instead.
    """
    original = {slug: validator_for(slug) for slug in WEDGE_SLUGS}
    try:
        for slug in WEDGE_SLUGS:
            unregister_validator(slug)
            report = reports.get(slug, _VACUOUS[slug])
            register_validator(slug, _returning(report))
        yield
    finally:
        for slug, validator in original.items():
            unregister_validator(slug)
            if validator is not None:
                register_validator(slug, validator)


def _returning(report: PropertyReport) -> Any:
    def validate(ir: WorkflowIR, /) -> PropertyReport:
        return report

    return validate


# ── The vacuous passes a case does not override ──────────────────────────────────────────

_VACUOUS: Final[dict[PropertySlug, PropertyReport]] = {
    "graph-well-formed": PropertyReport.passing(
        "graph-well-formed",
        WellFormednessWitness(
            kind="well-formedness",
            reachable_from_start=("book_flight", "check_availability", "send_confirmation"),
            terminal_nodes=("send_confirmation",),
            orphan_nodes=(),
            unresolved_targets=(),
        ),
    ),
    "termination-witness": PropertyReport.passing(
        "termination-witness",
        TerminationWitness(
            kind="termination",
            inventory=(),
            certificate=("START", "check_availability", "book_flight", "send_confirmation", "END"),
        ),
    ),
    "dataflow-completeness": PropertyReport.passing(
        "dataflow-completeness",
        DataflowWitness(
            kind="dataflow",
            coverage=(
                DataflowCoverage(
                    node="send_confirmation", key="booking_id", satisfied_by=("book_flight",)
                ),
            ),
        ),
    ),
    "effect-safety": PropertyReport.passing(
        "effect-safety", EffectSafetyWitness(kind="effect-safety", cycles=(), effects=())
    ),
    "determinism-replay": PropertyReport.passing(
        "determinism-replay",
        DeterminismWitness(kind="determinism", claims=(), claim_class="heuristic"),
    ),
}


# ── The witness variants (§4.3) ──────────────────────────────────────────────────────────

_TERMINATION_RICH = PropertyReport.passing(
    "termination-witness",
    TerminationWitness(
        kind="termination",
        inventory=(
            WitnessInventoryEntry(
                form="a",
                element=EdgeLocation(kind="edge", source="route", target="retry", label="again"),
                source=CounterGuardSource(
                    guard_edge=GuardEdgeRef(source="route", label="again"),
                    counter_key="attempts",
                    bound=3,
                ),
                discharges="all-simple-cycles-through-element",
            ),
            WitnessInventoryEntry(
                form="b",
                source=RecursionLimitSource(
                    recursion_limit=RecursionLimitDecl(
                        value=25, justification="the operator caps a support loop at 25 steps"
                    )
                ),
                discharges="blanket",
            ),
            WitnessInventoryEntry(
                form="c",
                element=NodeLocation(kind="node", node="refine"),
                source=VariantSource(variant=VariantDecl(key="budget", measure="budget")),
                discharges="all-simple-cycles-through-element",
            ),
            WitnessInventoryEntry(
                form="c",
                element=NodeLocation(kind="node", node="summarize"),
                source=VariantSource(variant=VariantDecl(key="pending", measure="len(pending)")),
                discharges=(),
            ),
        ),
        certificate=("START", "route", "refine", "END"),
        notes=(
            WitnessNote(
                kind="scc-covered-only-by-recursion-limit",
                severity="warning",
                locations=(
                    P02SccLocation(
                        kind="scc",
                        nodes=("refine", "route"),
                        representative_cycle=("refine", "route"),
                        exhaustive=False,
                        blanket_only=True,
                    ),
                ),
            ),
            WitnessNote(kind="recursion-limit-without-justification"),
            WitnessNote(kind="variant-key-not-in-state", node="refine", key="budget"),
            WitnessNote(
                kind="counter-key-not-qualified",
                guard_edge=GuardEdgeRef(source="route", label="again"),
                identifier="attempts",
                declared_type="str",
            ),
            WitnessNote(kind="cycle-census-capped"),
        ),
        cycles=CycleCensus(exhaustive=True, cycles=(("refine", "route"),)),
    ),
)

_EFFECT_SAFETY_RICH = PropertyReport.passing(
    "effect-safety",
    EffectSafetyWitness(
        kind="effect-safety",
        cycles=(("book_flight", "retry_booking"),),
        effects=(
            P06EffectRecord(
                node="book_flight",
                effect=("billable",),
                region="retry",
                cycle=("book_flight", "retry_booking"),
                protection="idempotency_key",
                key="booking_ref",
            ),
            P06EffectRecord(
                node="charge_card",
                effect=("billable", "irreversible"),
                region="cycle",
                cycle=("book_flight", "retry_booking"),
                protection="compensation_hook",
                hook="refund",
            ),
            P06EffectRecord(
                node="send_confirmation",
                effect=("audit",),
                region="acyclic",
                protection="none_required",
            ),
        ),
    ),
)

_DETERMINISM_RICH = PropertyReport.passing(
    "determinism-replay",
    DeterminismWitness(
        kind="determinism",
        claims=(
            DeterminismClaim(
                node="draft_itinerary",
                llm_backed=True,
                seed=7,
                temperature=0.0,
                divergence_handling="logged",
            ),
            DeterminismClaim(
                node="normalize",
                llm_backed=False,
                basis="pure-local-computation",
                pinning_required=False,
            ),
        ),
        caveat="provider-seed-reproducibility-not-guaranteed",
        claim_class="heuristic",
    ),
)


# ── The failure-side variants (§4.4) and the location variants (§4.5) ────────────────────

_P01_FAILURE = PropertyReport.failing(
    "graph-well-formed",
    Failure(
        property_condition="node-unreachable-from-start",
        location=NodeLocation(kind="node", node="escalate_to_human"),
        severity="fatal",
        claim_class="defensible",
        remediation="Wire an edge into the node, or remove it from the definition.",
        co_failures=(
            CoFailure(
                property="graph-well-formed",
                property_condition="edge-target-undefined",
                location=P01EdgeLocation(
                    kind="edge", source="route", label="escalate", undefined_target="escalate"
                ),
                severity="fatal",
                claim_class="defensible",
                note="the label names no node in the definition",
            ),
            CoFailure(
                property="graph-well-formed",
                property_condition="orphan-node",
                location=NodeLocation(kind="node", node="stranded"),
                severity="fatal",
                claim_class="defensible",
            ),
            CoFailure(
                property="graph-well-formed",
                property_condition="path-map-target-undefined",
                location=P01EdgeLocation(
                    kind="edge",
                    source="route",
                    target="book_flight",
                    label="book",
                    undefined_target="booking",
                ),
                severity="fatal",
                claim_class="defensible",
            ),
            CoFailure(
                property="graph-well-formed",
                property_condition="dead-end-node-not-wired-to-end",
                location=NodeLocation(kind="node", node="archive"),
                severity="fatal",
                claim_class="defensible",
                subsumed_by="P-01",
            ),
        ),
        advisories=(
            Advisory(
                property="determinism-replay",
                property_condition="deterministic-llm-seed-unpinned",
                severity="warning",
                claim_class="heuristic",
                location=NodeLocation(kind="node", node="draft_itinerary"),
            ),
        ),
    ),
)

_P02_FAILURE = PropertyReport.failing(
    "termination-witness",
    Failure(
        property_condition="cycle-without-termination-witness",
        location=P02SccLocation(
            kind="scc",
            nodes=("book_flight", "confirm", "retry_booking"),
            representative_cycle=("book_flight", "retry_booking", "confirm"),
            exhaustive=False,
        ),
        severity="fatal",
        claim_class="defensible",
        remediation="Declare a bounded counter guard with an exit edge, or annotate a variant.",
        co_failures=(
            CoFailure(
                property="termination-witness",
                property_condition="counter-guard-without-exit-edge",
                location=P02CycleLocation(
                    kind="cycle",
                    nodes=("book_flight", "retry_booking"),
                    counter_key="attempts",
                    guard_edge=GuardEdgeLabels(source="route", labels=("again", "stop")),
                ),
                severity="fatal",
                claim_class="defensible",
                notes=(
                    WitnessNote(
                        kind="counter-key-not-qualified",
                        guard_edge=GuardEdgeRef(source="route", label="again"),
                        identifier="attempts",
                    ),
                ),
            ),
        ),
        notes=(
            WitnessNote(
                kind="scc-covered-only-by-recursion-limit",
                severity="warning",
                locations=(
                    P02SccLocation(
                        kind="scc",
                        nodes=("draft", "review"),
                        representative_cycle=("draft", "review"),
                        exhaustive=False,
                        blanket_only=True,
                    ),
                ),
            ),
        ),
    ),
)

_P04_FAILURE = PropertyReport.failing(
    "dataflow-completeness",
    P04Failure(
        property_condition="read-key-never-written-on-path",
        location=DataflowLocation(
            kind="state-key",
            key="booking_id",
            node="send_confirmation",
            path=("START", "check_availability", "send_confirmation"),
        ),
        severity="fatal",
        claim_class="defensible-a",
        writers_on_other_paths=("book_flight",),
        downstream_writers=("archive",),
    ),
)

_P06_FAILURE = PropertyReport.failing(
    "effect-safety",
    Failure(
        property_condition="irreversible-with-keyless-idempotent",
        location=P06NodeLocation(
            kind="node",
            node="charge_card",
            effect=("billable", "irreversible"),
            idempotent="keyless",
            fanout="send",
            dangling_compensation_hook="refund",
        ),
        severity="fatal",
        claim_class="defensible-a",
        co_failures=(
            CoFailure(
                property="effect-safety",
                property_condition="unprotected-effect-in-cycle",
                location=CycleLocation(kind="cycle", nodes=("book_flight", "retry_booking")),
                severity="error",
                claim_class="defensible-a",
            ),
            CoFailure(
                property="effect-safety",
                property_condition="unprotected-effect-in-retry-region",
                location=P06NodeLocation(
                    kind="node",
                    node="book_flight",
                    effect=("billable",),
                    cycle=("book_flight", "retry_booking"),
                ),
                severity="error",
                claim_class="defensible-a",
            ),
        ),
        advisories=(
            # §3.2 rule 1: only a WARNING-grade finding may ride another property's report, so
            # the advisory carries one of the two §0.4 entries registered WARNING. Its anchor
            # is the §3.2 rule 3 reduction of P-08's own `DeterminismNodeLocation`.
            Advisory(
                property="determinism-replay",
                property_condition="deterministic-llm-temperature-unpinned",
                severity="warning",
                claim_class="heuristic",
                location=NodeLocation(kind="node", node="extract_fields"),
            ),
        ),
    ),
)

_P08_FAILURE = PropertyReport.failing(
    "determinism-replay",
    Failure(
        property_condition="deterministic-llm-seed-unpinned",
        location=DeterminismNodeLocation(
            kind="node",
            node="draft_itinerary",
            annotation="deterministic",
            form="bare-boolean",
            effects=("network", "external"),
        ),
        severity="warning",
        claim_class="heuristic",
        co_failures=(
            CoFailure(
                property="determinism-replay",
                property_condition="deterministic-llm-temperature-unpinned",
                location=DeterminismNodeLocation(
                    kind="node",
                    node="extract_fields",
                    annotation="deterministic",
                    seed=7,
                    temperature=0.7,
                ),
                severity="warning",
                claim_class="heuristic",
            ),
        ),
    ),
)

#: §4.5's bare anchors, on one report. The condition ID is a **carrier, not a claim**: §P-01.3
#: pins `P01EdgeLocation` for `edge-target-undefined`, and no conformant Phase-0 report anchors
#: it on an SCC, a Σ key or a path. These rows exist in §4.5 and a rendering must carry them, so
#: the catalog reaches them the only way it can — synthetically, with the grade and the class
#: read off the §0.4 registry so nothing here invents one.
_P01_EDGE_ANCHOR_FAILURE = PropertyReport.failing(
    "graph-well-formed",
    Failure(
        property_condition="edge-target-undefined",
        location=EdgeLocation(kind="edge", source="route", target="book_flight"),
        severity="fatal",
        claim_class="defensible",
        co_failures=(
            CoFailure(
                property="graph-well-formed",
                property_condition="edge-target-undefined",
                location=EdgeLocation(kind="edge", source="route", label="dangling"),
                severity="fatal",
                claim_class="defensible",
            ),
            CoFailure(
                property="graph-well-formed",
                property_condition="edge-target-undefined",
                location=SccLocation(kind="scc", nodes=("a", "b")),
                severity="fatal",
                claim_class="defensible",
            ),
            CoFailure(
                property="graph-well-formed",
                property_condition="edge-target-undefined",
                location=StateKeyLocation(kind="state-key", key="itinerary"),
                severity="fatal",
                claim_class="defensible",
            ),
            CoFailure(
                property="graph-well-formed",
                property_condition="edge-target-undefined",
                location=PathLocation(
                    kind="path", nodes=("START", "check_availability", "book_flight")
                ),
                severity="fatal",
                claim_class="defensible",
            ),
        ),
    ),
)


@dataclass(frozen=True)
class Case:
    """One catalog entry: a name, the run report it renders, and why it is in the catalog."""

    name: str
    report: RunReport
    covers: str


def case_report(
    reports: dict[PropertySlug, PropertyReport],
    *,
    strict: StrictPolicy | None = None,
    source: str = "travel_booking:build_graph",
    input_mode: str = "extracted",
    version: str | None = None,
    # The build that extracted the subject is this one — the value `gebra.cli.verify` and the
    # snapshot engine record — so the goldens normalize it together with `tool.version`
    # (``goldens.normalize``). A literal here would drift from that placeholder at the first
    # version bump, which is what the `0.0.1` release cut found (GOV-14).
    extractor_version: str | None = __version__,
    sidecar: str | None = None,
) -> RunReport:
    """Run ``verify()`` with the wedge five stubbed to return ``reports``."""
    subject = SubjectRef(
        source=source,
        input_mode=input_mode,  # type: ignore[arg-type]
        version=version,
        extractor_version=extractor_version,
        sidecar=sidecar,
    )
    with stub_wedge(reports):
        return verify(IR, RunPolicy(strict=strict or StrictPolicy(mode="off"), subject=subject))


def _tool_error_report() -> RunReport:
    """A dispatch tool error, produced the way §2.4 produces one: an unregistered wedge slug."""
    original = validator_for("graph-well-formed")
    unregister_validator("graph-well-formed")
    try:
        return verify(IR, RunPolicy(subject=SubjectRef(source="travel_booking:build_graph")))
    finally:
        if original is not None:
            register_validator("graph-well-formed", original)


#: A P-02 pass whose promotable-note vocabulary outruns TERMINATION-WITNESS-SPEC §6.1's
#: identity rule: a WARNING-grade ``variant-key-not-in-state`` has no §6.1 row, so
#: ``strict_promotions`` refuses rather than dropping a promotion the user was owed. §2.4's
#: ``1.1`` amendment turns that refusal into a ``dispatch`` tool error, which is the arm this
#: case renders — the same IR must not answer normally with strict off and raise with it on.
_TERMINATION_UNNAMEABLE_PROMOTION = PropertyReport.passing(
    "termination-witness",
    TerminationWitness(
        kind="termination",
        inventory=(),
        certificate=("START", "route", "END"),
        notes=(
            WitnessNote(
                kind="variant-key-not-in-state", severity="warning", node="refine", key="budget"
            ),
        ),
    ),
)


def _not_yet_implemented_report() -> RunReport:
    """The one §4.2 row ``verify()`` cannot produce, built through validation instead.

    ``not-yet-implemented`` is the marker for a **wedge** property with no registered
    validator — and a run in that state is exit 2 by §1.4 rule 2, which carries no outcomes at
    all. So the marker never reaches a run report the aggregation builds, while §4.2 still
    gives it a rendering row and a consumer loading a report from another build can meet one.
    This case is that report, validated rather than constructed (PC-6), so the shape is the
    model's own.
    """
    data = to_data(case_report({}))
    marker = to_data(not_implemented_marker("termination-witness"))
    data["properties"] = [
        marker if outcome.get("property") == "termination-witness" else outcome
        for outcome in data["properties"]
    ]
    return RunReport.model_validate_json(json.dumps(data))


def _tool_error_without_a_subject() -> RunReport:
    """§2.4's "where identity was never established, ``subject: null``".

    ``verify()`` reaches it only through a `CanonicalizationError` on an IR with no canonical
    form — a state no valid `WorkflowIR` in this repository is in — so the report is built
    through validation from the tool-error case with its subject dropped. §5.1 rule 1 still
    wants a subject line, and this is the run that has nothing to put in one.
    """
    data = to_data(_tool_error_report())
    data.pop("subject", None)
    return RunReport.model_validate_json(json.dumps(data))


def not_implemented_marker(slug: PropertySlug) -> Any:
    """The ``not-yet-implemented`` marker the registry answers with for an unwired wedge slug."""
    original = validator_for(slug)
    unregister_validator(slug)
    try:
        return not_implemented(slug)
    finally:
        if original is not None:
            register_validator(slug, original)


def _build_cases() -> tuple[Case, ...]:
    return (
        Case(
            name="all-pass",
            report=case_report({}, input_mode="ir-document", extractor_version=None),
            covers="§4.2 passing reports and markers; §4.3 vacuous witnesses; a clean gate",
        ),
        Case(
            name="rich-witnesses",
            report=case_report(
                {
                    "termination-witness": _TERMINATION_RICH,
                    "effect-safety": _EFFECT_SAFETY_RICH,
                    "determinism-replay": _DETERMINISM_RICH,
                },
                input_mode="snapshot",
                version="1.4.2.0",
                extractor_version=None,
            ),
            covers="§4.3 every witness substructure, every note kind, every region/protection",
        ),
        Case(
            name="rich-witnesses-strict",
            report=case_report(
                {
                    "termination-witness": _TERMINATION_RICH,
                    "effect-safety": _EFFECT_SAFETY_RICH,
                    "determinism-replay": _DETERMINISM_RICH,
                },
                strict=StrictPolicy(mode="all"),
            ),
            covers="§4.2 Promotion, including the §2.3 witness-note identity rule",
        ),
        Case(
            name="p01-fatal-best-effort",
            report=case_report(
                {
                    "graph-well-formed": _P01_FAILURE,
                    "termination-witness": _TERMINATION_RICH,
                    "dataflow-completeness": _P04_FAILURE,
                },
            ),
            covers="§4.2 best_effort; §4.4 co-failures, advisories, subsumed_by, a held id",
        ),
        Case(
            name="wedge-failures",
            report=case_report(
                {
                    "termination-witness": _P02_FAILURE,
                    "dataflow-completeness": _P04_FAILURE,
                    "effect-safety": _P06_FAILURE,
                    "determinism-replay": _P08_FAILURE,
                },
            ),
            covers="§4.4/§4.5 every wedge failure and every concrete location subtype",
        ),
        Case(
            name="warning-only-strict-per-property",
            report=case_report(
                {"determinism-replay": _P08_FAILURE},
                strict=StrictPolicy(mode="per-property", properties=("determinism-replay",)),
                sidecar="gebra.toml",
            ),
            covers="§2.2 a fail record at exit 1 by promotion only; a per-property policy",
        ),
        Case(
            name="warning-only-no-strict",
            report=case_report({"determinism-replay": _P08_FAILURE}),
            covers="§2.2 pass-with-notes: a `fail` record that leaves the run at exit 0",
        ),
        Case(
            name="wedge-failures-strict",
            report=case_report(
                {
                    "termination-witness": _P02_FAILURE,
                    "dataflow-completeness": _P04_FAILURE,
                    "effect-safety": _P06_FAILURE,
                    "determinism-replay": _P08_FAILURE,
                },
                strict=StrictPolicy(mode="all"),
            ),
            covers="§2.3's four promotion origins, including an advisory and a fail-path note",
        ),
        Case(
            name="not-yet-implemented-marker",
            report=_not_yet_implemented_report(),
            covers="§4.2's second NotImplementedMarker row, which `verify()` cannot produce",
        ),
        Case(
            name="anchor-locations",
            report=case_report({"graph-well-formed": _P01_EDGE_ANCHOR_FAILURE}),
            covers="§4.5 the bare anchors: edge, dangling edge, scc, state-key",
        ),
        Case(
            name="tool-error",
            report=_tool_error_report(),
            covers="§4.2 ToolError; §2.4 exit 2 with no outcomes; A.7's exit-2 SARIF log",
        ),
        Case(
            name="tool-error-without-a-subject",
            report=_tool_error_without_a_subject(),
            covers="§2.4's `subject: null` run — no identity was ever established",
        ),
        Case(
            name="tool-error-ungateable",
            report=case_report(
                {"termination-witness": _TERMINATION_UNNAMEABLE_PROMOTION},
                strict=StrictPolicy(mode="all"),
            ),
            covers="§2.4's `1.1` arm: a gate that cannot be derived is a dispatch tool error",
        ),
    )


#: The catalog. ``test_coverage.py`` proves it reaches every §4 row.
CASES: Final[tuple[Case, ...]] = _build_cases()
