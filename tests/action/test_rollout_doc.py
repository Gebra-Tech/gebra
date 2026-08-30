"""``docs/ci/github-action.md`` pinned to the shapes it documents (card TE-13).

The page is the adopter contract for the CI-gate action, and prose cannot hold itself
to code. So: the executed example must BE the DoD job's step — structural equality
against ``ci.yml``, which is what makes the page's one in-repo workflow example a
CI-executed example on every push (WA-12's discipline, with no examples harness in the
repository yet); the interface tables must name every input, output, mode and outcome
the manifest and driver declare; the rollout ladder must appear in rollout order; and
the strict rung must keep the promotion-changes-the-gate-never-the-record boundary and
the witness-presence wording. Every fence is parsed, never executed — the tests/docs
rule.
"""

from __future__ import annotations

import re
from types import ModuleType
from typing import Any, Final

import pytest
import yaml

from tests.action.conftest import ACTION_DIR, REPO_ROOT

PAGE: Final = REPO_ROOT / "docs" / "ci" / "github-action.md"
WORKFLOW: Final = REPO_ROOT / ".github" / "workflows" / "ci.yml"
POINTER: Final = ACTION_DIR / "README.md"

#: The local action reference the DoD job uses — the doc's executed example must match.
GATE_USES: Final = "./.github/actions/gebra-gate"


@pytest.fixture(scope="module")
def page_text() -> str:
    return PAGE.read_text(encoding="utf-8")


def _yaml_fences(text: str) -> list[str]:
    return re.findall(r"```yaml\n(.*?)```", text, flags=re.DOTALL)


def test_the_page_is_in_the_library_repo_beside_the_code() -> None:
    assert PAGE.is_file(), f"{PAGE} is missing"


def test_every_yaml_fence_parses(page_text: str) -> None:
    """Parsed, never executed — a fence that stopped being YAML fails the page."""
    fences = _yaml_fences(page_text)
    assert len(fences) >= 2, "the page lost its workflow examples"
    for fence in fences:
        yaml.safe_load(fence)


def test_the_executed_example_is_the_dod_jobs_step_verbatim(page_text: str) -> None:
    """The one in-repo example equals the workflow's own step, structurally.

    That equality is what turns the fenced example into an executed one: the `dod` job
    runs this exact step on every push, so the doc cannot describe an invocation CI
    does not perform.
    """
    matching = [
        yaml.safe_load(fence)
        for fence in _yaml_fences(page_text)
        if GATE_USES in fence and "tests/dod" in fence
    ]
    assert len(matching) == 1
    documented_steps = matching[0]
    assert isinstance(documented_steps, list) and len(documented_steps) == 1
    workflow: dict[str, Any] = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    dod_steps = workflow["jobs"]["dod"]["steps"]
    gate_steps = [step for step in dod_steps if step.get("uses") == GATE_USES]
    assert len(gate_steps) == 1
    assert documented_steps[0] == gate_steps[0]


def test_the_interface_tables_cover_the_whole_vocabulary(
    page_text: str, manifest: dict[str, Any], gate: ModuleType
) -> None:
    """Every input, output, mode and outcome the action declares is on the page."""
    for name in manifest["inputs"]:
        assert f"`{name}`" in page_text, name
    for name in manifest["outputs"]:
        assert f"`{name}`" in page_text, name
    for mode in gate.MODES:
        assert f"`{mode}`" in page_text, mode
    for outcome in gate.OUTCOMES:
        assert f"`{outcome}`" in page_text, outcome


def test_the_rollout_ladder_is_in_rollout_order(page_text: str) -> None:
    """The three rungs appear as sections, in the order adopters climb them."""
    rungs = (
        "### 1. `report-only`",
        "### 2. `gate`",
        "### 3. `strict`",
    )
    positions = [page_text.find(rung) for rung in rungs]
    assert all(position >= 0 for position in positions), positions
    assert positions == sorted(positions)


def test_the_strict_rung_keeps_the_record_boundary(page_text: str) -> None:
    """WA-06 on the page's own copy, in the plugin's words: promotion is a gate
    policy, never a re-grading, and P-02 language stays witness-presence-only."""
    assert "changes the gate, never the record" in page_text
    assert "`severity: warning`" in page_text
    assert "witness presence — never a statement that a run halts" in page_text


def test_the_empty_run_rule_is_stated(page_text: str) -> None:
    """The verdict table's sharpest edge is stated in words as well as cells."""
    assert "A gate that checked nothing never passes" in page_text
    assert "forgives test failures" in page_text


def test_the_action_readme_points_at_the_page(page_text: str) -> None:
    """The action-directory README is a pointer, not a second copy that can drift."""
    pointer_text = POINTER.read_text(encoding="utf-8")
    assert "docs/ci/github-action.md" in pointer_text
    assert len(pointer_text.splitlines()) < 25, "the pointer grew into a second doc"
