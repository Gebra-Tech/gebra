"""The plugin's gate: the severity matrix, ``--gebra-strict``, select/skip — card TE-07.

Same discipline as ``tests/plugin/test_plugin.py`` and for the same reason: what this card
claims is a fact about what **pytest** does with a flag, so the behavioural tests drive real
inner sessions through ``pytester`` rather than calling the hooks. A flag that produced the
right :class:`~gebra.pytest_plugin.GatePolicy` and never reached collection would pass a
hook-level test and fail every user.

**The targets, and why they are these.** The severity matrix needs one target per rung of
PROPERTY-CATALOG-SPEC §0.2's ladder, isolated — a graph that is FATAL *and* WARNING says
nothing about which rung moved the item. The vendored corpus has fixtures for three of them
(``tests/plugin/test_plugin.py`` uses those), but not for the fourth: **no fixture in the
corpus reaches a WARNING-grade witness note**, which is the record ``--gebra-strict``'s
witness-note reach exists for. That was checked over all sixty rather than assumed, and it is
the same shape of residue TE-06 recorded for advisories. So the matrix is built on the five
minimal IR shapes ``tests/verify/test_run.py`` already established for the run-level gate —
each the smallest graph that reaches exactly one rung — restated here as literal IR documents
so an inner session can load one without importing another test module.

Using authored IR rather than seeded travel-booking variants is also what keeps this card
inside its own boundary: what a seeded agent should emit is SD-09's acceptance box. The live
agent still appears, because TE-05 recorded it as clean under strict with nothing to promote
and that is a claim this card should not take on trust.

**WA-07 rides every test here.** The agent's eleven sentinel bodies record and raise, and the
ledger is asserted on entry to *and* exit from every test in the file — entry too, per the
finding TE-05's pre-review made about higher-scoped fixtures. Nothing in this file compiles a
graph, and the IR-document targets reach no substrate at all.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from gebra.pytest_plugin import (
    MARKER,
    SELECT_OPTION,
    SKIP_OPTION,
    STRICT_OPTION,
    GatePolicy,
    enabled_properties,
    gate_policy,
    item_outcome,
    notes_for,
    promoted_records,
    promotions_for,
    verify_target,
)
from gebra.testing import load_fixture
from gebra.verify import (
    PROPERTY_SLUGS,
    STRICT_ALL,
    STRICT_OFF,
    PropertyReport,
    RunPolicy,
    verify,
)
from tests.sample_workflows import travel_booking

if TYPE_CHECKING:
    from gebra.ir import WorkflowIR
    from gebra.verify import PropertySlug, RunReport

pytest_plugins = ["pytester"]

REPO_ROOT = Path(__file__).resolve().parents[2]
CORPUS = REPO_ROOT / "tests" / "fixtures" / "properties"

#: The five wedge slugs, in catalog order.
WEDGE: tuple[PropertySlug, ...] = (
    "graph-well-formed",
    "termination-witness",
    "dataflow-completeness",
    "effect-safety",
    "determinism-replay",
)

_PREAMBLE = f"""
import sys
sys.path.insert(0, {str(REPO_ROOT)!r})
import pytest
"""


# ── One IR per rung of the §0.2 ladder ───────────────────────────────────────────────────
#
# Literal documents rather than builders, because an inner test file has to be able to
# reproduce one from its own source. Each is the smallest graph that reaches exactly the rung
# it is named for; the shapes are `tests/verify/test_run.py`'s, which is where the run-level
# gate arithmetic over them is pinned.


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


#: Five passes, no finding, no note — the control the matrix needs to show a flag did nothing.
CLEAN: dict[str, Any] = _linear()

#: One P-08 WARNING (``deterministic-llm-seed-unpinned``): a bare boolean ``deterministic``
#: on a node whose declared effects evidence a remote provider that pins no seed.
SEEDLESS_LLM: dict[str, Any] = _linear(
    nodes=[
        {"id": "work", "annotations": {"deterministic": True, "effect": ["external"]}},
        {"id": "wrap"},
    ]
)

#: One P-06 ERROR (``unprotected-effect-in-retry-region``) and nothing else.
UNPROTECTED_RETRY: dict[str, Any] = _linear(
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

#: One P-01 FATAL (``path-map-target-undefined``) — and, with it, §0.3's best-effort
#: qualifier on the three topology properties that answer anyway.
DANGLING_TARGET: dict[str, Any] = {
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

#: The witness-note rung: an unwitnessed loop under a *justified* ``recursion_limit``, so P-02
#: passes carrying the WARNING-grade ``scc-covered-only-by-recursion-limit`` note —
#: TERMINATION-WITNESS-SPEC §2.4's form-(b) blanket-alone pass. The only record in the wedge
#: that ``--gebra-strict`` reaches which rides a *witness* rather than a finding.
BLANKET_ONLY: dict[str, Any] = {
    "ir_version": "1.0",
    "entry": "work",
    "finish": "wrap",
    "state": {},
    "runtime": {"recursion_limit": {"value": 25, "justification": "two supersteps per turn"}},
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

RUNGS: dict[str, dict[str, Any]] = {
    "clean": CLEAN,
    "seedless_llm": SEEDLESS_LLM,
    "unprotected_retry": UNPROTECTED_RETRY,
    "dangling_target": DANGLING_TARGET,
    "blanket_only": BLANKET_ONLY,
}


def _ir(block: dict[str, Any]) -> WorkflowIR:
    """A validated IR from a literal block — the JSON-mode path the strict models need."""
    from gebra.ir import WorkflowIR

    return WorkflowIR.model_validate_json(json.dumps(block))


def _ir_source(block: dict[str, Any], *, name: str) -> str:
    """An inner test file whose marked target is one literal IR document — fixture-only mode."""
    return (
        _PREAMBLE
        + f"""
import json
from gebra.ir import WorkflowIR

@pytest.mark.{MARKER}(name={name!r})
def test_gebra():
    return WorkflowIR.model_validate_json(json.dumps({block!r}))
"""
    )


def _agent_source(*, name: str = "travel_agent") -> str:
    """An inner test file marking the live, sentinel-guarded travel-booking agent."""
    return (
        _PREAMBLE
        + f"""
from tests.sample_workflows.travel_booking import build_travel_booking_agent

@pytest.mark.{MARKER}(name={name!r})
def test_gebra():
    return build_travel_booking_agent()
