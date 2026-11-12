"""The thirteen-slug property registry, and the dispatch it drives.

The acceptance claim here is the one the Phase-0 plan made and the Phase-1 catalog charter
(DEC-35) keeps: a property with no validator in this release is carried by the registry as a
**structured not-implemented marker, never a silent pass**. So the tests ask, for every one
of the thirteen slugs, what dispatch actually returns — and check that it is never a report,
never ``None``, and never an exception a caller has to guess the meaning of.

The charter adds three claims, each pinned here in both directions (DEC-35 §3.1, §3.5):
the scope vocabulary and the registration rule — a ``catalog`` row accepts a validator, a
``deferred-to-phase-1`` or two-snapshot row refuses one through this path; the marker copy —
the charter's words on every deferred marker (DEC-42 §3.1), and none of the phrases DEC-35
and DEC-42 retired left anywhere under ``src/``; and the derived counts — every count reads
the registry, and a synthetic registration moves all of them together. The ``catalog`` rows
these tests use are synthetic (``tests/_registry.py``): no real property moves.

The second claim is that the table is the single source of truth D-09 Deliverable 2 asks for:
thirteen rows, exactly the catalog's slugs, each carrying the claim class, severity and
derivation reference the catalog states, and none of them restating a condition ID the §0.4
registry already owns.

Nothing here executes a workflow, a node, or a network call (WA-07). The stub validators
registered here are local functions that return a fixed report; dispatch calling one is the
only "execution" in this module.
"""

from __future__ import annotations

import json
import re
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Any, Final, get_args

import pytest

from gebra.ir import WorkflowIR
from gebra.verify import (
    DEFERRED_READING,
    MARKER_REASONS,
    NO_VERDICT,
    NON_WEDGE_SLUGS,
    PROPERTY_REGISTRY,
    PROPERTY_SLUGS,
    SHIPPED_SCOPES,
    WEDGE_SLUGS,
    ClaimClass,
    NotImplementedMarker,
    NotImplementedStatus,
    PropertyEntry,
    PropertyId,
    PropertyRegistryError,
    PropertyReport,
    PropertyScope,
    PropertySlug,
    RegistryCounts,
    Severity,
    WellFormednessWitness,
    conditions_for,
    deferred_slugs,
    is_implemented,
    not_implemented,
    property_entry,
    register_validator,
    registry_counts,
    run_property,
    shipped_slugs,
    to_data,
    unregister_validator,
    validator_for,
    verify,
)
from gebra.verify.registry import _TABLE
from tests._registry import passing_validator, synthetic_catalog_row

#: The wedge five, as SOW §1 and the board's charter name them.
EXPECTED_WEDGE: tuple[PropertySlug, ...] = (
    "graph-well-formed",
    "termination-witness",
    "dataflow-completeness",
    "effect-safety",
    "determinism-replay",
)


@pytest.fixture
def ir() -> WorkflowIR:
    """The smallest valid IR document — dispatch needs an argument, not a graph."""
    return WorkflowIR.model_validate_json(
        json.dumps(
            {
                "ir_version": "1.0",
                "entry": "a",
                "finish": "a",
                "nodes": [{"id": "a"}],
                "edges": [],
            }
        )
    )


def _stub_report(_: WorkflowIR) -> PropertyReport:
    return PropertyReport.passing(
        "graph-well-formed",
        WellFormednessWitness(
            kind="well-formedness",
            reachable_from_start=("a",),
            terminal_nodes=("a",),
            orphan_nodes=(),
            unresolved_targets=(),
        ),
    )


@pytest.fixture
def clean_registrations() -> Any:
    """No test changes what is wired in — dispatch's answer is global state.

    Restoring rather than clearing: shipped validators register at import (P-08 since
    VAL-04), so dropping every slug would leave the rest of the session dispatching to
    ``not-yet-implemented`` for a property that is in fact implemented.
    """
    shipped = {slug: validator_for(slug) for slug in PROPERTY_SLUGS}
    yield
    for slug, implementation in shipped.items():
        unregister_validator(slug)
        if implementation is not None:
            register_validator(slug, implementation)


