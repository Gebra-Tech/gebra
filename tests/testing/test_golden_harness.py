"""The golden harness over the vendored corpus, and the core that drives it.

Two things live here. The **parametrized corpus run** is the harness itself in CI: one pytest
item per fixture for the load-and-plan layer, and one per *obligation* — a fixture's share of
one property — for the comparison layer, so a CI failure names the fixture and the property
rather than "the corpus". The rest is the unit coverage of ``gebra.testing.harness``: the
projection rules, the comparison routing, the classification order, and a seeded mismatch that
proves the green run is not green by construction.

**What green means here** is PD-006 R3, the owner-signed reading of SOW §2 criterion 2. Its
three layers map onto the items below: all 60 fixtures load (``test_fixture_loads``); every
wedge obligation is asserted by structural model equality or explained
(``test_obligation``); every non-wedge component is a structured skip naming its property and
citing SOW §8, counted and surfaced, never rendered as a pass
(``test_no_non_wedge_obligation_is_asserted``).

**A skip is never a pass, and never an xfail.** ``xfail`` would read as "we expect this to be
wrong", which is a claim about the corpus; the truth is that Phase 0 does not check the
property (SOW §8) or has not wired its validator yet. The two skip reasons are exactly the two
members of ``NotImplementedStatus`` the registry already uses at the API level, so the harness
and ``verify()`` say the same thing about the same absence.

WA-07: nothing here executes a workflow node, calls a model, or opens a network connection.
``tests/testing/test_hermeticity.py`` proves it for the harness core this module drives — it
runs `run_corpus` over the whole corpus inside a guarded interpreter, which executes every
registered validator there. This module's own code is neither run under that guard nor in the
closure its static scans cover (they are scoped to ``gebra.*`` and ``tools.*``), so what it
adds on top is reviewed rather than tripwired: it constructs reports, wires them into the
registry, and reads fixtures.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
import yaml

from gebra.ir import WorkflowIR
from gebra.testing import load_corpus, load_fixture
from gebra.testing.fixtures import PropertyFixture, fixture_from_document, iter_fixture_paths
from gebra.testing.harness import (
    PROJECTION_RULES,
    STATUS_ORDER,
    CorpusRun,
    Obligation,
    Outcome,
    _merged_source,
    expected_for,
    plan_corpus,
    plan_fixture,
    projection_rule,
    run_corpus,
    run_fixture,
    run_obligation,
)
from gebra.verify import (
    NON_WEDGE_SLUGS,
    WEDGE_SLUGS,
    NodeLocation,
    PropertyReport,
    PropertySlug,
    Validator,
    anchor_location,
    models_equivalent,
    properties,
    property_entry,
    register_validator,
    unregister_validator,
    validate_report,
    validator_for,
)
from tests.conftest import FIXTURES_DIR

#: PD-006 R3's own arithmetic: 60 fixtures, 78 obligations over them.
CORPUS_SIZE = 60
OBLIGATION_COUNT = 78

#: The four P-08 fixtures acceptance box 2 names — green since VAL-04 landed.
P08_FIXTURES = (
    "determinism-replay/negative-01-seedless-deterministic-llm-classifier",
    "determinism-replay/negative-02-seeded-llm-extractor-hot-temperature",
    "determinism-replay/positive-01-pinned-seed-zero-temp-classifier",
    "determinism-replay/positive-02-pure-fare-normalizer",
)

#: The six P-01 property fixtures (§1.6), whose validator landed at VAL-05.
P01_FIXTURES = (
    "graph-well-formed/negative-01-unreachable-escalation-node",
    "graph-well-formed/negative-02-dead-end-review-branch",
    "graph-well-formed/negative-03-path-map-typo-dangling-target",
    "graph-well-formed/positive-01-linear-document-pipeline",
    "graph-well-formed/positive-02-support-triage-branching",
    "graph-well-formed/positive-03-travel-parent-graph-with-booking-subgraph",
)

#: The six P-04 property fixtures (§4.6), whose validator landed at VAL-09.
P04_FIXTURES = (
    "dataflow-completeness/negative-01-express-path-skips-writer",
    "dataflow-completeness/negative-02-writer-downstream-of-reader",
    "dataflow-completeness/negative-03-fan-in-missing-branch-writer",
    "dataflow-completeness/positive-01-linear-itinerary-pipeline",
    "dataflow-completeness/positive-02-conditional-both-branches-write",
    "dataflow-completeness/positive-03-parallel-fanout-reduced-results",
)

#: The six P-06 property fixtures (§6.6), whose validator landed at VAL-10.
P06_FIXTURES = (
    "effect-safety/negative-01-billable-in-unguarded-retry",
    "effect-safety/negative-02-irreversible-in-refinement-cycle",
    "effect-safety/negative-03-keyless-idempotent-on-irreversible",
    "effect-safety/positive-01-keyed-idempotent-billable-retry",
    "effect-safety/positive-02-irreversible-outside-cycle",
    "effect-safety/positive-03-compensated-billable-hold-loop",
)

#: The flagship 4+4 P-02 fixtures (§2.6), whose validator landed at VAL-07.
P02_FIXTURES = (
    "termination-witness/negative-01-unwitnessed-reflection-loop",
    "termination-witness/negative-02-nested-scc-outer-only-witness",
    "termination-witness/negative-03-counter-guard-without-wired-exit",
    "termination-witness/negative-04-supervisor-delegation-scc-no-witness",
    "termination-witness/positive-01-counter-guarded-retry-loop",
    "termination-witness/positive-02-justified-recursion-limit-refinement-loop",
    "termination-witness/positive-03-shrinking-worklist-hotel-quotes",
    "termination-witness/positive-04-nested-scc-dual-counter-witnesses",
)

#: Every obligation the harness asserts green today, by id. Pinned rather than counted so
#: that a validator landing shows up as a diff here, and a *lost* assertion cannot hide
#: behind a new one.
MATCHED = (
    *(f"{fixture}::determinism-replay" for fixture in P08_FIXTURES),
    "mixed/10-all-properties-pass-healthy-research-pipeline::determinism-replay",
    # P-08's advisory records on `mixed/03` (PR-3), green since TE-04 gave that rule
    # REPORT-FORMAT-SPEC §3.2 rule 3's anchor reduction on both sides (FM-004 closed).
    "mixed/03-parallel-reducerless-key-with-unpinned-llm-writers::determinism-replay",
    *(f"{fixture}::graph-well-formed" for fixture in P01_FIXTURES),
    "mixed/10-all-properties-pass-healthy-research-pipeline::graph-well-formed",
    # P-01's `mixed/04` PR-1 primary, green since TE-04 gave PR-1 its merged-list clause on
    # REPORT-FORMAT-SPEC §3.3's terms (FM-007 closed). P-01 itself is unchanged.
    "mixed/04-dangling-path-map-target-orphans-downstream-reader::graph-well-formed",
    *(f"{fixture}::dataflow-completeness" for fixture in P04_FIXTURES),
    # P-04's one cross-property record obligation (PR-2), green since VAL-09.
    "mixed/02-unwitnessed-loop-reading-unwritten-key::dataflow-completeness",
    *(f"{fixture}::effect-safety" for fixture in P06_FIXTURES),
    # P-06's four mixed shares, green since VAL-10: two PR-1 primaries, one PR-2 record
    # multiset (`mixed/06`, where P-06 rides P-07's report), and one PR-4 witness entry.
    "mixed/01-witnessed-cycle-with-unkeyed-billable-node::effect-safety",
    "mixed/06-irreversible-cycle-idempotency-key-not-read::effect-safety",
    "mixed/09-send-fanout-billable-no-idempotency-in-retry::effect-safety",
    "mixed/10-all-properties-pass-healthy-research-pipeline::effect-safety",
    # P-04's mixed/10 PR-4 witness entry, green since the DEC-23 corpus revision replaced the
    # pre-contract aggregate with the validator-derived DataflowWitness (FM-003 closed).
    "mixed/10-all-properties-pass-healthy-research-pipeline::dataflow-completeness",
    *(f"{fixture}::termination-witness" for fixture in P02_FIXTURES),
    # P-02's three mixed shares, green since VAL-07: one PR-1 primary (`mixed/02`), one PR-2
    # record multiset (`mixed/08`, where P-02 rides P-04's report), and one PR-4 witness
    # entry (`mixed/10`, green since the DEC-23 guard reword put its declared bound inside
    # the §3 grammar). `mixed/05`'s P-02 share stays the ruled FM-005 unmodelled record.
    "mixed/02-unwitnessed-loop-reading-unwritten-key::termination-witness",
    "mixed/08-express-path-skips-gate-writer-and-witnessed-exit::termination-witness",
    "mixed/10-all-properties-pass-healthy-research-pipeline::termination-witness",
    # mixed/08's P-04 primary, green since the DEC-24 corpus revision (M13) closed FM-009.
    "mixed/08-express-path-skips-gate-writer-and-witnessed-exit::dataflow-completeness",
)

#: Every live deviation, by id. Each one has an open row in
#: ``docs/governance/FIDELITY-MATRIX.md``; ``tests/testing/test_fidelity_matrix.py`` is what
#: holds the two lists together.
DEVIATIONS = (
    "mixed/04-dangling-path-map-target-orphans-downstream-reader::dataflow-completeness",
    "mixed/05-evolution-drops-witness-and-state-field::termination-witness",
    "mixed/05-evolution-drops-witness-and-state-field::dataflow-completeness",
)


@pytest.fixture(scope="module")
def corpus() -> tuple[PropertyFixture, ...]:
    """The vendored corpus, loaded once for the module."""
    return load_corpus(FIXTURES_DIR)


@pytest.fixture(scope="module")
def run() -> CorpusRun:
    """One harness run over the vendored corpus, shared by the assertions that read it."""
    return run_corpus(FIXTURES_DIR)


def _by_id(run: CorpusRun) -> dict[str, Outcome]:
    return {outcome.obligation.id: outcome for outcome in run.outcomes}


@pytest.fixture(autouse=True)
def _registry_is_restored() -> Iterator[None]:
    """The wedge registry is process-global, and this module is the first to lean on it.

    Several tests seed a deliberately wrong validator to prove the comparison fires. A leak
    would not be silent — the pinned green set would fail — but it would fail somewhere other
    than where it was caused, so the invariant is checked per test instead: exactly the
    validators the shipped package registers, before and after.

    The expectation is **derived** from ``gebra.verify.properties`` rather than listed, so it
    keeps meaning the same thing as each VAL card lands instead of needing an edit per card.
    It is still not circular against a dirty registry: the comparison is by function identity
    against each module's own ``check_*``, so a test that replaced a shipped validator, or
    registered one the package does not ship, fails here either way.
    """
    shipped: dict[PropertySlug, object] = {
        module.PROPERTY_SLUG: getattr(module, f"check_{name}")
        for name in properties.__all__
        for module in (getattr(properties, name),)
    }
    assert shipped, "no validator module is shipped — this fixture would be vacuous"

    def wired() -> dict[PropertySlug, object]:
        return {slug: validator_for(slug) for slug in WEDGE_SLUGS if validator_for(slug)}

    assert wired() == shipped, "the registry was already dirty on entry"
    yield
    assert wired() == shipped, "a test left the wedge validator registry mutated"


# ── Layer 1: every fixture, one item each (PD-006 R3.1) ──────────────────────────────────


@pytest.mark.parametrize(
    "path",
    sorted(FIXTURES_DIR.rglob("*.yaml")),
    ids=lambda path: f"{path.parent.name}/{path.stem}",
)
def test_fixture_loads(path: Path) -> None:
    """Each fixture loads into models and states at least one obligation.

    The layer PD-006 R3.1 puts under *every* fixture, mixed and non-wedge included: the
    document parses, the IR blocks validate at ``ir_version`` 1.0, and the harness can say
    which properties it is answerable for. ``schema.yaml`` itself is excluded by the loader's
    own rule and skipped here for the same reason.
    """
    if path.name == "schema.yaml":
        pytest.skip("schema.yaml is the format spec, not a fixture")
    fixture = load_fixture(path)
    assert fixture.irs, "a fixture carries at least one IR snapshot"
    assert plan_fixture(fixture), f"{fixture.fixture_id} states no obligation"


# ── Layer 2/3: every obligation, one item each ───────────────────────────────────────────


def _obligations() -> tuple[Obligation, ...]:
    return plan_corpus(FIXTURES_DIR)


@pytest.mark.parametrize("obligation", _obligations(), ids=lambda obligation: obligation.id)
def test_obligation(obligation: Obligation, run: CorpusRun) -> None:
    """One fixture's share of one property: asserted, deferred, or a recorded deviation.

    This is the harness in CI. ``matched`` passes; the two structured absences skip with the
    reason the registry would give at the API level; a deviation skips naming the fidelity
    matrix, because a *recorded* deviation is a decision in flight rather than a red build —
    what fails when one is unrecorded is ``test_fidelity_matrix.py``, whose whole job is that
    one question.
    """
    outcome = _by_id(run)[obligation.id]
    if outcome.status == "matched":
        return
    if outcome.is_deviation:
        pytest.skip(
            f"deviation ({outcome.status}), recorded in docs/governance/FIDELITY-MATRIX.md: "
            f"{outcome.detail}"
        )
    pytest.skip(f"{outcome.status}: {outcome.detail}")


# ── Acceptance box 2: the P-08 fixtures assert green ─────────────────────────────────────


@pytest.mark.parametrize("fixture_id", P08_FIXTURES)
def test_the_p08_fixtures_assert_green(fixture_id: str, run: CorpusRun) -> None:
    """VAL-04 has landed, so P-08's four fixtures are compared and match, not skipped.

    Stated as its own item because "green" and "not run" are indistinguishable in a suite
    where most obligations skip: this asserts the *status*, so a P-08 validator that stopped
    registering would fail here rather than quietly become a skip.
    """
    outcome = _by_id(run)[f"{fixture_id}::determinism-replay"]
    assert outcome.status == "matched", outcome.detail


def test_the_wedge_obligations_that_are_asserted_are_exactly_the_pinned_ones(
    run: CorpusRun,
) -> None:
    """The green set is pinned, so a landing validator is a diff and a lost one is a failure."""
    matched = tuple(
        outcome.obligation.id for outcome in run.outcomes if outcome.status == "matched"
    )
    assert sorted(matched) == sorted(MATCHED)


def test_the_p08_witness_entry_of_mixed_10_is_asserted_through_pr_4(
    run: CorpusRun,
) -> None:
    """PR-4 is not theoretical: `mixed/10`'s P-08 sub-witness is compared and matches.

    Worth its own item because PR-4 is the one projection rule with a single green instance:
    the corpus has exactly one `multi-property` witness, so this obligation is what keeps the
    rule from being an untested code path. (PR-2 gained its own green instance at VAL-09 —
    `mixed/02`'s P-04 record — and both of PR-1's live instances and PR-3's only one went
    green at TE-04, when those two rules gained their REPORT-FORMAT-SPEC clauses.)
    """
    outcome = _by_id(run)[
        "mixed/10-all-properties-pass-healthy-research-pipeline::determinism-replay"
    ]
    assert outcome.obligation.rule == "PR-4"
    assert outcome.status == "matched"


# ── PD-006 R3.3: non-wedge components are structured skips, never passes ─────────────────


def test_no_non_wedge_obligation_is_asserted(run: CorpusRun) -> None:
    """Every one of the eight is deferred, by name, with SOW §8 in the reason."""
    non_wedge = [
        outcome for outcome in run.outcomes if outcome.obligation.property_slug in NON_WEDGE_SLUGS
    ]
    assert non_wedge
    for outcome in non_wedge:
        assert outcome.status == "deferred-to-phase-1", outcome.obligation.id
        assert outcome.obligation.property_slug in outcome.detail
        assert "SOW §8" in outcome.detail


def test_every_non_wedge_property_with_a_fixture_is_counted(run: CorpusRun) -> None:
    """Deferrals are surfaced and counted per property — never absent from the run report."""
    deferred = {
        outcome.obligation.property_slug
        for outcome in run.outcomes
        if outcome.status == "deferred-to-phase-1"
    }
    # P-05, P-10, P-11 and P-13 have no fixture in the corpus at all.
    assert deferred == {
        "signature-soundness",
        "retry-coherence",
        "parallel-safety",
        "evolution-safety",
    }


def test_the_run_counts_every_obligation_exactly_once(run: CorpusRun) -> None:
    """The counted summary PD-006 R3.3 asks be surfaced adds up, and the ids are unique."""
    assert len(run.outcomes) == OBLIGATION_COUNT
    assert len(run.fixture_ids) == CORPUS_SIZE
    assert sum(run.counts.values()) == OBLIGATION_COUNT
    assert tuple(run.counts) == STATUS_ORDER
    assert len({outcome.obligation.id for outcome in run.outcomes}) == OBLIGATION_COUNT


def test_the_deviations_are_exactly_the_pinned_ones(run: CorpusRun) -> None:
    assert sorted(outcome.obligation.id for outcome in run.deviations) == sorted(DEVIATIONS)


def test_a_run_is_deterministic() -> None:
    """Same corpus, same outcomes — the metaproperty every golden harness owes."""
    first, second = run_corpus(FIXTURES_DIR), run_corpus(FIXTURES_DIR)
    assert [(o.obligation, o.status) for o in first.outcomes] == [
        (o.obligation, o.status) for o in second.outcomes
    ]


# ── The id scheme ────────────────────────────────────────────────────────────────────────


def test_the_obligation_id_is_directory_stem_and_slug() -> None:
    obligation = Obligation("mixed/04-dangling.yaml", "graph-well-formed", "primary-projection")
    assert obligation.id == "mixed/04-dangling::graph-well-formed"
    assert obligation.wedge


def test_a_non_wedge_obligation_says_so() -> None:
    assert not Obligation("mixed/07-x.yaml", "parallel-safety", "report").wedge


def test_every_obligation_id_is_unique_across_the_corpus() -> None:
    obligations = _obligations()
    assert len({obligation.id for obligation in obligations}) == len(obligations)


# ── Planning: which obligations a fixture states ─────────────────────────────────────────


def _fixture(relative: str) -> PropertyFixture:
    return load_fixture(next(FIXTURES_DIR.glob(relative)))


def _document(relative: str) -> tuple[dict[str, Any], Path]:
    """A vendored fixture's raw document, as a mutable copy, with the path it came from.

    The copy is what makes a seeded-shape test possible without touching the corpus: the
    document is edited in memory and rebuilt through :func:`fixture_from_document`, so
    ``tests/fixtures/properties/`` is only ever read (WA-04/WA-11).
    """
    path = next(FIXTURES_DIR.glob(relative))
    return json.loads(json.dumps(yaml.safe_load(path.read_text(encoding="utf-8")))), path


def test_a_single_property_fixture_states_one_whole_report_obligation() -> None:
    fixture = _fixture("determinism-replay/positive-01-*.yaml")
    (obligation,) = plan_fixture(fixture)
    assert obligation.kind == "report"
    assert obligation.rule is None
    assert obligation.property_slug == "determinism-replay"


def test_a_failing_mixed_fixture_states_one_obligation_per_property() -> None:
    """`mixed/09`: a P-06 primary, a P-07 co-failure and a P-09 advisory — three rules."""
    fixture = _fixture("mixed/09-*.yaml")
    plan = plan_fixture(fixture)
    assert [(o.property_slug, o.kind, o.rule) for o in plan] == [
        ("effect-safety", "primary-projection", "PR-1"),
        ("retry-coherence", "cross-property-co-failure", "PR-2"),
        ("parallel-safety", "cross-property-advisory", "PR-3"),
    ]


def test_a_passing_mixed_fixture_states_one_obligation_per_witness_entry() -> None:
    fixture = _fixture("mixed/10-*.yaml")
    plan = plan_fixture(fixture)
    assert all(obligation.rule == "PR-4" for obligation in plan)
    assert [obligation.property_slug for obligation in plan] == list(fixture.properties)


def test_a_mixed_fixture_with_no_derivable_owner_falls_back_to_whole_reports() -> None:
    """`mixed/07`'s primary condition is one §0.4 holds back (DEC-05 D6), so no owner resolves.

    Both its properties are non-wedge, so both obligations defer — but the fallback is what
    keeps a future fixture in that shape from silently stating no obligation at all.
    """
    fixture = _fixture("mixed/07-*.yaml")
    plan = plan_fixture(fixture)
    assert [(o.property_slug, o.kind, o.rule) for o in plan] == [
        ("signature-soundness", "report", None),
        ("parallel-safety", "report", None),
    ]


def test_the_same_property_is_never_planned_twice_for_one_fixture() -> None:
    for fixture in load_corpus(FIXTURES_DIR):
        plan = plan_fixture(fixture)
        assert len({obligation.property_slug for obligation in plan}) == len(plan), (
            fixture.fixture_id
        )


# ── The projection rules ─────────────────────────────────────────────────────────────────


def test_pr_1_drops_advisories_and_another_property_s_co_failures() -> None:
    """`mixed/09`'s P-06 projection carries neither the P-07 co-failure nor the P-09 advisory.

    That is the whole point of PR-1: `emit_co_failure` refuses a name another property holds
    and `emit_failure` refuses a self-referential advisory, so a P-06 validator physically
    cannot produce the composed block — comparing against it would be a category error.
    """
    fixture = _fixture("mixed/09-*.yaml")
    obligation = plan_fixture(fixture)[0]
    projected = expected_for(fixture, obligation)
    assert isinstance(projected, PropertyReport)
    assert projected.property == "effect-safety"
    assert projected.failure is not None
    assert projected.failure.co_failures is None
    assert projected.failure.advisories is None
    # The unprojected block does carry both.
    raw = dict(fixture.expected)["failure"]
    assert raw["co_failures"] and raw["advisories"]


def test_pr_1_keeps_a_same_property_co_failure() -> None:
    """`mixed/04`'s P-01 projection keeps both P-01 records and drops the P-04 one."""
    fixture = _fixture("mixed/04-*.yaml")
    obligation = plan_fixture(fixture)[0]
    projected = expected_for(fixture, obligation)
    assert isinstance(projected, PropertyReport)
    assert projected.failure is not None
    kept = projected.failure.co_failures or ()
    assert [record.property for record in kept] == ["graph-well-formed", "graph-well-formed"]


