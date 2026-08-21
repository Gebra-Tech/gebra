"""The golden harness — one vendored fixture, the obligations it carries, and their outcomes.

A property fixture states what a validator should say about one workflow definition. The
harness turns that statement into **obligations**: the smallest units a run can pass, defer
or fail on, each naming exactly one property. A single-property fixture carries one; a
``mixed/`` fixture carries one per property it exercises, because a cross-property fixture's
``expected:`` block is a *run-level* composition and no single validator produces it whole
(§0.3's scope boundary hands the run-level wrapper to REPORT-FORMAT-SPEC).

**Comparison is model equality, never string or raw-dict equality** (§0.3; A6 PC-6). The
comparison itself is :func:`gebra.verify.models_equivalent` — model equality field by field,
with a field marked :class:`~gebra.verify.SetCompared` compared as a multiset because §0.3
says comparison is "set-comparison where order is not normative". Which fields those are is
a per-property spec statement carried on the models themselves, so this module chooses
nothing about ordering: it asks the envelope.

**Three outcomes are not failures, and none of them is a pass.** SOW §8 puts eight of the
thirteen properties outside Phase 0, so every non-wedge obligation is
:attr:`~OutcomeStatus` ``deferred-to-phase-1`` — named, counted and surfaced, never
rendered as a pass (the same discipline :func:`gebra.verify.not_implemented` applies at the
API level). A wedge obligation whose validator has not been wired yet is
``pending-validator``. An obligation whose expected value does not satisfy the §0.3 envelope
at all is ``unmodelled`` — a fact about the corpus, and one of the two statuses this module
calls a **deviation**.

**A deviation is a decision, never a quiet edit** (WA-04). The two deviation statuses —
``mismatched`` (validator and fixture both modelled, and they disagree) and ``unmodelled`` —
are what ``docs/governance/FIDELITY-MATRIX.md`` records, each with its disposition: fix the
validator, or route a fixture revision through R-05. ``python tools/golden_harness.py``
cross-checks the live deviations against that file in both directions.

**One boundary a consumer of these outcomes has to know.** §0.3 defines P-02, P-04 and P-06
results **only over P-01-clean topology**: where P-01 fails, another property's report is a
best-effort diagnostic rather than a contract-bearing verdict, and "a single-property-scoped
run on P-01-dirty topology is outside the defined result surface". The corpus has exactly one
such live obligation — ``mixed/04``'s P-04 share, on topology carrying both a dangling
``path_map`` target and an unreachable node — and this module compares it like any other. It
is a comparison, not a promise that the spec pins that answer; the fidelity matrix says so
beside the rule, so the validator card that meets it does not inherit an unstated pin.

Nothing here executes a workflow node, calls a model, or opens a network connection (WA-07):
fixtures are read through :mod:`gebra.testing.fixtures`, and a validator is a hermetic
function over a validated :class:`~gebra.ir.WorkflowIR`. The hermeticity of the *call* is
inherited rather than intrinsic: :func:`run_obligation` invokes whatever callable the
process-global registry holds for a slug, and what keeps that safe is
:func:`gebra.verify.register_validator`'s wedge gate plus the tripwire in
``tests/testing/test_hermeticity.py``, which runs this module over the whole corpus in an
interpreter where a substrate import, a socket and a name resolution each raise.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final, Literal, TypeAlias

from pydantic import ValidationError

from gebra.ir import WorkflowIR
from gebra.testing.fixtures import (
    FIXTURE_SUFFIX,
    FixtureError,
    FixtureErrorReason,
    PropertyFixture,
    iter_fixture_paths,
    load_fixture,
)
from gebra.verify import (
    NON_WEDGE_SLUGS,
    AnyLocation,
    CoFailure,
    PropertyReport,
    PropertySlug,
    ReportModel,
    Validator,
    anchor_location,
    models_equivalent,
    property_entry,
    to_data,
    validate_location,
    validate_report,
    validator_for,
)

if TYPE_CHECKING:
    import os

__all__ = [
    "PROJECTION_RULES",
    "STATUS_ORDER",
    "CorpusRun",
    "Expected",
    "Obligation",
    "ObligationKind",
    "Outcome",
    "OutcomeStatus",
    "ProjectionRule",
    "expected_for",
    "plan_corpus",
    "plan_fixture",
    "projection_rule",
    "run_corpus",
    "run_fixture",
    "run_obligation",
]


#: What an obligation compares. ``report`` is the whole ``expected:`` block of a
#: single-property fixture; the other four are the mixed-fixture projections, each of which
#: PD-006 R3.2 requires be logged in the fidelity matrix.
ObligationKind: TypeAlias = Literal[
    "report",
    "primary-projection",
    "cross-property-co-failure",
    "cross-property-advisory",
    "multi-property-witness",
]

#: How an obligation came out. Two of the five are deviations (:attr:`Outcome.is_deviation`);
#: two are structured skips; one is the green case.
OutcomeStatus: TypeAlias = Literal[
    "matched",
    "mismatched",
    "unmodelled",
    "pending-validator",
    "deferred-to-phase-1",
]

_DEVIATION_STATUSES: Final[frozenset[str]] = frozenset({"mismatched", "unmodelled"})

#: Statuses in report order — green, then the two skips, then the two deviations.
STATUS_ORDER: Final[tuple[OutcomeStatus, ...]] = (
    "matched",
    "pending-validator",
    "deferred-to-phase-1",
    "unmodelled",
    "mismatched",
)


@dataclass(frozen=True)
class ProjectionRule:
    """One rule for reading a single property's obligation out of a mixed fixture.

    PD-006 R3.2 scopes criterion 2 for mixed fixtures to "the wedge-derivable projection of
    the expected envelope … with each projection rule logged in the fidelity matrix", and
    leaves the rules themselves to this card. Carrying them as data — id, statement,
    citation — is what lets ``python tools/golden_harness.py`` verify that the file and the
    code name the same set.

    Attributes:
        id: The ``PR-n`` id the fidelity matrix and the harness both use.
        kind: The obligation kind this rule produces.
        statement: What the rule does, in one sentence.
        citation: The spec or ruling that licenses it.
    """

    id: str
    kind: ObligationKind
    statement: str
    citation: str


#: The four projection rules, keyed by id. ``report`` obligations need no rule: a
#: single-property fixture's ``expected:`` block *is* that property's report (§0.3).
PROJECTION_RULES: Final[tuple[ProjectionRule, ...]] = (
    ProjectionRule(
        id="PR-1",
        kind="primary-projection",
        statement=(
            "The owning property's obligation is the expected block with `co_failures` "
            "restricted to entries the owning property holds and `advisories` dropped; "
            "where the source list is *merged* — it carries a record another property "
            "holds — the restricted co-failures are compared as a multiset, everything "
            "else in the report exactly."
        ),
        citation=(
            "Co-failures: PROPERTY-CATALOG-SPEC §0.3 makes `co_failures` same-property "
            "carriage, and `emit_co_failure`'s ownership check refuses a name another "
            "property holds. Advisories: §0.3's scope boundary hands the run-level wrapper "
            "to REPORT-FORMAT-SPEC, so cross-property carriage is assembled above a single "
            "validator, which has no other property's findings in hand — §0.3 licenses an "
            "advisory *on* a report, and `_check_advisory_carriage` refuses only the "
            "self-referential kind, so neither says a lone validator emits one. Dropping "
            "them here is PD-006 R3.2's wedge-derivable-projection latitude, logged. "
            "The merged-list clause is REPORT-FORMAT-SPEC §3.3: above one property "
            "'order carries no meaning' and records are identified by "
            "`(property, property_condition, location)`, never by position — so the order "
            "a restriction inherits from a merged list states nothing, and comparing it "
            "positionally would test a normative order against a non-normative one. The "
            "produced side's own §P-nn order stays exactly compared everywhere else, and "
            "on every non-merged block."
        ),
    ),
    ProjectionRule(
        id="PR-2",
        kind="cross-property-co-failure",
        statement=(
            "A wedge property named in another property's `co_failures` gets its own "
            "obligation, compared as the multiset of (condition ID, location) against that "
            "property's own report records; an expected entry the fixture itself marks "
            "`subsumed_by` is excluded, on that fixture's own recorded reading."
        ),
        citation=(
            "PROPERTY-CATALOG-SPEC §0.3: cross-property carriage is run-level, so only the "
            "records are comparable. The exclusion is read off the fixture, not asserted as "
            "a general rule about `subsumed_by`: DEC-05 D2 is scoped to P-01/P-04, and "
            "`mixed/04`'s own note states the consequence for that record — 'the unreachable "
            "reader generates no P-04 obligation'. §0.3 also puts `subsumed_by` on a primary "
            "`Failure`, so a validator that emits such a record is not thereby wrong; it "
            "lands as a fidelity-matrix entry, which is where that question belongs."
        ),
    ),
    ProjectionRule(
        id="PR-3",
        kind="cross-property-advisory",
        statement=(
            "A wedge property riding another property's report as `advisories` gets the "
            "same multiset obligation as PR-2, with both sides' locations reduced to their "
            "§0.3 anchor first."
        ),
        citation=(
            "PROPERTY-CATALOG-SPEC §0.3: advisories are cross-property WARNING-class side "
            "findings (the `mixed/03` precedent); the property's own report packages the "
            "same findings as failure + co_failures, so only the records are comparable. "
            "The anchor reduction is REPORT-FORMAT-SPEC §3.2 rule 3: a finding projected "
            "onto another property's report keeps its anchor and drops the concrete "
            "subtype's evidence members, which is what an advisory record *is*. The "
            "fixture side is already in that form, the produced side is the property's own "
            "full record, and `gebra.verify.anchor_location` is the rule as a function — "
            "applied to both sides, and idempotent on an anchor."
        ),
    ),
    ProjectionRule(
        id="PR-4",
        kind="multi-property-witness",
        statement=(
            "A passing mixed fixture's `kind: multi-property` witness projects each entry of "
            "`properties` to `PropertyReport(property=<slug>, result='pass', witness=<entry>)`."
        ),
        citation=(
            "PROPERTY-CATALOG-SPEC §0.3 scope boundary — the multi-property wrapper is "
            "REPORT-FORMAT-SPEC's run-level shape, and each entry under it is the §P-nn.3 "
            "witness of one property; PD-006 R3.2 names `mixed/10`'s wedge witness entries "
            "as an assertion obligation."
        ),
    ),
)

_RULES_BY_ID: Final[Mapping[str, ProjectionRule]] = {rule.id: rule for rule in PROJECTION_RULES}


def projection_rule(rule_id: str) -> ProjectionRule:
    """The :class:`ProjectionRule` with ``rule_id``.

    Raises:
        KeyError: if no rule carries that id — the fidelity matrix and this table name one
            set, and ``tools/golden_harness.py --check`` is what keeps them equal.
    """
    return _RULES_BY_ID[rule_id]


#: The ``kind`` a run-level multi-property witness carries (``mixed/10``).
_MULTI_PROPERTY: Final = "multi-property"

_NON_WEDGE: Final[frozenset[str]] = frozenset(NON_WEDGE_SLUGS)


@dataclass(frozen=True)
class Obligation:
    """One property's share of one fixture — the unit a harness run reports on.

    Attributes:
        fixture_id: ``"<directory>/<filename>"``, as :attr:`PropertyFixture.fixture_id`.
        property_slug: The single catalog slug this obligation is about. Spelled the long
            way — the envelope's own field is ``property``, but a dataclass member of that
            name shadows the builtin the two computed members below are declared with.
        kind: What is being compared (see :data:`ObligationKind`).
        rule: The :class:`ProjectionRule` id, or ``None`` for a whole-report obligation.
    """

    fixture_id: str
    property_slug: PropertySlug
    kind: ObligationKind
    rule: str | None = None

    @property
    def id(self) -> str:
        """``"<directory>/<stem>::<property>"`` — the harness id, and the pytest item id.

        The suffix is dropped because every fixture carries the same one and it buys nothing
        in a test id; the property is always spelled, including on single-property fixtures
        where it repeats the directory, so that ``-k`` selects the same way everywhere and a
        mixed fixture's items sort beside their siblings.
        """
        directory, _, name = self.fixture_id.partition("/")
        stem = name.removesuffix(FIXTURE_SUFFIX)
        return f"{directory}/{stem}::{self.property_slug}"

    @property
    def wedge(self) -> bool:
        """Whether this obligation's property is one of the Phase-0 wedge five (SOW §1)."""
        return self.property_slug not in _NON_WEDGE


