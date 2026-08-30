"""Shared loading of the action's two parts — the YAML manifest and the driver module."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, Final

import pytest
import yaml

REPO_ROOT: Final = Path(__file__).resolve().parents[2]
ACTION_DIR: Final = REPO_ROOT / ".github" / "actions" / "gebra-gate"
ACTION_MANIFEST: Final = ACTION_DIR / "action.yml"
GATE_SCRIPT: Final = ACTION_DIR / "gate.py"


@pytest.fixture(scope="package")
def manifest() -> dict[str, Any]:
    """The parsed ``action.yml``."""
    loaded = yaml.safe_load(ACTION_MANIFEST.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


@pytest.fixture(scope="package")
def gate() -> ModuleType:
    """The driver, imported from its file — ``.github/`` is no package, deliberately.

    Registered in ``sys.modules`` before execution per the importlib recipe: the
    driver's frozen dataclass resolves its stringified annotations through the
    module's own ``sys.modules`` entry.
    """
    spec = importlib.util.spec_from_file_location("gebra_gate_driver", GATE_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