# ── The table ────────────────────────────────────────────────────────────────────────────


def test_the_registry_is_exactly_the_thirteen_catalog_slugs() -> None:
    assert set(PROPERTY_SLUGS) == set(get_args(PropertySlug))
    assert len(PROPERTY_SLUGS) == 13
    assert set(PROPERTY_REGISTRY) == set(PROPERTY_SLUGS)


def test_property_ids_are_p01_through_p13_in_catalog_order() -> None:
    ids = [PROPERTY_REGISTRY[slug].property_id for slug in PROPERTY_SLUGS]
    assert ids == list(get_args(PropertyId))


def test_the_wedge_is_the_five_sow_names() -> None:
    """SOW §1 in scope, SOW §8 out — the split the whole Phase-0 plan is built on.

    A fact about Phase-0's scope, fixed with the table: a non-wedge property that lands under
    the charter stays non-wedge and is live all the same, so the count of the split is read
    off the registry, never stated.
    """
    counts = registry_counts()
    assert WEDGE_SLUGS == EXPECTED_WEDGE
    assert set(NON_WEDGE_SLUGS) == set(PROPERTY_SLUGS) - set(EXPECTED_WEDGE)
    assert len(NON_WEDGE_SLUGS) == counts.total - counts.wedge


@pytest.mark.parametrize("slug", PROPERTY_SLUGS)
def test_every_row_carries_the_columns_the_brief_asks_for(slug: PropertySlug) -> None:
    """D-09 Deliverable 2: slug → claim class → severity → derivation reference, in one table."""
    entry = PROPERTY_REGISTRY[slug]
    assert entry.slug == slug
    assert entry.claim_classes and set(entry.claim_classes) <= set(get_args(ClaimClass))
    assert entry.severities and set(entry.severities) <= set(get_args(Severity))
    assert entry.derivation.strip()
    assert entry.spec_ref.strip()
    assert entry.wedge == (entry.scope == "phase-0-wedge")
    assert entry.deferred == (entry.scope == "deferred-to-phase-1")
    assert entry.shipped == (not entry.deferred)


def test_p12_is_the_only_two_snapshot_property() -> None:
    """D-09 in-scope item 5: ``validate(ir_before, ir_after)`` is P-12's shape alone."""
    two = [slug for slug in PROPERTY_SLUGS if PROPERTY_REGISTRY[slug].arity == "two-snapshot"]
    assert two == ["evolution-safety"]


def test_the_wedge_grades_match_the_drafted_sections() -> None:
    """The five §P-nn headers, read back off the table."""
    grades = {
        slug: (PROPERTY_REGISTRY[slug].claim_classes, PROPERTY_REGISTRY[slug].severities)
        for slug in WEDGE_SLUGS
    }
    assert grades == {
        "graph-well-formed": (("defensible",), ("fatal",)),
        "termination-witness": (("defensible",), ("fatal",)),
        "dataflow-completeness": (("defensible-a",), ("fatal",)),
        "effect-safety": (("defensible-a",), ("fatal", "error")),
        "determinism-replay": (("heuristic",), ("warning",)),
    }


@pytest.mark.parametrize("slug", PROPERTY_SLUGS)
def test_the_table_restates_no_condition_id(slug: PropertySlug) -> None:
    """Condition IDs live in the §0.4 registry; this table reads them, never copies them."""
    entry = PROPERTY_REGISTRY[slug]
    for held in conditions_for(slug):
        assert held.property_id == entry.property_id
        assert held.id not in entry.derivation


def test_an_unknown_slug_is_refused_by_name() -> None:
    with pytest.raises(PropertyRegistryError, match="thirteen catalog slugs"):
        property_entry("graph-wellformed")


# ── Dispatch: the eight are markers, never silent passes ────────────────────────────────


