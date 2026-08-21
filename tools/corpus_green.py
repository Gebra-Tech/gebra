"""Corpus-green gate — SOW §2 criterion 2, as four clauses a run can answer.

**What "corpus green" means is not this tool's to choose.** PD-006 R3 — the SD-D1 ruling,
owner-signed into ``docs/plan/PHASE-0-DOD-CHECKLIST.md`` C2 in the supplementary repo —
fixes it as a *two-layer* definition with four clauses, and this gate is those four clauses
executed together:

``R3.1`` (load layer)
    All 60 fixtures load hermetically, lint green against schema v2.2, their IR payloads
    ``model_validate``, **and their `expected:` blocks compose into envelope models**.
``R3.2`` (assertion layer)
    Every wedge assertion obligation is green by structural model equality — the 30 wedge
    single-property fixtures in full, and for mixed fixtures the wedge-derivable projections
    R3.2 enumerates: wedge primaries, wedge same-property co-failures, wedge cross-property
    advisories, and ``mixed/10``'s wedge witness entries.
``R3.3`` (skip layer)
    Every non-wedge component is an explicit structured skip naming the property and citing
    SOW §8 — counted and surfaced, never rendered as a pass.
``R3.4`` (run layer)
    A run-level report lists all thirteen properties, the eight non-wedge slugs carrying
    structured not-implemented markers.

Three of the four already had a gate: ``tools/corpus_lint.py`` owns most of R3.1,
``tools/golden_harness.py`` owns R3.2 and R3.3 obligation by obligation, and R3.4 is
``verify()``'s. What none of them states is criterion 2 **as one thing**, which is what an
acceptance evidence slot needs and what this command prints.

**The two places the definition and the corpus do not meet, and how this gate treats them.**

*R3.1's compose clause.* 33 of the 60 blocks compose; the other 27 are shapes the frozen
specs deliberately do not model — the non-wedge properties' witness and location shapes that
``schema.yaml`` marks provisional, the P-03 condition IDs §0.4 holds back, and ``mixed/10``'s
run-level wrapper, which REPORT-FORMAT-SPEC §3.4 says is not a §0.3 shape at all. Composing
them would mean inventing the contract PD-016 declined to invent (WA-03). So this gate does
not assert the clause literally; it asserts the checkable half: **every non-composing block
is attributed to a named non-wedge cause, derived and verified rather than labelled, and a
block that does not compose with no such cause is a violation.**

**That is now the clause, not a reading of it.** PD-039 Q1 was ratified 2026-08-08 and the
owner re-signed C2's clause (1) around it: a block composes *or* a named, machine-verified
non-wedge cause accounts for it, and the four causes are a **closed set** — admitting a fifth
is a PD event, never a code edit (:data:`COMPOSE_CAUSES`). What that makes impossible is a
fixture quietly joining the 27, in either direction: not by failing to compose unexplained,
and not by explaining itself with a cause nobody ratified.

The 27 are folded into the met clause as accounted findings, not residue — the
reclassification PD-039 bundled with the M13 execution (DEC-24, 2026-08-08), which is also
when ``mixed/08``'s one missing optional diagnostic landed via its R-05 revision and the CI
job took ``--strict``. Under the re-signed C2 clause (1), accounted-by-a-ratified-cause IS
the met state; ``--strict`` remains the harder line — it fails on any *residue*, and residue
is now reserved for R3.2 shortfalls awaiting an owner action. There are none today.

*R3.2 shortfalls.* An R3.2-scoped obligation that is not ``matched`` is residue **only if it
is routed** — read off ``docs/governance/FIDELITY-MATRIX.md`` §3, never assumed: no open row
there means **violation**, because the sentence this gate would otherwise print about it
would be false. Holding the file to the run in the other direction — an open row that no
longer reproduces — stays ``tools/golden_harness.py``'s job.

**Exit codes.** ``0`` when nothing is unaccounted — every violation is empty and every
shortfall carries its named cause or its routed matrix row. ``1`` when something is
unaccounted, and ``1`` under ``--strict`` if any residue remains at all, which is the literal
R3.1/R3.2 reading. ``2`` when no verdict was reached at all: an unreadable corpus, a fixture
that will not load, a missing decision log — none of which is "criterion 2 failed". The
verdict line says which of the first two it is; it never says criterion 2 is met when it is
not.

WA-07: nothing here executes a workflow node, calls a model, or opens a network connection.
It loads YAML, validates models, and calls hermetic validator functions over validated IR.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

from gebra.testing.fixtures import (
    SCHEMA_FILENAME,
    FixtureError,
    PropertyFixture,
    iter_fixture_paths,
    load_fixture,
)
from gebra.testing.harness import (
    CorpusRun,
    ObligationKind,
    expected_for,
    plan_fixture,
    run_corpus,
)
from gebra.verify import (
    NON_WEDGE_SLUGS,
    PROPERTY_REGISTRY,
    NotImplementedMarker,
    PropertySlug,
    is_registered,
    verify,
)

if __package__ in (None, ""):  # pragma: no cover - `python tools/corpus_green.py`
    # The only tool here that reuses another one. Run as a script, `sys.path[0]` is `tools/`
    # rather than the repository root, so the sibling is unreachable by the same import the
    # test suite and `python -m tools.corpus_green` use. Putting the root on the path is what
    # keeps those three spellings one module rather than two copies of the lint.
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.corpus_lint import CorpusLintError, CorpusReport
from tools.corpus_lint import check as lint_corpus
from tools.golden_harness import Matrix, MatrixError, open_obligations, parse_matrix

__all__ = [
    "COMPOSE_CAUSES",
    "R32_KINDS",
    "Attribution",
    "ClauseResult",
    "GreenReport",
    "attribute",
    "check",
    "format_report",
    "main",
]


#: The obligation kinds PD-006 R3.2 enumerates. ``cross-property-co-failure`` is deliberately
#: absent: R3.2 names wedge primaries, wedge *same-property* co-failures (which ride inside a
#: ``primary-projection``), wedge cross-property **advisories**, and ``mixed/10``'s witness
#: entries. The harness compares cross-property co-failures too — more than criterion 2 asks
#: for — so this gate reports them beside the clause rather than inside it.
R32_KINDS: Final[frozenset[ObligationKind]] = frozenset(
    {"report", "primary-projection", "cross-property-advisory", "multi-property-witness"}
)

#: Why a fixture's ``expected:`` block may legitimately not compose into a §0.3 report. Each
#: is a *derived* fact about the block, not a label applied to it — :func:`attribute` checks
#: the antecedent and says what it checked. A block outside this set is a violation.
#:
#: The set is not this module's enumeration: it is PD-016's own "out of scope (deliberate,
#: with authority)" list from the corpus reconciliation pass, one cause per item — the
#: non-wedge witness and location shapes ``schema.yaml`` calls "provisional until their
#: catalog sections are drafted" (two causes, by whether the block *is* such a report or
#: merely carries one), the P-03 condition IDs PROPERTY-CATALOG-SPEC §0.4 holds back by name
#: (DEC-05 D6), and ``mixed/10``'s run-level wrapper, which §0.3's own scope boundary hands
#: to REPORT-FORMAT-SPEC (§3.4).
#:
#: **Closed, and closed by ruling rather than by convention** (PD-039 Q1, ratified 2026-08-08;
#: ``PHASE-0-DOD-CHECKLIST`` C2 clause (1), re-signed the same day). A fifth cause is a **PD
#: event, never a code edit** — which is what stops the scoped reading of R3.1 from drifting
#: into "whatever the gate currently tolerates". If a fixture ever fails to compose for a
#: reason none of these four covers, the honest outcome is the violation this gate already
#: reports; widening the set is the owner's call and lands as a new PD amending C2 again.
#: ``tests/testing/test_corpus_green.py`` asserts the tuple against that ruling, so an added
#: member fails there rather than passing quietly.
COMPOSE_CAUSES: Final[tuple[str, ...]] = (
    "non-wedge-owner",
    "non-wedge-component",
    "held-back-condition-id",
    "run-level-wrapper",
)

#: The witness ``kind`` that is a run-level wrapper rather than one property's witness.
_MULTI_PROPERTY: Final = "multi-property"

#: Where the WA-04 decision log lives. R3.2 reads its §3 to tell a *routed* shortfall from an
#: unrecorded one; ``tools/golden_harness.py`` is what holds the file to the run both ways.
DEFAULT_MATRIX: Final = (
    Path(__file__).resolve().parent.parent / "docs/governance/FIDELITY-MATRIX.md"
)


class CorpusGreenError(RuntimeError):
    """No verdict was reached: an unreadable corpus, an unloadable fixture, a missing matrix."""


@dataclass(frozen=True)
class Attribution:
    """Why one non-composing ``expected:`` block does not compose, and what was checked."""

    fixture: str
    #: A member of :data:`COMPOSE_CAUSES`, or ``None`` when nothing accounts for it.
    cause: str | None
    #: The observation that establishes the cause — the evidence, not the claim.
    evidence: str

    @property
    def accounted(self) -> bool:
        return self.cause is not None


@dataclass
class ClauseResult:
    """One PD-006 R3 clause: what it observed, what falls short, and what is unaccounted."""

    id: str
    title: str
    #: Observation lines, in report order.
    findings: list[str] = field(default_factory=list)
    #: Shortfalls that carry a named cause or a routed matrix row — reported, never a pass.
    residue: list[str] = field(default_factory=list)
    #: Shortfalls nothing accounts for. Any one of these fails the gate in every mode.
    violations: list[str] = field(default_factory=list)

    @property
    def met(self) -> bool:
        """The clause holds as PD-006 wrote it — no residue and no violation."""
        return not self.residue and not self.violations


@dataclass
class GreenReport:
    """What one gate run found, clause by clause."""

    clauses: list[ClauseResult] = field(default_factory=list)

    @property
    def violations(self) -> list[str]:
        return [item for clause in self.clauses for item in clause.violations]

    @property
    def residue(self) -> list[str]:
        return [item for clause in self.clauses for item in clause.residue]

    @property
    def accounted(self) -> bool:
        """Nothing is unaccounted — the default gate's question."""
        return not self.violations

    @property
    def met(self) -> bool:
        """Criterion 2 holds as PD-006 R3 literally wrote it — the ``--strict`` question."""
        return self.accounted and not self.residue


