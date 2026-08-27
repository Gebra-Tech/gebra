"""``verify()`` — the run-level aggregation and its gate (REPORT-FORMAT-SPEC §1–§3).

What VAL-11 has to make observable is not that the five validators work — their own cards did
that — but that the **run** built on top of them says the right thing: thirteen outcomes in
catalog order, the §0.2 severity ladder mapped onto exit codes 0/1/2, strict promotion in both
of its forms with every record left exactly as it stands, the FATAL-suppresses-the-snapshot
signal, and the tool-error path that is never a verification result.

Three claims here are the card's acceptance boxes, and each is proven by a run that was
watched rather than by an assertion about the code:

* **the exit-code matrix** — every rung of §2.2 reached by a real IR through the real
  validators, including both strict forms, the per-property form declining to promote a
  property it does not name, and both ways a run reaches exit ``2``;
* **P-01 FATAL gating the contract-weight of the topology validators** — §0.3 defines P-02,
  P-04 and P-06 results only over P-01-clean topology, so the run reports them as best-effort
  *and* its gate is shown to be invariant under any answer they could have given;
* **hermeticity** — a fresh interpreter with socket and DNS raisers armed runs ``verify()``
  over all 67 IR snapshots of the vendored corpus and reports its own import closure, with
  four negative controls proving the raisers are live.

Nothing here executes a workflow node, calls a model or opens a network connection (WA-07).
The IRs are hand-built dictionaries and the corpus documents are read with ``safe_load``;
``source_snippet`` is never touched.
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any, Final, get_args

import pytest

from gebra.ir import DynamicEdge, WorkflowIR, graph_version
from gebra.ir.canonical import CanonicalizationError, CanonicalizationErrorReason
from gebra.verify import (
    PROPERTY_SLUGS,
    REPORT_FORMAT,
    STRICT_ALL,
    STRICT_OFF,
    TOPOLOGY_SLUGS,
    WEDGE_SLUGS,
    Advisory,
    CoFailure,
    DataflowLocation,
    DataflowWitness,
    EdgeLocation,
    EffectSafetyWitness,
    Failure,
    GateOutcome,
    NodeLocation,
    NotImplementedMarker,
    P01EdgeLocation,
    P02SccLocation,
    P06NodeLocation,
    Promotion,
    PropertyReport,
    PropertySlug,
    RunPolicy,
    RunReport,
    SeverityCounts,
    StateKeyLocation,
    StrictPolicy,
    SubjectRef,
    TerminationWitness,
    Tool,
    ToolError,
    Witness,
    WitnessNote,
    anchor_location,
    register_validator,
    to_data,
    to_json,
    unregister_validator,
    validator_for,
    verify,
)
from gebra.verify import run as run_module
from tests.conftest import FIXTURES_DIR

# ── IR shapes, each the smallest one that reaches the rung it is named for ───────────────


def _ir(block: dict[str, Any]) -> WorkflowIR:
    """A validated IR from a literal block — the JSON-mode path the strict models need."""
    return WorkflowIR.model_validate_json(json.dumps(block))


def _linear(**overrides: Any) -> dict[str, Any]:
    """START → work → wrap → END: acyclic, well formed, nothing declared."""
    block: dict[str, Any] = {
        "ir_version": "1.0",
        "entry": "work",
        "finish": "wrap",
        "state": {},
        "nodes": [{"id": "work"}, {"id": "wrap"}],
        "edges": [{"from": "work", "to": "wrap"}],
    }
    block.update(overrides)
    return block


def _clean() -> WorkflowIR:
    """The all-pass IR: five wedge passes, no finding, no note."""
    return _ir(_linear())


def _seedless_llm() -> WorkflowIR:
    """One P-08 WARNING (``deterministic-llm-seed-unpinned``) and nothing else.

    Appendix B C-1/C-2: a bare boolean ``deterministic`` on a node whose effects evidence a
    remote provider pins no seed anywhere.
    """
    return _ir(
        _linear(
            nodes=[
                {"id": "work", "annotations": {"deterministic": True, "effect": ["external"]}},
                {"id": "wrap"},
            ]
        )
    )


def _unprotected_retry_effect() -> WorkflowIR:
    """One P-06 ERROR (``unprotected-effect-in-retry-region``) and nothing else.

    A declared ``retry_policy`` makes a structural retry region with no cycle in it, so P-02
    still passes vacuously — which is what isolates the ERROR rung from the FATAL one.
    """
    return _ir(
        _linear(
            nodes=[
                {
                    "id": "work",
                    "annotations": {
                        "effect": ["billable"],
                        "retry_policy": {"max_attempts": 3, "retry_on": ["TimeoutError"]},
                    },
                },
                {"id": "wrap"},
            ]
        )
    )


def _dangling_target() -> WorkflowIR:
    """P-01-dirty: a ``path_map`` label naming no node — one FATAL, topology unfit to read."""
    return _ir(
        {
            "ir_version": "1.0",
            "entry": "work",
            "finish": "wrap",
            "state": {},
            "nodes": [{"id": "work"}, {"id": "review"}, {"id": "wrap"}],
            "edges": [
                {"from": "work", "to": "review"},
                {
                    "from": "review",
                    "kind": "conditional",
                    "condition": "an opaque reviewer judgement",
                    "path_map": {"again": "nowhere", "done": "wrap"},
                },
            ],
        }
    )


def _blanket_only() -> WorkflowIR:
    """An unwitnessed loop under a justified ``recursion_limit``.

    P-02 passes with the WARNING-grade ``scc-covered-only-by-recursion-limit`` note — the
    promotable record §0.2 names by name, and the only one in the wedge that rides a *witness*
    rather than a finding.
    """
    return _ir(
        {
            "ir_version": "1.0",
            "entry": "work",
            "finish": "wrap",
            "state": {},
            "runtime": {
                "recursion_limit": {"value": 25, "justification": "two supersteps per turn"}
            },
            "nodes": [{"id": "work"}, {"id": "review"}, {"id": "wrap"}],
            "edges": [
                {"from": "work", "to": "review"},
                {
                    "from": "review",
                    "kind": "conditional",
                    "condition": "an opaque reviewer judgement",
                    "path_map": {"again": "work", "done": "wrap"},
                },
            ],
        }
    )


# ── Registry fixtures: dispatch is process-global, so nothing may leak ───────────────────


@pytest.fixture
def clean_registrations() -> Iterator[None]:
    """Restore every registration this test session started with (the VAL-01 pattern)."""
    shipped = {slug: validator_for(slug) for slug in PROPERTY_SLUGS}
    yield
    for slug, implementation in shipped.items():
        unregister_validator(slug)
        if implementation is not None:
            register_validator(slug, implementation)


def _rewire(property_slug: PropertySlug, implementation: Any) -> None:
    """Swap the validator wired for ``property_slug`` (inside ``clean_registrations``)."""
    unregister_validator(property_slug)
    register_validator(property_slug, implementation)


#: A passing witness per topology property, for the stubs the invariance test swaps in.
_PASSING_WITNESS: Final[dict[PropertySlug, Witness]] = {
    "termination-witness": TerminationWitness(kind="termination", inventory=(), certificate=()),
    "dataflow-completeness": DataflowWitness(kind="dataflow", coverage=()),
    "effect-safety": EffectSafetyWitness(kind="effect-safety", cycles=(), effects=()),
}

#: A FATAL/ERROR finding per topology property, on that property's own ratified condition ID.
_STUB_FAILURE: Final[dict[PropertySlug, Failure]] = {
    "termination-witness": Failure(
        property_condition="cycle-without-termination-witness",
        location=P02SccLocation(
            kind="scc",
            nodes=("review", "work"),
            representative_cycle=("review", "work"),
            exhaustive=False,
        ),
        severity="fatal",
        claim_class="defensible",
    ),
    "dataflow-completeness": Failure(
        property_condition="read-key-never-written-on-path",
        location=DataflowLocation(kind="state-key", key="k", node="work", path=("START", "work")),
        severity="fatal",
        claim_class="defensible-a",
    ),
    "effect-safety": Failure(
        property_condition="unprotected-effect-in-cycle",
        location=P06NodeLocation(kind="node", node="work", effect=("billable",)),
        severity="error",
        claim_class="defensible-a",
    ),
}


def _always_passes(property_slug: PropertySlug) -> Any:
    def _stub(ir: WorkflowIR, /) -> PropertyReport:
        return PropertyReport.passing(property_slug, _PASSING_WITNESS[property_slug])

    return _stub


def _always_fails(property_slug: PropertySlug) -> Any:
    def _stub(ir: WorkflowIR, /) -> PropertyReport:
        return PropertyReport.failing(property_slug, _STUB_FAILURE[property_slug])

    return _stub


# ── §1: the wrapper's shape ──────────────────────────────────────────────────────────────


def test_a_verdict_run_carries_all_thirteen_properties_in_catalog_order() -> None:
    """§1.4 rule 1: one outcome per catalog slug, never an omission and never a pass."""
    report = verify(_clean())

    assert tuple(outcome.property for outcome in report.properties) == PROPERTY_SLUGS
    assert len(report.properties) == 13


def test_the_eight_non_wedge_properties_answer_with_markers_never_passes() -> None:
    """SOW §8 out-of-scope is a structured status, not a silent pass (§4.2's copy rule 5)."""
    report = verify(_clean())
    markers = {
        outcome.property: outcome
        for outcome in report.properties
        if isinstance(outcome, NotImplementedMarker)
    }

    assert set(markers) == set(PROPERTY_SLUGS) - set(WEDGE_SLUGS)
    assert {marker.status for marker in markers.values()} == {"deferred-to-phase-1"}
    assert all("not a pass" in marker.detail for marker in markers.values())


def test_every_wedge_property_produces_a_verdict() -> None:
    """The other half of the same rule: the five in scope answer with reports."""
    report = verify(_clean())
    verdicts = {
        outcome.property for outcome in report.properties if isinstance(outcome, PropertyReport)
    }

    assert verdicts == set(WEDGE_SLUGS)


def test_the_subject_carries_the_ir_s_own_identity_and_the_caller_s_label() -> None:
    """§1.3: the caller labels the run; the digest is computed, never accepted."""
    ir = _clean()
    report = verify(ir, RunPolicy(subject=SubjectRef(source="travel_booking:build_graph")))

    assert report.subject is not None
    assert report.subject.source == "travel_booking:build_graph"
    assert report.subject.ir_version == "1.0"
    assert report.subject.graph_version == graph_version(ir)


def test_the_report_never_invents_a_source_label() -> None:
    """§1.3: an in-process caller that named no reference gets a label, not a fabricated one.

    The default is deliberately unresolvable and deliberately not shaped like a target
    reference, an import path or a file path — so a reader can never mistake it for one.
    """
    report = verify(_clean())

    assert report.subject is not None
    assert report.subject.source == run_module.IN_PROCESS_SOURCE
    assert report.subject.source.startswith("<") and report.subject.source.endswith(">")
    assert report.subject.input_mode == "ir-document"
    assert report.subject.extractor_version is None


def test_a_snapshot_subject_without_its_label_is_the_caller_s_error() -> None:
    """§1.2's own invariant: ``version`` present iff ``input_mode == "snapshot"``.

    Raised rather than reported as a tool error — a mislabelled run is a bug in the caller,
    and exit 2 means "the run could not reach a verdict", not "the caller passed nonsense".
    """
    with pytest.raises(ValueError, match="version"):
        verify(_clean(), RunPolicy(subject=SubjectRef(source="s", input_mode="snapshot")))


def test_two_runs_over_one_ir_are_byte_identical() -> None:
    """§1.4 rule 5: same IR, same validators, same policy → the same document."""
    ir = _blanket_only()

    assert to_json(verify(ir)) == to_json(verify(ir))


def test_the_run_report_serializes_in_the_pc4_profile() -> None:
    """§1.5: definition order, absent optionals omitted rather than ``null``."""
    data = to_data(verify(_clean()))

    assert list(data) == [
        "report_format",
        "tool",
        "subject",
        "properties",
        "best_effort",
        "gate",
    ]
    assert "error" not in data  # an unset optional is omitted, never ``null``
    assert data["best_effort"] == []  # a repeated member is empty, not absent (§1.5)
    assert data["report_format"] == REPORT_FORMAT
    assert data["tool"]["name"] == "gebra"
    assert list(data["gate"]) == [
        "exit_code",
        "outcome",
        "counts",
        "strict",
        "promotions",
        "snapshot_eligible",
    ]


def test_the_report_format_is_the_one_the_spec_pins() -> None:
    """The code and REPORT-FORMAT-SPEC agree on the version the wrapper emits."""
    spec = (Path(__file__).resolve().parents[2] / "docs/specs/REPORT-FORMAT-SPEC.md").read_text(
        encoding="utf-8"
    )

    assert REPORT_FORMAT == "1.1"
    assert f'"report_format": "{REPORT_FORMAT}"' in spec
    assert f'report_format: Literal["{REPORT_FORMAT}"]' in spec


def test_p01_is_dispatched_first() -> None:
    """The P-01-gated order, observed rather than asserted about the source.

    §0.3 makes P-01 the precondition of the topology validators, so it is the run's first
    question. The catalog order agrees today; this pins the decision rather than the
    coincidence.
    """
    order: list[PropertySlug] = []

    def _recording(slug: PropertySlug) -> Any:
        shipped = validator_for(slug)
        assert shipped is not None

        def _stub(ir: WorkflowIR, /) -> PropertyReport:
            order.append(slug)
            return shipped(ir)

        return _stub

    shipped = {slug: validator_for(slug) for slug in WEDGE_SLUGS}
    try:
        for slug in WEDGE_SLUGS:
            _rewire(slug, _recording(slug))
        verify(_clean())
    finally:
        for slug, implementation in shipped.items():
            unregister_validator(slug)
            assert implementation is not None
            register_validator(slug, implementation)

    assert order[0] == "graph-well-formed"
    assert set(order) == set(WEDGE_SLUGS)


# ── §2.2: the exit-code matrix ───────────────────────────────────────────────────────────


def test_exit_0_pass_when_nothing_is_found() -> None:
    gate = verify(_clean()).gate

    assert (gate.exit_code, gate.outcome) == (0, "pass")
    assert gate.counts == SeverityCounts(fatal=0, error=0, warning=0)
    assert gate.promotions == ()
    assert gate.snapshot_eligible is True


def test_exit_0_pass_with_notes_when_only_warnings_are_found() -> None:
    """§2.2: a WARNING finding is a `result: "fail"` record and a passing gate."""
    report = verify(_seedless_llm())
    p08 = report.outcome_for("determinism-replay")

    assert isinstance(p08, PropertyReport)
    assert p08.result == "fail"  # the record says what was found …
    assert (report.gate.exit_code, report.gate.outcome) == (0, "pass-with-notes")  # … the gate
    assert report.gate.counts == SeverityCounts(fatal=0, error=0, warning=1)
    assert report.gate.snapshot_eligible is True


def test_exit_0_pass_with_notes_when_only_a_witness_note_is_carried() -> None:
    """The other half of the same rung: a note, on a report that passes with its witness."""
    report = verify(_blanket_only())
    p02 = report.outcome_for("termination-witness")

    assert isinstance(p02, PropertyReport) and p02.result == "pass"
    assert report.gate.counts.warning == 0  # a note is not a finding (§2.1)
    assert (report.gate.exit_code, report.gate.outcome) == (0, "pass-with-notes")


def test_exit_1_on_a_fatal_finding_and_no_snapshot_is_recorded() -> None:
    """The FATAL-no-snapshot signal — §0.2's one suppression, carried as a field (§2.5)."""
    report = verify(_dangling_target())

    assert (report.gate.exit_code, report.gate.outcome) == (1, "fail")
    assert report.gate.counts.fatal >= 1
    assert report.gate.snapshot_eligible is False


def test_exit_1_on_an_error_finding_and_the_snapshot_is_still_recorded() -> None:
    """§0.2: ERROR blocks the CI gate and does **not** suppress recording."""
    report = verify(_unprotected_retry_effect())
    p06 = report.outcome_for("effect-safety")

    assert isinstance(p06, PropertyReport) and p06.failure is not None
    assert p06.failure.severity == "error"
    assert (report.gate.exit_code, report.gate.outcome) == (1, "fail")
    assert report.gate.counts == SeverityCounts(fatal=0, error=1, warning=0)
    assert report.gate.snapshot_eligible is True


def test_exit_2_when_a_wedge_validator_is_not_registered(clean_registrations: None) -> None:
    """§1.4 rule 2: a run that checked four of the five would be a weakened gate."""
    unregister_validator("effect-safety")
    report = verify(_clean())

    assert (report.gate.exit_code, report.gate.outcome) == (2, "tool-error")
    assert report.error is not None and report.error.stage == "dispatch"
    assert "effect-safety" in report.error.detail
    assert report.properties == ()
    assert report.gate.snapshot_eligible is False


def test_exit_2_when_a_validator_raises(clean_registrations: None) -> None:
    """§2.4: an exception escaping a validator is a tool error, never a fail."""

    def _explodes(ir: WorkflowIR, /) -> PropertyReport:
        raise RuntimeError("the analysis fell over")

    _rewire("dataflow-completeness", _explodes)
    report = verify(_clean())

    assert (report.gate.exit_code, report.gate.outcome) == (2, "tool-error")
    assert report.error is not None and report.error.stage == "dispatch"
    assert "RuntimeError" in report.error.detail
    assert "the analysis fell over" in report.error.detail


def test_exit_2_when_the_gate_cannot_be_derived(clean_registrations: None) -> None:
    """§2.4, as amended at `1.1`: a property's promotion refusal is a tool error, not a crash.

    P-02 refuses to promote a WARNING-grade note it cannot anchor — §6.1 reports the promoted
    item on its residual SCC, and a note with no location names none, so dropping it would
    silently cost the user a gate. That refusal reaches the aggregation, and the rule that
    keeps it from being a *policy-dependent* crash is this one: the same IR must not answer
    normally with strict off and raise with strict on. It answers with a report either way.
    """
    unanchored = WitnessNote(kind="scc-covered-only-by-recursion-limit", severity="warning")

    def _stub(ir: WorkflowIR, /) -> PropertyReport:
        return PropertyReport.passing(
            "termination-witness",
            TerminationWitness(
                kind="termination", inventory=(), certificate=(), notes=(unanchored,)
            ),
        )

    _rewire("termination-witness", _stub)
    relaxed = verify(_clean())
    strict = verify(_clean(), RunPolicy(strict=STRICT_ALL))

    assert (relaxed.gate.exit_code, relaxed.gate.outcome) == (0, "pass-with-notes")
    assert (strict.gate.exit_code, strict.gate.outcome) == (2, "tool-error")
    assert strict.error is not None and strict.error.stage == "dispatch"
    assert "no location" in strict.error.detail
    assert strict.properties == ()


def test_verify_is_total_over_every_shape_this_suite_builds() -> None:
    """The contract §2.4 buys with the rule above: a report, or nothing — never both.

    Stated as a sweep rather than as a claim about the code: every IR this module builds, under
    every policy form, answers with a `RunReport`.
    """
    policies = (
        None,
        RunPolicy(),
        RunPolicy(strict=STRICT_ALL),
        RunPolicy(strict=StrictPolicy(mode="per-property", properties=("termination-witness",))),
    )
    builds = (_clean, _seedless_llm, _blanket_only, _unprotected_retry_effect, _dangling_target)

    for build in builds:
        for policy in policies:
            assert isinstance(verify(build(), policy), RunReport)


def test_exit_2_when_a_validator_answers_for_another_property(clean_registrations: None) -> None:
    """§2.4's other dispatch case: one property, one report (§0.3)."""

    def _wrong_property(ir: WorkflowIR, /) -> PropertyReport:
        return PropertyReport.passing(
            "dataflow-completeness", DataflowWitness(kind="dataflow", coverage=())
        )

    _rewire("effect-safety", _wrong_property)
    report = verify(_clean())

    assert (report.gate.exit_code, report.gate.outcome) == (2, "tool-error")
    assert report.error is not None and report.error.stage == "dispatch"


def test_a_tool_error_run_reaches_no_verdict_at_all(clean_registrations: None) -> None:
    """§2.4: exit 2 carries no outcomes, no promotions, no best-effort qualification."""
    unregister_validator("termination-witness")
    report = verify(_blanket_only(), RunPolicy(strict=STRICT_ALL))

    assert report.properties == ()
    assert report.best_effort == ()
    assert report.gate.promotions == ()
    assert report.gate.counts == SeverityCounts(fatal=0, error=0, warning=0)
    with pytest.raises(KeyError):
        report.outcome_for("graph-well-formed")


def test_the_exit_code_matrix_covers_every_rung() -> None:
    """The matrix in one place, so a rung cannot be lost by deleting a single test."""
    matrix = {
        "pass": (verify(_clean()), 0, "pass"),
        "pass-with-notes": (verify(_seedless_llm()), 0, "pass-with-notes"),
        "warning-note": (verify(_blanket_only()), 0, "pass-with-notes"),
        "error": (verify(_unprotected_retry_effect()), 1, "fail"),
        "fatal": (verify(_dangling_target()), 1, "fail"),
        "strict-bare": (verify(_seedless_llm(), RunPolicy(strict=STRICT_ALL)), 1, "fail"),
        "strict-note": (verify(_blanket_only(), RunPolicy(strict=STRICT_ALL)), 1, "fail"),
    }

    assert {
        name: (report.gate.exit_code, report.gate.outcome)
        for name, (report, _, _) in matrix.items()
    } == {name: (code, outcome) for name, (_, code, outcome) in matrix.items()}
    assert {report.gate.exit_code for report, _, _ in matrix.values()} == {0, 1}


# ── §2.3: strict mode, in both of its forms ──────────────────────────────────────────────


def test_bare_strict_promotes_every_warning_in_the_run() -> None:
    report = verify(_seedless_llm(), RunPolicy(strict=STRICT_ALL))

    assert (report.gate.exit_code, report.gate.outcome) == (1, "fail")
    assert report.gate.strict == STRICT_ALL
    assert [(p.property, p.origin, p.property_condition) for p in report.gate.promotions] == [
        ("determinism-replay", "failure", "deterministic-llm-seed-unpinned")
    ]


def test_per_property_strict_promotes_only_the_named_property() -> None:
    named = RunPolicy(strict=StrictPolicy(mode="per-property", properties=("determinism-replay",)))
    other = RunPolicy(strict=StrictPolicy(mode="per-property", properties=("termination-witness",)))

    promoted = verify(_seedless_llm(), named)
    declined = verify(_seedless_llm(), other)

    assert (promoted.gate.exit_code, promoted.gate.outcome) == (1, "fail")
    assert len(promoted.gate.promotions) == 1
    assert (declined.gate.exit_code, declined.gate.outcome) == (0, "pass-with-notes")
    assert declined.gate.promotions == ()


def test_strict_off_promotes_nothing_and_is_the_default() -> None:
    default = verify(_seedless_llm())
    explicit = verify(_seedless_llm(), RunPolicy(strict=STRICT_OFF))

    assert default.gate.strict == STRICT_OFF
    assert to_json(default) == to_json(explicit)
    assert default.gate.promotions == ()


def test_a_promoted_witness_note_carries_the_identity_its_spec_fixes() -> None:
    """The handed-over §6.1 question, answered: the promoted item keeps its own name.

    T-W-SPEC §6.1's third row reports a blanket-only SCC under
    ``cycle-without-termination-witness`` with ``blanket_only: true`` as "the distinguishing
    structured field", reusing the ID rather than introducing one. ``gate.promotions`` is the
    only artifact a promotion appears in, so this is where that identity lands — as the name
    of the promoted item, never as a grade: the promotion carries no severity, the note keeps
    its WARNING grade in the record, and the run's FATAL count stays zero.
    """
    report = verify(_blanket_only(), RunPolicy(strict=STRICT_ALL))
    (promotion,) = report.gate.promotions

    assert promotion.property == "termination-witness"
    assert promotion.origin == "witness-note"
    assert promotion.note_kind == "scc-covered-only-by-recursion-limit"
    assert promotion.property_condition == "cycle-without-termination-witness"
    assert isinstance(promotion.location, P02SccLocation)
    assert promotion.location.blanket_only is True
    assert not hasattr(promotion, "severity") and not hasattr(promotion, "claim_class")
    assert report.gate.counts == SeverityCounts(fatal=0, error=0, warning=0)
    assert report.gate.snapshot_eligible is True


def test_promotion_changes_the_gate_and_never_the_record() -> None:
    """§0.2 / DEC-11 item 6, machine-checked on both promotable carriers.

    The whole ``properties`` block is compared byte-for-byte across the two policies: not the
    note alone, not the P-02 report alone, but every record in the run.
    """
    for ir in (_blanket_only(), _seedless_llm()):
        relaxed = verify(ir)
        strict = verify(ir, RunPolicy(strict=STRICT_ALL))

        assert to_data(relaxed)["properties"] == to_data(strict)["properties"]
        assert relaxed.gate.exit_code == 0 and strict.gate.exit_code == 1
        assert strict.gate.promotions != ()


def test_a_promoted_note_leaves_the_pass_a_pass() -> None:
    """§2.3: "the pass stays a pass in the record"; the run around it exits 1."""
    report = verify(_blanket_only(), RunPolicy(strict=STRICT_ALL))
    p02 = report.outcome_for("termination-witness")

    assert isinstance(p02, PropertyReport)
    assert p02.result == "pass" and p02.witness is not None
    assert isinstance(p02.witness, TerminationWitness)
    assert [note.severity for note in p02.witness.notes] == ["warning"]
    assert report.gate.exit_code == 1


def test_strict_reach_matches_on_the_records_own_property(clean_registrations: None) -> None:
    """§2.3's reach table, including the row that is easy to get wrong.

    A WARNING co-failure and an advisory are their **own** property's findings wherever they
    are carried, so a per-property policy naming the host promotes neither, and a policy
    naming the owner promotes both.
    """
    host = Failure(
        property_condition="unprotected-effect-in-cycle",
        location=NodeLocation(kind="node", node="work"),
        severity="warning",
        claim_class="defensible-a",
        co_failures=(
            CoFailure(
                property="effect-safety",
                property_condition="unprotected-effect-in-retry-region",
                location=NodeLocation(kind="node", node="wrap"),
                severity="warning",
                claim_class="defensible-a",
            ),
        ),
        advisories=(
            Advisory(
                property="determinism-replay",
                property_condition="deterministic-llm-seed-unpinned",
                severity="warning",
                claim_class="heuristic",
                location=NodeLocation(kind="node", node="work"),
            ),
        ),
    )

    def _stub(ir: WorkflowIR, /) -> PropertyReport:
        return PropertyReport.failing("effect-safety", host)

    _rewire("effect-safety", _stub)

    owner_only = verify(
        _clean(),
        RunPolicy(strict=StrictPolicy(mode="per-property", properties=("determinism-replay",))),
    )
    host_only = verify(
        _clean(), RunPolicy(strict=StrictPolicy(mode="per-property", properties=("effect-safety",)))
    )
    everything = verify(_clean(), RunPolicy(strict=STRICT_ALL))

    assert [(p.property, p.origin) for p in owner_only.gate.promotions] == [
        ("determinism-replay", "advisory")
    ]
    assert [(p.property, p.origin) for p in host_only.gate.promotions] == [
        ("effect-safety", "failure"),
        ("effect-safety", "co-failure"),
    ]
    assert len(everything.gate.promotions) == 3


def test_a_warning_note_on_another_property_promotes_without_an_invented_identity(
    clean_registrations: None,
) -> None:
    """§0.2's reach is about severity; §0.4's registry is closed.

    P-02 is the only property whose spec fixes an identity for a promoted note. A WARNING-grade
    note carried by any other property is still selected — DEC-23 puts notes on the shared
    ``Failure.notes`` channel — and it is promoted with **no** ``property_condition``, because
    minting one would be exactly the registry improvisation §0.4 forbids.
    """
    note = WitnessNote(kind="recursion-limit-without-justification", severity="warning")
    ungraded = WitnessNote(kind="cycle-census-capped")  # no severity — never promotable

    def _stub(ir: WorkflowIR, /) -> PropertyReport:
        return PropertyReport.failing(
            "dataflow-completeness",
            Failure(
                property_condition="read-key-never-written-on-path",
                location=DataflowLocation(
                    kind="state-key", key="k", node="work", path=("START", "work")
                ),
                severity="fatal",
                claim_class="defensible-a",
                notes=(ungraded, note),
            ),
        )

    _rewire("dataflow-completeness", _stub)
    (promotion,) = verify(_clean(), RunPolicy(strict=STRICT_ALL)).gate.promotions

    assert promotion.property == "dataflow-completeness"
    assert promotion.origin == "witness-note"
    assert promotion.note_kind == "recursion-limit-without-justification"
    assert promotion.property_condition is None
    assert promotion.location is None


def test_a_note_that_is_not_warning_grade_can_never_flip_a_gate(
    clean_registrations: None,
) -> None:
    """§2.3: notes are never gate-bearing on their own — only the WARNING-grade ones promote.

    ``cycle-census-capped`` is the in-corpus case: it carries no ``severity`` at all (VAL-08
    asserts that as a property of the record), so an aborted census cannot make a bare-strict
    run fail.
    """
    census_note = WitnessNote(kind="cycle-census-capped")

    def _stub(ir: WorkflowIR, /) -> PropertyReport:
        return PropertyReport.passing(
            "termination-witness",
            TerminationWitness(
                kind="termination", inventory=(), certificate=(), notes=(census_note,)
            ),
        )

    _rewire("termination-witness", _stub)
    report = verify(_clean(), RunPolicy(strict=STRICT_ALL))

    assert census_note.severity is None
    assert report.gate.promotions == ()
    assert (report.gate.exit_code, report.gate.outcome) == (0, "pass")


# ── §0.3: P-01 gates the contract-weight of the topology validators ──────────────────────


def test_a_p01_fatal_marks_the_topology_validators_best_effort() -> None:
    """§0.3: P-02/P-04/P-06 results are defined only over P-01-clean topology.

    The run says so rather than leaving it to the reader: without this field a consumer
    reading a P-02 pass on a graph with a dangling target has no signal that it is a
    diagnostic rather than a contract-bearing verdict.
    """
    report = verify(_dangling_target())
    p01 = report.outcome_for("graph-well-formed")

    assert isinstance(p01, PropertyReport) and p01.failure is not None
    assert p01.failure.severity == "fatal"
    assert report.best_effort == TOPOLOGY_SLUGS
    assert report.best_effort == ("termination-witness", "dataflow-completeness", "effect-safety")


def test_best_effort_is_empty_on_p01_clean_topology() -> None:
    for ir in (_clean(), _seedless_llm(), _blanket_only(), _unprotected_retry_effect()):
        report = verify(ir)

        assert report.best_effort == ()
        assert to_data(report)["best_effort"] == []


def test_only_a_p01_fatal_qualifies_the_others(clean_registrations: None) -> None:
    """A FATAL from another property is not a precondition failure — §0.3 names P-01."""
    _rewire("dataflow-completeness", _always_fails("dataflow-completeness"))
    report = verify(_clean())

    assert report.gate.counts.fatal == 1
    assert report.best_effort == ()


@pytest.mark.parametrize("swap", ("passing", "failing"), ids=("all-pass", "all-fail"))
def test_the_gate_under_a_p01_fatal_does_not_depend_on_the_topology_validators(
    clean_registrations: None, swap: str
) -> None:
    """The contract-weight claim, stated in the direction that can fail.

    P-01's FATAL alone fixes the run's gate. Replacing all three topology validators with
    stubs that answer the opposite way — everything passes, or everything fails at its own
    ratified condition — leaves the exit code, the outcome word and snapshot eligibility
    exactly where P-01 put them. Their reports are still carried, and ``best_effort`` is what
    tells a reader how to weigh them.
    """
    ir = _dangling_target()
    baseline = verify(ir).gate
    make = _always_passes if swap == "passing" else _always_fails
    for slug in TOPOLOGY_SLUGS:
        _rewire(slug, make(slug))
    swapped = verify(ir)

    assert (
        (swapped.gate.exit_code, swapped.gate.outcome, swapped.gate.snapshot_eligible)
        == (
            baseline.exit_code,
            baseline.outcome,
            baseline.snapshot_eligible,
        )
        == (1, "fail", False)
    )
    assert swapped.best_effort == TOPOLOGY_SLUGS
    assert {outcome.property for outcome in swapped.properties} == set(PROPERTY_SLUGS)


def test_a_p01_dirty_run_still_carries_every_outcome() -> None:
    """Best-effort is a qualification, not a suppression: nothing is dropped (§1.4 rule 1)."""
    report = verify(_dangling_target())

    assert tuple(outcome.property for outcome in report.properties) == PROPERTY_SLUGS
    assert all(isinstance(report.outcome_for(slug), PropertyReport) for slug in TOPOLOGY_SLUGS)


# ── §2.1: what counts, and what does not ─────────────────────────────────────────────────


def test_counts_tally_findings_only_never_notes() -> None:
    """§2.1: "Notes are not findings … they are counted separately from ``gate.counts``"."""
    report = verify(_blanket_only())
    p02 = report.outcome_for("termination-witness")

    assert isinstance(p02, PropertyReport) and isinstance(p02.witness, TerminationWitness)
    assert len(p02.witness.notes) == 1
    assert report.gate.counts == SeverityCounts(fatal=0, error=0, warning=0)


def test_counts_are_derived_and_a_consumer_that_recomputes_agrees() -> None:
    """§1.3: ``gate.counts`` is carried so a renderer does not become a second derivation."""
    report = verify(_dangling_target())
    recomputed = {"fatal": 0, "error": 0, "warning": 0}
    for outcome in report.properties:
        if not isinstance(outcome, PropertyReport) or outcome.failure is None:
            continue
        recomputed[outcome.failure.severity] += 1
        for co_failure in outcome.failure.co_failures or ():
            recomputed[co_failure.severity] += 1
        for advisory in outcome.failure.advisories or ():
            recomputed[advisory.severity] += 1

    assert report.gate.counts == SeverityCounts(**recomputed)


def test_a_marker_never_contributes_to_the_exit_code() -> None:
    """§2.2: the eight are neither a pass nor a fail, and a run is no weaker for saying so."""
    report = verify(_clean())

    assert len([o for o in report.properties if isinstance(o, NotImplementedMarker)]) == 8
    assert (report.gate.exit_code, report.gate.outcome) == (0, "pass")


def test_only_the_termination_witness_carries_notes_on_its_witness() -> None:
    """Pins the generality of the note reader: which witness kinds declare ``notes`` today.

    ``_witness_notes`` asks the model rather than naming a class, so a witness kind that grows
    notes is read without an edit. This is the assertion that keeps that from being a guess.
    """
    carriers = {
        member.__name__
        for member in get_args(get_args(Witness)[0])
        if "notes" in member.model_fields
    }

    assert carriers == {"TerminationWitness"}


# ── §2.5: snapshot eligibility ───────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("build", "eligible"),
    (
        (_clean, True),
        (_seedless_llm, True),
        (_blanket_only, True),
        (_unprotected_retry_effect, True),
        (_dangling_target, False),
    ),
    ids=("pass", "warning", "note", "error", "fatal"),
)
def test_only_a_fatal_suppresses_the_snapshot(build: Any, eligible: bool) -> None:
    """§2.5: ``snapshot_eligible = (exit_code != 2) and (counts.fatal == 0)``."""
    report = verify(build())

    assert report.gate.snapshot_eligible is eligible
    assert report.gate.snapshot_eligible == (
        report.gate.exit_code != 2 and report.gate.counts.fatal == 0
    )