"""
    )


@pytest.fixture(autouse=True)
def _the_agent_never_ran() -> Any:
    """Every test in this file leaves the sentinel ledger empty, on entry and on exit."""
    assert travel_booking.TRIPPED == [], (
        f"a node body ran before this test: {travel_booking.TRIPPED}"
    )
    yield
    assert travel_booking.TRIPPED == [], (
        f"a node body ran during this test: {travel_booking.TRIPPED}"
    )


def _run(report: RunReport, slug: str) -> PropertyReport:
    """One property's verdict report, refusing the marker rather than returning ``None``."""
    outcome = report.outcome_for(slug)  # type: ignore[arg-type]
    assert isinstance(outcome, PropertyReport), f"{slug} produced a marker, not a verdict"
    return outcome


# ── Acceptance box 1: the severity matrix, end to end through pytest ─────────────────────

#: ``(rung, flags, passed, failed, failing item ids)`` — one row per cell of the matrix the
#: card asks to have integration-tested. The rows are stated as pytest outcomes because that
#: is what the contract is about: FATAL/ERROR fail the item, WARNING does not, and a strict
#: policy naming the property changes the *gate* for exactly that item.
MATRIX: tuple[tuple[str, tuple[str, ...], int, int, tuple[str, ...]], ...] = (
    # A clean graph is clean under every policy — the control that shows the flags are not
    # simply failing whatever they touch.
    ("clean", (), 5, 0, ()),
    ("clean", (STRICT_OPTION,), 5, 0, ()),
    # FATAL: fails exactly its own item. Strict changes nothing — there is no WARNING here.
    ("dangling_target", (), 4, 1, ("graph-well-formed",)),
    ("dangling_target", (STRICT_OPTION,), 4, 1, ("graph-well-formed",)),
    # ERROR: same rung behaviour, one step down the ladder.
    ("unprotected_retry", (), 4, 1, ("effect-safety",)),
    ("unprotected_retry", (STRICT_OPTION,), 4, 1, ("effect-safety",)),
    # WARNING finding: noted by default; promoted by bare strict and by the per-property form
    # that names it; untouched by a per-property form that names something else.
    ("seedless_llm", (), 5, 0, ()),
    ("seedless_llm", (STRICT_OPTION,), 4, 1, ("determinism-replay",)),
    ("seedless_llm", (f"{STRICT_OPTION}=determinism-replay",), 4, 1, ("determinism-replay",)),
    ("seedless_llm", (f"{STRICT_OPTION}=termination-witness",), 5, 0, ()),
    # WARNING-grade witness note: the same three cells, on the record that rides a witness.
    ("blanket_only", (), 5, 0, ()),
    ("blanket_only", (STRICT_OPTION,), 4, 1, ("termination-witness",)),
    ("blanket_only", (f"{STRICT_OPTION}=termination-witness",), 4, 1, ("termination-witness",)),
    ("blanket_only", (f"{STRICT_OPTION}=determinism-replay",), 5, 0, ()),
)


@pytest.mark.parametrize(("rung", "flags", "passed", "failed", "failing"), MATRIX)
def test_the_severity_matrix_holds_through_a_real_session(
    pytester: pytest.Pytester,
    rung: str,
    flags: tuple[str, ...],
    passed: int,
    failed: int,
    failing: tuple[str, ...],
) -> None:
    """§0.2's ladder and its strict overlay, one cell per row, as pytest outcomes.

    Both directions in every row: the count of passes is asserted beside the count of
    failures, and each failing item is named — so a policy that failed everything and a policy
    that failed nothing are both caught, and so is one that failed the *wrong* property's item.
    """
    pytester.makepyfile(test_target=_ir_source(RUNGS[rung], name=rung))
    result = pytester.runpytest(*flags)
    result.assert_outcomes(passed=passed, failed=failed)
    expected_exit = pytest.ExitCode.TESTS_FAILED if failed else pytest.ExitCode.OK
    assert result.ret == expected_exit
    for slug in failing:
        result.stdout.fnmatch_lines([f"*FAILED*test_gebra[[]{rung}-{slug}[]]*"])


@pytest.mark.parametrize(
    ("rung", "slug", "severity", "condition"),
    [
        ("dangling_target", "graph-well-formed", "fatal", "path-map-target-undefined"),
        ("unprotected_retry", "effect-safety", "error", "unprotected-effect-in-retry-region"),
        ("seedless_llm", "determinism-replay", "warning", "deterministic-llm-seed-unpinned"),
    ],
)
def test_each_rung_of_the_ladder_really_is_the_rung_it_is_named_for(
    rung: str, slug: PropertySlug, severity: str, condition: str
) -> None:
    """The matrix asserts pytest outcomes; this asserts the grades those outcomes rest on.

    Without it the matrix would pass unchanged if ``unprotected-effect-in-retry-region`` were
    graded FATAL — the item fails either way — and the claim that there is "one target per rung
    of §0.2's ladder" would be untested. Each record's own ``severity`` and condition ID are
    read out of the envelope, so the matrix above is anchored to the ladder rather than to a
    count of red items.
    """
    report = verify(_ir(RUNGS[rung]))
    failure = _run(report, slug).failure
    assert failure is not None
    assert failure.severity == severity
    assert failure.property_condition == condition


