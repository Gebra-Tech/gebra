"""The composite action's manifest, held to TE-13's documented interface.

What is pinned and why. The input/output vocabulary IS the adopter contract, so it is
asserted as a set equality with its defaults (`test_rollout_doc.py` separately holds
the rollout page's tables to the same manifest). The composite must stay fully local —
no `uses:` steps — because that is what makes every step of the action executable
outside a GitHub runner, which is what the PD-008 observation discipline runs. And no
input value may ever be spliced into shell text: inputs travel to the driver as
environment variables only, so a hostile input can name a slug that does not exist but
can never become shell syntax.

The driver itself is pinned standard-library-only by AST, because the action runs
before it is known whether the environment even has a working pytest — a driver that
imported ``gebra`` or ``pytest`` would turn "your environment is missing the gate"
into its own traceback. The same test is the WA-07-relevant statement that importing
the driver touches neither gebra nor the substrate.
"""

from __future__ import annotations

import ast
from typing import Any, Final

from tests.action.conftest import ACTION_DIR, GATE_SCRIPT, REPO_ROOT
from tools.honest_claims_lint import load_phrases, scan, scan_files

#: The adopter-facing inputs and their defaults. Changing this vocabulary is a
#: documented-interface change: edit docs/ci/github-action.md in the same commit —
#: test_rollout_doc.py holds the page to this manifest.
EXPECTED_INPUTS: Final[dict[str, str]] = {
    "tests": "",
    "mode": "gate",
    "strict-properties": "",
    "select": "",
    "skip": "",
    "pytest-args": "",
    "python": "python",
    "working-directory": ".",
}

#: Every input except `working-directory` (a step-level key, not script state) reaches
#: the driver as one environment variable under this prefix.
ENV_PREFIX: Final = "GEBRA_GATE_"

#: What the driver may import — the standard library it actually uses, nothing more.
ALLOWED_DRIVER_IMPORTS: Final = frozenset(
    {
        "__future__",
        "collections",
        "dataclasses",
        "os",
        "pathlib",
        "re",
        "shlex",
        "subprocess",
        "sys",
        "typing",
    }
)


def _steps(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    steps = manifest["runs"]["steps"]
    assert isinstance(steps, list)
    return steps


def test_the_manifest_declares_exactly_the_documented_inputs(
    manifest: dict[str, Any],
) -> None:
    """The input vocabulary and its defaults, as a set equality with descriptions."""
    inputs = manifest["inputs"]
    assert set(inputs) == set(EXPECTED_INPUTS)
    for name, default in EXPECTED_INPUTS.items():
        declared = inputs[name]
        assert declared["default"] == default, name
        assert declared["required"] is False, name
        assert str(declared["description"]).strip(), name


def test_the_outputs_are_the_two_documented_ones(manifest: dict[str, Any]) -> None:
    """`exit-code` and `outcome`, each wired from the gate step's own outputs."""
    outputs = manifest["outputs"]
    assert set(outputs) == {"exit-code", "outcome"}
    for name, declared in outputs.items():
        assert str(declared["description"]).strip(), name
        assert f"steps.gate.outputs.{name}" in declared["value"], name


def test_the_composite_is_fully_local(manifest: dict[str, Any]) -> None:
    """One bash step, no `uses:` anywhere — every step is executable off-runner."""
    assert manifest["runs"]["using"] == "composite"
    steps = _steps(manifest)
    assert len(steps) == 1
    step = steps[0]
    assert "uses" not in step
    assert step["id"] == "gate"
    assert step["shell"] == "bash"


def test_inputs_reach_the_driver_as_environment_only(manifest: dict[str, Any]) -> None:
    """The injection posture: no expression in the run body; env is the whole bridge.

    Every input except `working-directory` maps to exactly one `GEBRA_GATE_*` variable
    whose value is the bare input expression, and nothing else is in the env block —
    so the set of ways an input value can travel is closed and shell-free.
    """
    step = _steps(manifest)[0]
    assert "${{" not in step["run"]
    assert step["working-directory"] == "${{ inputs.working-directory }}"
    expected_env = {
        ENV_PREFIX + name.upper().replace("-", "_"): f"${{{{ inputs.{name} }}}}"
        for name in EXPECTED_INPUTS
        if name != "working-directory"
    }
    assert step["env"] == expected_env


def test_the_run_body_invokes_the_driver_beside_the_manifest(
    manifest: dict[str, Any],
) -> None:
    """The one command: the chosen interpreter on `gate.py`, both quoted, by env."""
    run = _steps(manifest)[0]["run"]
    assert '"$GEBRA_GATE_PYTHON"' in run
    assert '"$GITHUB_ACTION_PATH/gate.py"' in run
    assert GATE_SCRIPT.is_file()


def test_the_driver_imports_stdlib_only() -> None:
    """The driver depends on nothing the gated environment might be missing.

    In particular neither ``gebra`` nor ``pytest``: the driver must be able to report
    a broken environment as a red pytest exit instead of failing to start. This is
    also the WA-07 statement about the module itself — importing it reaches no gebra
    code and no substrate.
    """
    tree = ast.parse(GATE_SCRIPT.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.partition(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.module is not None and node.level == 0
            imported.add(node.module.partition(".")[0])
    assert imported <= ALLOWED_DRIVER_IMPORTS
    assert "gebra" not in imported and "pytest" not in imported


def test_the_action_tree_stays_inside_the_honest_claims_vocabulary() -> None:
    """WA-06 over the tree the default lint scope leaves out, held here permanently.

    `tools/honest_claims_lint.py`'s DEFAULT_INCLUDE covers `src/**`, `docs/**` and the
    top-level prose, not `.github/**` — prior cards swept such trees by hand. This
    test runs the same scan, same phrase list, over the action's manifest, driver and
    README on every run instead.
    """
    phrases = load_phrases(REPO_ROOT / "tools" / "honest-claims-phrases.txt")
    include = (".github/**/*.yml", ".github/**/*.md", ".github/**/*.py")
    covered = set(scan_files(REPO_ROOT, include, ()))
    action_dir = ACTION_DIR.relative_to(REPO_ROOT).as_posix()
    assert {
        f"{action_dir}/action.yml",
        f"{action_dir}/gate.py",
        f"{action_dir}/README.md",
    } <= covered
    report = scan(REPO_ROOT, phrases, include=include, exclude=())
    assert report.ok, [f"{v.path}:{v.line_no}: {v.detail}" for v in report.violations]