@dataclass(frozen=True)
class Outcome:
    """What running one :class:`Obligation` produced.

    Attributes:
        obligation: The obligation this answers.
        status: The verdict (see :data:`OutcomeStatus`).
        detail: One sentence a person reads — the skip reason, or what disagreed. Never
            parsed; branch on :attr:`status`.
    """

    obligation: Obligation
    status: OutcomeStatus
    detail: str

    @property
    def is_deviation(self) -> bool:
        """Whether this outcome needs a ``FIDELITY-MATRIX.md`` entry (WA-04)."""
        return self.status in _DEVIATION_STATUSES


@dataclass(frozen=True)
class CorpusRun:
    """Every outcome of one corpus run, with the counts PD-006 R3.3 asks be surfaced."""

    outcomes: tuple[Outcome, ...]

    @property
    def deviations(self) -> tuple[Outcome, ...]:
        """The outcomes that must appear in the fidelity matrix, in run order."""
        return tuple(outcome for outcome in self.outcomes if outcome.is_deviation)

    @property
    def counts(self) -> Mapping[OutcomeStatus, int]:
        """How many obligations landed in each status, in :data:`STATUS_ORDER` order."""
        tally = dict.fromkeys(STATUS_ORDER, 0)
        for outcome in self.outcomes:
            tally[outcome.status] += 1
        return tally

    @property
    def fixture_ids(self) -> tuple[str, ...]:
        """Every fixture that contributed an obligation, in run order, without repeats."""
        return tuple(dict.fromkeys(outcome.obligation.fixture_id for outcome in self.outcomes))

    def for_fixture(self, fixture_id: str) -> tuple[Outcome, ...]:
        """This run's outcomes for one fixture."""
        return tuple(
            outcome for outcome in self.outcomes if outcome.obligation.fixture_id == fixture_id
        )


