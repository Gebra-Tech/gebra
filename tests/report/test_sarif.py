"""The SARIF projection against Appendix A — and against the SARIF 2.1.0 schema (card CLI-03).

CLI-03's second acceptance box is "SARIF output validates against the SARIF 2.1.0 schema".
That is checked here against the schema **document** — `tests/schemas/sarif-2.1.0.json`, the
copy `json.schemastore.org` serves at the URI A.7 fixes — using `tools/json_schema.py`, a
draft-07 subset validator that refuses any keyword it does not implement. The refusal is what
makes the box mean what it says: a construct the validator cannot check fails the run instead
of passing unchecked.

The rest of the module is Appendix A itself: the rule catalog against the §0.4 registry, one
result per finding, the losses that must stay losses, and the fingerprints.

Nothing here executes a workflow node, calls a model or opens a socket (WA-07) — including the
schema, which is read from disk and never fetched.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Final
from unittest import mock

import pytest

from gebra.report import render_sarif, sarif_log, subject_slug
from gebra.report.findings import findings_of
from gebra.report.rules import SARIF_RULE_ENTRIES, rule_copy
from gebra.verify.conditions import CONDITION_REGISTRY
from gebra.verify.locations import NodeLocation
from gebra.verify.report import PropertyReport
from tests.report.goldens import compare_golden
from tests.report.variants import CASES
from tools.json_schema import validate

SCHEMA_PATH: Final = Path(__file__).resolve().parents[1] / "schemas" / "sarif-2.1.0.json"


@pytest.fixture(scope="module")
def schema() -> Any:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


# ── The acceptance box ───────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.name)
def test_every_variant_validates_against_the_sarif_schema(case: Any, schema: Any) -> None:
    """Acceptance box 2, stated directly, for every §4 variant."""
    issues = validate(sarif_log(case.report), schema)
    assert not issues, "\n".join(str(issue) for issue in issues)


def test_the_schema_the_logs_are_checked_against_is_the_one_they_declare(schema: Any) -> None:
    """A log that pointed at one schema and validated against another would prove nothing."""
    from gebra.report.sarif import SARIF_SCHEMA_URI

    assert SARIF_SCHEMA_URI == "https://json.schemastore.org/sarif-2.1.0.json"
    assert schema["$schema"] == "http://json-schema.org/draft-07/schema#"
    assert "SARIF" in schema["title"] and "2.1.0" in schema["title"]


def test_a_deliberately_broken_log_is_caught_by_the_schema(schema: Any) -> None:
    """The validator is load-bearing, so it must be able to fail: a negative control."""
    log = sarif_log(next(case.report for case in CASES if case.name == "wedge-failures"))
    log["runs"][0]["results"][0]["level"] = "catastrophic"
    assert validate(log, schema)


# ── A.3: the rules[] catalog ─────────────────────────────────────────────────────────────


def _driver(report_case: Any) -> dict[str, Any]:
    driver: dict[str, Any] = sarif_log(report_case)["runs"][0]["tool"]["driver"]
    return driver


def test_the_rule_catalog_is_the_emittable_registry_in_order() -> None:
    rules = _driver(CASES[0].report)["rules"]
    assert [rule["id"] for rule in rules] == [entry.id for entry in SARIF_RULE_ENTRIES]
    held = {entry.id for entry in CONDITION_REGISTRY.values() if not entry.emittable}
    assert not held & {rule["id"] for rule in rules}


def test_the_catalog_is_emitted_whether_or_not_a_rule_fired() -> None:
    """A.3: "so that a repository's rule metadata is stable across analyses"."""
    clean = _driver(CASES[0].report)["rules"]
    failing = _driver(next(c.report for c in CASES if c.name == "wedge-failures"))["rules"]
    assert clean == failing


def test_every_rule_carries_the_metadata_appendix_a_fixes() -> None:
    for rule, entry in zip(_driver(CASES[0].report)["rules"], SARIF_RULE_ENTRIES, strict=True):
        assert entry.severity is not None and entry.claim_class is not None
        level = "warning" if entry.severity == "warning" else "error"
        copy = rule_copy(entry.id)
        assert rule["name"] == f"{entry.property_id} {entry.property_slug}"
        assert rule["shortDescription"]["text"] == copy.short_description
        assert rule["fullDescription"]["text"] == copy.full_description
        assert rule["help"]["text"] == copy.help_text
        assert rule["defaultConfiguration"]["level"] == level
        assert rule["properties"]["problem.severity"] == level
        assert rule["properties"]["gebra/claimClass"] == entry.claim_class.upper()
        assert rule["properties"]["tags"] == [
            f"property/{entry.property_slug}",
            f"claim/{entry.claim_class.upper()}",
        ]


def test_no_rule_prose_carries_claim_language() -> None:
    """A.2: the claim class lives in the property bag, never in the prose."""
    for entry in SARIF_RULE_ENTRIES:
        copy = rule_copy(entry.id)
        assert entry.claim_class is not None
        for text in (copy.short_description, copy.full_description, copy.help_text):
            assert entry.claim_class.upper() not in text


# ── A.4: one result per finding ──────────────────────────────────────────────────────────


def _emittable_findings(report: Any) -> list[Any]:
    emittable = {entry.id for entry in SARIF_RULE_ENTRIES}
    return [
        finding
        for outcome in report.properties
        if isinstance(outcome, PropertyReport)
        for finding in findings_of(outcome)
        if finding.property_condition in emittable
    ]


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.name)
def test_one_result_per_finding_in_run_order(case: Any) -> None:
    """A.4: records are never merged into one result and never dropped."""
    results = sarif_log(case.report)["runs"][0]["results"]
    findings = _emittable_findings(case.report)
    assert [result["ruleId"] for result in results] == [
        finding.property_condition for finding in findings
    ]


def test_a_result_carries_the_records_own_grade_and_class() -> None:
    report = next(case.report for case in CASES if case.name == "wedge-failures")
    results = sarif_log(report)["runs"][0]["results"]
    for result, finding in zip(results, _emittable_findings(report), strict=True):
        assert result["properties"]["gebra/severity"] == finding.severity.upper()
        assert result["properties"]["gebra/claimClass"] == finding.claim_class.upper()
        assert result["properties"]["gebra/property"] == finding.owner
        assert result["level"] == ("warning" if finding.severity == "warning" else "error")
        if finding.severity == "warning":
            assert "rank" not in result, "Appendix C fixes no WARNING rank and none is invented"
        else:
            assert result["rank"] == (100.0 if finding.severity == "fatal" else 80.0)


def test_an_advisory_is_attributed_to_its_own_property_not_its_host() -> None:
    """§3.2/A.4: an advisory riding another property's report is still its own finding."""
    report = next(case.report for case in CASES if case.name == "wedge-failures")
    results = sarif_log(report)["runs"][0]["results"]
    pairs = list(zip(results, _emittable_findings(report), strict=True))
    advisories = [(result, f) for result, f in pairs if f.origin == "advisory"]
    assert advisories
    for result, finding in advisories:
        assert finding.owner != finding.host, "an advisory rides another property's report"
        assert result["properties"]["gebra/property"] == finding.owner
        assert result["level"] == "warning"


