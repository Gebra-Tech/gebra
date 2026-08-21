"""The §0.4 condition-ID registry: the closed set, the tiers, and the emission guard.

Three claims carry this module, one per acceptance box of the card that built the registry.

**A validator cannot emit an unregistered condition ID.** Two different guards, because the
question has two halves. An *unregistered* string is refused by the type — ``ConditionId`` is
a ``Literal`` over the registry's members, so every envelope entry point rejects it — and a
*registered but not emittable* one is refused by the emission constructors, which is where it
has to be: the vendored corpus records RESERVED IDs in ``expected:`` blocks, and PC-6 makes
those the same classes that a validator's output validates into.

**The registry is closed.** Both directions: the Literal's members and the table's rows are
the same set, and the corpus contains no condition string that is neither registered nor one
of the three §0.4 deliberately withholds.

**``edge-target-undefined`` is emittable as of DEC-12.** It stays filed PROPOSED (the tier
is where the name was filed, never the emission answer), and the lever that changed the
guard's answer is exactly the one §0.4 names: its dated decision record (DEC-12, vault
commit 9093972) landed and the vendored table now says so.

Nothing here executes a workflow, a node, or a network call (WA-07): the registry is a frozen
table, and the corpus is read with PyYAML's safe loader.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, get_args

import pytest
import yaml
from pydantic import ValidationError

from gebra.verify import (
    CONDITION_IDS,
    CONDITION_REGISTRY,
    EMITTABLE_CONDITION_IDS,
    PROPERTY_REGISTRY,
    PROPOSED_CONDITION_IDS,
    RATIFIED_CONDITION_IDS,
    RESERVED_CONDITION_IDS,
    START,
    UNREGISTERED_CORPUS_STRINGS,
    Advisory,
    AdvisoryCarriageError,
    CoFailure,
    ConditionEntry,
    ConditionId,
    ConditionOwnershipError,
    ConditionRegistryError,
    DataflowLocation,
    Failure,
    NodeLocation,
    NonEmittableConditionError,
    P01EdgeLocation,
    P04Failure,
    PropertyReport,
    PropertySlug,
    UnregisteredConditionError,
    condition,
    conditions_for,
    emit_advisory,
    emit_co_failure,
    emit_failure,
    emittable_condition,
    is_emittable,
    is_registered,
    property_for_condition,
    to_data,
    validate_report,
)
from tests.conftest import FIXTURES_DIR

SRC = Path(__file__).resolve().parents[2] / "src" / "gebra"

#: The one anchor these tests reuse; which anchor a condition takes is its section's business.
ANCHOR = NodeLocation(kind="node", node="escalate_to_human")


# ── The closed set (§0.4 registry discipline) ────────────────────────────────────────────


def test_the_literal_and_the_table_are_the_same_closed_set() -> None:
    """Neither spelling of the set may grow without the other — that is what "closed" buys."""
    assert set(CONDITION_IDS) == set(get_args(ConditionId))
    assert set(CONDITION_IDS) == set(CONDITION_REGISTRY)
    assert len(CONDITION_IDS) == len(set(CONDITION_IDS))


def test_the_three_tiers_partition_the_registry() -> None:
    """§0.4 tables 11 RATIFIED, 8 RESERVED and 2 PROPOSED entries — 21, and no fourth tier."""
    assert len(RATIFIED_CONDITION_IDS) == 11
    assert len(RESERVED_CONDITION_IDS) == 8
    assert len(PROPOSED_CONDITION_IDS) == 2
    assert (
        len(RATIFIED_CONDITION_IDS) + len(RESERVED_CONDITION_IDS) + len(PROPOSED_CONDITION_IDS)
        == len(CONDITION_IDS)
        == 21
    )


@pytest.mark.parametrize("condition_id", CONDITION_IDS)
def test_every_entry_names_a_catalog_property_consistently(condition_id: str) -> None:
    """A condition is held for exactly one property, spelled the same way in both registries."""
    entry = condition(condition_id)
    assert entry.id == condition_id
    assert PROPERTY_REGISTRY[entry.property_slug].property_id == entry.property_id
    assert property_for_condition(condition_id) == entry.property_slug


@pytest.mark.parametrize("condition_id", CONDITION_IDS)
def test_every_id_is_frozen_kebab_case(condition_id: str) -> None:
    """§0.4: "frozen, kebab-case identifiers" — and the SARIF ``rule.id`` namespace (§0.5)."""
    assert condition_id == condition_id.lower()
    assert condition_id.replace("-", "").isalnum()
    assert not condition_id.startswith("-") and not condition_id.endswith("-")


def test_conditions_for_partitions_by_property() -> None:
    grouped = [entry.id for slug in PROPERTY_REGISTRY for entry in conditions_for(slug)]
    assert sorted(grouped) == sorted(CONDITION_IDS)
    assert all(entry.property_slug == "effect-safety" for entry in conditions_for("effect-safety"))
    assert conditions_for("subgraph-consistency") == ()


# ── Emittability: a registered name is not automatically an emittable one ────────────────


def test_only_ratified_entries_are_emittable() -> None:
    """§0.4's trigger, stated once: an entry becomes emittable when a dated record ratifies it.

    That is 11 RATIFIED strings plus the two PROPOSED-tier latecomers with records of their
    own: ``orphan-node`` (DEC-11, by name) and ``edge-target-undefined`` (DEC-12).
    """
    assert set(EMITTABLE_CONDITION_IDS) == set(RATIFIED_CONDITION_IDS) | {
        "orphan-node",
        "edge-target-undefined",
    }
    assert all(condition(cid).ratified_by is not None for cid in EMITTABLE_CONDITION_IDS)


@pytest.mark.parametrize("condition_id", RESERVED_CONDITION_IDS)
def test_reserved_ids_are_registered_but_not_emittable(condition_id: str) -> None:
    """RESERVED names "ratify when their property sections … are merged" — not before."""
    assert is_registered(condition_id)
    assert not is_emittable(condition_id)
    assert condition(condition_id).ratified_by is None
    with pytest.raises(NonEmittableConditionError):
        emittable_condition(condition_id)


def test_a_reserved_id_may_still_be_recorded_by_a_report() -> None:
    """PC-6's other duty: ``mixed/06`` records a P-07 RESERVED id that P-06 must not emit."""
    recorded = CoFailure(
        property="retry-coherence",
        property_condition="idempotency-key-not-in-declared-reads",
        location=ANCHOR,
        severity="error",
        claim_class="defensible-a",
    )
    assert recorded.property_condition == "idempotency-key-not-in-declared-reads"
    with pytest.raises(NonEmittableConditionError):
        emit_co_failure("retry-coherence", "idempotency-key-not-in-declared-reads", ANCHOR)