def test_pr_1_survives_a_co_failure_shape_section_0_3_does_not_model_yet() -> None:
    """`mixed/01` does not compose whole — its P-07 co-failure has no §0.3 shape — yet its
    P-06 projection does, because the restriction runs on the document, not on a report."""
    fixture = _fixture("mixed/01-*.yaml")
    with pytest.raises(Exception):  # noqa: B017 - FixtureError; the point is that it raises
        fixture.expected_report()
    projected = expected_for(fixture, plan_fixture(fixture)[0])
    assert isinstance(projected, PropertyReport)
    assert projected.property == "effect-safety"


def test_pr_2_excludes_a_subsumed_record() -> None:
    """DEC-05 D2: `mixed/04`'s P-04 co-failure is not an independent finding, so P-04 owes
    nothing on that IR — the expected record set is empty rather than one entry."""
    fixture = _fixture("mixed/04-*.yaml")
    obligation = next(
        o for o in plan_fixture(fixture) if o.property_slug == "dataflow-completeness"
    )
    assert obligation.rule == "PR-2"
    assert expected_for(fixture, obligation) == ()


def test_pr_3_reads_the_records_off_the_advisories() -> None:
    fixture = _fixture("mixed/03-*.yaml")
    obligation = next(o for o in plan_fixture(fixture) if o.property_slug == "determinism-replay")
    records = expected_for(fixture, obligation)
    assert [condition for condition, _ in records] == [
        "deterministic-llm-seed-unpinned",
        "deterministic-llm-seed-unpinned",
    ]


