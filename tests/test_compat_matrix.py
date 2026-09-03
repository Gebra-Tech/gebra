"""The tested matrix: the 13 CI cells and the per-cell pins they install (GOV-04).

Normative authority: VERSION-COMPAT §1 (the ratified supported ranges and the three frozen
pair cells), §3 ("The matrix, exactly": Python {3.10, 3.11, 3.12, 3.13} x three pair cells =
12 blocking cells, plus one ``--pre`` cell = 13; the ``--pre`` cell runs
``xfail(strict=False)``), §4 (the per-cell pins, "including the transitively resolved
pydantic", are recorded in the ``gebra[compat-test]`` extra) and SOW §4 (every cell runs
``ruff check`` + ``ruff format --check`` + ``mypy --strict`` + ``pytest``). The pin *values*
are GOV-D3's, recorded in PD-030 §C3 and **FROZEN at the GOV-08 F2 freeze** (gate G7,
2026-08-31, citing green drift-suite run 33336160085).

The point of holding both halves here is that they can only drift together: the workflow
names a cell number and nothing else, so the pins it installs are the ones in
``pyproject.toml``, and these tests fail if either the cell count, the pin values, or the
gates a cell runs change without the other side moving with them.

These tests read and parse files only — TOML, YAML, and one import of
``gebra.extraction.compat`` for the classification cross-check. Nothing here builds,
installs, imports a workflow, executes a node, calls an LLM, or opens a socket (WA-07).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

from gebra.extraction.compat import CompatClass, SubstrateVersions, classify_substrate

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - exercised on the 3.10 matrix cells
    import tomli as tomllib

REPO_ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = REPO_ROOT / "pyproject.toml"
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"

#: §3's matrix, exactly: four tested Python minors x three frozen pair cells, +1 `--pre`.
TESTED_PYTHONS = ("3.10", "3.11", "3.12", "3.13")
FROZEN_CELLS = ("1", "2", "3")
BLOCKING_CELL_COUNT = len(TESTED_PYTHONS) * len(FROZEN_CELLS)
TOTAL_CELL_COUNT = BLOCKING_CELL_COUNT + 1

#: PD-030 §C3's pin table, frozen at F2 (GOV-08) — the substrate axis of each frozen cell.
#: The full pin set per cell lives in ``pyproject.toml``; these are the values a reviewer
#: checks against the PD and the freeze record, and the three the §3 rule and §4's
#: "including the transitively resolved pydantic" name directly.
FROZEN_PINS: dict[str, dict[str, str]] = {
    "1": {"langgraph": "1.0.10", "langchain-core": "1.1.3", "pydantic": "2.13.4"},
    "2": {"langgraph": "1.1.10", "langchain-core": "1.3.3", "pydantic": "2.13.4"},
    "3": {"langgraph": "1.2.10", "langchain-core": "1.5.3", "pydantic": "2.13.4"},
}

#: A2 §1 / §4: yanked releases are excluded by the matrix pins, never by the metadata range
#: (a version range cannot exclude a point version).
YANKED = {"langgraph": ("1.1.7", "1.2.3")}

GATES = {
    "ruff check": re.compile(r"\bruff check\b"),
    "ruff format --check": re.compile(r"\bruff format --check\b"),
    "mypy": re.compile(r"(?m)^\s*mypy\b"),
    "pytest": re.compile(r"\bpytest\b"),
}

pytestmark = pytest.mark.skipif(
    not PYPROJECT.is_file(),
    reason="matrix tests describe the source tree; no pyproject.toml beside tests/",
)


@pytest.fixture(scope="module")
def pyproject() -> dict[str, Any]:
    with PYPROJECT.open("rb") as handle:
        data: dict[str, Any] = tomllib.load(handle)
    return data


@pytest.fixture(scope="module")
def extras(pyproject: dict[str, Any]) -> dict[str, list[str]]:
    optional: dict[str, list[str]] = pyproject["project"]["optional-dependencies"]
    return optional


@pytest.fixture(scope="module")
def workflow() -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))
    return data


def _pins(requirements: list[str]) -> dict[str, str]:
    """The ``name == version`` pins in a requirement list, keyed by distribution name."""
    pinned: dict[str, str] = {}
    for requirement in requirements:
        name, separator, version = requirement.partition("==")
        if separator:
            pinned[name.strip()] = version.strip()
    return pinned


def _version_triple(version: str) -> tuple[int, int, int]:
    """``major[.minor[.micro]]`` as a comparable triple; missing components read as 0."""
    parts = [int(part) for part in version.split(".")]
    parts += [0] * (3 - len(parts))
    major, minor, micro = parts[:3]
    return major, minor, micro


def _job_run_steps(job: dict[str, Any]) -> list[str]:
    return [step["run"] for step in job["steps"] if "run" in step]


# ── The extra: per-cell pins (VERSION-COMPAT §4) ──


@pytest.mark.parametrize("cell", FROZEN_CELLS)
def test_every_frozen_cell_has_its_own_pin_extra(extras: dict[str, list[str]], cell: str) -> None:
    """One installable extra per §1 pair cell.

    A single extra cannot hold the matrix: the three cells pin the same distributions to
    different versions, so ``langgraph==1.0.10`` and ``langgraph==1.2.10`` in one
    requirement set is unsatisfiable by construction. The extra §4 names is therefore
    realized as one per cell, and `test_compat_test_extra_is_the_newest_frozen_cell` keeps
    the bare name pointing at a real cell rather than at nothing.
    """
    assert f"compat-cell-{cell}" in extras


@pytest.mark.parametrize("cell", FROZEN_CELLS)
def test_each_cell_pins_the_frozen_substrate(extras: dict[str, list[str]], cell: str) -> None:
    """The pin values are PD-030 §C3's, frozen at F2, incl. the transitive pydantic (§4).

    pydantic is pinned *per cell* rather than once for the matrix even though all three
    resolve to the same version today: PD-030 §C3 records that as "a property of today's
    resolution, not a durable one" — it changes the moment a cell's langchain-core caps
    pydantic, and drift test 7's soft full-dict assertion reads exactly this axis.
    """
    pinned = _pins(extras[f"compat-cell-{cell}"])
    for distribution, version in FROZEN_PINS[cell].items():
        assert pinned.get(distribution) == version, (
            f"cell {cell} must pin {distribution}=={version} (PD-030 §C3, frozen at GOV-08/F2 — "
            "changing it is a §4 ceiling extension with its own drift-suite run citation)"
        )


def test_cell_one_bounds_the_transitive_checkpoint(extras: dict[str, list[str]]) -> None:
    """PD-030 Q1/C1: without this bound cell 1 is red, and no resolver can prevent it.

    ``langgraph-checkpoint`` 4.1.0 changed a module-level ``Reviver()`` to
    ``Reviver(allowed_objects="core")``; that parameter first exists in the langchain-core
    1.2 line, so an unbounded cell 1 floats to 4.1.1 and dies at ``import langgraph.graph``.
    Checkpoint declares only ``langchain-core>=0.2.38`` and langgraph 1.0.10 declares
    ``langgraph-checkpoint<5.0.0`` — both satisfied by the failing resolution, which is why
    the bound is a recorded decision rather than something the resolver could find.
    """
    assert _pins(extras["compat-cell-1"]).get("langgraph-checkpoint") == "4.0.3"


@pytest.mark.parametrize("cell", FROZEN_CELLS)
def test_cell_pins_are_exact(extras: dict[str, list[str]], cell: str) -> None:
    """§3: per-cell pins resolve *deterministically*. A range is not a pin."""
    loose = [
        requirement
        for requirement in extras[f"compat-cell-{cell}"]
        if "==" not in requirement or any(op in requirement for op in ("<", ">", "!", "~", ","))
    ]
    assert loose == [], f"cell {cell} carries non-exact requirements: {loose}"


@pytest.mark.parametrize("cell", FROZEN_CELLS)
def test_no_cell_pins_a_yanked_release(extras: dict[str, list[str]], cell: str) -> None:
    """§4: yanked releases (langgraph 1.1.7, 1.2.3) are excluded by the pins themselves."""
    pinned = _pins(extras[f"compat-cell-{cell}"])
    for distribution, yanked_versions in YANKED.items():
        assert pinned.get(distribution) not in yanked_versions


@pytest.mark.parametrize("cell", FROZEN_CELLS)
def test_cell_pins_stay_inside_the_declared_metadata_range(
    pyproject: dict[str, Any], extras: dict[str, list[str]], cell: str
) -> None:
    """The tested matrix lives inside the installability envelope, never outside it.

    §4 keeps the two apart in the other direction — an in-range pairing is not thereby
    claimed tested — but a *tested* pairing that the package's own metadata refuses to
    install would be untestable by anyone installing gebra normally.
    """
    declared = {
        requirement.split(">=")[0].strip(): requirement
        for requirement in pyproject["project"]["dependencies"]
    }
    pinned = _pins(extras[f"compat-cell-{cell}"])
    for distribution in ("langgraph", "langchain-core", "pydantic"):
        assert distribution in declared, f"{distribution} is not a declared dependency"
        floor, ceiling = re.findall(r"[<>]=?([\d.]+)", declared[distribution])
        assert _version_triple(floor) <= _version_triple(pinned[distribution])
        assert _version_triple(pinned[distribution]) < _version_triple(ceiling)


def test_compat_test_extra_is_the_newest_frozen_cell(extras: dict[str, list[str]]) -> None:
    """``pip install "gebra[compat-test]"`` installs a real cell, not nothing.

    §4 names one ``compat-test`` extra; the matrix needs three. The bare name resolves to
    cell 3 — the newest frozen pair, the substrate line the committed ``uv.lock`` already
    tracks — spelled out verbatim rather than as a self-referential
    ``gebra[compat-cell-3]`` requirement, because a self-reference invites the resolver to
    look for gebra on an index rather than in this tree. This test is what keeps the
    duplication honest.
    """
    assert extras["compat-test"] == extras["compat-cell-3"]


@pytest.mark.parametrize("cell", FROZEN_CELLS)
def test_each_cell_is_a_tested_pairing_by_the_runtime_check(
    extras: dict[str, list[str]], cell: str
) -> None:
    """Cross-check against EX-12: what CI installs is what ``extract()`` calls tested.

    ``gebra.extraction.compat`` classifies against §1's *bands*; these pins come from §3's
    resolution *rule*. They are separately derived and must agree — a pin that made
    ``extract()`` warn :class:`GebraVersionWarning` on the very substrate CI tests would
    mean one of the two readings of §1 is wrong.
    """
    pinned = _pins(extras[f"compat-cell-{cell}"])
    for python in TESTED_PYTHONS:
        major, minor = (int(part) for part in python.split("."))
        versions = SubstrateVersions(
            python=(major, minor),
            langgraph=_version_triple(pinned["langgraph"]),
            langchain_core=_version_triple(pinned["langchain-core"]),
            langgraph_raw=pinned["langgraph"],
            langchain_core_raw=pinned["langchain-core"],
        )
        assert classify_substrate(versions) is CompatClass.TESTED


def test_the_three_cells_are_distinct_pairings(extras: dict[str, list[str]]) -> None:
    """Three cells, three substrates — §1's pair matrix, not one substrate three times."""
    pairs = {
        (
            _pins(extras[f"compat-cell-{cell}"])["langgraph"],
            _pins(extras[f"compat-cell-{cell}"])["langchain-core"],
        )
        for cell in FROZEN_CELLS
    }
    assert len(pairs) == len(FROZEN_CELLS)


