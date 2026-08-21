"""Cold-cache regression guard for the mypy gate (GOV-11).

A warm ``.mypy_cache`` can report ``Success`` on a build that is actually broken:
incremental mode skips re-checking a module whose cache entry looks fresh, so a genuine
``--strict`` error introduced upstream of an already-cached file goes unseen on a
developer's machine — while every CI runner, always a fresh checkout with no persisted
``.mypy_cache``, sees it immediately. That gap is exactly how GOV-04's PD-038 Finding 1 hid
on ``main`` for weeks: two ``--strict`` errors in
``tests/sample_workflows/sentinel_resolution.py`` (a ``typeddict-item`` on the lone-surrogate
state key and a ``redundant-expr``), invisible under a warm cache, crashing mypy 2.3.0's own
cache writer once a cold run actually tried to serialize the surrogate-bearing error text.

This test forces the same cold path a CI runner always takes — a ``--cache-dir`` that has
never been written to — so that class of regression fails here, in the default test-suite
lane (``pytest -q``, the ``test-locked`` CI job), rather than being discoverable only inside
the heavier 13-cell compat matrix's own per-cell mypy step.

Runs the ``mypy`` executable as a subprocess against the repository's own ``pyproject.toml``
configuration; nothing under test is imported, no workflow node runs, no LLM call, no network
(WA-07).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_mypy_is_green_from_a_fresh_cache_dir(tmp_path: Path) -> None:
    """``mypy`` (the bare CI command; every knob lives in ``[tool.mypy]``) against a
    ``--cache-dir`` that starts empty — what every CI runner's cache always is, since
    ``.github/workflows/ci.yml``'s ``typecheck`` job persists nothing between runs.

    A warm developer cache can never hide this class again: this test's cache dir is a
    fresh ``tmp_path`` on every run, so it always takes the cold path regardless of what is
    sitting in the repo's own ``.mypy_cache``.
    """
    result = subprocess.run(
        [sys.executable, "-m", "mypy", "--cache-dir", str(tmp_path / "mypy_cache")],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        "mypy failed from a cold cache (what every CI runner is) — see PD-038 Finding 1 / "
        f"GOV-11:\n--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
    )