def test_a_promoted_p08_finding_keeps_severity_warning_in_the_record(
    pytester: pytest.Pytester,
) -> None:
    """The card's own box: P-08 promoted under strict, the stored record unchanged.

    Two assertions, and the second is the one that matters. The first is that the item fails —
    which is the gate. The second is on the **record**, read out of the envelope rather than
    off the terminal: ``severity`` is still ``warning`` and ``claim_class`` still
    ``heuristic``, exactly as §0.2 requires ("promotion changes the gate, never the record …
    rewriting a HEURISTIC advisory into an ERROR would violate the honest-claims discipline").

    ``ItemOutcome.blocking`` is asserted empty in the same breath, because that is where the
    distinction lives in code: nothing about the item's failure came from the severity ladder,
    so the finding is still not *blocking* — it is promoted, which is a different fact.
    """
    ir = _ir(SEEDLESS_LLM)
    verification = verify_target(ir, name="seedless_llm", source="test", strict=STRICT_ALL)
    report = verification.report

    stored = _run(report, "determinism-replay")
    assert stored.result == "fail"
    failure = stored.failure
    assert failure is not None
    assert failure.severity == "warning"
    assert failure.claim_class == "heuristic"
    assert failure.property_condition == "deterministic-llm-seed-unpinned"
    # The gate moved and the ladder did not: §2.1 counts findings by their own severity.
    assert report.gate.counts.warning == 1
    assert report.gate.counts.blocking == 0
    assert report.gate.exit_code == 1

    outcome = item_outcome(verification, "determinism-replay")
    assert outcome.failed is True
    assert outcome.blocking == ()
    assert [promotion.property_condition for promotion in outcome.promotions] == [
        "deterministic-llm-seed-unpinned"
    ]
    # Every other item is untouched — a bare strict policy promotes what is there, not more.
    assert all(
        item_outcome(verification, slug).failed is False
        for slug in WEDGE
        if slug != "determinism-replay"
    )

    pytester.makepyfile(test_target=_ir_source(SEEDLESS_LLM, name="seedless_llm"))
    result = pytester.runpytest(STRICT_OPTION)
    result.assert_outcomes(passed=4, failed=1)
    result.stdout.fnmatch_lines(["*FAILED*test_gebra[[]seedless_llm-determinism-replay[]]*"])
    # The message says what it is: a promotion, with the record's own grade and claim class.
    result.stdout.fnmatch_lines(
        ["*promoted by --gebra-strict: WARNING deterministic-llm-seed-unpinned [[]heuristic[]]*"]
    )
    result.stdout.fnmatch_lines(["*keeps `severity: warning`*"])


def test_the_same_finding_is_a_note_and_not_a_failure_without_the_flag(
    pytester: pytest.Pytester,
) -> None:
    """The other half of the box: the default mapping leaves the identical record advisory.

    Asserted on the *same* IR as the promoted case, so the only difference between the two
    tests is the flag. D-10's own risk table is the reason this matters — "a strict CI gate
    that over-blocks makes teams disable the plugin", answered by "default severity mapping
    keeps WARNINGs advisory; `--gebra-strict` is opt-in".
    """
    pytester.makepyfile(test_target=_ir_source(SEEDLESS_LLM, name="seedless_llm"))
    result = pytester.runpytest("-rA")
    result.assert_outcomes(passed=5, failed=0)
    assert result.ret == pytest.ExitCode.OK
    # Rendered as the finding it is — the envelope's own severity word (§5.1 obligation 3),
    # not under the `note` label that obligation reserves for witness notes — with the fact
    # that it did not gate said in words rather than by relabelling the record.
    result.stdout.fnmatch_lines(
        [
            "*WARNING deterministic-llm-seed-unpinned [[]heuristic[]]*",
            "*advisory under the default mapping*",
        ]
    )
    result.stdout.fnmatch_lines(["*exit 0 — pass-with-notes; strict off*"])


# ── Witness-note reach, and the promotion-identity trap ──────────────────────────────────


def test_a_warning_grade_witness_note_is_reached_by_strict(pytester: pytest.Pytester) -> None:
    """§0.2's reach is about severity, so it reaches notes — the record no finding walk sees.

    "Promotion reaches WARNING-grade findings wherever they surface in the record: WARNING
    `Failure`s and co-findings **and** WARNING-grade structured witness **notes** — a
    pass-with-notes report whose witness carries a promotable note … gates as exit `1` under a
    strict flag naming its property, with the report, witness, and note records unchanged."

    All four clauses are asserted: the note is on the witness, P-02's report still reads
    ``result: "pass"``, the run exits 1, and the item fails.
    """
    ir = _ir(BLANKET_ONLY)
    verification = verify_target(ir, name="blanket_only", source="test", strict=STRICT_ALL)
    report = verification.report

    stored = _run(report, "termination-witness")
    assert stored.result == "pass"  # "the pass stays a pass in the record" (§2.3)
    witness = stored.witness
    assert witness is not None
    notes = notes_for(report, "termination-witness")
    assert [note.kind for note in notes] == ["scc-covered-only-by-recursion-limit"]
    assert notes[0].severity == "warning"
    assert report.gate.exit_code == 1
    # A promoted note is not a finding, so nothing entered the tally — and §2.5's eligibility
    # rule reads the FATAL count, which is why a promoted run is still snapshot-eligible.
    assert report.gate.counts.warning == 0
    assert report.gate.snapshot_eligible is True

    outcome = item_outcome(verification, "termination-witness")
    assert outcome.failed is True
    assert outcome.blocking == ()
    assert outcome.witness_notes == notes

    pytester.makepyfile(test_target=_ir_source(BLANKET_ONLY, name="blanket_only"))
    result = pytester.runpytest(f"{STRICT_OPTION}=termination-witness")
    result.assert_outcomes(passed=4, failed=1)
    result.stdout.fnmatch_lines(["*FAILED*test_gebra[[]blanket_only-termination-witness[]]*"])


def test_a_promoted_note_is_never_rendered_with_its_condition_ids_registered_grade(
    pytester: pytest.Pytester,
) -> None:
    """§4.6 rule 8's trap, closed: the promoted-item identity is a name, not a severity.

    P-02's promoted note is reported under ``cycle-without-termination-witness``, which the
    §0.4 registry grades **FATAL**, while the record it names is a WARNING-grade note.
    "Displaying it as a fatal finding would invert §0.2's whole rule." So the rendering is
    asserted in both directions: the identity appears and is labelled as an identity, and the
    word FATAL appears nowhere in the item's message.
    """
    ir = _ir(BLANKET_ONLY)
    verification = verify_target(ir, name="blanket_only", source="test", strict=STRICT_ALL)
    outcome = item_outcome(verification, "termination-witness")

    (record,) = promoted_records(outcome)
    assert record.joined is True
    assert record.origin == "witness-note"
    assert record.label == "scc-covered-only-by-recursion-limit"
    assert record.severity == "warning"  # the record's own, joined back per rule 8
    assert record.claim_class is None  # a note carries none by design
    assert record.reported_under == "cycle-without-termination-witness"
    # The id it is reported under really is registered FATAL — otherwise this test is vacuous.
    from gebra.verify import condition

    assert condition("cycle-without-termination-witness").severity == "fatal"

    pytester.makepyfile(test_target=_ir_source(BLANKET_ONLY, name="blanket_only"))
    result = pytester.runpytest(STRICT_OPTION)
    result.assert_outcomes(passed=4, failed=1)
    result.stdout.fnmatch_lines(["*witness note scc-covered-only-by-recursion-limit*"])
    result.stdout.fnmatch_lines(
        ["*reported under cycle-without-termination-witness — the promoted item's identity*"]
    )
    message = "\n".join(result.stdout.lines)
    _, _, after = message.partition("blanket_only-termination-witness")
    failure_text, _, _ = after.partition("= gebra =")
    assert "FATAL" not in failure_text, failure_text


