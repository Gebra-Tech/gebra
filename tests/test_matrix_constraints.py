"""The freeze-time pin lock: matrix cells resolve from the lock, not the day's index.

Three layers, mirroring what GOV-08 landed:

* the **committed file** — ``tools/matrix-constraints.txt`` regenerates byte-identically
  from ``uv.lock`` + ``pyproject.toml`` (the staleness gate: a lock refresh without its
  constraints refresh is a red test in every CI cell), and its content obeys the policy
  (substrate family out, dev toolchain locked, marker-partitioned multi-versions);
* the **generator** — the policy edges proven on synthetic locks: overlapping markers
  refuse to emit, family agreement is verified against the lock, non-exact extras are an
  error, and every error path is loud (exit 2, never a silent pass);
* the **wiring** — every pip-installing job in ``ci.yml`` resolves under ``-c``, while
  the ``--pre`` cell's substrate resolve step deliberately does not (VERSION-COMPAT §3:
  that cell exists to see today's index).

Everything here reads and parses files or calls the generator in-process on data —
nothing installs, builds, executes a node, calls an LLM, or opens a socket (WA-07).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

from tools import matrix_constraints
from tools.matrix_constraints import (
    CONSTRAINTS,
    MatrixConstraintsError,
    main,
    regenerate,
    render,
)

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - exercised on the 3.10 matrix cells
    import tomli as tomllib

REPO_ROOT = Path(__file__).resolve().parents[1]
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"

pytestmark = pytest.mark.skipif(
    not (REPO_ROOT / "uv.lock").is_file() or not CI_WORKFLOW.is_file(),
    reason="constraint tests describe the source tree; no uv.lock/workflow beside tests/",
)

#: The distributions the three cells pin to different versions — never constrained.
DIVERGENT_FAMILY = (
    "langgraph",
    "langchain-core",
    "langgraph-checkpoint",
    "langgraph-prebuilt",
    "langgraph-sdk",
)

#: Ecosystem-drift history this lock exists to close: a hypothesis profile change went
#: red as TE-16, typer 0.27.2 as CLI-10 — both arrived through fresh floors in the cells.
DEV_TOOLCHAIN = ("pytest", "pytest-cov", "hypothesis", "ruff", "mypy", "typer", "rich")


def constraint_pins(text: str) -> dict[str, list[str]]:
    """``name -> [version, ...]`` for every non-comment constraint line."""
    pins: dict[str, list[str]] = {}
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        requirement = line.split(";")[0].strip()
        name, separator, version = requirement.partition("==")
        assert separator, f"a constraints line without an exact pin: {line!r}"
        pins.setdefault(name.strip(), []).append(version.strip())
    return pins


@pytest.fixture(scope="module")
def committed() -> str:
    return CONSTRAINTS.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def pins(committed: str) -> dict[str, list[str]]:
    return constraint_pins(committed)


# ── The committed file ───────────────────────────────────────────────────────────────────


def test_the_committed_constraints_match_the_lock(committed: str) -> None:
    """THE staleness gate: uv.lock moved but the constraints did not — red in every cell."""
    assert committed == regenerate(), (
        "tools/matrix-constraints.txt is stale against uv.lock/pyproject.toml — run "
        "`python tools/matrix_constraints.py --write` in the same commit"
    )


@pytest.mark.parametrize("name", sorted(DIVERGENT_FAMILY))
def test_the_divergent_substrate_family_is_never_constrained(
    pins: dict[str, list[str]], name: str
) -> None:
    """The compat-cell extras are the substrate's single source of truth (PD-005 item 4);
    a constraint would contradict two of the three cells."""
    assert name not in pins


def test_the_project_itself_is_never_constrained(pins: dict[str, list[str]]) -> None:
    assert "gebra" not in pins


def test_family_members_the_extras_agree_on_are_constrained(
    pins: dict[str, list[str]],
) -> None:
    """pydantic is pinned identically by every cell extra, so the constraint also covers
    the jobs that install no cell extra (pip-editable, docs, the --pre cell's dev half)."""
    assert pins["pydantic"] == ["2.13.4"]
    assert pins["langchain-protocol"] == ["0.0.18"]


@pytest.mark.parametrize("name", sorted(DEV_TOOLCHAIN))
def test_the_dev_toolchain_is_locked(pins: dict[str, list[str]], name: str) -> None:
    assert name in pins, f"{name} is not constrained — the TE-16/CLI-10 class stays open"
    assert len(pins[name]) == 1


def test_a_python_split_distribution_carries_partitioning_markers(committed: str) -> None:
    """networkx resolves per Python line; each version's line binds only its own line."""
    lines = [line for line in committed.splitlines() if line.startswith("networkx==")]
    assert len(lines) == 2
    markers = set()
    for line in lines:
        _, _, marker = line.partition(";")
        assert "python_full_version" in marker
        markers.add(marker.strip())
    assert len(markers) == 2, "the two networkx lines must scope to disjoint interpreters"


def test_a_cell_dependent_distribution_is_excluded_by_name(
    committed: str, pins: dict[str, list[str]]
) -> None:
    """packaging resolves per cell (uv conflict markers): constraining it would refuse
    every resolution; leaving it silently would hide the hole. The header names it."""
    assert "packaging" not in pins
    assert re.search(r"^#\s+packaging - cell-dependent", committed, re.MULTILINE)


def test_every_constraint_is_a_version_the_lock_resolved(pins: dict[str, list[str]]) -> None:
    with (REPO_ROOT / "uv.lock").open("rb") as handle:
        lock = tomllib.load(handle)
    locked: dict[str, set[str]] = {}
    for entry in lock["package"]:
        locked.setdefault(entry["name"], set()).add(entry["version"])
    for name, versions in pins.items():
        for version in versions:
            assert version in locked.get(name, set()), (
                f"{name}=={version} is constrained but not what uv.lock resolved"
            )


# ── The generator's policy edges (synthetic locks; no file touched) ──────────────────────


def _lock(*entries: tuple[str, str, list[str]]) -> dict[str, object]:
    return {
        "package": [
            {"name": name, "version": version, "resolution-markers": markers}
            for name, version, markers in entries
        ]
    }


def _pyproject(**extras: list[str]) -> dict[str, object]:
    return {"project": {"optional-dependencies": dict(extras)}}


GOOD_PYPROJECT = _pyproject(**{"compat-cell-1": ["langgraph==1.0.10", "pydantic==2.13.4"]})


def test_overlapping_markers_exclude_rather_than_emit_conflicting_lines() -> None:
    """Two versions whose markers cover the same interpreter would refuse every install."""
    marker = "python_full_version >= '3.10'"
    rendered = render(
        _lock(("langgraph", "1.0.10", []), ("weird", "1.0", [marker]), ("weird", "2.0", [marker])),
        GOOD_PYPROJECT,
    )
    assert "weird==" not in rendered
    assert "weird - cell-dependent" in rendered


def test_python_partitioned_versions_emit_one_scoped_line_each() -> None:
    rendered = render(
        _lock(
            ("langgraph", "1.0.10", []),
            ("split", "1.0", ["python_full_version < '3.11'"]),
            ("split", "2.0", ["python_full_version >= '3.11'"]),
        ),
        GOOD_PYPROJECT,
    )
    assert "split==1.0 ; (python_full_version < '3.11')" in rendered
    assert "split==2.0 ; (python_full_version >= '3.11')" in rendered


def test_multi_version_without_markers_is_excluded_not_guessed() -> None:
    rendered = render(
        _lock(("langgraph", "1.0.10", []), ("dup", "1.0", []), ("dup", "2.0", [])),
        GOOD_PYPROJECT,
    )
    assert "dup==" not in rendered
    assert "dup - multiple locked versions" in rendered


def test_an_agreed_family_pin_that_disagrees_with_the_lock_is_a_loud_error() -> None:
    """The freeze holds the extras and the lock to one story about pydantic."""
    with pytest.raises(MatrixConstraintsError, match="pydantic.*reconcile"):
        render(_lock(("pydantic", "2.14.0", []), ("langgraph", "1.0.10", [])), GOOD_PYPROJECT)


def test_a_non_exact_compat_requirement_is_a_loud_error() -> None:
    with pytest.raises(MatrixConstraintsError, match="non-exact"):
        render(_lock(("x", "1.0", [])), _pyproject(**{"compat-cell-1": ["langgraph>=1.0"]}))


def test_a_pyproject_without_compat_extras_is_a_loud_error() -> None:
    with pytest.raises(MatrixConstraintsError, match="no compat"):
        render(_lock(("x", "1.0", [])), _pyproject(dev=["pytest>=8"]))


# ── The CLI ──────────────────────────────────────────────────────────────────────────────


def test_check_is_green_on_the_committed_tree() -> None:
    assert main(["--check"]) == 0


def test_check_fails_on_a_stale_copy(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    stale = tmp_path / "matrix-constraints.txt"
    stale.write_text(CONSTRAINTS.read_text(encoding="utf-8") + "extra==1.0\n", encoding="utf-8")
    monkeypatch.setattr(matrix_constraints, "CONSTRAINTS", stale)
    assert main(["--check"]) == 1


def test_check_fails_when_the_file_is_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(matrix_constraints, "CONSTRAINTS", tmp_path / "absent.txt")
    assert main(["--check"]) == 1


def test_write_then_check_round_trips(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    target = tmp_path / "matrix-constraints.txt"
    monkeypatch.setattr(matrix_constraints, "CONSTRAINTS", target)
    assert main(["--write"]) == 0
    assert main(["--check"]) == 0
    assert target.read_text(encoding="utf-8") == CONSTRAINTS.read_text(encoding="utf-8")


def test_an_inconsistent_input_is_exit_two(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    broken = tmp_path / "uv.lock"
    broken.write_text('this = "is not a lock"\n', encoding="utf-8")
    monkeypatch.setattr(matrix_constraints, "LOCKFILE", broken)
    assert main(["--check"]) == 2


def test_the_help_carries_no_bypass_flag(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["--help"])
    assert excinfo.value.code == 0
    text = capsys.readouterr().out
    assert not any(flag in text for flag in ("--skip", "--force", "--allow", "--ignore"))


# ── The ci.yml wiring ────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def workflow() -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))
    return data


def _runs(job: dict[str, Any]) -> list[str]:
    return [step["run"] for step in job["steps"] if "run" in step]


@pytest.mark.parametrize("job", ["test-matrix", "dod", "pip-editable", "docs"])
def test_every_fresh_pip_job_resolves_under_the_constraints(
    workflow: dict[str, Any], job: str
) -> None:
    installs = [run for run in _runs(workflow["jobs"][job]) if "pip install -e" in run]
    assert installs, f"{job} no longer pip-installs the package?"
    assert all("-c tools/matrix-constraints.txt" in run for run in installs)


def test_the_docs_toolchain_install_is_constrained_too(workflow: dict[str, Any]) -> None:
    """The docs job installs twice; an unconstrained second install could silently
    re-resolve a distribution the first install just locked (pyyaml, for example)."""
    [install] = [run for run in _runs(workflow["jobs"]["docs"]) if "requirements.txt" in run]
    for line in install.splitlines():
        if "pip install" in line:
            assert "-c tools/matrix-constraints.txt" in line, line


def test_the_pre_cell_locks_dev_but_never_the_substrate_resolve(
    workflow: dict[str, Any],
) -> None:
    """The 13th cell's early warning is the substrate float; the dev half locks so a red
    pre cell attributes to the substrate, not to a dev tool that drifted overnight."""
    runs = _runs(workflow["jobs"]["test-matrix-pre"])
    [dev_install] = [run for run in runs if "pip install -e" in run]
    assert "-c tools/matrix-constraints.txt" in dev_install
    [resolve] = [run for run in runs if "--pre" in run and "--upgrade" in run]
    assert "-c" not in resolve.split("--upgrade")[0] and "matrix-constraints" not in resolve


@pytest.mark.parametrize("job", ["test-matrix", "dod"])
def test_the_pip_cache_keys_on_the_constraints_too(workflow: dict[str, Any], job: str) -> None:
    """A cache keyed only on pyproject.toml would serve yesterday's wheels after a
    constraints refresh."""
    [setup] = [
        step
        for step in workflow["jobs"][job]["steps"]
        if str(step.get("uses", "")).startswith("actions/setup-python")
    ]
    dependency_path = setup["with"]["cache-dependency-path"]
    assert "pyproject.toml" in dependency_path
    assert "tools/matrix-constraints.txt" in dependency_path