# ── Planning: fixture → obligations ──────────────────────────────────────────────────────


def plan_fixture(fixture: PropertyFixture) -> tuple[Obligation, ...]:
    """The obligations ``fixture`` carries, one per property, in declared order.

    A single-property fixture carries exactly one whole-report obligation. A ``mixed/``
    fixture is decomposed by the :data:`PROJECTION_RULES`: the owning property's restricted
    report (PR-1), one obligation per further property named in ``co_failures`` (PR-2) or
    ``advisories`` (PR-3), or — for a passing cross-property fixture — one per entry of the
    run-level ``multi-property`` witness (PR-4).

    A mixed fixture whose owning property cannot be derived and which carries no
    multi-property witness falls back to one whole-report obligation per declared property.
    That case is ``mixed/07``, whose primary condition is one §0.4 deliberately holds back
    (DEC-05 D6) — both its properties are non-wedge, so both obligations are deferrals; a
    future fixture in that shape naming a wedge property would surface as ``unmodelled``
    rather than disappear.
    """
    if not fixture.is_mixed:
        return (Obligation(fixture.fixture_id, fixture.properties[0], "report"),)
    witness = fixture.expected_witness
    if witness is not None and witness.get("kind") == _MULTI_PROPERTY:
        return _plan_multi_property(fixture)
    try:
        owner = fixture.owning_property
    except FixtureError:
        return tuple(Obligation(fixture.fixture_id, slug, "report") for slug in fixture.properties)
    return _plan_failing_mixed(fixture, owner)