# ── Acceptance box 2: select/skip ────────────────────────────────────────────────────────


def _collected(result: pytest.RunResult) -> list[str]:
    """The item ids an inner ``--collect-only -q`` session reported, in order."""
    return [line.split("::", 1)[1] for line in result.stdout.lines if line.startswith("test_")]


@pytest.mark.parametrize(
    ("flags", "expected"),
    [
        ((), WEDGE),
        ((f"{SELECT_OPTION}=graph-well-formed",), ("graph-well-formed",)),
        (
            (f"{SELECT_OPTION}=effect-safety,graph-well-formed",),
            ("graph-well-formed", "effect-safety"),
        ),
        # Repeated flags accumulate, and the result is in catalog order however it was typed.
        (
            (f"{SELECT_OPTION}=effect-safety", f"{SELECT_OPTION}=graph-well-formed"),
            ("graph-well-formed", "effect-safety"),
        ),
        (
            (f"{SKIP_OPTION}=determinism-replay",),
            ("graph-well-formed", "termination-witness", "dataflow-completeness", "effect-safety"),
        ),
        (
            (f"{SKIP_OPTION}=termination-witness,effect-safety",),
            ("graph-well-formed", "dataflow-completeness", "determinism-replay"),
        ),
        # Composed: select first, then subtract. An overlap is a subtraction, not a conflict.
        (
            (
                f"{SELECT_OPTION}=graph-well-formed,effect-safety,determinism-replay",
                f"{SKIP_OPTION}=effect-safety",
            ),
            ("graph-well-formed", "determinism-replay"),
        ),
    ],
)
def test_select_and_skip_subset_the_generated_items(
    pytester: pytest.Pytester, flags: tuple[str, ...], expected: tuple[str, ...]
) -> None:
    """The subsetting is a fact about **collection**, so it is asserted on collected ids.

    Not on outcomes: a run whose items all pass would look identical whether four or five were
    generated, and "subsets correctly" is a statement about which items exist.
    """
    pytester.makepyfile(test_target=_ir_source(CLEAN, name="clean"))
    result = pytester.runpytest("--collect-only", "-q", *flags)
    assert _collected(result) == [f"test_gebra[clean-{slug}]" for slug in expected]
    assert result.ret == pytest.ExitCode.OK


def test_a_skipped_property_still_fails_nothing_and_a_selected_one_still_fails(
    pytester: pytest.Pytester,
) -> None:
    """Subsetting decides which items exist; it never decides what an item says.

    The same ERROR-bearing graph, twice: skipping P-06 leaves four green items and a green
    run, and selecting P-06 alone leaves one item and a red one. That pairing is what shows
    the flags are subsetting rather than suppressing — the finding did not go anywhere.
    """
    pytester.makepyfile(test_target=_ir_source(UNPROTECTED_RETRY, name="retry"))

    skipped = pytester.runpytest(f"{SKIP_OPTION}=effect-safety")
    skipped.assert_outcomes(passed=4, failed=0)
    assert skipped.ret == pytest.ExitCode.OK

    selected = pytester.runpytest(f"{SELECT_OPTION}=effect-safety")
    selected.assert_outcomes(passed=0, failed=1)
    selected.stdout.fnmatch_lines(["*FAILED*test_gebra[[]retry-effect-safety[]]*"])


def test_subsetting_never_reaches_the_run_itself(pytester: pytest.Pytester) -> None:
    """A skipped property is un-itemized, never unchecked — ``verify()`` answers all thirteen.

    The distinction has teeth: ``gebra_verification.report`` is what a suite writes its own
    assertions against and what the closing report renders, and a subsetting flag that
    silently narrowed the *run* would turn ``--gebra-skip`` into a way to make a report say
    less than it knows.
    """
    pytester.makeconftest(
        _PREAMBLE
        + f"""
import json
from gebra.ir import WorkflowIR

@pytest.fixture
def gebra_workflow():
    return WorkflowIR.model_validate_json(json.dumps({UNPROTECTED_RETRY!r}))
"""
    )
    pytester.makepyfile(
        test_whole_run=_PREAMBLE
        + """
def test_the_report_is_whole(gebra_verification):
    report = gebra_verification.report
    assert len(report.properties) == 13
    assert report.outcome_for("effect-safety").result == "fail"
    assert report.gate.exit_code == 1
"""
    )
    result = pytester.runpytest(f"{SKIP_OPTION}=effect-safety")
    result.assert_outcomes(passed=1, failed=0)


def test_strict_reaches_the_fixture_surface_too(pytester: pytest.Pytester) -> None:
    """The gate a suite asserts on is the gate CI ran.

    ``gebra_verification`` takes the session's strict policy, so a suite that reads
    ``report.gate.exit_code`` under ``--gebra-strict`` sees the same 1 the marker items see.
    Without this the two surfaces would disagree about one run, which is the sort of
    disagreement a CI gate cannot afford.
    """
    pytester.makeconftest(
        _PREAMBLE
        + f"""
import json
from gebra.ir import WorkflowIR

@pytest.fixture
def gebra_workflow():
    return WorkflowIR.model_validate_json(json.dumps({SEEDLESS_LLM!r}))
"""
    )
    pytester.makepyfile(
        test_gate=_PREAMBLE
        + """
def test_the_gate_is_strict(gebra_verification):
    gate = gebra_verification.report.gate
    assert gate.strict.mode == "all"
    assert gate.exit_code == 1
    assert [p.property for p in gate.promotions] == ["determinism-replay"]
    # And the record is untouched, on this surface as on the other.
    assert gebra_verification.report.outcome_for(
        "determinism-replay"
    ).failure.severity == "warning"
"""
    )
    result = pytester.runpytest(STRICT_OPTION)
    result.assert_outcomes(passed=1, failed=0)


