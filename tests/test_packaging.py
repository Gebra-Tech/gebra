"""Packaging-configuration tests for the GOV-D1-ruled build system.

The ruling is [PD-005](build-backend ruling, ratified 2026-07-24): the build
backend is hatchling on a ``hatchling>=1.27`` floor, the repo is uv-managed with
``uv.lock`` committed for the default development environment, the setuptools
configuration is gone, and per-cell compatibility pins stay out of the lock (they
belong to the future ``gebra[compat-test]`` extra).

These tests read files and parse TOML only. Nothing here builds, installs,
imports a workflow, executes a node, calls an LLM, or opens a socket (WA-07).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - exercised on the 3.10 matrix cells
    import tomli as tomllib

REPO_ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = REPO_ROOT / "pyproject.toml"
LOCKFILE = REPO_ROOT / "uv.lock"

pytestmark = pytest.mark.skipif(
    not PYPROJECT.is_file(),
    reason="packaging tests describe the source tree; no pyproject.toml beside tests/",
)


def _load(path: Path) -> dict[str, Any]:
    with path.open("rb") as handle:
        data: dict[str, Any] = tomllib.load(handle)
    return data


@pytest.fixture(scope="module")
def pyproject() -> dict[str, Any]:
    return _load(PYPROJECT)


@pytest.fixture(scope="module")
def lockfile() -> dict[str, Any]:
    if not LOCKFILE.is_file():
        pytest.fail("uv.lock is missing; PD-005 item 3 requires it committed at the repo root")
    return _load(LOCKFILE)


def test_build_backend_is_hatchling(pyproject: dict[str, Any]) -> None:
    """PD-005 item 1: hatchling is the PEP 517 backend, floor ``hatchling>=1.27``.

    The floor is the PEP 639 floor — the project declares ``license = "Apache-2.0"``
    plus ``license-files``, which hatchling only understands from 1.27 on.
    """
    build_system = pyproject["build-system"]
    assert build_system["build-backend"] == "hatchling.build"
    assert build_system["requires"] == ["hatchling>=1.27"]
    assert pyproject["project"]["license"] == "Apache-2.0"
    assert pyproject["project"]["license-files"] == ["LICENSE", "NOTICE"]


def test_no_setuptools_configuration_survives(pyproject: dict[str, Any]) -> None:
    """PD-005 item 2: the ``[tool.setuptools.*]`` tables and their era are gone."""
    assert "setuptools" not in pyproject.get("tool", {})
    for legacy in ("setup.py", "setup.cfg", "MANIFEST.in"):
        assert not (REPO_ROOT / legacy).exists(), f"setuptools-era file survives: {legacy}"


def test_no_egg_info_artifacts_in_the_tree() -> None:
    """PD-005 item 2, egg-info hygiene: no in-tree ``*.egg-info`` build artifact.

    Hatchling never produces one; a reappearance means something built through
    setuptools again.
    """
    candidates = [*REPO_ROOT.glob("*.egg-info"), *REPO_ROOT.glob("*/*.egg-info")]
    strays = sorted(
        str(path.relative_to(REPO_ROOT)) for path in candidates if ".venv" not in path.parts
    )
    assert strays == []


def test_wheel_packages_the_src_layout_and_the_typing_marker(pyproject: dict[str, Any]) -> None:
    """The wheel carries ``gebra/`` from ``src/gebra/``, ``py.typed`` included.

    Hatchling ships every file under a packaged directory, so the marker needs no
    separate package-data declaration — but it does need to exist.
    """
    wheel_target = pyproject["tool"]["hatch"]["build"]["targets"]["wheel"]
    assert wheel_target["packages"] == ["src/gebra"]
    assert (REPO_ROOT / "src" / "gebra" / "py.typed").is_file()


def test_the_pytest_plugin_is_declared_as_a_pytest11_entry_point(
    pyproject: dict[str, Any],
) -> None:
    """D-10 In-Scope 2, card TE-06: the plugin ships in the distribution's metadata.

    The source-side half of the claim — the declaration exists and names a module that is
    actually in the wheel. The installed-metadata half is
    ``tests/plugin/test_plugin.py::test_the_plugin_loads_from_its_entry_point``, because a
    declaration that never made it into a dist-info does nothing.
    """
    entry_points = pyproject["project"]["entry-points"]["pytest11"]
    assert entry_points == {"gebra": "gebra.pytest_plugin"}
    assert (REPO_ROOT / "src" / "gebra" / "pytest_plugin.py").is_file()


def test_lockfile_matches_the_declared_python_floor(
    pyproject: dict[str, Any], lockfile: dict[str, Any]
) -> None:
    """PD-005 item 3: the committed lock locks *this* project's environment."""
    assert lockfile["requires-python"] == pyproject["project"]["requires-python"]