def test_pr_4_projects_one_witness_entry_to_one_report() -> None:
    fixture = _fixture("mixed/10-*.yaml")
    obligation = next(o for o in plan_fixture(fixture) if o.property_slug == "graph-well-formed")
    projected = expected_for(fixture, obligation)
    assert isinstance(projected, PropertyReport)
    assert projected.result == "pass"
    assert projected.witness is not None
    assert projected.witness.kind == "well-formedness"


def test_pr_1_compares_a_merged_co_failure_list_without_its_order(run: CorpusRun) -> None:
    """The merged-list clause (TE-04, closing `FM-007`), asserted in both directions.

    Forward: `mixed/04`'s P-01 obligation matches, and it can only match through the clause —
    the two sides really do list the same two records in opposite orders, which the second
    half asserts rather than assumes. Backward: `_merged_source` fires on exactly the two
    fixtures whose vendored `co_failures` carries more than one property, so no *unmerged*
    block silently loses its order comparison. Everything else in the report stays exactly
    compared, which is what keeps this narrower than a `SetCompared` mark.
    """
    outcome = _by_id(run)[
        "mixed/04-dangling-path-map-target-orphans-downstream-reader::graph-well-formed"
    ]
    assert outcome.status == "matched"
    assert "multiset" in outcome.detail and "REPORT-FORMAT-SPEC §3.3" in outcome.detail

    fixture = _fixture("mixed/04-*.yaml")
    obligation = next(o for o in plan_fixture(fixture) if o.property_slug == "graph-well-formed")
    expected = expected_for(fixture, obligation)
    assert isinstance(expected, PropertyReport)
    assert expected.failure is not None
    p01 = validator_for("graph-well-formed")
    assert p01 is not None and fixture.ir is not None
    produced = p01(fixture.ir)
    assert produced.failure is not None
    orders = (
        [record.property_condition for record in expected.failure.co_failures or ()],
        [record.property_condition for record in produced.failure.co_failures or ()],
    )
    assert orders[0] != orders[1], "the two orders agree now — FM-007's premise is gone"
    assert sorted(orders[0]) == sorted(orders[1])
    assert not models_equivalent(produced, expected), (
        "exact model equality passes now, so the clause is no longer what makes this match"
    )

    merged = {
        fixture.fixture_id
        for path in iter_fixture_paths(FIXTURES_DIR)
        for fixture in (load_fixture(path),)
        if _merged_source(fixture)
    }
    assert sorted(name.split("-")[0] for name in merged) == ["mixed/04", "mixed/05"]