# ── The refusals: a flag the plugin cannot read is never a quiet default ─────────────────


@pytest.mark.parametrize(
    ("flags", "message"),
    [
        ((f"{SELECT_OPTION}=graph-wellformed",), "*not a property slug*"),
        ((f"{SKIP_OPTION}=determinism_replay",), "*not a property slug*"),
        ((f"{STRICT_OPTION}=P-08",), "*not a property slug*"),
        ((f"{SELECT_OPTION}=graph-well-formed,",), "*empty property slug*"),
        # A deferred property cannot be selected: the item it asks for cannot exist.
        ((f"{SELECT_OPTION}=retry-coherence",), "*no validator in this build answers*"),
    ],
)
def test_an_unreadable_gate_flag_ends_the_session(
    pytester: pytest.Pytester, flags: tuple[str, ...], message: str
) -> None:
    """A typo is refused, never ignored.

    The dangerous half is ``--gebra-skip``: a slug that silently failed to match would gate on
    a property the user asked to leave out, and the run would be green-or-red for a reason
    nothing on screen mentions. The same argument runs the other way for ``--gebra-strict``,
    where a dropped slug is a gate that quietly did not tighten.
    """
    pytester.makepyfile(test_target=_ir_source(CLEAN, name="clean"))
    result = pytester.runpytest(*flags)
    assert result.ret == pytest.ExitCode.USAGE_ERROR
    result.stderr.fnmatch_lines([message])


def test_skipping_every_property_is_refused_at_collection(pytester: pytest.Pytester) -> None:
    """A subset that leaves nothing is refused where TE-06 refuses an empty enabled set.

    "A gebra run that checked nothing must not report a green item" — and the shape of the
    refusal matters as much as the fact of it: this one lands at *collection*, because that is
    when the subset is known, so it ends the run as a collection error rather than as five
    green items nobody generated. The message says which flags emptied it, since an empty
    subset assembled from ``addopts`` plus a command line is otherwise a puzzle.
    """
    pytester.makepyfile(test_target=_ir_source(CLEAN, name="clean"))
    result = pytester.runpytest(f"{SKIP_OPTION}={','.join(WEDGE)}")
    assert result.ret == pytest.ExitCode.INTERRUPTED
    result.stdout.fnmatch_lines(["*has no property to check*"])
    result.stdout.fnmatch_lines([f"*{SKIP_OPTION} left nothing to check*"])


def test_a_bare_strict_flag_before_a_path_is_refused_loudly(pytester: pytest.Pytester) -> None:
    """``--gebra-strict`` takes an optional value, and argparse will eat the next token.

    ``pytest --gebra-strict test_target.py`` reads the path as the strict value — that is
    argparse's behaviour for ``nargs="?"`` and it cannot be prevented at the parser. What it
    can be is loud: the value is checked against the closed thirteen-slug vocabulary, so the
    session ends with a message that names both the vocabulary and the ``=`` form rather than
    running a differently-scoped gate over a silently-dropped path.
    """
    pytester.makepyfile(test_target=_ir_source(CLEAN, name="clean"))
    result = pytester.runpytest(STRICT_OPTION, "test_target.py")
    assert result.ret == pytest.ExitCode.USAGE_ERROR
    result.stderr.fnmatch_lines(["*not a property slug*"])
    result.stderr.fnmatch_lines([f"*{STRICT_OPTION} takes its value joined with `=`*"])


def test_an_explicitly_empty_strict_value_is_refused_rather_than_widened(
    pytester: pytest.Pytester,
) -> None:
    """``--gebra-strict=`` is a malformed per-property list, not the bare form.

    The two are distinguishable — argparse stores the option's ``const`` for the bare form and
    the literal empty string for ``=`` with nothing after it — and keeping them apart matters
    in one direction only: reading an empty list as "promote everything" would widen a gate the
    user did not ask to widen, which is the opposite of every other refusal in this surface.
    """
    pytester.makepyfile(test_target=_ir_source(SEEDLESS_LLM, name="seedless_llm"))
    result = pytester.runpytest(f"{STRICT_OPTION}=")
    assert result.ret == pytest.ExitCode.USAGE_ERROR
    result.stderr.fnmatch_lines(["*empty property slug*"])


def test_a_bare_strict_flag_at_the_end_of_the_command_line_is_bare(
    pytester: pytest.Pytester,
) -> None:
    """The ordinary CI spelling — ``pytest tests/ --gebra-strict`` — is the bare form.

    The complement of the test above, and the reason that one is a refusal rather than a
    redesign: with nothing left to consume, ``nargs="?"`` yields the const and the run gets
    §0.2's promote-everything policy.
    """
    pytester.makepyfile(test_target=_ir_source(SEEDLESS_LLM, name="seedless_llm"))
    result = pytester.runpytest("test_target.py", STRICT_OPTION)
    result.assert_outcomes(passed=4, failed=1)
    result.stdout.fnmatch_lines(["*exit 1 — fail; strict --gebra-strict; 1 promoted*"])
    # §5.1 obligation 6 asks for "the strict policy in force with what it promoted" — a count
    # is not a *what*, so the closing summary names each promoted record beside the policy.
    result.stdout.fnmatch_lines(
        [
            "*promoted by --gebra-strict — the gate moved, the records did not*",
            "*determinism-replay: WARNING deterministic-llm-seed-unpinned [[]heuristic[]]*",
        ]
    )


# ── The closing report (REPORT-FORMAT-SPEC §5's human profile) ───────────────────────────