def test_an_emittable_entry_must_pin_its_severity_and_claim_class() -> None:
    """§0.1: every emitted record classifies its own claim, so the grades cannot be absent."""
    with pytest.raises(ConditionRegistryError):
        ConditionEntry(
            id="read-key-removed",
            property_slug="evolution-safety",
            property_id="P-12",
            tier="reserved",
            ratified_by="a decision record that does not exist",
        )


# ── Acceptance: an unregistered condition ID cannot be emitted, or even built ────────────


def test_the_emission_constructors_refuse_an_unregistered_string() -> None:
    with pytest.raises(UnregisteredConditionError):
        emit_failure("graph-well-formed", "node-unreachable", ANCHOR)
    with pytest.raises(UnregisteredConditionError):
        emit_co_failure("graph-well-formed", "node-unreachable", ANCHOR)
    with pytest.raises(UnregisteredConditionError):
        emit_advisory("determinism-replay", "llm-is-vibing", ANCHOR)
    with pytest.raises(UnregisteredConditionError):
        condition("node-unreachable")


@pytest.mark.parametrize(
    "build",
    [
        pytest.param(
            lambda cid: Failure(
                property_condition=cid, location=ANCHOR, severity="fatal", claim_class="defensible"
            ),
            id="Failure",
        ),
        pytest.param(
            lambda cid: CoFailure(
                property="graph-well-formed",
                property_condition=cid,
                location=ANCHOR,
                severity="fatal",
                claim_class="defensible",
            ),
            id="CoFailure",
        ),
        pytest.param(
            lambda cid: Advisory(
                property="determinism-replay",
                property_condition=cid,
                severity="warning",
                claim_class="heuristic",
                location=ANCHOR,
            ),
            id="Advisory",
        ),
    ],
)
def test_no_envelope_record_can_carry_an_unregistered_id(build: Any) -> None:
    """The type-level half of the guard: the constructor route, not just the emission one."""
    with pytest.raises(ValidationError):
        build("invented-condition")
    assert build("node-unreachable-from-start").property_condition == "node-unreachable-from-start"


