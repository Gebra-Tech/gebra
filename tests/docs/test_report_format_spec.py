"""REPORT-FORMAT-SPEC held to the envelope it wraps (card CLI-01).

The spec is a contract document, so the thing worth testing is not its prose but its
**coverage**: a §0.3 variant that exists in :mod:`gebra.verify` and has no rendering in the
spec is a hole a downstream consumer falls into, and a SARIF rule table that disagrees with
the §0.4 registry about a severity is a report that contradicts the catalog.

So this module reads the document and cross-checks it against the live models:

* every envelope model class has a row in the rendering catalog (§4);
* every closed vocabulary the envelope carries — witness-note kinds, effect regions,
  protection forms, inventory forms, not-implemented statuses — is named there too;
* the SARIF ``rules[]`` table lists exactly the **emittable** condition IDs, in registry
  order, with the severity, claim class and level the registry pins;
* the normative model stubs are syntactically valid Python that declares the classes the
  prose names;
* the exit-code contract states all three §0.2 codes.

Nothing here imports langgraph, executes anything, or opens a socket (WA-07): the test reads
one markdown file and inspects already-imported models.
"""

from __future__ import annotations

import ast
import inspect
import re
from pathlib import Path
from typing import Final, get_args

import pytest

import gebra.verify.locations as locations_module
import gebra.verify.registry as registry_module
import gebra.verify.report as report_module
import gebra.verify.witnesses as witnesses_module
from gebra.verify.base import ReportModel
from gebra.verify.conditions import CONDITION_REGISTRY, ConditionEntry
from gebra.verify.registry import NotImplementedStatus
from gebra.verify.witnesses import P06EffectRecord, Region, WitnessInventoryEntry, WitnessNoteKind

#: ``tests/docs/`` → the repository root.
REPO_ROOT: Final = Path(__file__).resolve().parents[2]

SPEC_PATH: Final = REPO_ROOT / "docs" / "specs" / "REPORT-FORMAT-SPEC.md"

#: The one severity → SARIF level collapse Appendix C fixes (FATAL and ERROR share a level).
SARIF_LEVEL: Final = {"fatal": "error", "error": "error", "warning": "warning"}

#: Appendix C fixes a rank for FATAL and ERROR only; WARNING has none, and the table says so.
SARIF_RANK: Final = {"fatal": "100.0", "error": "80.0", "warning": "—"}


@pytest.fixture(scope="module")
def spec_text() -> str:
    return SPEC_PATH.read_text(encoding="utf-8")


_HEADING = re.compile(r"^(#{1,6}) \S")


def _section(text: str, heading: str) -> str:
    """The body under ``heading``, up to the next heading of the same or a higher level.

    Fenced blocks are skipped rather than scanned: a ``#:`` doc-comment at column 0 inside a
    normative stub is not a markdown heading, and treating it as one truncated §1.2.
    """
    level = len(heading) - len(heading.lstrip("#"))
    lines = text.splitlines()
    try:
        start = lines.index(heading)
    except ValueError:  # pragma: no cover - the failure message below is the useful one
        pytest.fail(f"{SPEC_PATH.name} carries no heading {heading!r}")
    fenced = False
    for offset, line in enumerate(lines[start + 1 :], start=start + 1):
        if line.startswith("```"):
            fenced = not fenced
            continue
        if fenced:
            continue
        match = _HEADING.match(line.rstrip())
        if match is not None and len(match.group(1)) <= level:
            return "\n".join(lines[start + 1 : offset])
    return "\n".join(lines[start + 1 :])


def _flat(text: str) -> str:
    """``text`` with runs of whitespace collapsed — for prose assertions that wrap."""
    return " ".join(text.split())


def _table_rows(section: str) -> list[list[str]]:
    """The data rows of every markdown table in ``section``, cells stripped."""
    rows: list[list[str]] = []
    for line in section.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if all(set(cell) <= {"-", ":", " "} and cell for cell in cells):
            continue  # the header separator
        rows.append(cells)
    return rows


def _envelope_model_classes() -> dict[str, type[ReportModel]]:
    """Every concrete §0.3 envelope model, by class name."""
    modules = (witnesses_module, locations_module, report_module, registry_module)
    return {
        name: obj
        for module in modules
        for name, obj in vars(module).items()
        if inspect.isclass(obj)
        and issubclass(obj, ReportModel)
        and obj is not ReportModel
        and obj.__module__ == module.__name__
    }


def _code_blocks(section: str, language: str) -> list[str]:
    fence = re.compile(rf"^```{language}\n(.*?)^```", re.MULTILINE | re.DOTALL)
    return [match.group(1) for match in fence.finditer(section)]


# ── The document exists and says what it is ──────────────────────────────────────────────