# ── R3.1: the load layer ─────────────────────────────────────────────────────────────────


def attribute(fixture: PropertyFixture) -> Attribution:
    """Why ``fixture``'s ``expected:`` block does not compose into a §0.3 ``PropertyReport``.

    Each cause is decided on the raw document, and the questions are asked in the order the
    §0.3 composition itself asks them, so that every answer is a *fact* rather than a guess.

    First, is there one property whose report this block could be at all?

    1. ``run-level-wrapper`` — the block's witness is ``kind: multi-property``. §0.3 composes
       one report per property; a wrapper over several is REPORT-FORMAT-SPEC §3.4's shape,
       and that section says outright that neither is derived from the other.
    2. ``held-back-condition-id`` — the owning property cannot be derived, because the block's
       primary names a condition ID absent from the §0.4 registry. This repository never
       emits an unregistered id (§0.4 holds P-03's three back by name, DEC-05 D6), so no §0.3
       report over it can exist. **Narrowed to a fixture that declares no wedge property**,
       because §0.4's registry is closed: an unregistered id on a fixture that *does* exercise
       the wedge is a misspelling or an invented name, and laundering it as an accounted cause
       would weaken the one check that would notice. `mixed/07` — the only fixture that takes
       this branch — declares `[signature-soundness, parallel-safety]`, both deferred.

    Then, given an owner, is the shape §0.3 refuses a non-wedge one?

    3. ``non-wedge-owner`` — the owner lies outside the Phase-0 wedge (SOW §8). Its witness
       and location shapes are the ones ``schema.yaml`` marks provisional and §0.3 does not
       model.
    4. ``non-wedge-component`` — the owner is a wedge property, and the block carries a
       record or advisory a non-wedge property holds. This is the only cause that is not true
       by inspection alone — it is a claim about what *would* happen — so it is **verified**:
       the owner's ``PR-1`` projection is composed, and the cause holds only if restricting
       the non-wedge records out is what makes the block compose.

    Returns:
        An :class:`Attribution` whose ``cause`` is ``None`` when none of the four holds —
        which is the case the gate refuses.
    """
    witness = fixture.expected_witness
    if witness is not None and witness.get("kind") == _MULTI_PROPERTY:
        return Attribution(
            fixture.fixture_id,
            "run-level-wrapper",
            "the `expected:` witness is `kind: multi-property`, a run-level wrapper over "
            "several properties — REPORT-FORMAT-SPEC §3.4, not a §0.3 report",
        )

    try:
        owner = fixture.owning_property
    except FixtureError as exc:
        unregistered = _unregistered_conditions(fixture)
        wedge_declared = sorted(set(fixture.properties) - set(NON_WEDGE_SLUGS))
        if unregistered and not wedge_declared:
            return Attribution(
                fixture.fixture_id,
                "held-back-condition-id",
                f"the block names {', '.join(repr(name) for name in unregistered)}, which "
                f"PROPERTY-CATALOG-SPEC §0.4 does not carry, so no owning property and no "
                f"§0.3 report can be derived (DEC-05 D6 holds P-03's three back); the "
                f"fixture declares only deferred properties "
                f"({', '.join(fixture.properties)}), so no wedge assertion is lost",
            )
        if unregistered:
            return Attribution(
                fixture.fixture_id,
                None,
                f"the block names {', '.join(repr(name) for name in unregistered)}, which "
                f"§0.4 does not carry — but the fixture declares the wedge propert(y/ies) "
                f"{', '.join(wedge_declared)}, so this is a misspelled or invented id rather "
                f"than a deferred one. §0.4's registry is closed",
            )
        return Attribution(fixture.fixture_id, None, f"the owning property is unresolved: {exc}")

    if owner in NON_WEDGE_SLUGS:
        return Attribution(
            fixture.fixture_id,
            "non-wedge-owner",
            f"the block is {owner!r}'s report, and SOW §8 puts that property outside the "
            f"Phase-0 wedge — §0.3 models no witness or failure shape for it",
        )

    foreign = _non_wedge_records(fixture, owner)
    if foreign and _projection_composes(fixture, owner):
        return Attribution(
            fixture.fixture_id,
            "non-wedge-component",
            f"the block is {owner!r}'s report carrying {', '.join(sorted(foreign))} "
            f"record(s); its wedge share composes once they are restricted out (PR-1), so "
            f"the shapes §0.3 does not model are exactly the non-wedge ones",
        )
    if foreign:
        return Attribution(
            fixture.fixture_id,
            None,
            f"the block carries {', '.join(sorted(foreign))} record(s), but restricting "
            f"them out does not make {owner!r}'s share compose — so a wedge shape is what "
            f"§0.3 refuses, which is a corpus question and not a non-wedge deferral",
        )
    return Attribution(
        fixture.fixture_id,
        None,
        f"the block is {owner!r}'s report, {owner!r} is inside the wedge, and nothing "
        f"non-wedge rides on it — §0.3 refuses a wedge shape",
    )