def _plan_multi_property(fixture: PropertyFixture) -> tuple[Obligation, ...]:
    """PR-4 — one obligation per *declared* property of a ``multi-property`` witness.

    The declared ``property:`` list is iterated rather than the witness map, because the
    declaration is the fixture's contract: a property declared but missing from the map then
    yields an obligation that reports itself ``unmodelled`` instead of vanishing from the
    run. On ``mixed/10`` the two are the same eight slugs.
    """
    return tuple(
        Obligation(fixture.fixture_id, slug, "multi-property-witness", "PR-4")
        for slug in fixture.properties
    )


def _plan_failing_mixed(fixture: PropertyFixture, owner: PropertySlug) -> tuple[Obligation, ...]:
    """PR-1/PR-2/PR-3 — the owner's restricted report, then each further property once."""
    obligations = [Obligation(fixture.fixture_id, owner, "primary-projection", "PR-1")]
    failure = fixture.expected_failure or {}
    for key, kind, rule in (
        ("co_failures", "cross-property-co-failure", "PR-2"),
        ("advisories", "cross-property-advisory", "PR-3"),
    ):
        seen: set[str] = set()
        for record in _records(failure.get(key)):
            slug = record.get("property")
            if not isinstance(slug, str) or slug == owner or slug in seen:
                continue
            if slug not in fixture.properties:  # pragma: no cover - the corpus declares them
                continue
            seen.add(slug)
            obligations.append(
                Obligation(fixture.fixture_id, _slug(slug), kind, rule)  # type: ignore[arg-type]
            )
    return tuple(obligations)


def plan_corpus(root: str | os.PathLike[str]) -> tuple[Obligation, ...]:
    """Every obligation under ``root``, in :func:`iter_fixture_paths` order.

    Raises:
        FixtureError: on the first fixture that cannot be loaded — the corpus lint is what
            reports every fault at once.
    """
    return tuple(
        obligation
        for path in iter_fixture_paths(root)
        for obligation in plan_fixture(load_fixture(path))
    )


# ── Expected values: obligation → what the validator must reproduce ──────────────────────

#: A whole-report obligation compares one model; a PR-2/PR-3 obligation compares the multiset
#: of ``(condition ID, location)`` pairs, because advisory and co-failure carriage drops the
#: packaging (``remediation``, witness/failure nesting) a property's own report would carry.
_Records: TypeAlias = tuple[tuple[str, AnyLocation], ...]
Expected: TypeAlias = "PropertyReport | _Records"