def test_the_pins_are_marked_frozen_with_the_freeze_citation() -> None:
    """PD-030 decision item 7, second half: GOV-08 removed the candidate marker and the
    frozen marker cites the green drift-suite run (F2, gate G7).

    Read as text on purpose — the marker is a comment, and a comment is exactly where
    someone about to mistake the nature of these pins is looking.
    """
    text = PYPROJECT.read_text(encoding="utf-8")
    assert "CANDIDATE pins, not frozen" not in text
    assert "FROZEN pins" in text
    assert "33336160085" in text, "the freeze must cite its green drift-suite run"
    assert "PD-030" in text and "GOV-08" in text


# ── The workflow: 13 cells, four gates each (VERSION-COMPAT §3, SOW §4) ──


def test_the_matrix_is_four_pythons_by_three_cells(workflow: dict[str, Any]) -> None:
    """§3 "The matrix, exactly": 4 x 3 = 12 blocking cells."""
    matrix = workflow["jobs"]["test-matrix"]["strategy"]["matrix"]
    assert tuple(matrix["python-version"]) == TESTED_PYTHONS
    assert tuple(matrix["cell"]) == FROZEN_CELLS
    assert len(matrix["python-version"]) * len(matrix["cell"]) == BLOCKING_CELL_COUNT