def _unregistered_conditions(fixture: PropertyFixture) -> tuple[str, ...]:
    """Every condition ID the block names that the §0.4 registry does not carry."""
    failure = fixture.expected_failure or {}
    names: list[str] = []
    for record in (
        failure,
        *_records(failure.get("co_failures")),
        *_records(failure.get("advisories")),
    ):
        condition = record.get("property_condition")
        if isinstance(condition, str) and not is_registered(condition):
            names.append(condition)
    return tuple(dict.fromkeys(names))


def _non_wedge_records(fixture: PropertyFixture, owner: PropertySlug) -> set[str]:
    """The non-wedge properties whose records ride ``owner``'s block."""
    failure = fixture.expected_failure or {}
    return {
        str(record["property"])
        for record in (*_records(failure.get("co_failures")), *_records(failure.get("advisories")))
        if isinstance(record.get("property"), str)
        and record["property"] != owner
        and record["property"] in NON_WEDGE_SLUGS
    }


def _projection_composes(fixture: PropertyFixture, owner: PropertySlug) -> bool:
    """Does ``owner``'s ``PR-1`` share of this block compose into a §0.3 report?

    Asked through the harness's public planning API rather than its projection helper, so the
    obligation this composes is the same object the golden harness would run — a change to
    how `PR-1` is planned cannot move this attribution without moving that run too.
    """
    obligation = next(
        (
            item
            for item in plan_fixture(fixture)
            if item.kind == "primary-projection" and item.property_slug == owner
        ),
        None,
    )
    if obligation is None:  # pragma: no cover - a failing mixed block always plans its primary
        return False
    try:
        expected_for(fixture, obligation)
    except FixtureError:
        return False
    return True