def test_a_promoted_warning_does_not_suppress_the_snapshot() -> None:
    """§2.5: "promotion moves the gate, not the ladder"."""
    report = verify(_blanket_only(), RunPolicy(strict=STRICT_ALL))

    assert report.gate.exit_code == 1
    assert report.gate.snapshot_eligible is True


# ── §3.2 rule 3: the anchor projection ───────────────────────────────────────────────────


def test_the_anchor_projection_drops_evidence_and_keeps_the_anchor() -> None:
    """A finding projected onto another property's report keeps only its §0.3 anchor."""
    concrete = P06NodeLocation(
        kind="node", node="charge_card", effect=("billable",), idempotent="keyless"
    )

    assert anchor_location(concrete) == NodeLocation(kind="node", node="charge_card")
    assert anchor_location(
        P01EdgeLocation(kind="edge", source="review", label="again", undefined_target="nowhere")
    ) == EdgeLocation(kind="edge", source="review", label="again")
    assert anchor_location(
        DataflowLocation(kind="state-key", key="k", node="work", path=("START", "work"))
    ) == StateKeyLocation(kind="state-key", key="k", node="work")


def test_the_anchor_projection_is_the_identity_on_an_anchor() -> None:
    anchor = NodeLocation(kind="node", node="work")

    assert anchor_location(anchor) == anchor