def test_subsumed_by_rides_the_property_bag() -> None:
    report = next(case.report for case in CASES if case.name == "p01-fatal-best-effort")
    bags = [result["properties"] for result in sarif_log(report)["runs"][0]["results"]]
    assert any("gebra/subsumedBy" in bag for bag in bags)


def test_a_promoted_warning_still_exports_as_a_warning() -> None:
    """§2.3/A.2: promotion moves the gate, never the record."""
    report = next(case.report for case in CASES if case.name == "wedge-failures-strict")
    assert report.gate.promotions
    for result in sarif_log(report)["runs"][0]["results"]:
        if result["properties"]["gebra/severity"] == "WARNING":
            assert result["level"] == "warning"


def test_no_log_carries_a_held_condition_id() -> None:
    """A log may not advertise a rule for a name no validator may emit (A.3)."""
    held = {entry.id for entry in CONDITION_REGISTRY.values() if not entry.emittable}
    assert held
    for case in CASES:
        ids = {result["ruleId"] for result in sarif_log(case.report)["runs"][0]["results"]}
        assert not ids & held, case.name


def test_a_held_condition_id_is_refused_not_dropped() -> None:
    """A.4: records are "never dropped". A record carrying a held §0.4 name has no rule to
    name, so the projection refuses rather than skipping it — the disposition the module
    docstring states.

    The finding below is a *rendering* struct, not a §0.3 record: its grade is immaterial and
    asserts nothing about the registry, which pins none for a RESERVED entry. What the refusal
    fires on is the identity.
    """
    from gebra.report.findings import Finding
    from gebra.report.sarif import _results

    held = next(entry for entry in CONDITION_REGISTRY.values() if not entry.emittable)
    report = next(case.report for case in CASES if case.name == "wedge-failures")
    outcome = report.outcome_for("effect-safety")
    assert isinstance(outcome, PropertyReport)

    def _one_held_finding(_: PropertyReport) -> list[Finding]:
        return [
            Finding(
                owner=held.property_slug,
                host="effect-safety",
                origin="advisory",
                severity="warning",
                claim_class="defensible-a",
                property_condition=held.id,
                location=NodeLocation(kind="node", node="merge"),
            )
        ]

    with (
        mock.patch("gebra.report.sarif.findings_of", _one_held_finding),
        pytest.raises(ValueError, match="not emittable"),
    ):
        _results(report)