def _records(value: object) -> tuple[Mapping[str, Any], ...]:
    """A record list off the raw document, defensively — the schema is the lint's to enforce.

    Matches ``gebra.testing.harness._records``: the loader hands back mappings that are not
    ``dict`` (the fixture document is exposed read-only), so the membership tests are on the
    abstract types rather than the concrete ones.
    """
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(item for item in value if isinstance(item, Mapping))


def _clause_r31(lint: CorpusReport, fixtures: tuple[PropertyFixture, ...]) -> ClauseResult:
    """R3.1 — load, lint, ``model_validate``, and the composition ledger."""
    clause = ClauseResult("R3.1", "load layer — 60 fixtures load, lint, validate, compose")
    clause.findings.append(
        f"{len(fixtures)} fixture(s) loaded hermetically and their IR payload(s) "
        f"model_validate(d); corpus lint {'OK' if lint.ok else 'FAILED'} against schema v2.2 "
        f"in {lint.directories_checked} director(y/ies)"
    )
    clause.violations.extend(
        f"R3.1 corpus lint: {violation.rendered().strip()}" for violation in lint.violations
    )

    by_id = {fixture.fixture_id: fixture for fixture in fixtures}
    composing = len(lint.composing)
    attributions = [attribute(by_id[status.fixture]) for status in lint.not_composing]
    clause.findings.append(
        f"{composing}/{len(lint.envelope)} `expected:` block(s) compose into a §0.3 "
        f"PropertyReport; {len(attributions)} do not"
    )
    for cause in COMPOSE_CAUSES:
        count = sum(1 for item in attributions if item.cause == cause)
        if count:
            clause.findings.append(f"  {count:>2} attributed to {cause}")
    for item in attributions:
        if not item.accounted:
            clause.violations.append(
                f"R3.1 compose: {item.fixture} does not compose and no non-wedge cause "
                f"accounts for it — {item.evidence}"
            )
    if attributions and not clause.violations:
        clause.findings.append(
            f"R3.1's compose clause is MET as re-signed (C2 clause (1), 2026-08-08): "
            f"{composing}/{len(lint.envelope)} blocks compose and the other "
            f"{len(attributions)} each carry a machine-verified cause from the closed "
            f"PD-039 Q1 set — accounted, not residue, per the reclassification DEC-24 "
            f"bundled with the M13 execution."
        )
    return clause