def test_the_run_report_assembles_no_advisories_of_its_own() -> None:
    """Recorded as behaviour, because §3.2 puts advisory assembly above the validators.

    No frozen spec fixes which host report a WARNING-grade finding rides, and §3.2 rule 2 has
    carriage never removing the source record — every finding already stands in its own
    property's outcome, all thirteen of which the run carries. So this aggregation projects
    nothing; :func:`anchor_location` is the rule-3 primitive an assembler that does would use.
    """
    for ir in (_clean(), _seedless_llm(), _dangling_target(), _unprotected_retry_effect()):
        for outcome in verify(ir).properties:
            if isinstance(outcome, PropertyReport) and outcome.failure is not None:
                assert outcome.failure.advisories is None


# ── The model invariants §1.2 and §2.2 state ─────────────────────────────────────────────


def test_the_outcome_word_and_the_exit_code_can_never_disagree() -> None:
    with pytest.raises(ValueError, match="disagree"):
        GateOutcome(
            exit_code=0,
            outcome="fail",
            counts=SeverityCounts(fatal=0, error=0, warning=0),
            strict=STRICT_OFF,
            snapshot_eligible=True,
        )


def test_an_error_is_present_exactly_when_the_code_is_2() -> None:
    gate = GateOutcome(
        exit_code=0,
        outcome="pass",
        counts=SeverityCounts(fatal=0, error=0, warning=0),
        strict=STRICT_OFF,
        snapshot_eligible=True,
    )
    with pytest.raises(ValueError, match="exit_code == 2"):
        RunReport(
            report_format=REPORT_FORMAT,
            tool=Tool(name="gebra", version="0.0.0"),
            gate=gate,
            error=ToolError(stage="input", detail="…"),
        )