@pytest.mark.parametrize("slug", PROPERTY_SLUGS)
def test_dispatch_answers_every_slug_with_something_structured(
    slug: PropertySlug, ir: WorkflowIR
) -> None:
    """No slug returns ``None``, raises, or quietly passes — the registry answers for all 13."""
    answer = run_property(slug, ir)
    assert answer.property == slug
    if is_implemented(slug):
        assert isinstance(answer, PropertyReport)
        return
    assert isinstance(answer, NotImplementedMarker)
    assert not isinstance(answer, PropertyReport)
    assert answer.property_id == PROPERTY_REGISTRY[slug].property_id
    assert answer.kind == "not-implemented"


@pytest.mark.parametrize("slug", deferred_slugs())
def test_every_deferred_slug_answers_with_the_charters_copy(
    slug: PropertySlug, ir: WorkflowIR
) -> None:
    """D-09's stub discipline in DEC-42 §3.1's words: a distinct status, a pointer, no pass.

    The detail carries PROPERTY-CATALOG-SPEC §0.6 item 1's copy for the token verbatim (DEC-42
    §3.1), points at the property's catalog section with no standing stated (DEC-42 §3.4), and
    keeps the sentence the charter keeps verbatim (DEC-35 §3.1); nothing in it names Phase 0 as
    the present.
    """
    marker = run_property(slug, ir)
    assert isinstance(marker, NotImplementedMarker)
    assert marker.status == "deferred-to-phase-1"
    entry = PROPERTY_REGISTRY[slug]
    assert marker.detail.startswith(f"{entry.property_id} {slug} {DEFERRED_READING}.")
    assert marker.detail.endswith(NO_VERDICT)
    assert entry.spec_ref in marker.detail
    assert "Phase-0" not in marker.detail and "SOW" not in marker.detail


@pytest.mark.parametrize("slug", WEDGE_SLUGS)
def test_an_unwired_wedge_slug_says_so_in_its_own_words(slug: PropertySlug, ir: WorkflowIR) -> None:
    """Out-of-scope and not-yet-built are different absences; neither is a verdict.

    A wedge slug whose validator has landed answers with a report instead — the marker is
    the *unwired* case, and which wedge slugs those are shrinks as the VAL cards land. Both
    halves are asserted here, off the registry's own answer rather than off a hand-kept list.
    """
    answer = run_property(slug, ir)
    if is_implemented(slug):
        assert isinstance(answer, PropertyReport)
        assert not isinstance(answer, NotImplementedMarker)
        return
    assert isinstance(answer, NotImplementedMarker)
    assert answer.status == "not-yet-implemented"
    assert answer.detail.endswith(NO_VERDICT)


def test_the_wedge_validators_that_have_landed_are_the_ones_wired_in() -> None:
    """The build-order statement, asserted rather than assumed (VAL-04 wired P-08; VAL-05 P-01;
    VAL-09 P-04; VAL-10 P-06; VAL-07 P-02 — the wedge five complete)."""
    assert {slug for slug in WEDGE_SLUGS if is_implemented(slug)} == {
        "dataflow-completeness",
        "determinism-replay",
        "effect-safety",
        "graph-well-formed",
        "termination-witness",
    }
    assert not any(is_implemented(slug) for slug in deferred_slugs())
    assert all(is_implemented(slug) for slug in shipped_slugs())


def test_a_marker_is_not_a_report_and_carries_no_verdict_field() -> None:
    marker = not_implemented("parallel-safety")
    data = to_data(marker)
    assert set(data) == {"kind", "property", "property_id", "status", "detail"}
    assert "result" not in data and "witness" not in data and "failure" not in data
    assert NotImplementedMarker.model_validate_json(json.dumps(data)) == marker


# ── Dispatch: a registered validator answers instead ─────────────────────────────────────