def expected_for(fixture: PropertyFixture, obligation: Obligation) -> Expected:
    """The value ``obligation`` says a validator must reproduce, as models.

    Raises:
        FixtureError: if the fixture's ``expected:`` block cannot be carried into the §0.3
            envelope for this obligation. That is a corpus-side fact, not a defect in either
            side by itself — :func:`run_obligation` reports it as ``unmodelled`` and the
            fidelity matrix records what to do about it.
    """
    if obligation.kind == "report":
        return fixture.expected_report()
    if obligation.kind == "primary-projection":
        return _primary_projection(fixture, obligation.property_slug)
    if obligation.kind == "multi-property-witness":
        return _witness_projection(fixture, obligation.property_slug)
    return _record_projection(fixture, obligation)


def _primary_projection(fixture: PropertyFixture, owner: PropertySlug) -> PropertyReport:
    """PR-1 — the expected block with every record another property owns removed.

    The restriction runs on the parsed document rather than on a composed report, so a
    fixture whose *cross-property* record has no §0.3 shape yet still yields a modelled
    obligation for its own wedge property (``mixed/01``, whose P-07 co-failure is what
    stops the whole block composing).
    """
    expected = dict(fixture.expected)
    failure = expected.get("failure")
    if isinstance(failure, dict):
        restricted = dict(failure)
        kept = [
            record
            for record in _records(restricted.get("co_failures"))
            if record.get("property") == owner
        ]
        if kept:
            restricted["co_failures"] = kept
        else:
            restricted.pop("co_failures", None)
        restricted.pop("advisories", None)
        expected["failure"] = restricted
    return _validate(fixture, owner, expected, "the PR-1 projection")


def _witness_projection(fixture: PropertyFixture, slug: PropertySlug) -> PropertyReport:
    """PR-4 — one entry of a run-level ``multi-property`` witness, as that property's report."""
    witness = fixture.expected_witness or {}
    entries = witness.get("properties")
    entry = entries.get(slug) if isinstance(entries, dict) else None
    return _validate(fixture, slug, {"result": "pass", "witness": entry}, "the PR-4 projection")


def _record_projection(fixture: PropertyFixture, obligation: Obligation) -> _Records:
    """PR-2/PR-3 — the (condition ID, location) pairs one property contributes to a report.

    Entries carrying ``subsumed_by`` are dropped: DEC-05 D2 makes a subsumed record "not an
    independent finding", and the ``mixed/04`` note spells out the consequence — P-04
    generates no obligation for a reader the P-01 finding already owns, so P-04's own report
    on that IR must not carry the record either.
    """
    failure = fixture.expected_failure or {}
    key = "co_failures" if obligation.kind == "cross-property-co-failure" else "advisories"
    pairs: list[tuple[str, AnyLocation]] = []
    for record in _records(failure.get(key)):
        if (
            record.get("property") != obligation.property_slug
            or record.get("subsumed_by") is not None
        ):
            continue
        condition = record.get("property_condition")
        if not isinstance(condition, str):  # pragma: no cover - schema requires it
            raise _unmodelled(fixture, obligation.property_slug, "a record names no condition ID")
        try:
            pairs.append((condition, validate_location(record.get("location"))))
        except (ValidationError, TypeError, ValueError) as exc:
            raise _unmodelled(
                fixture,
                obligation.property_slug,
                f"the {condition!r} record's location has no §0.3 shape: {_first(exc)}",
            ) from exc
    return tuple(pairs)


def _validate(
    fixture: PropertyFixture, slug: PropertySlug, expected: Mapping[str, Any], what: str
) -> PropertyReport:
    try:
        return validate_report({"property": slug, **expected})
    except (ValidationError, TypeError, ValueError) as exc:
        raise _unmodelled(
            fixture, slug, f"{what} does not satisfy the §0.3 envelope: {_first(exc)}"
        ) from exc


# ── Running: obligation → outcome ────────────────────────────────────────────────────────