def test_a_loaded_report_cannot_carry_an_unregistered_id() -> None:
    """The fixture route (§0.3 loading rule) is refused on the same annotation."""
    with pytest.raises(ValidationError):
        validate_report(
            {
                "property": "graph-well-formed",
                "result": "fail",
                "failure": {
                    "property_condition": "invented-condition",
                    "location": {"kind": "node", "node": "escalate_to_human"},
                    "severity": "fatal",
                    "claim_class": "defensible",
                },
            }
        )


@pytest.mark.parametrize("withheld", sorted(UNREGISTERED_CORPUS_STRINGS))
def test_the_p03_strings_the_spec_withholds_are_not_registered(withheld: str) -> None:
    """§0.4: P-03's three strings "enter the registry with §P-03, not before" (DEC-05 D6)."""
    assert not is_registered(withheld)
    assert not is_emittable(withheld)
    with pytest.raises(UnregisteredConditionError):
        emit_failure("signature-soundness", withheld, ANCHOR)


def test_no_non_emittable_id_is_written_as_a_literal_anywhere_in_the_package() -> None:
    """The guard a validator cannot route around by hand-building a model.

    ``emit_*`` refuses a held name, but a validator could in principle spell one into a
    ``Failure`` directly. Nothing outside the registry itself has any business naming one, so
    this asserts that nothing does — the check a future P-01 or P-06 change has to survive.
    """
    held = set(CONDITION_IDS) - set(EMITTABLE_CONDITION_IDS)
    #: The table itself, and the Literal it is keyed on — the two places held names belong.
    exempt = {"verify/conditions.py", "verify/base.py"}
    offenders = {
        (path.relative_to(SRC).as_posix(), condition_id)
        for path in SRC.rglob("*.py")
        if path.relative_to(SRC).as_posix() not in exempt
        for condition_id in held
        if condition_id in path.read_text(encoding="utf-8")
    }
    assert offenders == set(), (
        "a non-emittable §0.4 condition ID is named outside the registry module; "
        "held names are recorded there and emitted nowhere"
    )


# ── Acceptance: ``edge-target-undefined`` is ratified by DEC-12 ──────────────────────────


def test_edge_target_undefined_is_ratified_and_emittable() -> None:
    """DEC-12 (vault commit 9093972) is the dated record §0.4's trigger asks for."""
    entry = condition("edge-target-undefined")
    assert entry.tier == "proposed"
    assert entry.property_slug == "graph-well-formed"
    assert entry.ratified_by is not None and "DEC-12" in entry.ratified_by
    assert entry.precedent is not None and "mixed/04" in entry.precedent
    assert entry.emittable
    assert is_emittable("edge-target-undefined")
    assert "edge-target-undefined" in EMITTABLE_CONDITION_IDS


@pytest.mark.parametrize(
    "emit",
    [
        pytest.param(lambda: emit_failure("graph-well-formed", "edge-target-undefined", ANCHOR)),
        pytest.param(lambda: emit_co_failure("graph-well-formed", "edge-target-undefined", ANCHOR)),
    ],
    ids=["failure", "co_failure"],
)
def test_finding_routes_accept_edge_target_undefined(emit: Any) -> None:
    built = emit()
    assert built.property_condition == "edge-target-undefined"
    assert (built.severity, built.claim_class) == ("fatal", "defensible")