def test_a_registered_validator_takes_over_dispatch(
    ir: WorkflowIR, clean_registrations: Any
) -> None:
    """The registry drives dispatch: wire a validator in, and the marker gives way to it.

    P-01's real validator registers at import since VAL-05, so the unwired half of the
    transition has to be re-created rather than assumed. ``clean_registrations`` puts the
    shipped one back afterwards.
    """
    unregister_validator("graph-well-formed")
    assert isinstance(run_property("graph-well-formed", ir), NotImplementedMarker)

    register_validator("graph-well-formed", _stub_report)

    assert is_implemented("graph-well-formed")
    assert validator_for("graph-well-formed") is _stub_report
    answer = run_property("graph-well-formed", ir)
    assert isinstance(answer, PropertyReport)
    assert answer.result == "pass"

    unregister_validator("graph-well-formed")
    assert isinstance(run_property("graph-well-formed", ir), NotImplementedMarker)


@pytest.mark.parametrize("slug", deferred_slugs())
def test_registration_is_refused_for_every_deferred_row(
    slug: PropertySlug, clean_registrations: Any
) -> None:
    """A validator cannot appear at runtime for a ``deferred-to-phase-1`` row, ratified or not.

    The refusal states the charter's copy for the row (DEC-42 §3.1) and the edit that would
    license the registration — the row's move to ``catalog`` — rather than any phase (DEC-35
    §3.1).
    """
    with pytest.raises(PropertyRegistryError, match=re.escape(DEFERRED_READING)) as refused:
        register_validator(slug, _stub_report)
    assert "`catalog`" in str(refused.value)
    assert not is_implemented(slug)


def test_a_second_registration_is_refused(clean_registrations: Any) -> None:
    """P-02's real validator registers at import since VAL-07, so the free slot is re-made."""
    unregister_validator("termination-witness")
    register_validator("termination-witness", _stub_report)
    with pytest.raises(PropertyRegistryError, match="already has a registered validator"):
        register_validator("termination-witness", _stub_report)


def test_a_validator_answering_for_another_property_is_refused(
    ir: WorkflowIR, clean_registrations: Any
) -> None:
    """One property, one report (§0.3) — a mis-wired validator is caught at the boundary."""
    unregister_validator("termination-witness")
    register_validator("termination-witness", _stub_report)
    with pytest.raises(PropertyRegistryError, match="one property, one report"):
        run_property("termination-witness", ir)


def test_dispatch_refuses_an_unknown_slug(ir: WorkflowIR) -> None:
    with pytest.raises(PropertyRegistryError):
        run_property("graph-wellformed", ir)  # type: ignore[arg-type]


def test_the_entry_is_frozen_data() -> None:
    """The table is a contract surface, not a scratch pad."""
    entry: PropertyEntry = PROPERTY_REGISTRY["effect-safety"]
    with pytest.raises(FrozenInstanceError):
        entry.slug = "graph-well-formed"  # type: ignore[misc]


# ── The charter's scope vocabulary and registration rule (DEC-35 §3.1) ──────────────────


def test_the_scope_vocabulary_is_the_charters_three_tokens() -> None:
    """``catalog`` joins the two Phase-0 tokens, which stay as they were (DEC-35 §2, (1a)).

    Additive: the wire token ``deferred-to-phase-1`` is untouched, and the two shipped scopes
    are the ones registration accepts.
    """
    assert get_args(PropertyScope) == ("phase-0-wedge", "catalog", "deferred-to-phase-1")
    assert SHIPPED_SCOPES == ("phase-0-wedge", "catalog")
    assert {entry.scope for entry in PROPERTY_REGISTRY.values()} <= set(get_args(PropertyScope))