# ── R3.2 and R3.3: the assertion and skip layers ─────────────────────────────────────────


def _clause_r32(run: CorpusRun, matrix: Matrix | None) -> ClauseResult:
    """R3.2 — every wedge assertion obligation green by structural model equality.

    A shortfall here is residue **only if it is routed**, and that is read off
    ``FIDELITY-MATRIX.md`` §3 rather than assumed: an R3.2-scoped obligation that is not
    ``matched`` and has no open row is a violation, because the sentence this gate would
    otherwise print about it — "a logged deviation with a route" — would be false. The
    two-way cross-check that keeps the file honest in the other direction (an open row that
    no longer reproduces) stays ``tools/golden_harness.py``'s; this reads the same table for
    the one question criterion 2 turns on.
    """
    clause = ClauseResult("R3.2", "assertion layer — wedge obligations by model equality")
    routed = frozenset[str]() if matrix is None else open_obligations(matrix)
    log = "the fidelity matrix" if matrix is None else matrix.path.name
    scoped = [
        outcome
        for outcome in run.outcomes
        if outcome.obligation.wedge and outcome.obligation.kind in R32_KINDS
    ]
    beyond = [
        outcome
        for outcome in run.outcomes
        if outcome.obligation.wedge and outcome.obligation.kind not in R32_KINDS
    ]
    matched = [outcome for outcome in scoped if outcome.status == "matched"]
    clause.findings.append(
        f"{len(matched)}/{len(scoped)} R3.2-scoped wedge obligation(s) matched by "
        f"PROPERTY-CATALOG-SPEC §0.3 model equality (structural — never string equality)"
    )
    clause.findings.append(
        f"{sum(1 for outcome in beyond if outcome.status == 'matched')}/{len(beyond)} "
        f"cross-property co-failure obligation(s) matched — compared by the harness, beyond "
        f"what R3.2's enumeration asks for"
    )
    for outcome in scoped:
        if outcome.status == "matched":
            continue
        if outcome.status == "pending-validator":
            clause.violations.append(
                f"R3.2 {outcome.obligation.id}: no validator is registered for a wedge "
                f"property — criterion 2 has nothing to assert"
            )
        elif outcome.obligation.id in routed:
            clause.residue.append(
                f"R3.2 {outcome.obligation.id}: {outcome.status} — an open row in "
                f"{log} §3 carries its route; reported and counted, never "
                f"rendered as a pass"
            )
        else:
            clause.violations.append(
                f"R3.2 {outcome.obligation.id}: {outcome.status} with no open row in "
                f"{log} §3. A shortfall is residue only when it is routed "
                f"(WA-04); an unrecorded one is what this gate refuses. Observed: "
                f"{outcome.detail}"
            )
    return clause