def test_the_closing_report_states_what_a_default_run_would_otherwise_hide(
    pytester: pytest.Pytester,
) -> None:
    """§5.1's obligations, on the marker path, with no flag at all.

    This is the surface TE-06 handed forward: a marker-only adopter never touches
    ``gebra_verification``, so without it a green run shows five green items and nothing else —
    no witness, and no sign that eight properties were not checked. Obligations 1, 4, 5 and 6
    are asserted here; 7 has its own test below, and 3's note label is asserted wherever a
    note exists.
    """
    pytester.makepyfile(test_target=_ir_source(CLEAN, name="clean"))
    result = pytester.runpytest()
    result.assert_outcomes(passed=5, failed=0)
    result.stdout.fnmatch_lines(["*= gebra =*"])
    # (1) a subject line, with the digest recognizable as a prefix.
    result.stdout.fnmatch_lines(["*sha256:*… · ir 1.0 · ir-document*"])
    # (4) every pass shown, with its claim class and a witness summary.
    result.stdout.fnmatch_lines(["*pass*graph-well-formed [[]defensible[]]*reachable from START*"])
    result.stdout.fnmatch_lines(["*pass*effect-safety [[]defensible-a[]]*"])
    # (5) the markers shown as not checked, never as passes.
    for slug in ("signature-soundness", "retry-coherence", "evolution-safety"):
        result.stdout.fnmatch_lines([f"*not checked*{slug} [[]deferred-to-phase-1[]]*"])
    # (6) a closing summary: counts, exit code and reason, and the policy in force.
    result.stdout.fnmatch_lines(
        ["*5 properties reported · 8 not checked · 0 fatal · 0 error · 0 warning*"]
    )
    result.stdout.fnmatch_lines(["*exit 0 — pass; strict off*"])


def test_the_report_says_which_properties_a_subset_run_actually_itemized(
    pytester: pytest.Pytester,
) -> None:
    """A subset run must not read as though every verdict below it gated CI.

    The block still shows all thirteen outcomes, because that is what the run answered — but
    with ``--gebra-select``/``--gebra-skip`` in force only some of them had an item, and the
    difference between "answered" and "gated on" is the whole of what those flags do. Without
    this line the report would state five verdicts under a gate that was two.
    """
    pytester.makepyfile(test_target=_ir_source(UNPROTECTED_RETRY, name="retry"))
    result = pytester.runpytest(f"{SELECT_OPTION}=graph-well-formed,determinism-replay")
    result.assert_outcomes(passed=2, failed=0)
    # The P-06 ERROR is still reported — it just did not gate.
    result.stdout.fnmatch_lines(
        ["*fail*P-06 effect-safety*", "*error unprotected-effect-in-retry-region*"]
    )
    itemized = (
        f"*{SELECT_OPTION}/{SKIP_OPTION} generated an item for: graph-well-formed, "
        "determinism-replay*"
    )
    result.stdout.fnmatch_lines([itemized])
    # And the gate that no item could fail is counted and its owner named, rather than left
    # for a reader to notice that a green session sits under exit 1.
    result.stdout.fnmatch_lines(
        ["*1 blocking finding(s) and 0 promotion(s) fall outside that subset — effect-safety*"]
    )
    result.stdout.fnmatch_lines(["*exit 1 — fail; strict off*"])
    assert result.ret == pytest.ExitCode.OK


def test_the_report_renders_every_record_and_summarizes_none_away() -> None:
    """§4.2's fail row and §4.4's last row, over every fixture the corpus has.

    "Every co-failure and advisory rendered too — never summarized away"; "every record
    rendered; a count that matches; no record dropped, collapsed or re-packaged". So the
    assertion is per record and by condition ID rather than by a count alone: a rendering that
    printed the primary and said "(+2 more)" would satisfy a count and fail this.

    Run over the whole corpus rather than one chosen fixture, because which shapes carry
    riders is the corpus's fact and not this file's — and asserted non-vacuous, since a walk
    that found no rider anywhere would pass without checking anything.
    """
    from gebra.pytest_plugin import _render_property_line

    riders = 0
    for name, ir in _every_ir():
        report = verify(ir)
        for outcome in report.properties:
            if not isinstance(outcome, PropertyReport) or outcome.failure is None:
                continue
            failure = outcome.failure
            rendered = "\n".join(_render_property_line(outcome, report))
            records = [(failure.property_condition, failure.claim_class)]
            records.extend(
                (rider.property_condition, rider.claim_class) for rider in failure.co_failures or ()
            )
            records.extend(
                (rider.property_condition, rider.claim_class) for rider in failure.advisories or ()
            )
            assert f"— {len(records)} record(s)" in rendered, f"{name}: {rendered}"
            for condition, claim_class in records:
                assert condition in rendered, f"{name}: {condition}"
                assert claim_class in rendered, f"{name}: {condition}"
            riders += len(records) - 1
    assert riders >= 1, "no fixture carried a co-failure or advisory — check the walk"


def test_the_report_qualifies_a_best_effort_answer_where_the_answer_is(
    pytester: pytest.Pytester,
) -> None:
    """§5.1 obligation 7 — "stated where its reports are, not only in the summary".

    "Silence here is the failure mode the field exists to prevent — a P-02 pass on a graph
    with a dangling target reads as a verdict." So the qualifier is asserted on the property's
    own line, and the FATAL that caused it is asserted to suppress snapshot recording (§0.2).
    """
    pytester.makepyfile(test_target=_ir_source(DANGLING_TARGET, name="dangling"))
    result = pytester.runpytest()
    result.assert_outcomes(passed=4, failed=1)
    result.stdout.fnmatch_lines(
        [
            "*pass*termination-witness*",
            "*answered on topology P-01 found ill-formed — a diagnostic*",
        ]
    )
    result.stdout.fnmatch_lines(["*3 best-effort*"])
    result.stdout.fnmatch_lines(["*no snapshot is recorded for this run*"])


def test_one_target_gets_one_block_however_many_items_it_has(
    pytester: pytest.Pytester,
) -> None:
    """Five items, one extraction each, one report block — not five copies of one.

    The de-duplication key is the item's nodeid with the gebra parametrization stripped, so a
    target parametrized *another* way keeps its own block. Both halves are asserted, because
    a key that collapsed too much would report one graph's verdicts under another's name.
    """
    pytester.makepyfile(
        test_target=_PREAMBLE
        + f"""
import json
from gebra.ir import WorkflowIR

BLOCKS = {{"clean": {CLEAN!r}, "warning": {SEEDLESS_LLM!r}}}

@pytest.mark.parametrize("shape", sorted(BLOCKS))
@pytest.mark.{MARKER}(name="target")
def test_gebra(shape):
    return WorkflowIR.model_validate_json(json.dumps(BLOCKS[shape]))
"""
    )
    result = pytester.runpytest()
    result.assert_outcomes(passed=10, failed=0)
    blocks = [line for line in result.stdout.lines if "properties reported" in line]
    assert len(blocks) == 2, blocks
    # The two are different runs, and the report shows it: one has the WARNING, one does not.
    assert sorted(line.split("·")[-1].strip() for line in blocks) == ["0 warning", "1 warning"]