def test_the_wire_status_vocabulary_is_unchanged() -> None:
    """The charter's two new marker statuses are not this build's to admit.

    DEC-35 §4: ``NotImplementedMarker.status`` admits ``not-enabled`` and ``two-snapshot-only``
    "by their own sections' landings", and §3.3 puts them on G13's and G14's ``report_format``
    rows. Until those landings the wire carries exactly the two Phase-0 statuses — so a
    landing that admits one must move this pin in plain sight.
    """
    assert get_args(NotImplementedStatus) == ("deferred-to-phase-1", "not-yet-implemented")
    with pytest.raises(ValueError):
        NotImplementedMarker.model_validate(
            {
                "kind": "not-implemented",
                "property": "evolution-safety",
                "property_id": "P-12",
                "status": "two-snapshot-only",
                "detail": "x",
            }
        )


def test_every_wire_status_has_its_reason_and_no_other() -> None:
    """The reason table is held in lockstep with the wire vocabulary, both ways.

    Every surface that renders a marker states the reason its status keys here, so a status
    a section's landing admits (``not-enabled``, ``two-snapshot-only``) fails this test until
    its ruled reason joins — no surface can fall back to another status's words — and the
    deferred reason is the charter's own (DEC-42 §3.1).
    """
    assert set(MARKER_REASONS) == set(get_args(NotImplementedStatus))
    assert MARKER_REASONS["deferred-to-phase-1"] == DEFERRED_READING
    assert all(reason and not reason.endswith(".") for reason in MARKER_REASONS.values())
    assert all("Phase" not in reason and "SOW" not in reason for reason in MARKER_REASONS.values())


def test_a_catalog_row_accepts_a_throwaway_validator(ir: WorkflowIR) -> None:
    """The ruled path: a row in scope ``catalog`` registers, and dispatch answers with it.

    The row is synthetic — P-07's moved to ``catalog`` for this test only — and the validator
    a throwaway; on exit both are put back, and P-07 answers with its deferred marker again.
    """
    stub = passing_validator("retry-coherence")
    with synthetic_catalog_row("retry-coherence", stub) as row:
        assert row.scope == "catalog" and row.shipped and not row.deferred and not row.wedge
        assert validator_for("retry-coherence") is stub
        answer = run_property("retry-coherence", ir)
        assert isinstance(answer, PropertyReport)
        assert answer.property == "retry-coherence"
    assert property_entry("retry-coherence").deferred
    assert not is_implemented("retry-coherence")
    marker = run_property("retry-coherence", ir)
    assert isinstance(marker, NotImplementedMarker) and marker.status == "deferred-to-phase-1"


def test_a_catalog_row_without_a_validator_answers_not_yet_implemented(ir: WorkflowIR) -> None:
    """A shipped row with no validator wired is the build-order absence, not the scope one."""
    with synthetic_catalog_row("retry-coherence"):
        marker = run_property("retry-coherence", ir)
        assert isinstance(marker, NotImplementedMarker)
        assert marker.status == "not-yet-implemented"
        assert DEFERRED_READING not in marker.detail
        assert marker.detail.endswith(NO_VERDICT)


def test_a_two_snapshot_row_refuses_the_one_snapshot_path_even_in_catalog_scope() -> None:
    """P-12's shape is its own landing's to add (DEC-35 §3.6), whatever its row's scope.

    So a synthetic ``catalog`` P-12 still refuses a one-snapshot validator — the refusal P-12's
    landing keeps ("still refusing a two-snapshot implementation through the one-snapshot
    path") — and the table is left exactly as it was.
    """
    with synthetic_catalog_row("evolution-safety") as row:
        assert row.shipped and row.arity == "two-snapshot"
        assert not row.reports_on_one_snapshot
        with pytest.raises(PropertyRegistryError, match="reads two snapshots"):
            register_validator("evolution-safety", passing_validator("evolution-safety"))
        assert not is_implemented("evolution-safety")
    assert property_entry("evolution-safety").deferred