def test_pr_3_reduces_both_sides_to_the_section_0_3_anchor(run: CorpusRun) -> None:
    """The anchor reduction (TE-04, closing `FM-004`), and why it is not a relaxation.

    `mixed/03`'s advisories carry a bare `NodeLocation`; P-08's own report anchors on §8.3's
    `DeterminismNodeLocation` with its `annotation`/`form`/`effects` evidence. Both sides go
    through `gebra.verify.anchor_location` — REPORT-FORMAT-SPEC §3.2 rule 3 as a function —
    so an advisory is compared against an advisory. Asserted here: the obligation matches,
    the produced record really does carry the richer subtype (otherwise the reduction would
    be doing nothing), and the reduction is idempotent on the fixture's side.
    """
    outcome = _by_id(run)[
        "mixed/03-parallel-reducerless-key-with-unpinned-llm-writers::determinism-replay"
    ]
    assert outcome.status == "matched"

    fixture = _fixture("mixed/03-*.yaml")
    p08 = validator_for("determinism-replay")
    assert p08 is not None and fixture.ir is not None
    produced = p08(fixture.ir)
    assert produced.failure is not None
    assert produced.failure.location.kind == "node"
    assert type(produced.failure.location) is not NodeLocation, (
        "P-08 no longer anchors on the §8.3 subtype — the reduction has nothing to reduce"
    )
    assert anchor_location(produced.failure.location) != produced.failure.location

    obligation = next(o for o in plan_fixture(fixture) if o.property_slug == "determinism-replay")
    records = expected_for(fixture, obligation)
    assert not isinstance(records, PropertyReport)
    for _, location in records:
        assert anchor_location(location) == location, "the fixture side is already an anchor"


