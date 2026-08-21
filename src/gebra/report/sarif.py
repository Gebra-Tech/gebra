"""The SARIF 2.1.0 projection — REPORT-FORMAT-SPEC Appendix A.

`--format sarif` emits a **lossy, findings-only** projection of the run report: derived from
it, never round-tripped (§0.1, A.1). Three losses are structural and are implemented as
refusals rather than as gaps to fill later:

1. **Pass witnesses do not map** (A.1 loss 1). A witness has no SARIF home, and this module
   never smuggles one through a property bag — the native report owns that schema.
2. **FATAL and ERROR collapse** to ``level: "error"`` (A.1 loss 2). The distinction survives
   in ``result.properties["gebra/severity"]``, which is why that bag member exists.
3. **Not-implemented markers do not map** (A.1 loss 3). "A rule with no result would advertise
   a check that did not run", so the eight non-wedge properties are simply absent from a log.

Two more absences are deliberate. There is **no ``physicalLocation``** on any result: IR 1.0
carries no source spans, and A.5 refuses to fabricate an artifact URI and a line — a wrong
anchor moves a baseline matcher's fingerprints in ways it reads as real churn. And there is no
``primaryLocationLineHash``, which A.6 emits "only when a ``physicalLocation`` was emitted".
``result.baselineState`` is likewise absent: A.2 emits it "only when the run actually has a
baseline to compare against", and a ``verify`` run has none.

What *is* always emitted: the ``rules[]`` catalog of every emittable §0.4 condition in registry
order whether or not it produced a result (A.3), ``logicalLocations`` on every result (A.5
rule 1), and ``results: []`` on a clean run so a consumer closes fixed alerts (A.7). A
tool-error run carries ``run.properties["gebra/exitCode"]: 2``, so an exit-2 log is never
indistinguishable from a clean one.

One refusal rather than a fourth loss: a finding whose condition ID is registered but **not
emittable** has no rule in the A.3 catalog, and A.4 makes dropping a record the failure mode.
``verify()`` cannot produce one — the §0.4 emission constructors refuse a held name — so this
module raises instead of quietly skipping it.

Nothing here imports langgraph, executes anything, or opens a socket (WA-07): the input is a
:class:`~gebra.verify.run.RunReport` and the output is JSON data.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Final

from gebra.report.anchors import LogicalAnchor, location_evidence, location_phrase, logical_anchor
from gebra.report.findings import Finding, findings_of
from gebra.report.rules import SARIF_RULE_ENTRIES, rule_copy
from gebra.verify.base import ClaimClass, Severity
from gebra.verify.conditions import ConditionEntry
from gebra.verify.report import PropertyReport
from gebra.verify.run import RunReport

__all__ = [
    "SARIF_SCHEMA_URI",
    "SARIF_VERSION",
    "render_sarif",
    "sarif_log",
    "subject_slug",
]

#: The ``$schema`` A.7 fixes. It is a pointer for consumers, not a fetch this package makes.
SARIF_SCHEMA_URI: Final = "https://json.schemastore.org/sarif-2.1.0.json"

#: The one SARIF version this projection targets (A.7).
SARIF_VERSION: Final = "2.1.0"

#: The severity → ``level`` collapse of A.1 loss 2 / A.2.
_LEVEL: Final[dict[Severity, str]] = {"fatal": "error", "error": "error", "warning": "warning"}

#: A.2/A.3 fix a rank for FATAL and ERROR only; Appendix C fixes none for WARNING and none is
#: invented here.
_RANK: Final[dict[Severity, float]] = {"fatal": 100.0, "error": 80.0}

#: A.7's ``<subject-slug>`` rule: lowercase, every run of characters outside ``[a-z0-9]``
#: replaced by a single ``-``, leading/trailing ``-`` trimmed.
_NON_SLUG = re.compile(r"[^a-z0-9]+")


def subject_slug(source: str) -> str:
    """A.7's deterministic slug of ``subject.source``; ``""`` when nothing survives it."""
    return _NON_SLUG.sub("-", source.lower()).strip("-")


def _display_class(claim_class: ClaimClass) -> str:
    """The uppercase display form A.2 fixes for the bags and tags — a one-way convention."""
    return claim_class.upper()


def _text(value: str) -> dict[str, str]:
    return {"text": value}


def _rule_object(entry: ConditionEntry) -> dict[str, Any]:
    """One ``reportingDescriptor`` of the A.3 catalog."""
    assert entry.severity is not None and entry.claim_class is not None  # §0.4 emittable row
    copy = rule_copy(entry.id)
    level = _LEVEL[entry.severity]
    return {
        "id": entry.id,
        "name": f"{entry.property_id} {entry.property_slug}",
        "shortDescription": _text(copy.short_description),
        "fullDescription": _text(copy.full_description),
        "help": _text(copy.help_text),
        "defaultConfiguration": {"level": level},
        "properties": {
            "tags": [
                f"property/{entry.property_slug}",
                f"claim/{_display_class(entry.claim_class)}",
            ],
            "gebra/claimClass": _display_class(entry.claim_class),
            "problem.severity": level,
        },
    }


def _logical_location(anchor: LogicalAnchor) -> dict[str, Any]:
    location: dict[str, Any] = {"kind": anchor.kind}
    if anchor.name is not None:
        location["name"] = anchor.name
    location["fullyQualifiedName"] = anchor.fully_qualified_name
    return location


def _condition_hash(condition: str, fully_qualified_name: str) -> str:
    """A.6: SHA-256 over the condition ID and the canonical logical FQN, joined by one ``\\n``."""
    digest = hashlib.sha256(f"{condition}\n{fully_qualified_name}".encode())
    return digest.hexdigest()