def test_the_scope_predicates_read_the_table_when_asked() -> None:
    """The call-time views follow a row the moment it moves — no tuple frozen at import."""
    before = deferred_slugs()
    with synthetic_catalog_row("parallel-safety"):
        assert "parallel-safety" not in deferred_slugs()
        assert "parallel-safety" in shipped_slugs()
        assert "parallel-safety" in NON_WEDGE_SLUGS  # still not one of the wedge five
        assert PROPERTY_REGISTRY["parallel-safety"].scope == "catalog"
        assert property_entry("parallel-safety").scope == "catalog"
    assert deferred_slugs() == before
    assert _TABLE["parallel-safety"].deferred


# ── Derived counts (DEC-35 §3.5 (c)) ─────────────────────────────────────────────────────


def _counted_by_hand() -> RegistryCounts:
    """The counts, recomputed here from the public table rather than read off the helper."""
    rows = [PROPERTY_REGISTRY[slug] for slug in PROPERTY_SLUGS]
    return RegistryCounts(
        total=len(rows),
        wedge=sum(row.scope == "phase-0-wedge" for row in rows),
        catalog=sum(row.scope == "catalog" for row in rows),
        deferred=sum(row.scope == "deferred-to-phase-1" for row in rows),
        registered=sum(validator_for(row.slug) is not None for row in rows),
        reported=sum(row.scope in SHIPPED_SCOPES and row.arity == "one-snapshot" for row in rows),
    )


def test_the_derived_counts_are_the_tables_own() -> None:
    """Every count reads the table and the registrations; none is stated anywhere."""
    counts = registry_counts()
    assert counts == _counted_by_hand()
    assert counts.total == len(PROPERTY_SLUGS) == len(get_args(PropertySlug))
    assert counts.wedge == len(WEDGE_SLUGS)
    assert counts.deferred == len(deferred_slugs())
    assert counts.shipped == len(shipped_slugs()) == counts.wedge + counts.catalog
    assert counts.shipped + counts.deferred == counts.total
    assert counts.not_checked == counts.total - counts.reported


def _surface_counts(ir: WorkflowIR) -> tuple[int, int, str, str]:
    """What three surfaces print for a run over ``ir``: report tallies, human, plugin."""
    from gebra.pytest_plugin import _render_gate
    from gebra.report import render_human
    from gebra.report.human import TerminalOptions

    report = verify(ir)
    reported = sum(isinstance(outcome, PropertyReport) for outcome in report.properties)
    markers = sum(isinstance(outcome, NotImplementedMarker) for outcome in report.properties)
    human = render_human(report, TerminalOptions(color=False, width=200))
    plugin = "\n".join(_render_gate(report))
    return reported, markers, human, plugin


def test_a_throwaway_registration_moves_every_derived_count_together(ir: WorkflowIR) -> None:
    """The mutation test: one row lands (synthetically), and every count follows it.

    A throwaway validator registers under a synthetic ``catalog`` row and the registry's
    counts, the run report's tallies, the human summary and the plugin's closing tally all move
    by exactly one, in step — with no literal edited anywhere. On exit everything is back.
    """
    before = registry_counts()
    reported, markers, human, plugin = _surface_counts(ir)
    assert (reported, markers) == (before.reported, before.not_checked)
    assert f"{before.reported} reported | {before.not_checked} produced no verdict" in human
    assert f"{before.reported} properties reported · {before.not_checked} not checked" in plugin

    with synthetic_catalog_row("join-key-soundness", passing_validator("join-key-soundness")):
        during = registry_counts()
        assert during == _counted_by_hand()
        assert (during.total, during.wedge) == (before.total, before.wedge)
        assert during.catalog == before.catalog + 1
        assert during.deferred == before.deferred - 1
        assert during.shipped == before.shipped + 1
        assert during.registered == before.registered + 1
        assert during.reported == before.reported + 1
        assert during.not_checked == before.not_checked - 1
        reported, markers, human, plugin = _surface_counts(ir)
        assert (reported, markers) == (during.reported, during.not_checked)
        assert f"{during.reported} reported | {during.not_checked} produced no verdict" in human
        assert f"{during.reported} properties reported · {during.not_checked} not checked" in plugin

    assert registry_counts() == before