def test_a_fixture_advisory_carrying_a_subtype_is_a_mismatch_not_an_absorption() -> None:
    """The rule-3 reduction must never *hide* a fixture-side disagreement.

    `Advisory.location` accepts either shape for loading (§3.2 rule 3's own parenthetical —
    PC-6's fixture duty), so a future fixture could state a concrete subtype where the corpus
    states an anchor. Reducing that away would silently absorb exactly the question the
    fidelity matrix says is owed a row. Seeded here on a hand-built `mixed/03` document: the
    outcome is `mismatched` and its detail routes the reader to the matrix.
    """
    document, path = _document("mixed/03-*.yaml")
    advisories = document["expected"]["failure"]["advisories"]
    assert advisories[0]["location"] == {"kind": "node", "node": "market_analysis"}, (
        "the seed is stale — mixed/03's advisories no longer carry a bare NodeLocation"
    )
    advisories[0]["location"] = {
        "kind": "node",
        "node": "market_analysis",
        "annotation": "deterministic",
        "form": "bare-boolean",
        "effects": ["network", "external"],
    }
    fixture = fixture_from_document(document, path)

    obligation = next(o for o in plan_fixture(fixture) if o.property_slug == "determinism-replay")
    outcome = run_obligation(fixture, obligation)
    assert outcome.status == "mismatched"
    assert "DeterminismNodeLocation" in outcome.detail
    assert "matrix row" in outcome.detail