def test_advisory_route_still_refuses_edge_target_undefined() -> None:
    """Ratification changes emittability, not grade: §0.3 admits only WARNING advisories."""
    with pytest.raises(ConditionRegistryError):
        emit_advisory("graph-well-formed", "edge-target-undefined", ANCHOR)


def test_edge_target_undefined_ratification_is_the_record_not_a_tier_promotion() -> None:
    """Emittability comes from the dated record; the tier stays where the name was filed.

    Both P-01 latecomers still sit in the PROPOSED table — ``orphan-node`` emittable because
    DEC-11 ratified it by name, ``edge-target-undefined`` emittable because DEC-12 (its own
    §0.4 addendum, filed per PD-007/M7 with the ``mixed/04`` co-failure revision) landed in
    the vault's R-05 decisions. §0.4's trigger asks for the record, never a tier flip.
    """
    filed_together = {condition(cid).tier for cid in ("orphan-node", "edge-target-undefined")}
    assert filed_together == {"proposed"}
    assert is_emittable("orphan-node")
    assert is_emittable("edge-target-undefined")
    assert condition("edge-target-undefined").ratified_by != condition("orphan-node").ratified_by


# ── The emission surface: grades come off §0.4, never off the caller ─────────────────────


def test_emit_failure_reads_its_grades_off_the_registry() -> None:
    built = emit_failure("graph-well-formed", "node-unreachable-from-start", ANCHOR)
    assert built == Failure(
        property_condition="node-unreachable-from-start",
        location=ANCHOR,
        severity="fatal",
        claim_class="defensible",
    )


def test_emit_failure_passes_a_sections_own_members_through() -> None:
    """``model`` selects a concrete subtype; the extra members ride ``fields``."""
    built = emit_failure(
        "dataflow-completeness",
        "read-key-never-written-on-path",
        DataflowLocation(kind="state-key", key="quote", node="book", path=(START, "book")),
        model=P04Failure,
        downstream_writers=("fetch_quote",),
        remediation="Write `quote` before `book` reads it.",
    )
    assert isinstance(built, P04Failure)
    assert built.severity == "fatal" and built.claim_class == "defensible-a"
    assert built.downstream_writers == ("fetch_quote",)


def test_emit_co_failure_derives_the_property_and_the_grades() -> None:
    built = emit_co_failure(
        "dataflow-completeness",
        "read-key-never-written-on-path",
        ANCHOR,
        subsumed_by="P-01",
        note="Owned by P-01 (DEC-05 D2).",
    )
    assert built.property == "dataflow-completeness"
    assert (built.severity, built.claim_class) == ("fatal", "defensible-a")
    assert built.subsumed_by == "P-01"


def test_emit_advisory_carries_only_warning_grade_findings() -> None:
    """§0.3: advisories are cross-property WARNING-class side findings, and nothing else."""
    built = emit_advisory("determinism-replay", "deterministic-llm-seed-unpinned", ANCHOR)
    assert (built.property, built.severity, built.claim_class) == (
        "determinism-replay",
        "warning",
        "heuristic",
    )
    with pytest.raises(ConditionRegistryError):
        emit_advisory("graph-well-formed", "node-unreachable-from-start", ANCHOR)


def test_a_property_cannot_ride_its_own_finding_as_an_advisory() -> None:
    """§0.3: ``advisories`` is cross-property; a same-property finding rides ``co_failures``.

    The packaging rule that says findings are "never re-packaged as self-referential
    advisories" is enforced where the finding is built, not left to review.
    """
    own = emit_advisory("determinism-replay", "deterministic-llm-seed-unpinned", ANCHOR)
    with pytest.raises(AdvisoryCarriageError):
        emit_failure(
            "determinism-replay",
            "deterministic-llm-seed-unpinned",
            ANCHOR,
            advisories=(own,),
        )
    riding_another_report = emit_failure(
        "graph-well-formed", "node-unreachable-from-start", ANCHOR, advisories=(own,)
    )
    assert riding_another_report.advisories == (own,)