def test_a_verdict_run_that_lost_a_property_is_refused() -> None:
    gate = GateOutcome(
        exit_code=0,
        outcome="pass",
        counts=SeverityCounts(fatal=0, error=0, warning=0),
        strict=STRICT_OFF,
        snapshot_eligible=True,
    )
    with pytest.raises(ValueError, match="thirteen"):
        RunReport(
            report_format=REPORT_FORMAT,
            tool=Tool(name="gebra", version="0.0.0"),
            subject=verify(_clean()).subject,
            properties=(verify(_clean()).properties[0],),
            gate=gate,
        )


def test_a_promotion_names_what_it_promoted() -> None:
    with pytest.raises(ValueError, match="note_kind"):
        Promotion(property="termination-witness", origin="witness-note")
    with pytest.raises(ValueError, match="condition ID"):
        Promotion(property="determinism-replay", origin="failure")


def test_a_strict_policy_lists_properties_iff_it_is_per_property() -> None:
    with pytest.raises(ValueError, match="per-property"):
        StrictPolicy(mode="per-property")
    with pytest.raises(ValueError, match="per-property"):
        StrictPolicy(mode="all", properties=("determinism-replay",))


def test_a_tool_error_gate_promotes_nothing() -> None:
    """§2.4: no verdict was reached, so there was nothing for a policy to select."""
    with pytest.raises(ValueError, match="promoted nothing"):
        GateOutcome(
            exit_code=2,
            outcome="tool-error",
            counts=SeverityCounts(fatal=0, error=0, warning=0),
            strict=STRICT_ALL,
            promotions=(
                Promotion(
                    property="determinism-replay",
                    origin="failure",
                    property_condition="deterministic-llm-seed-unpinned",
                ),
            ),
            snapshot_eligible=False,
        )