def test_every_projection_rule_is_reachable_from_the_corpus() -> None:
    """No rule is dead code: each of the four is exercised by at least one vendored fixture."""
    used = {obligation.rule for obligation in _obligations()} - {None}
    assert used == {rule.id for rule in PROJECTION_RULES}


def test_a_projection_rule_carries_its_citation() -> None:
    for rule in PROJECTION_RULES:
        assert projection_rule(rule.id) is rule
        assert rule.citation.strip()
        assert rule.statement.strip()
    with pytest.raises(KeyError):
        projection_rule("PR-99")


# ── Classification order ─────────────────────────────────────────────────────────────────


def test_scope_is_decided_before_shape() -> None:
    """A non-wedge obligation defers even when its expected value has no §0.3 shape.

    The order matters: checking the shape first would report the eight properties' provisional
    witness shapes as corpus deviations, and ``schema.yaml`` calls those provisional by design.
    """
    fixture = _fixture("parallel-safety/negative-01-*.yaml")
    (outcome,) = run_fixture(fixture)
    assert outcome.status == "deferred-to-phase-1"
    with pytest.raises(Exception):  # noqa: B017 - the block genuinely has no §0.3 shape
        fixture.expected_report()


def test_shape_is_decided_before_wiring(run: CorpusRun) -> None:
    """`mixed/05`'s wedge records are unmodelled even with every wedge validator wired.

    Reporting the modelling fact before consulting the registry is what surfaced
    FM-005/FM-006 at VAL-01 rather than at TE-04 — and now that P-02 *is* wired (VAL-07),
    the same order is what keeps the ruled record ``unmodelled`` rather than letting a live
    validator turn a corpus-side fact into a comparison.
    """
    outcomes = _by_id(run)
    assert (
        outcomes["mixed/05-evolution-drops-witness-and-state-field::termination-witness"].status
        == "unmodelled"
    )
    assert validator_for("termination-witness") is not None