def _clause_r33(run: CorpusRun) -> ClauseResult:
    """R3.3 — every non-wedge component an explicit structured skip, counted and surfaced."""
    clause = ClauseResult("R3.3", "skip layer — non-wedge components structured-skipped")
    non_wedge = [outcome for outcome in run.outcomes if not outcome.obligation.wedge]
    clause.findings.append(
        f"{len(non_wedge)} non-wedge obligation(s) over "
        f"{len({outcome.obligation.property_slug for outcome in non_wedge})} propert(y/ies), "
        f"every one a structured skip naming the property and citing SOW §8"
    )
    for outcome in non_wedge:
        if outcome.status != "deferred-to-phase-1":
            clause.violations.append(
                f"R3.3 {outcome.obligation.id}: a non-wedge obligation reports "
                f"{outcome.status!r}; SOW §8 puts it outside Phase 0 and it must be a named "
                f"skip, never a pass and never a comparison"
            )
        elif (
            outcome.obligation.property_slug not in outcome.detail or "SOW §8" not in outcome.detail
        ):
            clause.violations.append(
                f"R3.3 {outcome.obligation.id}: the skip reason names neither the property "
                f"nor SOW §8 — R3.3 requires both, so a reader is never left guessing"
            )
    return clause


# ── R3.4: the run layer ──────────────────────────────────────────────────────────────────


def _clause_r34(fixtures: tuple[PropertyFixture, ...]) -> ClauseResult:
    """R3.4 — a run report lists all thirteen properties with the eight non-wedge markers."""
    clause = ClauseResult("R3.4", "run layer — thirteen outcomes, eight not-implemented markers")
    subject = next((fixture for fixture in fixtures if fixture.ir is not None), None)
    if subject is None:  # pragma: no cover - the corpus always carries single-snapshot fixtures
        clause.violations.append("R3.4: no single-snapshot fixture to run verify() over")
        return clause
    assert subject.ir is not None
    report = verify(subject.ir)
    slugs = tuple(outcome.property for outcome in report.properties)
    markers = {
        outcome.property
        for outcome in report.properties
        if isinstance(outcome, NotImplementedMarker)
    }
    clause.findings.append(
        f"gebra.verify.verify() on {subject.fixture_id} answers {len(slugs)} propert(y/ies) "
        f"in catalog order, {len(markers)} of them with structured not-implemented markers"
    )
    if slugs != tuple(PROPERTY_REGISTRY):
        clause.violations.append(
            f"R3.4: the run report lists {list(slugs)}; the catalog order is "
            f"{list(PROPERTY_REGISTRY)}"
        )
    if markers != set(NON_WEDGE_SLUGS):
        clause.violations.append(
            f"R3.4: the not-implemented markers cover {sorted(markers)}; the eight non-wedge "
            f"slugs are {sorted(NON_WEDGE_SLUGS)}"
        )
    return clause


# ── The gate ─────────────────────────────────────────────────────────────────────────────