@pytest.mark.parametrize(
    ("property_slug", "condition_id"),
    [
        ("termination-witness", "node-unreachable-from-start"),
        ("graph-well-formed", "cycle-without-termination-witness"),
        ("effect-safety", "deterministic-llm-seed-unpinned"),
    ],
)
def test_a_property_cannot_emit_a_name_another_property_holds(
    property_slug: PropertySlug, condition_id: str
) -> None:
    """§0.4 holds each name for its property and forbids reuse."""
    with pytest.raises(ConditionOwnershipError):
        emit_failure(property_slug, condition_id, ANCHOR)


def test_a_report_emitted_through_the_registry_equals_the_fixture() -> None:
    """PC-6, end to end: registry → envelope → the vendored ``graph-well-formed/negative-03``."""
    document = yaml.safe_load(
        (
            FIXTURES_DIR / "graph-well-formed/negative-03-path-map-typo-dangling-target.yaml"
        ).read_text(encoding="utf-8")
    )
    loaded = validate_report({"property": document["property"], **document["expected"]})
    emitted = PropertyReport.failing(
        "graph-well-formed",
        emit_failure(
            "graph-well-formed",
            "path-map-target-undefined",
            P01EdgeLocation(
                kind="edge",
                source="review_booking",
                label="confirm",
                undefined_target="send_confirmatoin",
            ),
            co_failures=(
                emit_co_failure(
                    "graph-well-formed",
                    "node-unreachable-from-start",
                    NodeLocation(kind="node", node="send_confirmation"),
                ),
            ),
        ),
    )
    assert emitted == loaded
    assert to_data(emitted) == to_data(loaded)


# ── The corpus attests the table ─────────────────────────────────────────────────────────


def _corpus_records() -> list[tuple[str, dict[str, Any]]]:
    """Every ``property_condition``-carrying record in the vendored corpus, with its fixture."""
    found: list[tuple[str, dict[str, Any]]] = []

    def walk(node: object, where: str) -> None:
        if isinstance(node, dict):
            if "property_condition" in node:
                found.append((where, node))
            for value in node.values():
                walk(value, where)
        elif isinstance(node, list):
            for value in node:
                walk(value, where)

    for path in sorted(FIXTURES_DIR.rglob("*.yaml")):
        if path.name == "schema.yaml":
            continue
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        walk(document.get("expected"), path.relative_to(FIXTURES_DIR).as_posix())
    return found


def test_the_corpus_names_no_condition_the_registry_has_never_heard_of() -> None:
    """Every string in the corpus is registered, or is one of the three §0.4 withholds."""
    unknown = {
        (where, record["property_condition"])
        for where, record in _corpus_records()
        if not is_registered(record["property_condition"])
        and record["property_condition"] not in UNREGISTERED_CORPUS_STRINGS
    }
    assert unknown == set()


def test_the_registry_grades_agree_with_every_grade_the_corpus_states() -> None:
    """The table is the catalog's; where the reviewed corpus states a grade, it is the same one.

    Only the entries §0.4 grades are checked — the RESERVED tier carries no severity column
    there, and inventing one from a fixture would be exactly the improvisation the tier exists
    to prevent.
    """
    divergences = {
        (where, record["property_condition"], record.get("severity"), record.get("claim_class"))
        for where, record in _corpus_records()
        if is_registered(record["property_condition"])
        and condition(record["property_condition"]).severity is not None
        and (
            (record.get("severity"), record.get("claim_class"))
            not in {
                (None, None),
                (
                    condition(record["property_condition"]).severity,
                    condition(record["property_condition"]).claim_class,
                ),
            }
        )
    }
    assert divergences == set()


def test_the_corpus_grades_of_reserved_ids_stay_inside_their_property_row() -> None:
    """The RESERVED tier's grades arrive with its section; the property row is what exists now."""
    for where, record in _corpus_records():
        cid = record["property_condition"]
        if not is_registered(cid) or condition(cid).severity is not None:
            continue
        entry = PROPERTY_REGISTRY[condition(cid).property_slug]
        if record.get("severity") is not None:
            assert record["severity"] in entry.severities, where
        if record.get("claim_class") is not None:
            assert record["claim_class"] in entry.claim_classes, where