def run_obligation(fixture: PropertyFixture, obligation: Obligation) -> Outcome:
    """Run one obligation and classify it.

    The order of the questions is the ruling's own. **Scope first**: SOW §8 puts the eight
    non-wedge properties outside Phase 0, so a non-wedge obligation is deferred whatever
    shape its expected value has — checking the shape first would report a provisional
    non-wedge witness as a corpus deviation, which it is not (``schema.yaml`` calls those
    shapes provisional by design). **Then modelling**, because whether the corpus states an
    obligation in the frozen envelope is a fact about the corpus that does not wait on a
    validator. **Then wiring**, and only then the comparison.
    """
    if not obligation.wedge:
        entry = property_entry(obligation.property_slug)
        return Outcome(
            obligation,
            "deferred-to-phase-1",
            f"{entry.property_id} {entry.slug} is outside the Phase-0 wedge (SOW §8); no "
            f"validator exists in this release and none is claimed. Its contract is "
            f"{entry.spec_ref}.",
        )
    try:
        expected = expected_for(fixture, obligation)
    except FixtureError as exc:
        return Outcome(obligation, "unmodelled", str(exc))
    validator = validator_for(obligation.property_slug)
    if validator is None:
        entry = property_entry(obligation.property_slug)
        return Outcome(
            obligation,
            "pending-validator",
            f"{entry.property_id} {entry.slug} is one of the Phase-0 wedge five, but no "
            f"validator is registered in this build; its card has not landed. The expected "
            f"value is modelled and this obligation is live the moment one registers.",
        )
    return _compare(fixture, obligation, expected, validator)


def _compare(
    fixture: PropertyFixture,
    obligation: Obligation,
    expected: Expected,
    validator: Validator,
) -> Outcome:
    """Run the validator and compare, by the rule the obligation's kind fixes."""
    produced = validator(_snapshot(fixture))
    if isinstance(expected, PropertyReport):
        if obligation.kind == "primary-projection" and _merged_source(fixture):
            if _equivalent_modulo_co_failures(produced, expected):
                return Outcome(
                    obligation,
                    "matched",
                    "model equality (PROPERTY-CATALOG-SPEC §0.3), with the co-failures "
                    "restricted out of a merged cross-property list compared as a multiset "
                    "(PR-1; REPORT-FORMAT-SPEC §3.3)",
                )
            return Outcome(obligation, "mismatched", _report_diff(expected, produced))
        if models_equivalent(produced, expected):
            return Outcome(obligation, "matched", "model equality (PROPERTY-CATALOG-SPEC §0.3)")
        return Outcome(obligation, "mismatched", _report_diff(expected, produced))
    actual = _emitted_records(produced, obligation.property_slug)
    if obligation.kind == "cross-property-advisory":
        carried = _unanchored(expected)
        if carried:
            return Outcome(
                obligation,
                "mismatched",
                f"the fixture's advisory record(s) carry a concrete location subtype "
                f"({', '.join(carried)}) where REPORT-FORMAT-SPEC §3.2 rule 3 puts the §0.3 "
                f"anchor. `Advisory.location` accepts either shape for loading, so this is a "
                f"fixture-side question and a matrix row, never something PR-3 absorbs by "
                f"reducing it away",
            )
        expected, actual = _anchored(expected), _anchored(actual)
    if _multiset_equal(expected, actual):
        return Outcome(
            obligation,
            "matched",
            f"{len(expected)} (condition ID, location) record(s) equal as a multiset",
        )
    return Outcome(obligation, "mismatched", _records_diff(expected, actual))


def run_fixture(fixture: PropertyFixture) -> tuple[Outcome, ...]:
    """Plan ``fixture`` and run every obligation it carries."""
    return tuple(run_obligation(fixture, obligation) for obligation in plan_fixture(fixture))


def run_corpus(root: str | os.PathLike[str]) -> CorpusRun:
    """Run every fixture under ``root``, in :func:`iter_fixture_paths` order.

    Raises:
        FixtureError: on the first fixture that cannot be *loaded*. A fixture that loads but
            whose expected value has no §0.3 shape is an ``unmodelled`` outcome, not an
            exception — the harness reports the corpus, it does not refuse it.
    """
    return CorpusRun(
        tuple(
            outcome
            for path in iter_fixture_paths(root)
            for outcome in run_fixture(load_fixture(path))
        )
    )


# ── Helpers ──────────────────────────────────────────────────────────────────────────────


def _snapshot(fixture: PropertyFixture) -> WorkflowIR:
    """The IR a wedge validator reads for this fixture.

    Single-snapshot fixtures carry ``ir``. For an evolution pair the wedge records the
    corpus carries are scoped ``snapshot: ir_after`` (§4.6; kept as P-12's pair-scoping
    convention by DEC-17's Q-03 ruling), so ``ir_after`` is the snapshot a wedge obligation
    on a pair fixture reads.
    """
    snapshot = fixture.ir if fixture.ir is not None else fixture.ir_after
    if snapshot is None:  # pragma: no cover - the loader admits only the two IR shapes
        raise FixtureError(
            f"{fixture.fixture_id}: carries no IR snapshot to validate",
            reason=FixtureErrorReason.IR_SHAPE,
            path=fixture.path,
        )
    return snapshot