def _message(finding: Finding, entry: ConditionEntry) -> str:
    """A.4's finding-first sentence: what was found, where, and at which grade.

    It carries no claim language — A.2 keeps the claim class in the property bag — and no
    remediation, which A.3 puts in ``rule.help``.
    """
    sentence = (
        f"{rule_copy(entry.id).short_description} — {location_phrase(finding.location)}. "
        f"{entry.property_id} {entry.property_slug}, {finding.severity.upper()}."
    )
    if finding.severity == "fatal":
        sentence += " No snapshot is recorded for a run carrying it (PROPERTY-CATALOG-SPEC §0.2)."
    return sentence


def _result(finding: Finding, entry: ConditionEntry, graph_version: str) -> dict[str, Any]:
    """One SARIF ``result`` per finding (A.4): the primary, each co-failure, each advisory."""
    anchor = logical_anchor(finding.location)
    result: dict[str, Any] = {
        "ruleId": entry.id,
        "level": _LEVEL[finding.severity],
    }
    rank = _RANK.get(finding.severity)
    if rank is not None:
        result["rank"] = rank
    result["message"] = _text(_message(finding, entry))
    result["locations"] = [{"logicalLocations": [_logical_location(anchor)]}]
    if anchor.related:
        result["relatedLocations"] = [
            {"logicalLocations": [{"kind": "function", "fullyQualifiedName": name}]}
            for name in anchor.related
        ]
    result["partialFingerprints"] = {
        "gebraConditionHash/v1": _condition_hash(entry.id, anchor.fully_qualified_name),
        "gebraGraphVersion/v1": graph_version,
    }
    properties: dict[str, Any] = {
        "gebra/severity": finding.severity.upper(),
        "gebra/claimClass": _display_class(finding.claim_class),
        "gebra/property": finding.owner,
    }
    if finding.subsumed_by is not None:
        properties["gebra/subsumedBy"] = finding.subsumed_by
    properties.update(location_evidence(finding.location))
    properties.update(finding.evidence)
    result["properties"] = properties
    return result


def _results(report: RunReport) -> list[dict[str, Any]]:
    """Every finding of the run, in the report's own traversal order (A.4).

    Catalog order by property, then each property's own record order — so two runs over one IR
    produce byte-identical logs. A run whose subject is absent reached no verdict and carries
    no findings, which is why the digest below is only read where one exists.
    """
    subject = report.subject
    if subject is None:
        return []
    by_condition = {entry.id: entry for entry in SARIF_RULE_ENTRIES}
    results: list[dict[str, Any]] = []
    for outcome in report.properties:
        if not isinstance(outcome, PropertyReport):
            continue  # A.1 loss 3: a marker advertises no rule and produces no result
        for finding in findings_of(outcome):
            entry = by_condition.get(finding.property_condition)
            if entry is None:
                # A.4: records are "never merged into one result and never dropped". A held
                # §0.4 name can be *recorded* by a loaded report (PC-6's fixture duty) but
                # never emitted by a validator, so it has no rule in the A.3 catalog and no
                # result the log could carry — and dropping it silently is the failure mode
                # A.4 names. It is unreachable from `verify()`, whose emission constructors
                # refuse a non-emittable ID, so refusing here costs nothing and says so.
                raise ValueError(
                    f"{finding.property_condition!r} is registered but not emittable (§0.4), "
                    f"so the A.3 rule catalog carries no rule for it and this log would have "
                    f"to drop the {finding.origin} on {finding.host}. A run report from "
                    f"gebra.verify.verify() never carries one; a report loaded from another "
                    f"build may, and it has no SARIF projection."
                )
            results.append(_result(finding, entry, subject.graph_version))
    return results


def sarif_log(report: RunReport) -> dict[str, Any]:
    """The SARIF 2.1.0 log for ``report`` — Appendix A, as JSON data.

    Deterministic: given the same run report, the same log, byte for byte, with
    ``tool.driver.version`` the only environment-dependent value (§1.3).
    """
    subject = report.subject
    run_properties: dict[str, Any] = {}
    if subject is not None:
        run_properties["gebra/graphVersion"] = subject.graph_version
        if subject.version is not None:
            run_properties["gebra/version"] = subject.version
    run_properties["gebra/exitCode"] = report.gate.exit_code

    run: dict[str, Any] = {
        "tool": {
            "driver": {
                "name": report.tool.name,
                "version": report.tool.version,
                "rules": [_rule_object(entry) for entry in SARIF_RULE_ENTRIES],
            }
        }
    }
    slug = subject_slug(subject.source) if subject is not None else ""
    if slug:
        # A.7 derives the id from `subject.source`; a source that slugs to nothing derives no
        # id, and omitting the optional object is honest where inventing one would not be.
        run["automationDetails"] = {"id": f"gebra/verify/{slug}"}
    run["results"] = _results(report)
    run["properties"] = run_properties
    return {"$schema": SARIF_SCHEMA_URI, "version": SARIF_VERSION, "runs": [run]}


def render_sarif(report: RunReport, *, compact: bool = False, for_file: bool = False) -> str:
    """The SARIF log as JSON text, under the same serialization profile as §1.5.

    Two-space indentation matching ``.editorconfig``, non-ASCII kept as itself, and the
    trailing-newline rule of §1.5: a file ends with one, a stream is not given one.
    """
    text = json.dumps(
        sarif_log(report),
        indent=None if compact else 2,
        ensure_ascii=False,
        allow_nan=False,
    )
    return f"{text}\n" if for_file else text