def test_a_tool_error_run_carries_neither_outcomes_nor_a_qualification() -> None:
    """The two halves of §2.4's "partial outcomes are deliberately not carried"."""
    tool_error_gate = GateOutcome(
        exit_code=2,
        outcome="tool-error",
        counts=SeverityCounts(fatal=0, error=0, warning=0),
        strict=STRICT_OFF,
        snapshot_eligible=False,
    )
    verdict = verify(_clean())
    common: dict[str, Any] = {
        "report_format": REPORT_FORMAT,
        "tool": Tool(name="gebra", version="0.0.0"),
        "gate": tool_error_gate,
        "error": ToolError(stage="input", detail="…"),
    }

    with pytest.raises(ValueError, match="carries no outcomes"):
        RunReport(**common, properties=verdict.properties)
    with pytest.raises(ValueError, match="no verdict to qualify"):
        RunReport(**common, best_effort=TOPOLOGY_SLUGS)


def test_a_verdict_run_without_a_subject_is_refused() -> None:
    """§1.2: ``subject`` may be absent only on a tool-error run — identity is not optional."""
    verdict = verify(_clean())

    with pytest.raises(ValueError, match="only on a tool-error run"):
        RunReport(
            report_format=REPORT_FORMAT,
            tool=Tool(name="gebra", version="0.0.0"),
            properties=verdict.properties,
            gate=verdict.gate,
        )