def _merged_source(fixture: PropertyFixture) -> bool:
    """Does this fixture's ``expected.co_failures`` list carry more than one property?

    A *merged* list is a run-level composition — no single validator produces it, because
    §0.3 makes ``co_failures`` same-property carriage and ``emit_co_failure``'s ownership
    check refuses a name another property holds. REPORT-FORMAT-SPEC §3.3 fixes what its
    order means: above one property, "order carries no meaning". So the order a PR-1
    restriction inherits from such a list is not an assertion, and PR-1 compares the
    restricted records as a multiset. Exactly two corpus fixtures carry one — ``mixed/04``
    and ``mixed/05`` — and the check is on the *raw* document, so it reports the block as
    authored rather than as projected.

    **Deliberately not narrowed to an *interleaved* merge**, though ``mixed/04`` is one (its
    P-04 record sits between the two P-01 records, which is what makes the induced order most
    obviously an artifact). §3.3 admits no such exception: it says order above one property
    carries no meaning, not that it recovers meaning when the owner's records happen to be
    contiguous — and a rule turning on authoring layout would be this module drawing a
    distinction the spec does not. Raised at the TE-04 pre-review and declined on that ground;
    if a fixture ever makes the difference observable, that is a matrix row.
    """
    failure = fixture.expected_failure or {}
    owners = {
        record.get("property")
        for record in _records(failure.get("co_failures"))
        if isinstance(record.get("property"), str)
    }
    return len(owners) > 1


def _equivalent_modulo_co_failures(produced: PropertyReport, expected: PropertyReport) -> bool:
    """Model equality on everything but ``failure.co_failures``, which is a multiset.

    Everything the report states — result, witness, the primary failure and every one of its
    fields, each co-failure record in full — is compared exactly by
    :func:`~gebra.verify.models_equivalent`; only the *position* of a co-failure within the
    restricted list is not. This is not
    :class:`~gebra.verify.SetCompared` on the field: that mark is a spec statement, and the
    per-property sections do fix an order for a property's own report (§1.4 Step 5 for
    P-01). It is the narrower fact that the list this projection restricts was never one
    property's own list to begin with.
    """
    if not models_equivalent(_without_co_failures(produced), _without_co_failures(expected)):
        return False
    return _co_failures_equal(_co_failures(produced), _co_failures(expected))


def _without_co_failures(report: PropertyReport) -> PropertyReport:
    """``report`` with ``failure.co_failures`` cleared — the exactly-compared remainder."""
    failure = report.failure
    if failure is None or failure.co_failures is None:
        return report
    return report.model_copy(update={"failure": failure.model_copy(update={"co_failures": None})})


def _co_failures(report: PropertyReport) -> tuple[CoFailure, ...]:
    """The co-failure records ``report`` carries, if any."""
    failure = report.failure
    return () if failure is None or failure.co_failures is None else failure.co_failures


def _co_failures_equal(left: Sequence[CoFailure], right: Sequence[CoFailure]) -> bool:
    """The same co-failure records in any order, each compared as a whole model."""
    if len(left) != len(right):
        return False
    unmatched = list(right)
    for record in left:
        for index, other in enumerate(unmatched):
            if models_equivalent(record, other):
                del unmatched[index]
                break
        else:
            return False
    return True


def _anchored(records: _Records) -> _Records:
    """Every record's location reduced to its §0.3 anchor — REPORT-FORMAT-SPEC §3.2 rule 3."""
    return tuple((condition, anchor_location(location)) for condition, location in records)


def _unanchored(records: _Records) -> tuple[str, ...]:
    """The type names of any record whose location is *not* already its §0.3 anchor.

    The rule-3 reduction is applied to both sides of a `PR-3` obligation, and on the fixture
    side that is meant to be the identity: §3.2 rule 3 says an advisory carries the anchor,
    and every advisory in this corpus does. But `Advisory.location` accepts either shape for
    *loading* (rule 3's own parenthetical — PC-6's fixture duty), so a future fixture could
    state a concrete subtype, and reducing it away would silently absorb exactly the
    disagreement the matrix says is owed a row. This is what turns that into a mismatch
    instead.
    """
    return tuple(
        type(location).__name__
        for _, location in records
        if not models_equivalent(anchor_location(location), location)
    )


def _emitted_records(report: PropertyReport, slug: PropertySlug) -> _Records:
    """The (condition ID, location) pairs ``report`` states for its own property."""
    failure = report.failure
    if failure is None:
        return ()
    pairs = [(failure.property_condition, failure.location)]
    pairs.extend(
        (record.property_condition, record.location)
        for record in failure.co_failures or ()
        if record.property == slug
    )
    return tuple(pairs)