def test_the_spec_is_in_the_library_repo_beside_the_code() -> None:
    """CLI-01's artifact is an in-repo contract, not a delivery-repo process document."""
    assert SPEC_PATH.is_file(), f"{SPEC_PATH} is missing"


def test_the_spec_states_it_describes_no_shipped_capability(spec_text: str) -> None:
    """WA-12: a contract spec may describe a contract, never an unbuilt capability as usable."""
    assert "not user documentation" in spec_text
    assert "WA-12" in spec_text


def test_the_spec_names_its_authorities(spec_text: str) -> None:
    for authority in ("PROPERTY-CATALOG-SPEC", "PD-015", "PD-031", "PD-012", "Appendix C"):
        assert authority in spec_text, f"{authority} is not cited anywhere in the spec"


# ── §4: every envelope variant has a rendering ───────────────────────────────────────────


def test_every_envelope_model_has_a_row_in_the_rendering_catalog(spec_text: str) -> None:
    """The card's second acceptance box, machine-checked.

    A model that exists in the envelope and is unnamed in §4 is a variant CLI-03 would have
    to invent a rendering for.
    """
    catalog = _section(spec_text, "## 4. The rendering catalog")
    missing = sorted(name for name in _envelope_model_classes() if f"`{name}`" not in catalog)
    assert not missing, f"§4 defines no rendering for: {', '.join(missing)}"


def test_every_witness_union_member_is_named_by_its_kind(spec_text: str) -> None:
    catalog = _section(spec_text, "## 4. The rendering catalog")
    for member in get_args(get_args(witnesses_module.Witness)[0]):
        kind = get_args(member.model_fields["kind"].annotation)[0]
        assert f'`kind: "{kind}"`' in catalog, f"§4 does not name the {kind!r} witness kind"


def test_every_closed_vocabulary_of_the_envelope_is_rendered(spec_text: str) -> None:
    """The literal vocabularies a renderer has to branch on, each named in §4."""
    catalog = _section(spec_text, "## 4. The rendering catalog")
    vocabularies: dict[str, tuple[str, ...]] = {
        "witness-note kind": get_args(WitnessNoteKind),
        "effect region": get_args(Region),
        "protection": get_args(P06EffectRecord.model_fields["protection"].annotation),
        "inventory form": get_args(WitnessInventoryEntry.model_fields["form"].annotation),
        "not-implemented status": get_args(NotImplementedStatus),
    }
    missing = [
        f"{label} {value!r}"
        for label, values in vocabularies.items()
        for value in values
        if f"`{value}`" not in catalog and f'"{value}"' not in catalog
    ]
    assert not missing, f"§4 does not render: {', '.join(missing)}"


def test_the_catalog_covers_all_three_surfaces(spec_text: str) -> None:
    catalog = _section(spec_text, "## 4. The rendering catalog")
    assert "does not project" in catalog, "§4 must say where the SARIF projection drops a variant"
    for surface in ("Native JSON", "Human", "SARIF"):
        assert surface in catalog


def test_the_copy_rules_pin_the_claim_class_and_witness_presence(spec_text: str) -> None:
    rules = _section(spec_text, "### 4.6 Copy rules")
    assert "claim class is always displayed" in rules
    assert "Witness-presence wording" in rules
    assert "never rendered as a pass" in rules


# ── §1/§2: the wrapper and the gate ──────────────────────────────────────────────────────


def test_the_normative_stubs_are_valid_python_declaring_the_wrapper(spec_text: str) -> None:
    stubs = _code_blocks(_section(spec_text, "### 1.2 Normative model stubs"), "python")
    assert stubs, "§1.2 carries no normative stub block"
    declared: set[str] = set()
    for block in stubs:
        tree = ast.parse(block)  # a SyntaxError here fails the test, which is the point
        declared |= {node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)}
    expected = {
        "RunReport",
        "RunReportModel",
        "Tool",
        "Subject",
        "StrictPolicy",
        "Promotion",
        "SeverityCounts",
        "ToolError",
        "GateOutcome",
    }
    assert expected <= declared, f"§1.2 declares no {sorted(expected - declared)}"


def test_the_wrapper_carries_all_thirteen_properties_in_catalog_order(spec_text: str) -> None:
    ordering = _flat(_section(spec_text, "### 1.4 Ordering, completeness and determinism"))
    assert "thirteen" in ordering
    assert "catalog order" in ordering
    assert "NotImplementedMarker" in ordering


def test_the_exit_code_contract_states_all_three_codes(spec_text: str) -> None:
    derivation = _section(spec_text, "## 2. Exit-code derivation")
    for code in ("exit_code = 0", "exit_code = 1", "exit_code = 2"):
        assert code in derivation, f"§2 does not derive {code}"
    assert "pass-with-notes" in derivation
    assert "promotion moves the gate" in derivation.lower() or "never the record" in derivation