def test_an_ir_with_no_digest_is_a_tool_error_before_any_property_runs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No identity, no report to hang on it (§2.4 ``ir-validation``).

    ``graph_version`` is the one thing ``verify()`` computes before dispatch, and a report
    whose subject could not be identified is not a verdict about anything. The digest is
    forced to fail here because no IR that satisfies ``WorkflowIR`` reaches that branch — the
    branch exists so the failure is a tool error rather than a traceback.
    """

    def _no_digest(ir: WorkflowIR) -> str:
        raise CanonicalizationError(
            "no canonical form",
            reason=CanonicalizationErrorReason.UNSUPPORTED_TYPE,
            path=(),
            value=None,
        )

    monkeypatch.setattr(run_module, "graph_version", _no_digest)
    report = verify(_clean())

    assert (report.gate.exit_code, report.gate.outcome) == (2, "tool-error")
    assert report.error is not None and report.error.stage == "ir-validation"
    assert report.subject is None  # identity was never established (§2.4)
    assert report.properties == ()


def test_an_ir_1_1_document_is_a_tool_error_rather_than_a_verdict() -> None:
    """§2.4 ``ir-validation``: "the IR document did not validate against ``ir_version`` 1.0".

    ir 1.1 added the ``dynamic`` edge kind (ratified — DEC-28, 2026-08-09) and with it a set of
    validator semantics this build does not carry: the P-01/P-02/P-04/P-06 skip branches, P-01's
    condition-(i) over-approximation, and two optional diagnostics, all of which DEC-28 assigns
    to a paired validator regression card. Running the 1.0 rules over such a document would
    report ``node-unreachable-from-start`` for every node only the router reaches — a FATAL the
    ruling forbids by name — so the run stops before any property is dispatched.

    Exit ``2`` with no subject and no outcomes, which is what "no verdict was reached" means:
    an honest absence, and specifically **not** exit ``1``, which would be a verdict.
    """
    clean = _clean()
    document = WorkflowIR(
        ir_version="1.1",
        entry=clean.entry,
        finish=clean.finish,
        state=clean.state,
        nodes=clean.nodes,
        edges=(*clean.edges, DynamicEdge(kind="dynamic", **{"from": "work"}, condition="route")),
        runtime=clean.runtime,
    )

    report = verify(document)

    assert (report.gate.exit_code, report.gate.outcome) == (2, "tool-error")
    assert report.error is not None and report.error.stage == "ir-validation"
    assert "1.1" in report.error.detail
    assert "paired validator regression card" in report.error.detail
    assert report.subject is None
    assert report.properties == ()
    assert report.gate.snapshot_eligible is False


def test_the_1_1_refusal_never_fires_on_a_1_0_document() -> None:
    """The guard is a version test and nothing else — every 1.0 document still reaches a verdict.

    Worth its own test rather than left to the rest of the file: a guard placed before the subject
    is built is exactly where an over-broad condition would silently turn the whole suite's
    verdicts into exit ``2``, and a suite of tool-error runs can look green from a distance.
    """
    report = verify(_clean())

    assert report.error is None
    assert report.gate.exit_code == 0
    assert report.subject is not None and report.subject.ir_version == "1.0"


# ── WA-07: no langgraph anywhere on the verify path ──────────────────────────────────────

#: The execution substrate plus the HTTP and LLM clients whose presence in the closure would
#: mean the aggregation had grown a way to reach the network. VAL-06's list, unchanged.
_FORBIDDEN = (
    "{'langgraph', 'langgraph_sdk', 'langchain', 'langchain_core', 'langchain_openai', "
    "'langchain_anthropic', 'langsmith', 'litellm', 'networkx', 'openai', "
    "'anthropic', 'httpx', 'requests', 'aiohttp', 'urllib3'}"
)


def _tripwire_script(probe: str = "") -> str:
    """The guarded child: patch, import, run ``verify()`` over every corpus snapshot, report.

    ``probe`` arms the raiser; the tripwire and its negative controls share this one script so
    a control cannot drift onto a different raiser from the one the real test relies on.
    """
    return (
        "import glob, json, socket, sys\n"
        "attempts = []\n"
        "class _TripSocket(socket.socket):\n"
        "    def __new__(cls, *a, **k):\n"
        "        attempts.append('socket'); print('WA07-TRIP', file=sys.stderr)\n"
        "        raise AssertionError('socket created on the verify path')\n"
        "def _trip(name):\n"
        "    def _raise(*a, **k):\n"
        "        attempts.append(name); print('WA07-TRIP', file=sys.stderr)\n"
        "        raise AssertionError(name + ' reached on the verify path')\n"
        "    return _raise\n"
        "socket.socket = _TripSocket\n"
        "socket.getaddrinfo = _trip('getaddrinfo')\n"
        "socket.gethostbyname = _trip('gethostbyname')\n"
        "socket.create_connection = _trip('create_connection')\n"
        "import yaml\n"
        "from gebra.ir import WorkflowIR\n"
        "from gebra.verify import RunPolicy, StrictPolicy, to_json, verify\n"
        "strict = RunPolicy(strict=StrictPolicy(mode='all'))\n"
        "codes = {0: 0, 1: 0, 2: 0}\n"
        "seen = 0\n"
        f"for path in sorted(glob.glob({str(FIXTURES_DIR)!r} + '/*/*.yaml')):\n"
        "    with open(path, encoding='utf-8') as handle:\n"
        "        document = yaml.safe_load(handle)\n"
        "    for key in ('ir', 'ir_before', 'ir_after'):\n"
        "        block = document.get(key)\n"
        "        if not block:\n"
        "            continue\n"
        "        ir = WorkflowIR.model_validate_json(json.dumps(block))\n"
        "        report = verify(ir)\n"
        "        promoted = verify(ir, strict)\n"
        "        codes[report.gate.exit_code] += 1\n"
        "        codes[promoted.gate.exit_code] += 1\n"
        "        assert len(report.properties) == 13, path\n"
        "        assert len(promoted.properties) == 13, path\n"
        "        to_json(report)\n"
        "        to_json(promoted)\n"
        "        seen += 1\n"
        "assert seen == 78, seen\n"
        "assert codes[2] == 0, codes\n"
        "assert codes[0] and codes[1], codes\n"
        f"{probe}"
        f"print([m for m in sys.modules if m.split('.')[0] in {_FORBIDDEN}] + attempts)\n"
    )


def test_running_verify_over_the_corpus_creates_no_socket_and_resolves_no_name() -> None:
    """The card's hermeticity box, proven the only way a transitive import can be.

    A fresh interpreter, because another test in this session may have imported anything.
    Three claims, separately enforced: no execution-substrate or HTTP/LLM-client package
    enters the import closure of ``gebra.verify`` — the aggregation, the models, all five
    validators and the serialization profile; no socket is created and no name resolved,
    either while importing or while running ``verify()`` over all 67 IR snapshots of the
    vendored corpus under both a relaxed and a bare-strict policy; and a swallowed exception
    still fails the run, because every attempt is recorded before the raise and also announced
    on stderr.

    The child asserts its own counts, so a glob that silently stopped matching would fail the
    tripwire rather than pass it vacuously: 67 snapshots, **no** tool error anywhere (every
    wedge validator registers at import, and none of them raises on any corpus IR), and both
    the zero and the non-zero exit codes reached — so the sweep demonstrably exercises both
    verdict paths of the gate rather than one.

    **The one hazard this aggregation adds, and why it does not blunt the tripwire.**
    ``verify()`` catches ``Exception`` around validator dispatch, because §2.4 makes *any*
    escaping exception a tool error — so a raiser firing inside a validator would be swallowed
    into an exit-``2`` report rather than propagating. Two of the child's own assertions cover
    that, and neither depends on the exception surviving: it asserts ``codes[2] == 0``, so a
    swallowed raiser shows up as a tool error the sweep refuses, and every raiser prints the
    ``WA07-TRIP`` sentinel on stderr *before* raising, which the caller checks independently of
    the child's exit status. That is the same record-before-raise design VAL-13 fixed, doing
    exactly the job it was designed for.

    One residual, named rather than left implicit, the same one VAL-03/VAL-05…VAL-08 recorded:
    the package leg is a post-hoc ``sys.modules`` scan, not an import blocker.
    ``tests/testing/test_hermeticity.py`` installs a real blocker on the wider path.
    """
    completed = subprocess.run(
        [sys.executable, "-c", _tripwire_script()], capture_output=True, text=True, check=True
    )

    assert completed.stdout.strip() == "[]", completed.stdout
    assert "WA07-TRIP" not in completed.stderr, completed.stderr


@pytest.mark.parametrize(
    "probe",
    (
        "socket.socket()\n",
        "socket.getaddrinfo('example.invalid', 80)\n",
        "socket.gethostbyname('example.invalid')\n",
        "socket.create_connection(('example.invalid', 80))\n",
    ),
    ids=("socket", "getaddrinfo", "gethostbyname", "create_connection"),
)
def test_the_tripwire_fires_when_the_guarded_path_is_armed(probe: str) -> None:
    """The negative control: prove the raiser is live, on the *same* script the tripwire runs."""
    completed = subprocess.run(
        [sys.executable, "-c", _tripwire_script(probe)],
        capture_output=True,
        text=True,
        check=False,  # a non-zero exit is the expected result here, not an error
    )

    assert completed.returncode != 0, completed.stdout
    assert "WA07-TRIP" in completed.stderr, completed.stderr


def test_the_aggregation_module_imports_nothing_that_could_execute_anything() -> None:
    """The static half: the import set of the run module, pinned exactly.

    Pinned at full dotted names rather than at package roots, on the WA-07 reviewer's N2 at
    this card's pre-review: a root-level pin would let ``from gebra.extraction import extract``
    — which *does* put langgraph in the closure — collapse onto the ``gebra`` root and pass.
    At this granularity a langgraph import cannot appear without this test changing, and
    neither can an interpreter (``importlib``), a process (``subprocess``) or a socket. The
    dynamic half is the guarded child above, which is what covers a transitive import.
    """
    tree = ast.parse(Path(run_module.__file__).read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module is not None and node.level == 0:
            imported.add(node.module)

    assert imported == {
        "__future__",
        "collections.abc",
        "dataclasses",
        "gebra",
        "gebra.ir",
        "gebra.ir.canonical",
        "gebra.verify.base",
        "gebra.verify.locations",
        "gebra.verify.properties.termination_witness",
        "gebra.verify.registry",
        "gebra.verify.report",
        "gebra.verify.witnesses",
        "pydantic",
        "typing",
    }


def test_the_aggregation_names_no_execution_primitive() -> None:
    """No ``eval``/``exec``/``compile``/``__import__`` **as a bare name** in the aggregation.

    A bare name is all this walk sees, and that is all it claims: a method call such as
    ``builder.compile()`` is an attribute and would not appear here. It is covered elsewhere
    and by construction — ``verify()`` takes a validated ``WorkflowIR``, so no builder ever
    crosses this boundary, and the first thing it does is canonicalize the IR.
    """
    tree = ast.parse(Path(run_module.__file__).read_text(encoding="utf-8"))
    named = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}

    assert named.isdisjoint({"eval", "exec", "compile", "literal_eval", "__import__"})