def check(corpus: Path, schema: Path, matrix_path: Path | None = DEFAULT_MATRIX) -> GreenReport:
    """Evaluate PD-006 R3's four clauses over ``corpus``.

    ``matrix_path`` is the WA-04 decision log R3.2 reads to tell a routed shortfall from an
    unrecorded one. Passing ``None`` runs without it, and the answer is then strictly
    *stricter*, never laxer: with no log in hand nothing is routed, so every R3.2 shortfall
    is a violation. That is the mode ``tests/testing/test_hermeticity.py``'s guarded child
    uses, so that a governance document being edited can never turn a WA-07 tripwire red.

    Raises:
        CorpusGreenError: if the corpus cannot be linted, a fixture cannot be loaded, or a
            requested fidelity matrix cannot be read — each is a broken checkout, not a
            criterion-2 answer, and answering "criterion 2 failed" to any of them would be a
            lie.
    """
    try:
        lint = lint_corpus(corpus, schema)
        fixtures = tuple(load_fixture(path) for path in iter_fixture_paths(corpus))
        run = run_corpus(corpus)
        matrix = None if matrix_path is None else parse_matrix(matrix_path)
    except (CorpusLintError, FixtureError, MatrixError, OSError) as exc:
        raise CorpusGreenError(str(exc)) from exc
    return GreenReport(
        [
            _clause_r31(lint, fixtures),
            _clause_r32(run, matrix),
            _clause_r33(run),
            _clause_r34(fixtures),
        ]
    )


# ── Rendering ────────────────────────────────────────────────────────────────────────────


def format_report(report: GreenReport, *, strict: bool = False) -> str:
    """Render the four clauses, then the verdict — the C2 evidence artifact."""
    lines = ["corpus green — SOW §2 criterion 2, per PD-006 R3 (the SD-D1 ruling)", ""]
    for clause in report.clauses:
        mark = "OK  " if clause.met else ("FAIL" if clause.violations else "OPEN")
        lines.append(f"{mark}  {clause.id}  {clause.title}")
        lines.extend(f"        {finding}" for finding in clause.findings)
    if report.residue:
        lines += ["", "residue — accounted for, routed, and never rendered as a pass:"]
        lines += [f"  - {item}" for item in report.residue]
    if report.violations:
        lines += ["", "violations — nothing accounts for these:"]
        lines += [f"  - {item}" for item in report.violations]
    lines.append("")
    if report.met:
        lines.append("verdict: criterion 2 MET — every clause holds as PD-006 R3 wrote it.")
    elif report.accounted:
        lines.append(
            f"verdict: criterion 2 NOT YET MET — {len(report.residue)} accounted shortfall(s), "
            f"listed above with their route. Nothing is unaccounted, so this gate exits "
            f"{'1 under --strict' if strict else '0'}."
        )
    else:
        lines.append(
            f"verdict: criterion 2 NOT MET — {len(report.violations)} unaccounted "
            f"violation(s). A shortfall with no named cause and no routed matrix row is what "
            f"this gate exists to refuse."
        )
    return "\n".join(lines)


# ── CLI ──────────────────────────────────────────────────────────────────────────────────


def build_parser(default_corpus: Path) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="corpus_green.py",
        description=(
            "Evaluate SOW §2 criterion 2 over the property-fixture corpus as PD-006 R3's "
            "four clauses, and print the evidence."
        ),
    )
    parser.add_argument(
        "--corpus",
        type=Path,
        default=default_corpus,
        help=f"corpus root to evaluate (default: {default_corpus})",
    )
    parser.add_argument(
        "--schema",
        type=Path,
        default=None,
        help=f"fixture schema to lint against (default: <corpus>/{SCHEMA_FILENAME})",
    )
    parser.add_argument(
        "--matrix",
        type=Path,
        default=DEFAULT_MATRIX,
        help=f"fidelity matrix whose open rows route a shortfall (default: {DEFAULT_MATRIX})",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="fail on any residue, not only on unaccounted violations — the literal "
        "R3.1/R3.2 reading",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    root = Path(__file__).resolve().parent.parent
    args = build_parser(root / "tests" / "fixtures" / "properties").parse_args(argv)

    try:
        report = check(args.corpus, args.schema or args.corpus / SCHEMA_FILENAME, args.matrix)
    except CorpusGreenError as exc:
        print(f"corpus green: {exc}", file=sys.stderr)
        return 2

    ok = report.met if args.strict else report.accounted
    print(format_report(report, strict=args.strict), file=sys.stdout if ok else sys.stderr)
    return 0 if ok else 1


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