# ── A.1: the losses that must stay losses ────────────────────────────────────────────────


def test_pass_witnesses_do_not_project() -> None:
    """A.1 loss 1, checked the only way it can be: a clean run carries no results at all."""
    log = sarif_log(CASES[0].report)
    assert log["runs"][0]["results"] == []
    text = json.dumps(log)
    for payload in ("inventory", "certificate", "coverage", "claims", "effects", "caveat"):
        assert f'"{payload}"' not in text, f"a witness payload leaked into the log: {payload}"


def test_not_implemented_markers_do_not_project() -> None:
    """A.1 loss 3: the eight non-wedge properties are simply absent from a log."""
    log = json.dumps(sarif_log(CASES[0].report))
    assert "not-implemented" not in log
    assert "deferred-to-phase-1" not in log


def test_fatal_and_error_collapse_but_the_distinction_survives() -> None:
    report = next(case.report for case in CASES if case.name == "wedge-failures")
    severities = {
        (result["level"], result["properties"]["gebra/severity"])
        for result in sarif_log(report)["runs"][0]["results"]
    }
    assert ("error", "FATAL") in severities
    assert ("error", "ERROR") in severities


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.name)
def test_no_physical_location_is_fabricated(case: Any) -> None:
    """A.5: IR 1.0 has no source spans, and a wrong anchor is worse than an absent one."""
    log = json.dumps(sarif_log(case.report))
    assert "physicalLocation" not in log
    assert "primaryLocationLineHash" not in log
    assert "baselineState" not in log


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.name)
def test_every_result_carries_a_logical_location(case: Any) -> None:
    """A.5 rule 1: always, for every result."""
    for result in sarif_log(case.report)["runs"][0]["results"]:
        anchors = result["locations"][0]["logicalLocations"]
        assert len(anchors) == 1
        assert anchors[0]["fullyQualifiedName"]
        assert anchors[0]["kind"]


# ── A.6/A.7: fingerprints and run-level fields ───────────────────────────────────────────