def test_lockfile_covers_the_declared_dependency_set(
    pyproject: dict[str, Any], lockfile: dict[str, Any]
) -> None:
    """Every declared runtime and dev distribution resolves to a locked package."""
    locked = {package["name"] for package in lockfile["package"]}
    declared = [
        *pyproject["project"]["dependencies"],
        *pyproject["project"]["optional-dependencies"]["dev"],
    ]
    missing = sorted(
        {_distribution_name(requirement) for requirement in declared} - locked - {"gebra"}
    )
    assert missing == [], f"declared but unlocked: {missing} — refresh uv.lock"


def test_lockfile_carries_no_matrix_pins(
    pyproject: dict[str, Any], lockfile: dict[str, Any]
) -> None:
    """PD-005 item 4 as amended at PD-049: the lock never decides what a cell tests.

    The compat extras (SOW §4; values recorded by GOV-D3, installed per cell by GOV-04)
    pin mutually exclusive substrates, and ``uv lock`` resolves every extra of a project —
    the original letter ("pins never enter the lock") was unsatisfiable alongside a
    resolvable lock, which the first real CI run surfaced (PD-049, 2026-08-13; filed as PD-046, renumbered). The
    surviving invariants, asserted here: every compat extra is declared in one
    ``[tool.uv] conflicts`` set (so the lock records them only as conflicting
    alternatives), and the DEV line's substrate resolution is exactly the ruled dev pins —
    the cells still install from ``pyproject.toml`` via pip, never from the lock.
    """
    declared = {
        extra
        for extra in pyproject["project"]["optional-dependencies"]
        if extra.startswith("compat")
    }
    assert declared, "the compatibility extras are gone; SOW §4 requires them"
    conflict_sets = pyproject.get("tool", {}).get("uv", {}).get("conflicts", [])
    conflicted = {
        member["extra"]
        for conflict_set in conflict_sets
        for member in conflict_set
        if "extra" in member
    }
    assert declared <= conflicted, (
        "every compat extra must be declared conflicting (PD-049); missing: "
        f"{sorted(declared - conflicted)}"
    )
    # The dev line is untouched by the cells: the newest-pair substrate (the ruled dev
    # line, == cell 3's pins per PD-030 §C3) is present in the lock, and the older cells'
    # substrate versions appear only as conflict-split alternatives, never displacing it.
    expected_dev = {"langgraph": "1.2.10", "langchain-core": "1.5.3"}
    for name, version in expected_dev.items():
        found = {package["version"] for package in lockfile["package"] if package["name"] == name}
        assert version in found, f"dev-line {name}=={version} missing from the lock: {found}"


def _locked_project_extras(lockfile: dict[str, Any]) -> set[str]:
    for package in lockfile["package"]:
        if package["name"] == "gebra":
            return set(package.get("optional-dependencies", {}))
    pytest.fail("uv.lock does not contain the gebra project package")


def _distribution_name(requirement: str) -> str:
    """Normalize a PEP 508 requirement string to its PEP 503 distribution name."""
    name = requirement.split(";", 1)[0]
    for separator in ("[", "=", "<", ">", "!", "~", " "):
        name = name.split(separator, 1)[0]
    return name.strip().lower().replace("_", "-").replace(".", "-")