def test_strict_promotion_reaches_every_warning_grade_carrier(spec_text: str) -> None:
    """§0.2's reach: warning failures, co-failures, advisories and warning-grade witness notes."""
    strict = _section(spec_text, "### 2.3 Strict mode")
    for carrier in ("`Failure`", "`CoFailure`", "`Advisory`", "`WitnessNote`"):
        assert carrier in strict, f"§2.3 does not say whether strict mode reaches {carrier}"


def test_snapshot_suppression_is_fatal_only(spec_text: str) -> None:
    eligibility = _section(spec_text, "### 2.5 Snapshot eligibility")
    assert "counts.fatal == 0" in eligibility
    assert "do **not** suppress recording" in eligibility


# ── Appendix A.3: the SARIF rule catalog against the §0.4 registry ───────────────────────


def _rules_table(spec_text: str) -> list[list[str]]:
    section = _section(spec_text, "### A.3 The `rules[]` catalog")
    rows = _table_rows(section)
    header, *data = rows
    assert header[0] == "Condition ID", f"unexpected A.3 table header: {header}"
    return data


def _emittable_entries() -> tuple[ConditionEntry, ...]:
    return tuple(entry for entry in CONDITION_REGISTRY.values() if entry.emittable)


def test_the_sarif_rule_catalog_lists_exactly_the_emittable_conditions(spec_text: str) -> None:
    """A rule for a name no validator may emit would advertise a check that does not exist."""
    tabled = [row[0].strip("`") for row in _rules_table(spec_text)]
    assert tabled == [entry.id for entry in _emittable_entries()]


def test_no_held_condition_id_appears_in_the_sarif_rule_catalog(spec_text: str) -> None:
    tabled = {row[0].strip("`") for row in _rules_table(spec_text)}
    held = {entry.id for entry in CONDITION_REGISTRY.values() if not entry.emittable}
    assert not (tabled & held), f"A.3 tables non-emittable ids: {sorted(tabled & held)}"


def test_every_sarif_rule_row_matches_the_registry(spec_text: str) -> None:
    """Severity, claim class, level and rank are the §0.4 registry's — never restated by hand."""
    for row, entry in zip(_rules_table(spec_text), _emittable_entries(), strict=True):
        condition_id, rule_name, level, rank, severity, claim_class, short = row
        assert entry.severity is not None and entry.claim_class is not None
        assert condition_id == f"`{entry.id}`"
        assert rule_name == f"{entry.property_id} {entry.property_slug}"
        assert level == f"`{SARIF_LEVEL[entry.severity]}`"
        assert rank == SARIF_RANK[entry.severity]
        assert severity == entry.severity.upper()
        assert claim_class == entry.claim_class.upper()
        assert short, f"{entry.id} has no shortDescription text"


def test_the_projection_states_what_it_loses(spec_text: str) -> None:
    losses = _section(spec_text, "### A.1 Scope and the losses it accepts")
    assert "Pass witnesses do not map" in losses
    assert "FATAL and ERROR collapse" in losses
    assert "Not-implemented markers do not map" in losses


def test_the_physical_location_gap_is_recorded_honestly(spec_text: str) -> None:
    """Phase-0 has no source spans; the spec must say so rather than fabricate an anchor."""
    gap = _section(spec_text, "### A.5 Locations, and the physical-anchor gap")
    assert "no source anchors" in gap.lower()
    assert "Fabricating" in gap


# ── §6: the audit-export reconciliation the card asks for ────────────────────────────────


def test_the_audit_export_profile_ratifies_one_schema(spec_text: str) -> None:
    profile = _section(spec_text, "## 6. The audit-export profile")
    assert "reports/<version>.report.json" in profile
    assert "SD-07 defines no export schema of its own" in profile
    assert '`"snapshot"`' in profile


def test_the_audit_export_path_is_the_one_the_store_computes(spec_text: str) -> None:
    """The path is PD-012's; the spec must not mint a second one."""
    from gebra.store.store import REPORT_SUFFIX, REPORTS_DIRNAME

    profile = _section(spec_text, "## 6. The audit-export profile")
    assert f"{REPORTS_DIRNAME}/<version>{REPORT_SUFFIX}" in profile


def test_consumers_have_stated_obligations(spec_text: str) -> None:
    obligations = _section(spec_text, "## 7. Conformance obligations")
    for card in ("CLI-03", "VAL-11", "SD-07", "TE-07", "CLI-07"):
        assert card in obligations, f"§7 states no obligation for {card}"
