"""CLI-03 acceptance box 1 — every variant renders, and *every* means every (card CLI-03).

"Every wedge witness/failure variant renders without error (golden-tested)" is a claim about
the envelope, not about a sample of it. So this module does not trust the catalog in
``variants.py`` to be complete: it enumerates the live models — every concrete §0.3 and §1.2
class, and every closed vocabulary the envelope branches on — and fails when a variant is
reachable in the envelope and absent from the catalog. The same enumeration
``tests/docs/test_report_format_spec.py`` uses to hold the *spec* complete now holds the
*renderer's evidence* complete, which is the pair CLI-01 §7 asks for.

Rendering itself is then checked on all three surfaces for every case, with the goldens in
``test_human.py``/``test_sarif.py``/``test_native.py`` pinning what was rendered.

Nothing here executes a workflow node, calls a model or opens a socket (WA-07).
"""

from __future__ import annotations

import inspect
from typing import Any, Final, get_args

import pytest

import gebra.verify.locations as locations_module
import gebra.verify.registry as registry_module
import gebra.verify.report as report_module
import gebra.verify.run as run_module
import gebra.verify.witnesses as witnesses_module
from gebra.report import REPORT_FORMATS, ReportFormat, render
from gebra.verify.base import ReportModel
from gebra.verify.registry import NotImplementedStatus
from gebra.verify.run import PROMOTION_ORIGINS
from gebra.verify.witnesses import P06EffectRecord, Region, WitnessInventoryEntry, WitnessNoteKind
from tests.report.variants import CASES

#: The bases are not variants; every other envelope/run model is.
_ABSTRACT: Final[frozenset[str]] = frozenset({"ReportModel", "RunReportModel"})


def _model_classes() -> dict[str, type[ReportModel]]:
    """Every concrete envelope (§0.3) and run-level (§1.2) model, by class name."""
    modules = (witnesses_module, locations_module, report_module, registry_module, run_module)
    return {
        name: obj
        for module in modules
        for name, obj in vars(module).items()
        if inspect.isclass(obj)
        and issubclass(obj, ReportModel)
        and name not in _ABSTRACT
        and obj.__module__ == module.__name__
    }


def _walk(value: Any) -> set[type]:
    """Every model class reachable from ``value``."""
    seen: set[type] = set()
    if isinstance(value, ReportModel):
        seen.add(type(value))
        for name in type(value).model_fields:
            seen |= _walk(getattr(value, name))
    elif isinstance(value, tuple):
        for item in value:
            seen |= _walk(item)
    return seen


def _rendered_classes() -> set[type]:
    classes: set[type] = set()
    for case in CASES:
        classes |= _walk(case.report)
    return classes


def _catalog_values(reader: Any) -> set[Any]:
    """Every value ``reader`` extracts from any model reachable from any case."""
    values: set[Any] = set()
    for case in CASES:
        for model in _walk_instances(case.report):
            found = reader(model)
            if found is not None:
                values.add(found)
    return values


def _walk_instances(value: Any) -> list[ReportModel]:
    instances: list[ReportModel] = []
    if isinstance(value, ReportModel):
        instances.append(value)
        for name in type(value).model_fields:
            instances.extend(_walk_instances(getattr(value, name)))
    elif isinstance(value, tuple):
        for item in value:
            instances.extend(_walk_instances(item))
    return instances


def _field_values(field: str) -> set[Any]:
    return _catalog_values(lambda model: getattr(model, field, None))


# ── The catalog is complete against the live models ──────────────────────────────────────


def test_every_envelope_and_run_model_is_rendered_by_some_case() -> None:
    """A model class no case carries is a variant the acceptance box does not cover."""
    rendered = {klass.__name__ for klass in _rendered_classes()}
    missing = sorted(name for name in _model_classes() if name not in rendered)
    assert not missing, (
        "no catalog case carries: "
        + ", ".join(missing)
        + " — add one to tests/report/variants.py rather than narrowing the claim"
    )


@pytest.mark.parametrize("kind", get_args(WitnessNoteKind))
def test_every_witness_note_kind_is_rendered(kind: str) -> None:
    assert kind in _field_values("kind")


@pytest.mark.parametrize("region", get_args(Region))
def test_every_effect_region_is_rendered(region: str) -> None:
    assert region in _field_values("region")


@pytest.mark.parametrize(
    "protection", get_args(P06EffectRecord.model_fields["protection"].annotation)
)
def test_every_protection_form_is_rendered(protection: str) -> None:
    assert protection in _field_values("protection")


@pytest.mark.parametrize("form", get_args(WitnessInventoryEntry.model_fields["form"].annotation))
def test_every_inventory_form_is_rendered(form: str) -> None:
    assert form in _field_values("form")


def test_the_vacuous_form_c_carrier_is_rendered() -> None:
    """§4.3's "form (c) with ``discharges: []``" row — declared content, no finding implied."""
    assert () in _field_values("discharges")


@pytest.mark.parametrize("status", get_args(NotImplementedStatus))
def test_every_not_implemented_status_is_rendered(status: str) -> None:
    """Both §4.2 marker rows.

    ``not-yet-implemented`` is the marker for a **wedge** slug with no registered validator, and
    a run in that state is exit 2 with no outcomes at all (§1.4 rule 2) — so ``verify()`` never
    produces a report carrying one, while §4.2 still gives it a rendering and a consumer loading
    a report from another build can meet one. The catalog carries that report, validated rather
    than constructed.
    """
    assert status in _field_values("status")


@pytest.mark.parametrize("origin", PROMOTION_ORIGINS)
def test_promotion_origins_are_covered_or_unreachable(origin: str) -> None:
    """§2.3's four origins. ``verify()`` assembles no advisories (§3.2), and an advisory is
    always WARNING-grade, so all four are reachable through a canned record — the catalog
    carries a promoted advisory, co-failure, failure and witness note."""
    origins = {promotion.origin for case in CASES for promotion in case.report.gate.promotions}
    assert origin in origins


@pytest.mark.parametrize("outcome", ("pass", "pass-with-notes", "fail", "tool-error"))
def test_every_gate_outcome_is_rendered(outcome: str) -> None:
    assert outcome in {case.report.gate.outcome for case in CASES}


@pytest.mark.parametrize("stage", ("dispatch",))
def test_the_reachable_tool_error_stages_are_rendered(stage: str) -> None:
    """``input``/``extraction``/``ir-validation`` are the CLI's and the extractor's to reach
    (CLI-SPEC §2.6); ``verify()`` reaches ``dispatch`` and ``ir-validation`` only, and the
    renderer branches on none of them — it shows ``error.stage`` as carried."""
    stages = {case.report.error.stage for case in CASES if case.report.error is not None}
    assert stage in stages


# ── Every case renders, on every surface ─────────────────────────────────────────────────


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.name)
@pytest.mark.parametrize("report_format", REPORT_FORMATS)
def test_every_case_renders_on_every_surface(case: Any, report_format: ReportFormat) -> None:
    """The acceptance box, stated directly: no variant raises, and none renders as nothing."""
    text = render(case.report, report_format)
    assert text.strip(), f"{case.name} rendered empty on {report_format}"


def test_render_refuses_an_unknown_surface() -> None:
    with pytest.raises(ValueError, match="three surfaces"):
        render(CASES[0].report, "yaml")  # type: ignore[arg-type]