def test_an_extraction_warning_survives_a_run_that_reached_no_verdict(
    pytester: pytest.Pytester,
) -> None:
    """INTROSPECTION-SPEC §8 has no exception for exit 2 — and that is its sharpest case.

    "Warnings are never silently droppable." The run that reached no verdict is precisely the
    run whose extraction warning is the most diagnostic thing it has: a hintless conditional
    router warns ``unsupported-construct`` and stamps ``ir_version 1.1``, which ``verify()``
    then refuses as an ir-validation tool error — so "warned, and no verdict" is that path's
    *normal* outcome rather than a corner. The closing block used to state the tool error and
    return before it reached the notes; it now renders them first.

    Provoked here by TE-06's own mechanism — unregistering a validator, which makes ``verify()``
    refuse to assemble the run — over a target that does warn, since the travel-booking agent
    extracts warning-free by TE-05's design and could not reach both facts at once. Both
    surfaces are checked in one session, because ``gebra_verification`` is the one that has no
    other unconditional home for a note.

    A **subprocess**, because the registry is process-global. WA-07 cost, on TE-06's terms: the
    parent ledger cannot see a different process and this child does perform a real extraction,
    so the child asserts its own copy of the sentinel ledger as its last item.
    """
    pytester.makeconftest(
        _PREAMBLE
        + """
from gebra.verify import unregister_validator
from tests.plugin.test_plugin import _build_warning_bearing_agent

unregister_validator("determinism-replay")

@pytest.fixture
def gebra_workflow():
    return _build_warning_bearing_agent()
"""
    )
    pytester.makepyfile(
        test_widener=_PREAMBLE
        + f"""
from tests.plugin.test_plugin import _build_warning_bearing_agent

@pytest.mark.{MARKER}(name="widener")
def test_gebra():
    return _build_warning_bearing_agent()

def test_the_fixture_surface_reached_no_verdict(gebra_verification):
    assert gebra_verification.report.gate.exit_code == 2

def test_zz_no_node_body_ran_in_this_process():
    from tests.plugin.test_plugin import WIDENER_TRIPPED

    assert WIDENER_TRIPPED == []
"""
    )
    result = pytester.runpytest_subprocess()
    result.assert_outcomes(passed=2, failed=4)
    result.stdout.fnmatch_lines(["*no verdict was reached*dispatch*"])
    # Once per surface, in the closing section, with no `-r` flag: the marker target's block
    # and the `gebra_verification` block. Both are tool-error blocks, which is the point.
    warnings = [
        line for line in result.stdout.lines if "extraction warning [contract-defaulted]" in line
    ]
    assert len(warnings) >= 2, warnings
    # §8's "what it carries" column reaches the reader too, not only the taxonomy code —
    # `contract-defaulted`'s row carries which rule applied, and a reader of a pytest run had
    # no way to reach it before.
    result.stdout.fnmatch_lines(
        ["*extraction warning [[]contract-defaulted[]]*rule=no-write-evidence*"]
    )


# ── The live agent: TE-05's "clean under strict with nothing to promote", verified ───────


def test_the_travel_booking_agent_is_clean_under_every_strict_form(
    pytester: pytest.Pytester,
) -> None:
    """The shared substrate stays green under the flags the consuming cards will run.

    TE-05 recorded this as a hand-off fact; it is asserted here rather than inherited, because
    six cards downstream build on it. Bare strict and the per-property form naming P-08 — the
    property whose findings are all WARNING-grade, so the one most likely to move — both leave
    five green items.

    WA-07: the agent's bodies are sentinels, and the file-level ledger assertion runs on entry
    to and exit from this test. The inner session runs in-process, so it shares that ledger.
    """
    pytester.makepyfile(test_target=_agent_source())
    for flags in ((STRICT_OPTION,), (f"{STRICT_OPTION}=determinism-replay",)):
        result = pytester.runpytest(*flags)
        result.assert_outcomes(passed=5, failed=0)
        assert result.ret == pytest.ExitCode.OK
        result.stdout.fnmatch_lines(["*exit 0 — pass; strict*"])
    assert travel_booking.TRIPPED == []


# ── The policy object, and the seam TE-06 left ───────────────────────────────────────────


def test_a_session_with_no_gebra_flag_still_imports_nothing_of_gebra(
    pytester: pytest.Pytester,
) -> None:
    """TE-06's import-closure fact survives the new ``pytest_configure`` work.

    Parsing the gate flags needs the closed slug vocabulary, which lives in ``gebra.verify``
    (~190 ms) — so :func:`_parse_policy` returns ``None`` *before* importing anything when no
    gebra flag was given, and ``pytest_configure`` does nothing else that imports. That is
    load-bearing rather than tidy: a ``pytest11`` entry point is imported and configured at the
    start of every session in every environment that has gebra installed, including sessions
    with nothing gebra-related in them.

    A **subprocess**, because the parent has long since imported ``gebra.verify`` and
    ``sys.modules`` there says nothing. No gebra target runs in the child, so it reaches no
    workflow object at all — the WA-07 ledger this file asserts has nothing to speak for
    across that boundary and needs none.
    """
    pytester.makepyfile(
        test_plain="""
import sys

def test_nothing_gebra_was_imported():
    loaded = sorted(name for name in sys.modules if name.split(".")[0] == "gebra")
    assert loaded == ["gebra", "gebra.pytest_plugin"], loaded
"""
    )
    result = pytester.runpytest_subprocess()
    result.assert_outcomes(passed=1, failed=0)


def test_the_default_policy_is_strict_off_and_subsets_nothing() -> None:
    """No flag means no policy — and ``gate_policy(None)`` still answers, for a bare call."""
    policy = gate_policy(None)
    assert policy == GatePolicy(strict=STRICT_OFF)
    assert policy.select is None
    assert policy.skip == ()
    assert enabled_properties() == tuple(slug for slug in PROPERTY_SLUGS if slug in WEDGE)