def test_the_matrix_is_thirteen_cells_in_total(workflow: dict[str, Any]) -> None:
    """§3: 12 blocking cells plus **one** ``--pre`` cell — and the 13th is a single cell."""
    pre = workflow["jobs"]["test-matrix-pre"]
    assert "strategy" not in pre, "the --pre cell is one cell, never a matrix"
    matrix = workflow["jobs"]["test-matrix"]["strategy"]["matrix"]
    assert len(matrix["python-version"]) * len(matrix["cell"]) + 1 == TOTAL_CELL_COUNT


def test_a_red_cell_never_cancels_the_others(workflow: dict[str, Any]) -> None:
    """A matrix that stops at its first red cell cannot report a compatibility surface."""
    assert workflow["jobs"]["test-matrix"]["strategy"]["fail-fast"] is False


def test_the_matrix_installs_the_cells_pins_from_the_extra(workflow: dict[str, Any]) -> None:
    """The workflow names a cell number; the pins stay in ``pyproject.toml``.

    This is what makes the two halves of this file inseparable: there is nowhere else for a
    CI cell's substrate to come from, so a §4 ceiling extension re-resolves in a
    ``pyproject.toml`` edit and nothing else (plus its drift-suite run citation, per the
    F2 freeze discipline).
    """
    steps = _job_run_steps(workflow["jobs"]["test-matrix"])
    assert any("compat-cell-${{ matrix.cell }}" in step for step in steps)