def _multiset_equal(left: _Records, right: _Records) -> bool:
    """The two record collections hold the same pairs, in any order.

    Order is not compared because the two sides package the same findings differently — an
    advisory list and a failure + ``co_failures`` chain have different ordering rules — and
    §0.3's per-section ordering rules bind a property's *own* report, which the whole-report
    obligations compare exactly.
    """
    if len(left) != len(right):
        return False
    unmatched = list(right)
    for condition, location in left:
        for index, (other_condition, other_location) in enumerate(unmatched):
            if condition == other_condition and models_equivalent(location, other_location):
                del unmatched[index]
                break
        else:
            return False
    return True


def _report_diff(expected: PropertyReport, produced: PropertyReport) -> str:
    """One sentence naming the first field on which two reports part company."""
    if expected.result != produced.result:
        return f"expected result {expected.result!r}, the validator returned {produced.result!r}"
    for name in ("witness", "failure"):
        mine, theirs = getattr(expected, name), getattr(produced, name)
        if not models_equivalent(mine, theirs):
            return f"the {name} differs: fixture {_render(mine)} vs validator {_render(theirs)}"
    return "the reports differ"  # pragma: no cover - result/witness/failure are the fields


def _records_diff(expected: _Records, actual: _Records) -> str:
    """One sentence naming which (condition ID, location) records are unmatched."""
    missing = tuple(pair for pair in expected if not _pick(actual, pair))
    extra = tuple(pair for pair in actual if not _pick(expected, pair))
    parts = []
    if missing:
        parts.append(f"the fixture states {_render_records(missing)}, which the validator does not")
    if extra:
        parts.append(f"the validator states {_render_records(extra)}, which the fixture does not")
    return "; ".join(parts) or "the record sets differ"


def _pick(records: _Records, pair: tuple[str, AnyLocation]) -> _Records:
    """``records`` narrowed to the ones matching ``pair`` — the multiset membership test."""
    return tuple(
        other for other in records if other[0] == pair[0] and models_equivalent(other[1], pair[1])
    )


def _render_records(records: _Records) -> str:
    return ", ".join(f"{condition} at {to_data(location)}" for condition, location in records)


def _render(value: object) -> str:
    """A witness or failure as its PC-4 data, or ``None`` as itself."""
    return str(to_data(value)) if isinstance(value, ReportModel) else repr(value)


def _records(value: object) -> Sequence[Mapping[str, Any]]:
    """A repeated ``expected:`` member as a sequence of mappings, tolerant of absence."""
    if not isinstance(value, (list, tuple)):
        return ()
    return [item for item in value if isinstance(item, Mapping)]


def _slug(value: str) -> PropertySlug:
    """Narrow a corpus-supplied string to a catalog slug, refusing anything else."""
    property_entry(value)
    return value  # type: ignore[return-value]


def _unmodelled(fixture: PropertyFixture, slug: PropertySlug, complaint: str) -> FixtureError:
    return FixtureError(
        f"{fixture.fixture_id} [{slug}]: {complaint}",
        reason=FixtureErrorReason.EXPECTED_INVALID,
        path=fixture.path,
        key="expected",
    )


def _first(exc: Exception) -> str:
    """A validation failure rendered as the *closest* candidate shape's complaint.

    The envelope's locations and failures are unions of strict models, so one bad key
    produces an error per member — dozens of lines in which the actual fault is one line.
    Reporting the first is close to useless here: it is whichever member the union happens
    to try first. The member with the **fewest** complaints is the shape the value nearly
    satisfies, and its complaints are the ones a reader (or a fidelity-matrix entry) wants:
    for ``mixed/05`` that is ``P02SccLocation: snapshot`` — the one extra key — rather than
    seven missing fields of an edge location it was never trying to be.
    """
    if not isinstance(exc, ValidationError):
        return str(exc)
    errors = exc.errors()
    if not errors:  # pragma: no cover - pydantic always reports at least one
        return str(exc)
    candidates: dict[str, list[str]] = {}
    for error in errors:
        parts = [str(part) for part in error["loc"]]
        tag = parts[0] if len(parts) > 1 else ""
        rest = ".".join(parts[1:] if len(parts) > 1 else parts) or "(root)"
        candidates.setdefault(tag, []).append(f"{rest}: {error['msg']}")
    tag, complaints = min(candidates.items(), key=lambda item: len(item[1]))
    rendered = f"{tag}: {'; '.join(complaints[:_MAX_COMPLAINTS])}" if tag else complaints[0]
    if len(candidates) > 1:
        rendered += f" (closest of {len(candidates)} candidate shapes)"
    return rendered


#: How many of the closest candidate's complaints a rendered message carries.
_MAX_COMPLAINTS: Final = 3