@pytest.mark.parametrize(
    ("select", "skip", "expected"),
    [
        (None, (), WEDGE),
        (("effect-safety", "graph-well-formed"), (), ("graph-well-formed", "effect-safety")),
        (None, ("graph-well-formed",), WEDGE[1:]),
        (("graph-well-formed", "effect-safety"), ("effect-safety",), ("graph-well-formed",)),
        (("graph-well-formed",), ("graph-well-formed",), ()),
    ],
)
def test_enabled_properties_applies_select_then_skip(
    select: tuple[PropertySlug, ...] | None,
    skip: tuple[PropertySlug, ...],
    expected: tuple[str, ...],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``enabled ∩ select \\ skip``, in that order — the composition, stated as a table.

    The last row is the one worth having: a slug named by both flags is subtracted, which is
    what makes the composition total. It is refused higher up, at collection, rather than
    silently generating nothing.
    """

    class _Config:
        stash = pytest.Stash()

    config = _Config()
    from gebra.pytest_plugin import POLICY_KEY

    config.stash[POLICY_KEY] = GatePolicy(strict=STRICT_OFF, select=select, skip=skip)
    assert enabled_properties(config) == expected  # type: ignore[arg-type]


# ── Drift tripwires: this module's walks against ``verify()``'s own ──────────────────────


def _every_ir() -> list[tuple[str, WorkflowIR]]:
    """Every vendored single-IR fixture, plus the five rungs above."""
    subjects = [(name, _ir(block)) for name, block in RUNGS.items()]
    for path in sorted(CORPUS.rglob("*.yaml")):
        if path.name == "schema.yaml":
            continue
        fixture = load_fixture(path)
        if fixture.ir is not None:
            subjects.append((str(path.relative_to(CORPUS)), fixture.ir))
    return subjects


def test_the_note_walk_agrees_with_the_promotions_verify_derives() -> None:
    """``notes_for`` must see exactly the notes ``verify()`` promotes — over the whole corpus.

    The two are derived independently: this module walks the reports, ``verify()`` walks its
    own records and applies each property's identity rule. A note carrier added to the
    envelope that this walk missed would move them apart, and a WARNING-grade note this walk
    invented would too. Sixty-odd subjects, so the arithmetic is asserted as well as the
    agreement — a tripwire that silently compared two empty sets would be no tripwire.

    Compared as an ordered list of ``(kind, location)`` rather than as a set of kinds, so that
    multiplicity and anchor are in scope: two notes of one kind on different SCCs are two
    promotions, and a set of kinds would call that one. The equality also carries the other
    direction — a note carrying **no** severity must promote nothing, which is what keeps
    ``cycle-census-capped`` from ever flipping a gate. That arm is asserted by construction
    rather than observed: nothing in this corpus or in the five rungs reaches an ungraded note,
    which is stated here rather than left as an unnoticed hole in the walk.
    """
    subjects = _every_ir()
    assert len(subjects) > 30, "the corpus walk found almost nothing — check the loader"
    promotable = 0
    for name, ir in subjects:
        report = verify(ir, RunPolicy(strict=STRICT_ALL))
        for slug in PROPERTY_SLUGS:
            notes = notes_for(report, slug)
            walked = [
                (note.kind, location)
                for note in notes
                if note.severity == "warning"
                for location in note.locations or (None,)
            ]
            promoted = [
                (promotion.note_kind, promotion.location)
                for promotion in promotions_for(report, slug)
                if promotion.origin == "witness-note"
            ]
            assert walked == promoted, f"{name} · {slug}: {walked} vs {promoted}"
            promotable += len(walked)
    # Non-vacuity: at least the `blanket_only` rung reaches this, which is why it exists.
    assert promotable >= 1


def test_every_promotion_joins_back_to_a_record() -> None:
    """§4.6 rule 8's join is total over everything this build can produce.

    An unjoined promotion is not a crash — it renders with §2.3's guarantee standing in for
    the record's own grade and says so — but it is drift, and it is exactly the drift that
    would let a promotion be shown with the wrong weight. So it is a tripwire rather than a
    fallback nobody watches.
    """
    joined = 0
    for name, ir in _every_ir():
        verification = verify_target(ir, name=name, source=name, strict=STRICT_ALL)
        for slug in PROPERTY_SLUGS:
            outcome = item_outcome(verification, slug)
            for record in promoted_records(outcome):
                assert record.joined, f"{name} · {slug}: {record.promotion}"
                assert record.severity == "warning", record
                joined += 1
    assert joined >= 5, f"only {joined} promotions over the whole corpus — check the walk"


def test_the_per_item_promotions_partition_the_runs_promotions() -> None:
    """Every promotion lands on exactly one item, and none is left carried by no item.

    The mirror of TE-06's orphan-owner tripwire, for the gate rather than the ladder: a
    promotion owned by a property with no item would move ``gate.exit_code`` while every item
    stayed green, which is the one way the per-item projection can disagree with the run.
    """
    for name, ir in _every_ir():
        verification = verify_target(ir, name=name, source=name, strict=STRICT_ALL)
        report = verification.report
        per_item = [
            promotion
            for slug in enabled_properties()
            for promotion in item_outcome(verification, slug).promotions
        ]
        assert sorted(per_item, key=str) == sorted(report.gate.promotions, key=str), name


def test_a_subset_policy_leaves_promotions_no_item_can_fail_and_the_report_says_so() -> None:
    """The partition above holds only for the *default* enabled set — and that is the hazard.

    ``--gebra-skip`` is a request to generate fewer items, not to gate on less: ``verify()``
    still promotes what a strict policy names, so a promotion owned by a skipped property
    raises ``gate.exit_code`` to 1 with no item left to fail on it. That is the user's explicit
    request and it is not refused — but §2.2 makes ``exit_code`` the contract and a gate the
    user was owed must not go missing in silence, so the closing block counts what fell outside
    the subset and names its owners. Asserted on the rendering, since the rendering is the only
    place the fact exists.
    """
    verification = verify_target(
        _ir(SEEDLESS_LLM), name="seedless_llm", source="test", strict=STRICT_ALL
    )
    report = verification.report
    assert report.gate.exit_code == 1
    itemized = tuple(slug for slug in WEDGE if slug != "determinism-replay")
    assert promotions_for(report, "determinism-replay")
    assert not [promotion for promotion in report.gate.promotions if promotion.property in itemized]

    from gebra.pytest_plugin import _render_run

    rendered = "\n".join(_render_run("where", verification, itemized))
    assert "0 blocking finding(s) and 1 promotion(s) fall outside that subset" in rendered
    assert "determinism-replay" in rendered
    assert "the run's own exit code did" in rendered