@pytest.mark.parametrize("gate", sorted(GATES))
def test_every_blocking_cell_runs_every_gate(workflow: dict[str, Any], gate: str) -> None:
    """SOW §4: each cell runs ruff check + format-check + mypy --strict + pytest."""
    steps = _job_run_steps(workflow["jobs"]["test-matrix"])
    assert any(GATES[gate].search(step) for step in steps), f"the matrix cells do not run {gate}"


@pytest.mark.parametrize("gate", sorted(GATES))
def test_the_pre_cell_runs_every_gate_too(workflow: dict[str, Any], gate: str) -> None:
    """The 13th cell is an early warning over the same gates, not a reduced smoke test."""
    steps = _job_run_steps(workflow["jobs"]["test-matrix-pre"])
    assert any(GATES[gate].search(step) for step in steps), f"the --pre cell does not run {gate}"


def test_the_pre_cell_is_non_blocking(workflow: dict[str, Any]) -> None:
    """§3: on the ``--pre`` cell only, failures never block — ``xfail(strict=False)``.

    Job-level ``continue-on-error`` is that semantics in CI's vocabulary: the job still goes
    red in the checks list (strict=False xfails are *reported*, not hidden), and the run is
    not blocked by it.
    """
    assert workflow["jobs"]["test-matrix-pre"]["continue-on-error"] is True


def test_no_blocking_cell_is_allowed_to_fail(workflow: dict[str, Any]) -> None:
    """§3: the twelve frozen cells block. Nothing downgrades them quietly.

    Checked at both levels — a job-level ``continue-on-error`` and a step-level one on any
    gate would each turn a red cell into a passing run.
    """
    job = workflow["jobs"]["test-matrix"]
    assert "continue-on-error" not in job
    assert all("continue-on-error" not in step for step in job["steps"])


def test_the_pre_cell_resolves_prereleases_and_pins_nothing(workflow: dict[str, Any]) -> None:
    """§3: ``pip install --pre`` of both named packages; PD-030 §C4: never pinned.

    Pinning this cell's *substrate* would delete the early warning it exists to give. (Its
    dev toolchain resolves under the freeze-time constraints since GOV-08 — asserted in
    ``tests/test_matrix_constraints.py`` — which pins no substrate-family member the cells
    diverge on.)
    """
    steps = _job_run_steps(workflow["jobs"]["test-matrix-pre"])
    assert any(
        "--pre" in step and "langgraph" in step and "langchain-core" in step for step in steps
    )
    assert not any("compat-cell" in step for step in steps)