def test_the_condition_hash_is_the_documented_function() -> None:
    import hashlib

    report = next(case.report for case in CASES if case.name == "wedge-failures")
    for result in sarif_log(report)["runs"][0]["results"]:
        fqn = result["locations"][0]["logicalLocations"][0]["fullyQualifiedName"]
        expected = hashlib.sha256(f"{result['ruleId']}\n{fqn}".encode()).hexdigest()
        assert result["partialFingerprints"]["gebraConditionHash/v1"] == expected
        assert len(expected) == 64 and expected == expected.lower()


def test_the_graph_version_fingerprint_is_carried_verbatim() -> None:
    report = next(case.report for case in CASES if case.name == "wedge-failures")
    assert report.subject is not None
    for result in sarif_log(report)["runs"][0]["results"]:
        assert result["partialFingerprints"]["gebraGraphVersion/v1"] == report.subject.graph_version


def test_run_level_fields_are_appendix_a7s() -> None:
    report = next(case.report for case in CASES if case.name == "rich-witnesses")
    run = sarif_log(report)["runs"][0]
    assert report.subject is not None
    assert run["properties"]["gebra/graphVersion"] == report.subject.graph_version
    assert run["properties"]["gebra/version"] == report.subject.version
    assert run["properties"]["gebra/exitCode"] == report.gate.exit_code
    assert run["tool"]["driver"]["name"] == "gebra"
    assert run["tool"]["driver"]["version"] == report.tool.version


def test_the_automation_id_is_the_slug_rule() -> None:
    report = next(case.report for case in CASES if case.name == "wedge-failures")
    run = sarif_log(report)["runs"][0]
    assert report.subject is not None
    assert run["automationDetails"]["id"] == (f"gebra/verify/{subject_slug(report.subject.source)}")


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("travel_booking:build_graph", "travel-booking-build-graph"),
        ("Agents/Support Triage.py", "agents-support-triage-py"),
        ("---", ""),
        ("<in-process ir>", "in-process-ir"),
    ],
)
def test_the_subject_slug_rule(source: str, expected: str) -> None:
    assert subject_slug(source) == expected


def test_a_source_that_slugs_to_nothing_derives_no_automation_id() -> None:
    """A.7 derives the id from the source; where nothing survives, none is invented."""
    from tests.report.variants import case_report

    run = sarif_log(case_report({}, source="---"))["runs"][0]
    assert "automationDetails" not in run


def test_a_clean_run_emits_an_empty_results_array_not_an_empty_file() -> None:
    log = sarif_log(CASES[0].report)
    assert log["runs"][0]["results"] == []
    assert log["runs"][0]["tool"]["driver"]["rules"]


@pytest.mark.parametrize("name", ["tool-error", "tool-error-ungateable"])
def test_a_tool_error_log_is_never_indistinguishable_from_a_clean_run(name: str) -> None:
    """A.7's MUST: an exit-2 log carries ``gebra/exitCode: 2``."""
    report = next(case.report for case in CASES if case.name == name)
    run = sarif_log(report)["runs"][0]
    assert run["results"] == []
    assert run["properties"]["gebra/exitCode"] == 2


# ── Determinism and the serialization profile ────────────────────────────────────────────


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.name)
def test_the_projection_is_deterministic(case: Any) -> None:
    assert render_sarif(case.report) == render_sarif(case.report)


def test_a_file_ends_with_one_newline_and_a_stream_does_not() -> None:
    text = render_sarif(CASES[0].report)
    assert not text.endswith("\n")
    assert render_sarif(CASES[0].report, for_file=True) == f"{text}\n"


def test_the_compact_form_carries_identical_content() -> None:
    report = next(case.report for case in CASES if case.name == "wedge-failures")
    compact = render_sarif(report, compact=True)
    assert "\n" not in compact
    assert json.loads(compact) == json.loads(render_sarif(report))


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.name)
def test_sarif_golden(case: Any) -> None:
    compare_golden(f"sarif/{case.name}.json", render_sarif(case.report, for_file=True))