def test_a_pending_obligation_says_its_expectation_is_already_modelled() -> None:
    """The wedge property whose validator is unwired: modelled, not compared, not a deviation.

    Its predecessor read the pending set off the vendored run and asked to be deleted once
    the wedge completed; VAL-07 completed it (the run now has zero ``pending-validator``
    outcomes — the harness-side counterpart asserts that), so the transition is re-created
    here instead: unwire P-02, run its flagship fixture, and the obligation reports pending
    with the modelled expectation named — never a deviation.
    """
    unregister_validator("termination-witness")
    try:
        fixture = _fixture("termination-witness/positive-01-*.yaml")
        (outcome,) = run_fixture(fixture)
        assert outcome.status == "pending-validator"
        entry = property_entry("termination-witness")
        assert entry.property_id in outcome.detail
        assert "modelled" in outcome.detail
        assert not outcome.is_deviation
    finally:
        register_validator(
            "termination-witness", properties.termination_witness.check_termination_witness
        )


# ── Comparison: model equality, set-comparison where the spec marks order free ───────────


def _report(data: dict[str, Any]) -> PropertyReport:
    return validate_report(data)


def _permuted(fixture: PropertyFixture, field: str) -> PropertyReport:
    """The fixture's own expected report with one repeated witness member reversed."""
    expected = dict(fixture.expected)
    witness = dict(expected["witness"])
    witness[field] = list(reversed(witness[field]))
    expected["witness"] = witness
    return validate_report({"property": fixture.properties[0], **expected})


def test_a_set_compared_field_is_compared_as_a_multiset() -> None:
    """§4.3 marks P-04's ``coverage`` order non-normative, and the harness honours the mark.

    Run against a real fixture rather than a constructed pair, so what is proven is that the
    *harness* asks the envelope — the marks live on ``DataflowWitness.coverage`` with their
    citation, and the comparison reads them off there.
    """
    fixture = _fixture("dataflow-completeness/positive-01-*.yaml")
    permuted = _permuted(fixture, "coverage")
    assert permuted != fixture.expected_report(), "plain equality is order-sensitive"
    outcome = _run_wired(fixture, permuted)
    assert outcome.status == "matched", outcome.detail


def test_an_unmarked_repeated_field_is_compared_exactly() -> None:
    """A permuted ``certificate`` is not a topological order, so it is not equivalent.

    Nothing marks ``TerminationWitness.certificate``, and the default is exact for exactly
    this reason: relaxing it would accept a certificate that certifies nothing.
    """
    fixture = _fixture("termination-witness/positive-01-*.yaml")
    outcome = _run_wired(fixture, _permuted(fixture, "certificate"))
    assert outcome.status == "mismatched"
    assert "witness differs" in outcome.detail


def _run_wired(fixture: PropertyFixture, produced: PropertyReport) -> Outcome:
    """Run ``fixture``'s single obligation against a validator that returns ``produced``."""
    (obligation,) = plan_fixture(fixture)
    with _wired(obligation.property_slug, lambda _ir: produced):
        return run_obligation(fixture, obligation)


@contextmanager
def _wired(slug: PropertySlug, implementation: Validator) -> Iterator[None]:
    """Register ``implementation`` for ``slug`` for the duration, then put back what was there.

    The registry is process-global by design (a validator registers itself at import), so a
    test that wires one must unwire it — and must restore P-08's real validator, which is the
    only one registered today. The swap is inside the ``try`` so that a failure *between* the
    unregister and the register still restores; ``_registry_is_restored`` is the belt to this
    module's braces.
    """
    previous = validator_for(slug)
    try:
        unregister_validator(slug)
        register_validator(slug, implementation)
        yield
    finally:
        unregister_validator(slug)
        if previous is not None:
            register_validator(slug, previous)


# ── The seeded mismatch: the green run is not green by construction ──────────────────────


def test_a_seeded_wrong_validator_is_reported_as_a_mismatch() -> None:
    """Wire a P-01 validator that always passes vacuously, and the harness says so.

    Without this the whole suite's green could mean "the comparison never fires". It fires:
    every P-01 obligation whose fixture expects a failure flips to ``mismatched``, and the
    detail names the field that parted company.
    """
    vacuous = _report(
        {
            "property": "graph-well-formed",
            "result": "pass",
            "witness": {
                "kind": "well-formedness",
                "reachable_from_start": [],
                "terminal_nodes": [],
                "orphan_nodes": [],
                "unresolved_targets": [],
            },
        }
    )
    fixture = _fixture("graph-well-formed/negative-01-*.yaml")
    (obligation,) = plan_fixture(fixture)
    with _wired("graph-well-formed", lambda _ir: vacuous):
        outcome = run_obligation(fixture, obligation)
    assert outcome.status == "mismatched"
    assert outcome.is_deviation
    assert "result" in outcome.detail