# ── The retired copy (DEC-35 §3.1, DEC-42) ───────────────────────────────────────────────

SRC: Final = Path(__file__).resolve().parents[2] / "src"

#: The marker copy two rulings retired. The Phase-0 copy DEC-35 §3.1 retired, as each surface
#: spelled it: the marker detail and the harness's deferral ("is outside the Phase-0 wedge
#: (SOW §8)"), the human status line ("it is outside the Phase-0 wedge"), the plugin's
#: ``--gebra-select`` refusal ("SOW §8 defers them to Phase 1"), the registration refusal ("is
#: out of Phase-0 scope"), the ``snapshot`` marker line ("no safe/breaking classification
#: exists in Phase 0") and the not-yet-implemented detail ("one of the Phase-0 wedge five, but
#: no validator"). Then what DEC-42 retired, each a statement that turns untrue when a section
#: is ratified: the second clause of DEC-35's copy (§3.1), DEC-35's definition of the deferred
#: scope (§3.2), the token's reading DEC-42 §3.3 replaced, and the note the eight deferred
#: rows' contract pointers carried (§3.4). Exact needles: a bare "not yet ratified" would also
#: hit sentences about condition-ID emission and version compatibility, which are not copy.
RETIRED_PHRASES: Final = (
    "outside the Phase-0 wedge",
    "defers them to Phase 1",
    "is out of Phase-0 scope",
    "classification exists in Phase 0",
    "one of the Phase-0 wedge five, but",
    "its catalog section is not yet ratified",
    "whose section is not yet ratified",
    "scheduled for Phase 1",
    "stub; Verification-Properties",
)


def _retired_hits(text: str) -> list[str]:
    """Every retired phrase in ``text``, with line breaks and indentation folded to one space.

    Folded because a docstring or a wrapped string literal can split a phrase across lines,
    and a scan that read line by line would pass it.
    """
    flat = re.sub(r"\s+", " ", text)
    return [phrase for phrase in RETIRED_PHRASES if phrase in flat]


def test_the_retired_scan_sees_a_phrase_split_across_lines() -> None:
    """Arms the scan below: a phrase wrapped onto two lines is still found."""
    assert _retired_hits(
        'detail = (\n    "P-03 is outside the\n    Phase-0 wedge (SOW §8)"\n)'
    ) == ["outside the Phase-0 wedge"]
    assert _retired_hits(f"P-03 signature-soundness {DEFERRED_READING}. {NO_VERDICT}") == []


def test_the_retired_scan_sees_each_phrase_dec_42_retired() -> None:
    """Arms the scan for DEC-42's four needles, on the texts that carried them before it.

    The marker detail as VAL-16 built it, DEC-35's definition and reading as the registry's
    docstrings stated them, and a contract pointer with its note, wrapped across lines.
    """
    assert _retired_hits(
        "P-03 signature-soundness has no validator in this release; its catalog\n"
        "    section is not yet ratified. The catalog contract is PROPERTY-CATALOG-SPEC\n"
        "    §P-03 (stub;\n    Verification-Properties §2 authoritative). " + NO_VERDICT
    ) == ["its catalog section is not yet ratified", "stub; Verification-Properties"]
    assert _retired_hits(
        "a property whose section is not yet ratified, read as\n"
        '    "scheduled for Phase 1, not landed in this release"'
    ) == ["whose section is not yet ratified", "scheduled for Phase 1"]
    assert (
        _retired_hits(
            "an ID registered but not yet ratified for emission; a range not yet ratified"
        )
        == []
    )


def test_no_retired_marker_phrase_remains_in_src() -> None:
    """Box 2's grep: the retired Phase-0 copy appears nowhere under ``src/``."""
    found = {
        str(path.relative_to(SRC)): hits
        for path in sorted(SRC.rglob("*.py"))
        if (hits := _retired_hits(path.read_text(encoding="utf-8")))
    }
    assert found == {}