def test_the_pre_cell_runs_on_the_newest_tested_python(workflow: dict[str, Any]) -> None:
    """§3: "a single cell on the newest tested Python (3.13)"."""
    setups = [
        step
        for step in workflow["jobs"]["test-matrix-pre"]["steps"]
        if str(step.get("uses", "")).startswith("actions/setup-python")
    ]
    assert [step["with"]["python-version"] for step in setups] == [TESTED_PYTHONS[-1]]


def test_the_pre_cell_is_not_cached(workflow: dict[str, Any]) -> None:
    """A cell that exists to see today's index must not be served yesterday's."""
    setups = [
        step
        for step in workflow["jobs"]["test-matrix-pre"]["steps"]
        if str(step.get("uses", "")).startswith("actions/setup-python")
    ]
    assert all("cache" not in step.get("with", {}) for step in setups)


def test_a_red_pre_cell_is_reported_rather_than_swallowed(workflow: dict[str, Any]) -> None:
    """§3: a soft/non-blocking failure "never lives only in logs".

    The reporting step runs ``if: always()`` — so one red gate cannot skip it — and raises a
    warning annotation naming the supported-range review §3 routes the failure to.
    """
    steps = workflow["jobs"]["test-matrix-pre"]["steps"]
    reports = [step for step in steps if step.get("if") == "always()"]
    assert reports, "the --pre cell has no always-run reporting step"
    # `.get`: the GOV-07 drift-report upload also runs `if: always()` and has no `run`.
    body = "\n".join(step.get("run", "") for step in reports)
    assert "::warning" in body
    assert "GITHUB_STEP_SUMMARY" in body
    assert "supported-range review" in body


def test_every_pre_cell_gate_reports_its_own_outcome(workflow: dict[str, Any]) -> None:
    """One red gate must not hide the other three.

    Each gate carries its own step-level ``continue-on-error`` (so the run reaches all four
    even when the first fails) and its own id, and the reporting step reads every one of
    those outcomes — a gate whose outcome nothing reads is a gate that can fail silently.
    """
    steps = workflow["jobs"]["test-matrix-pre"]["steps"]
    gated = [step for step in steps if step.get("continue-on-error") is True]
    assert len(gated) >= len(GATES), "not every --pre gate runs independently of the others"
    assert all("id" in step for step in gated)

    reported = "\n".join(
        "\n".join([*map(str, step.get("env", {}).values()), step.get("run", "")])
        for step in steps
        if step.get("if") == "always()"
    )
    for step in gated:
        assert f"steps.{step['id']}.outcome" in reported, (
            f"the --pre report never reads the outcome of step {step['id']!r}"
        )


# ── The watch: post-phase runs keep arriving without pushes (GOV-08; VERSION-COMPAT §4) ──


def test_the_watch_runs_weekly_and_on_dispatch(workflow: dict[str, Any]) -> None:
    """§4's ceiling-extension cadence and 2.0 watch need the matrix — and the `--pre`
    early-warning cell, and the drift-issue automation — to run when pushes no longer
    arrive: a weekly schedule, plus `workflow_dispatch` as the immediate run §4 names for
    the day a 2.0 alpha appears. (PyYAML reads the bare `on:` key as boolean True.)
    """
    keys: dict[Any, Any] = workflow
    triggers = keys.get("on", keys.get(True))
    assert triggers is not None
    assert "push" in triggers
    assert "pull_request" in triggers
    assert "workflow_dispatch" in triggers
    [cron] = triggers["schedule"]
    fields = str(cron["cron"]).split()
    assert len(fields) == 5
    minute, _hour, day_of_month, month, day_of_week = fields
    assert day_of_month == "*" and month == "*" and day_of_week != "*", (
        "the watch is weekly: a fixed day of week, every week"
    )
    assert minute != "0", "off-the-hour minute — scheduled-load etiquette"