def test_a_seeded_wrong_record_set_is_reported_as_a_mismatch() -> None:
    """The PR-2/PR-3 multiset comparison fires too — proved on `mixed/04`'s P-04 obligation.

    Its expected record set is empty (the one record is `subsumed_by`), so a P-04 validator
    that reported the orphaned read anyway is exactly the regression DEC-05 D2 rules out.
    """
    fixture = _fixture("mixed/04-*.yaml")
    obligation = next(
        o for o in plan_fixture(fixture) if o.property_slug == "dataflow-completeness"
    )
    reporting = _report(
        {
            "property": "dataflow-completeness",
            "result": "fail",
            "failure": {
                "property_condition": "read-key-never-written-on-path",
                "location": {
                    "kind": "state-key",
                    "key": "legal_hold_ref",
                    "node": "compliance_log",
                    "path": ["START", "compliance_log"],
                },
                "severity": "fatal",
                "claim_class": "defensible-a",
            },
        }
    )
    with _wired("dataflow-completeness", lambda _ir: reporting):
        outcome = run_obligation(fixture, obligation)
    assert outcome.status == "mismatched"
    assert "read-key-never-written-on-path" in outcome.detail


def test_a_validator_that_passes_satisfies_an_empty_record_obligation() -> None:
    """The green half of DEC-05 D2 on `mixed/04`: P-04 owes nothing, and saying so matches.

    Paired with the seeded mismatch above, this pins the rule in both directions — a P-04 that
    reports the orphaned read fails, and a P-04 that passes on that IR is exactly right.
    """
    fixture = _fixture("mixed/04-*.yaml")
    obligation = next(
        o for o in plan_fixture(fixture) if o.property_slug == "dataflow-completeness"
    )
    passing = _report(
        {
            "property": "dataflow-completeness",
            "result": "pass",
            "witness": {"kind": "dataflow", "coverage": []},
        }
    )
    with _wired("dataflow-completeness", lambda _ir: passing):
        outcome = run_obligation(fixture, obligation)
    assert outcome.status == "matched"
    assert "0 (condition ID, location) record(s)" in outcome.detail


def test_a_matching_record_set_in_another_order_still_matches() -> None:
    """PR-3's multiset is order-free: the two sides package the same findings differently."""
    fixture = _fixture("mixed/03-*.yaml")
    obligation = next(o for o in plan_fixture(fixture) if o.property_slug == "determinism-replay")
    matching = _report(
        {
            "property": "determinism-replay",
            "result": "fail",
            "failure": {
                "property_condition": "deterministic-llm-seed-unpinned",
                "location": {"kind": "node", "node": "risk_analysis"},
                "severity": "warning",
                "claim_class": "heuristic",
                "co_failures": [
                    {
                        "property": "determinism-replay",
                        "property_condition": "deterministic-llm-seed-unpinned",
                        "location": {"kind": "node", "node": "market_analysis"},
                        "severity": "warning",
                        "claim_class": "heuristic",
                    }
                ],
            },
        }
    )
    with _wired("determinism-replay", lambda _ir: matching):
        outcome = run_obligation(fixture, obligation)
    assert outcome.status == "matched", outcome.detail


# ── Diagnostics ──────────────────────────────────────────────────────────────────────────


def test_an_unmodelled_detail_names_the_closest_candidate_shape(run: CorpusRun) -> None:
    """One extra key must not render as seven missing fields of a shape it never was."""
    outcome = _by_id(run)["mixed/05-evolution-drops-witness-and-state-field::termination-witness"]
    assert "P02SccLocation" in outcome.detail
    assert "snapshot" in outcome.detail


def test_a_mismatch_detail_names_both_sides(run: CorpusRun) -> None:
    """A record-multiset mismatch reads as two sides, not as one opaque "differs".

    Anchored on `FM-008` — `mixed/04`'s P-04 share, where the fixture states *no* obligation
    (its record is `subsumed_by: P-01`) and the validator states one. (It was anchored on
    `mixed/03` until TE-04's `PR-3` anchor reduction closed `FM-004`.)
    """
    outcome = _by_id(run)[
        "mixed/04-dangling-path-map-target-orphans-downstream-reader::dataflow-completeness"
    ]
    assert "the validator states" in outcome.detail
    assert "which the fixture does not" in outcome.detail
    assert "read-key-never-written-on-path" in outcome.detail
    assert "legal_hold_ref" in outcome.detail, "the record's own location is what is at issue"


def test_the_run_can_be_read_per_fixture(run: CorpusRun) -> None:
    outcomes = run.for_fixture("mixed/10-all-properties-pass-healthy-research-pipeline.yaml")
    assert len(outcomes) == 8
    assert {outcome.status for outcome in outcomes} == {
        "matched",
        "deferred-to-phase-1",
    }


def test_running_one_fixture_agrees_with_running_the_corpus(
    corpus: tuple[PropertyFixture, ...], run: CorpusRun
) -> None:
    for fixture in corpus:
        single = [(o.obligation.id, o.status) for o in run_fixture(fixture)]
        whole = [(o.obligation.id, o.status) for o in run.for_fixture(fixture.fixture_id)]
        assert single == whole, fixture.fixture_id


def test_the_wedge_five_are_the_asserted_properties(run: CorpusRun) -> None:
    """Every obligation that is compared at all belongs to a wedge property (SOW §1)."""
    compared = {
        outcome.obligation.property_slug
        for outcome in run.outcomes
        if outcome.status in ("matched", "mismatched")
    }
    assert compared <= set(WEDGE_SLUGS)


def test_an_evolution_pair_obligation_reads_the_after_snapshot() -> None:
    """A pair fixture has no ``ir``; the wedge records it carries are scoped ``ir_after``."""
    fixture = _fixture("evolution-safety/negative-01-*.yaml")
    assert fixture.ir is None and fixture.ir_after is not None
    assert isinstance(fixture.ir_after, WorkflowIR)
