"""``docs/guides/use-cases.md`` pinned to the scenarios it documents (card REL-06).

The page's claim is that each scenario it shows is the scenario CI runs, and that every verdict
on it is one the run printed. Prose cannot hold itself to that, so this module does:

* each ``workflow.py`` is reproduced byte for byte as an *executed* example, and each
  ``test_verdict.py`` as a fence, both held equal to the files under ``examples/scenarios/``;
* the seeded defects are what the page names — one finding per scenario, three distinct
  condition IDs from three properties, none of them ``ci_gate``'s P-06 — asserted by running
  ``verify()`` over each builder rather than by trusting the page, and each fix passes;
* the finding's claim class is named beside it, on the page and in each scenario's README;
* the suite CI runs — ``python -m pytest examples/scenarios -q``, a step of the ``pip-editable``
  job — is green as a suite in a child process, and the marked items it collects are the fixed
  variants and only those;
* the ledgers are live on both paths: a scenario body that ran fails the page's example and
  fails the pytest path through ``examples/conftest.py``'s sweep, which is shown to discover
  every scenario;
* the honest-claims lint runs over the page and the scenario sources (WA-06).

The module reads Markdown and YAML, runs pytest and the examples harness in child processes, and
calls scenario bodies on purpose in the fired controls — each records and raises, and the ledger
is cleared afterwards. It executes no workflow node otherwise, calls no model and opens no
connection (WA-07).
"""

from __future__ import annotations

import dataclasses
import importlib
import re
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType
from typing import Any, Final

import pytest
import yaml

import gebra
from gebra.pytest_plugin import enabled_properties, findings_for
from gebra.verify import PropertySlug, RunPolicy, StrictPolicy, verify
from tests.docs.test_docs_site import WRITTEN_PAGES
from tests.test_toolchain_config import _workflow_run_steps
from tools.docs_examples import DocExample, parse_markdown, run_example
from tools.honest_claims_lint import load_phrases, scan, scan_files

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - exercised on the 3.10 matrix cells
    import tomli as tomllib

REPO_ROOT: Final = Path(__file__).resolve().parents[2]
PAGE_PATH: Final = "docs/guides/use-cases.md"
PAGE: Final = REPO_ROOT / PAGE_PATH
SCENARIOS: Final = REPO_ROOT / "examples" / "scenarios"
CI_WORKFLOW: Final = REPO_ROOT / ".github" / "workflows" / "ci.yml"
MKDOCS: Final = REPO_ROOT / "mkdocs.yml"

#: The command the card names, as the `pip-editable` job's step runs it.
CI_STEP: Final = "python -m pytest examples/scenarios -q"

#: What every scenario directory carries.
SCENARIO_FILES: Final[tuple[str, ...]] = (
    "__init__.py",
    "workflow.py",
    "test_verdict.py",
    "README.md",
)

#: The CI-gating guide's seeded defect, which no scenario here may duplicate.
CI_GATE_CONDITION: Final = "unprotected-effect-in-retry-region"


@dataclasses.dataclass(frozen=True)
class Scenario:
    """One scenario as the page and the card describe it — held to the code below."""

    slug: str
    heading: str
    builder: str
    fixed: str
    property_slug: PropertySlug
    condition: str
    severity: str
    claim_class: str
    #: One node body of the seeded graph, and the label it records — for the fired controls.
    body: str

    @property
    def target(self) -> str:
        """The marked target name — the fixed builder's, minus its ``build_`` prefix."""
        return self.fixed.removeprefix("build_")

    @property
    def module_name(self) -> str:
        return f"examples.scenarios.{self.slug}.workflow"

    @property
    def example_id(self) -> str:
        return self.slug.replace("_", "-") + "-workflow"

    @property
    def fix_example_id(self) -> str:
        return self.slug.replace("_", "-") + "-fix"


SCENARIO_TABLE: Final[tuple[Scenario, ...]] = (
    Scenario(
        slug="research_loop",
        heading="## A research loop with no declared bound",
        builder="build_research_loop",
        fixed="build_research_loop_bounded",
        property_slug="termination-witness",
        condition="cycle-without-termination-witness",
        severity="fatal",
        claim_class="defensible",
        body="search",
    ),
    Scenario(
        slug="support_triage",
        heading="## A triage path that reads what nothing wrote",
        builder="build_support_triage",
        fixed="build_support_triage_summary_first",
        property_slug="dataflow-completeness",
        condition="read-key-never-written-on-path",
        severity="fatal",
        claim_class="defensible-a",
        body="escalate",
    ),
    Scenario(
        slug="pipeline_replay",
        heading="## A determinism claim the definition cannot back",
        builder="build_pipeline_replay",
        fixed="build_pipeline_replay_pinned",
        property_slug="determinism-replay",
        condition="deterministic-llm-temperature-unpinned",
        severity="warning",
        claim_class="heuristic",
        body="extract_fields",
    ),
)

SCENARIO_IDS: Final = [scenario.slug for scenario in SCENARIO_TABLE]

#: The strict policy the P-08 scenario's second verdict is read under.
STRICT_ON_P08: Final = StrictPolicy(mode="per-property", properties=("determinism-replay",))


def _module(scenario: Scenario) -> ModuleType:
    return importlib.import_module(scenario.module_name)


def _ledger(scenario: Scenario) -> list[str]:
    ledger: list[str] = _module(scenario).TRIPPED
    return ledger


@pytest.fixture(autouse=True)
def _no_scenario_body_ran() -> Iterator[None]:
    """The examples' own conftest idiom, held here too: every ledger empty before and after.

    The fired controls below call a body on purpose and clear the ledger before returning;
    this fixture is what makes forgetting to do so a failure of that test rather than of the
    next one.
    """
    assert {s.slug: list(_ledger(s)) for s in SCENARIO_TABLE if _ledger(s)} == {}
    yield
    assert {s.slug: list(_ledger(s)) for s in SCENARIO_TABLE if _ledger(s)} == {}


@pytest.fixture(scope="module")
def page_text() -> str:
    return PAGE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def examples(page_text: str) -> dict[str, DocExample]:
    """The page's marked examples, by id — parsed by the harness itself."""
    return {example.example_id: example for example in parse_markdown(page_text, path=PAGE_PATH)}


def _fences(text: str, language: str) -> list[str]:
    """Every fenced block of one language on the page, in document order."""
    return re.findall(rf"```{language}\n(.*?)```", text, flags=re.DOTALL)


def _section(page_text: str, heading: str) -> str:
    """The page from ``heading`` to the next ``## `` heading."""
    start = page_text.index(f"{heading}\n")
    following = page_text.find("\n## ", start + len(heading))
    return page_text[start : following if following >= 0 else len(page_text)]


def _run(*arguments: str, cwd: Path = REPO_ROOT) -> subprocess.CompletedProcess[str]:
    """A child interpreter from the repository root, as CI's step and the harness run one."""
    return subprocess.run(
        [sys.executable, *arguments], cwd=cwd, capture_output=True, text=True, check=False
    )


# ── The scenarios: four files each, reproduced verbatim ─────────────────────────────────


def test_every_scenario_is_four_files_and_the_page_knows_each() -> None:
    """The set on disk is the set the page walks through — no fourth scenario lands unshown."""
    on_disk = sorted(
        path.name for path in SCENARIOS.iterdir() if path.is_dir() and path.name[0] != "_"
    )

    assert on_disk == sorted(SCENARIO_IDS)
    for scenario in SCENARIO_TABLE:
        for name in SCENARIO_FILES:
            assert (SCENARIOS / scenario.slug / name).is_file(), f"{scenario.slug}/{name}"


@pytest.mark.parametrize("scenario", SCENARIO_TABLE, ids=SCENARIO_IDS)
def test_the_workflow_is_the_executed_example_byte_for_byte(
    scenario: Scenario, examples: dict[str, DocExample]
) -> None:
    """The block that runs is the file — not a retelling, and not a fence beside the real one."""
    source = (SCENARIOS / scenario.slug / "workflow.py").read_text(encoding="utf-8")

    assert examples[scenario.example_id].code == source
    assert 'if __name__ == "__main__":' in source, "the file must print its verdict as a script"


@pytest.mark.parametrize("scenario", SCENARIO_TABLE, ids=SCENARIO_IDS)
def test_the_test_module_is_reproduced_verbatim(scenario: Scenario, page_text: str) -> None:
    source = (SCENARIOS / scenario.slug / "test_verdict.py").read_text(encoding="utf-8")

    assert source in _fences(page_text, "python"), f"{scenario.slug}/test_verdict.py"


@pytest.mark.parametrize("scenario", SCENARIO_TABLE, ids=SCENARIO_IDS)
def test_the_fix_is_shown_only_where_a_block_runs_it(
    scenario: Scenario, examples: dict[str, DocExample]
) -> None:
    """The second executed block imports the scenario and verifies the fixed builder."""
    fix = examples[scenario.fix_example_id]

    assert f"from examples.scenarios.{scenario.slug} import workflow" in fix.code
    assert f"workflow.{scenario.fixed}()" in fix.code
    assert "assert workflow.TRIPPED == []" in fix.code, "the sweep does not reach examples/"
    assert fix.expected_output.rstrip("\n").endswith("node bodies run  []")


# ── The seeded defects, checked by running the validators rather than reading the page ───


@pytest.mark.parametrize("scenario", SCENARIO_TABLE, ids=SCENARIO_IDS)
def test_the_seeded_defect_is_one_finding_from_its_property(scenario: Scenario) -> None:
    """Exactly one finding, owned by the named property, with the named grade and class."""
    module = _module(scenario)
    report = verify(gebra.extract(getattr(module, scenario.builder)()).ir)

    findings = [f for slug in enabled_properties() for f in findings_for(report, slug)]
    assert len(findings) == 1, findings
    (finding,) = findings
    assert finding.owner == scenario.property_slug
    assert finding.property_condition == scenario.condition
    assert (finding.severity, finding.claim_class) == (scenario.severity, scenario.claim_class)
    assert report.gate.exit_code == (0 if scenario.severity == "warning" else 1)
    assert _ledger(scenario) == []


def test_the_three_defects_are_distinct_and_none_is_the_ci_gating_guides() -> None:
    conditions = {scenario.condition for scenario in SCENARIO_TABLE}
    properties = {scenario.property_slug for scenario in SCENARIO_TABLE}

    assert len(conditions) == len(properties) == 3
    assert CI_GATE_CONDITION not in conditions
    assert "effect-safety" not in properties
    # And the guide's defect really is P-06's, read off its own module rather than remembered.
    guide_module = (REPO_ROOT / "examples" / "ci_gate" / "test_unprotected_retry.py").read_text(
        encoding="utf-8"
    )
    assert "P-06" in guide_module and "effect-safety" in guide_module


@pytest.mark.parametrize("scenario", SCENARIO_TABLE, ids=SCENARIO_IDS)
def test_the_fix_passes_under_both_policies(scenario: Scenario) -> None:
    """A fix that only passes because a warning is not gated would not be a fix."""
    module = _module(scenario)
    ir = gebra.extract(getattr(module, scenario.fixed)()).ir

    for policy in (RunPolicy(), RunPolicy(strict=STRICT_ON_P08)):
        gate = verify(ir, policy).gate
        assert (gate.exit_code, gate.outcome, gate.promotions) == (0, "pass", ())
    assert _ledger(scenario) == []


def test_the_p08_scenario_moves_only_under_its_own_strict_policy() -> None:
    """The warning-grade scenario's second verdict: exit 1 under the flag, record unchanged."""
    (scenario,) = [s for s in SCENARIO_TABLE if s.severity == "warning"]
    ir = gebra.extract(getattr(_module(scenario), scenario.builder)()).ir
    default = verify(ir)
    strict = verify(ir, RunPolicy(strict=STRICT_ON_P08))

    assert (default.gate.exit_code, strict.gate.exit_code) == (0, 1)
    slug = scenario.property_slug
    assert [(p.property, p.origin) for p in strict.gate.promotions] == [(slug, "failure")]
    assert strict.outcome_for(slug) == default.outcome_for(slug)


# ── What the page says about each finding ────────────────────────────────────────────────


@pytest.mark.parametrize("scenario", SCENARIO_TABLE, ids=SCENARIO_IDS)
def test_the_page_names_the_condition_the_grade_and_the_claim_class(
    scenario: Scenario, page_text: str
) -> None:
    """WA-06: a finding on the page carries its class, in the section that shows it."""
    section = _section(page_text, scenario.heading)

    assert f"`{scenario.condition}`" in section
    assert scenario.severity.upper() in section
    assert scenario.claim_class.upper() in section
    assert f"`{scenario.property_slug}`" in section


@pytest.mark.parametrize("scenario", SCENARIO_TABLE, ids=SCENARIO_IDS)
def test_the_printed_verdict_names_the_same_finding(
    scenario: Scenario, examples: dict[str, DocExample]
) -> None:
    """The output block is the run's, and it carries the condition, grade and class too."""
    printed = examples[scenario.example_id].expected_output

    assert f"{scenario.severity.upper()} {scenario.condition} [{scenario.claim_class}]" in printed
    assert printed.rstrip("\n").endswith("node bodies run  []")


@pytest.mark.parametrize("scenario", SCENARIO_TABLE, ids=SCENARIO_IDS)
def test_each_readme_names_its_property_condition_and_class(scenario: Scenario) -> None:
    readme = (SCENARIOS / scenario.slug / "README.md").read_text(encoding="utf-8")

    assert f"`{scenario.condition}`" in readme
    assert f"`{scenario.property_slug}`" in readme
    assert scenario.claim_class.upper() in readme
    assert "docs/guides/use-cases.md" in readme


def test_the_page_keeps_the_witness_wording(page_text: str) -> None:
    """P-02 language is witness presence, never a statement that a run halts (WA-06)."""
    prose = re.sub(r"\s+", " ", page_text)

    assert "does not say the loop fails to terminate" in prose
    assert "never whether a run halts" in prose
    assert "None of the three is a statement about behaviour at run time" in prose


# ── The suite CI runs, run here ──────────────────────────────────────────────────────────


def test_the_ci_step_runs_the_scenarios_from_the_pip_editable_job() -> None:
    """A step, not a job: the toolchain test's own reader sees it, and the job count holds."""
    assert CI_STEP in _workflow_run_steps()

    workflow: dict[str, Any] = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))
    steps = [step.get("run") for step in workflow["jobs"]["pip-editable"]["steps"]]
    assert CI_STEP in steps
    assert steps.index("pytest -q") < steps.index(CI_STEP)
    assert len(workflow["jobs"]) == 18


def test_the_scenario_suite_is_green_as_a_suite() -> None:
    """The card's condition: no item is red by design. The CI step, run, exiting zero."""
    finished = _run("-m", "pytest", "examples/scenarios", "-q", "-p", "no:cacheprovider")

    assert finished.returncode == 0, finished.stdout + finished.stderr
    # The last line is pytest's own summary; the plugin's closing `gebra` section above it
    # prints severity tallies ("0 error"), so the words are read off the summary line alone.
    summary = finished.stdout.rstrip().splitlines()[-1]
    passed = re.fullmatch(r"(\d+) passed in [\d.]+s(?: \(.*\))?", summary)
    assert passed is not None, summary
    assert int(passed.group(1)) >= 3 * (3 + len(enabled_properties()))


def test_only_the_fixed_variants_are_marked() -> None:
    """The item ids pytest collects: one marked target per scenario, and it is the fix."""
    collected = _run(
        "-m", "pytest", "examples/scenarios", "--collect-only", "-q", "-p", "no:cacheprovider"
    )
    assert collected.returncode == 0, collected.stdout + collected.stderr

    marked = re.findall(r"::test_gebra\[([a-z_]+)-([a-z-]+)\]", collected.stdout)
    assert {target for target, _slug in marked} == {s.target for s in SCENARIO_TABLE}
    for scenario in SCENARIO_TABLE:
        slugs = [slug for target, slug in marked if target == scenario.target]
        assert slugs == list(enabled_properties()), scenario.slug


def test_the_scenarios_are_outside_testpaths() -> None:
    """Reached by path only — the CI step and the children above — like ``ci_gate/``."""
    with (REPO_ROOT / "pyproject.toml").open("rb") as handle:
        pyproject = tomllib.load(handle)

    assert pyproject["tool"]["pytest"]["ini_options"]["testpaths"] == ["tests"]
    assert "/examples" in pyproject["tool"]["hatch"]["build"]["targets"]["sdist"]["include"]


# ── The ledgers, fired on both paths ─────────────────────────────────────────────────────


@pytest.mark.parametrize("scenario", SCENARIO_TABLE, ids=SCENARIO_IDS)
def test_every_body_of_the_scenario_records_and_raises(scenario: Scenario) -> None:
    """A tripwire nobody trips proves nothing: each body, called, lands in the ledger first."""
    module = _module(scenario)
    ledger = _ledger(scenario)
    bodies = [
        name
        for name, value in vars(module).items()
        if callable(value)
        and getattr(value, "__module__", None) == module.__name__
        and not name.startswith(("_", "build_", "main"))
        and not isinstance(value, type)
    ]
    assert len(bodies) >= 4, bodies

    for name in bodies:
        with pytest.raises(BaseException, match="was invoked") as caught:
            getattr(module, name)({})
        assert not isinstance(caught.value, Exception), "an `except Exception` could swallow it"
        assert ledger[-1] == name
    assert ledger == bodies
    ledger.clear()


def test_the_conftest_sweep_discovers_every_scenario_ledger() -> None:
    """``examples/conftest.py`` holds each scenario's own list object, never a copy."""
    conftest = importlib.import_module("examples.conftest")

    assert set(conftest.LEDGERS) == {"travel_booking", *SCENARIO_IDS}
    for scenario in SCENARIO_TABLE:
        assert conftest.LEDGERS[scenario.slug] is _ledger(scenario)


def test_the_conftest_refuses_a_scenario_that_keeps_no_ledger(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The discovery's fail-closed leg, fired: a ledger-less scenario is refused at import.

    Discovery is pointed at a scratch tree holding one scenario, whose module is registered in
    ``sys.modules`` under the name the conftest imports — so the import returns the stub and
    nothing under ``examples/`` is touched. A stub carrying no ``TRIPPED`` is refused, naming
    the file; the same stub carrying a list is discovered under its slug, with identity.
    """
    conftest = importlib.import_module("examples.conftest")
    (tmp_path / "ledgerless").mkdir()
    (tmp_path / "ledgerless" / "workflow.py").write_text("", encoding="utf-8")
    monkeypatch.setattr(conftest, "SCENARIOS", tmp_path)
    stub = ModuleType("examples.scenarios.ledgerless.workflow")
    monkeypatch.setitem(sys.modules, stub.__name__, stub)

    with pytest.raises(TypeError, match="examples/scenarios/ledgerless/workflow.py keeps no"):
        conftest._scenario_ledgers()

    ledger: list[str] = []
    monkeypatch.setattr(stub, "TRIPPED", ledger, raising=False)
    discovered = conftest._scenario_ledgers()
    assert set(discovered) == {"travel_booking", "ledgerless"}
    assert discovered["ledgerless"] is ledger


def test_a_body_that_ran_fails_the_pytest_path(tmp_path: Path) -> None:
    """The conftest sweep, fired: a swallowed body call errors the test at teardown."""
    scenario = SCENARIO_TABLE[0]
    scratch = tmp_path / "test_swallowed.py"
    scratch.write_text(
        f"from {scenario.module_name} import {scenario.body}\n"
        "\n"
        "\n"
        "def test_a_body_runs_and_is_swallowed() -> None:\n"
        "    try:\n"
        f"        {scenario.body}({{}})\n"
        "    except BaseException:\n"
        "        pass\n",
        encoding="utf-8",
    )
    clean = tmp_path / "test_clean.py"
    clean.write_text("def test_nothing_ran() -> None:\n    pass\n", encoding="utf-8")

    swept = _run(
        "-m", "pytest", "-p", "examples.conftest", "-q", "-p", "no:cacheprovider", str(scratch)
    )
    assert swept.returncode == 1, swept.stdout + swept.stderr
    assert f"{{'{scenario.slug}': ['{scenario.body}']}}" in swept.stdout
    control = _run(
        "-m", "pytest", "-p", "examples.conftest", "-q", "-p", "no:cacheprovider", str(clean)
    )
    assert control.returncode == 0, control.stdout + control.stderr


@pytest.mark.parametrize("scenario", SCENARIO_TABLE, ids=SCENARIO_IDS)
def test_a_body_that_ran_fails_the_page_example(
    scenario: Scenario, examples: dict[str, DocExample]
) -> None:
    """Both halves of the executed file's arming, fired.

    Tripped *before* ``main()``, the file's own assertion exits the child 1 and the printed
    output is not the page's. Tripped *after* it, the file has printed a clean verdict and the
    harness trailer's ``__main__`` sweep is what names the body — the leg that makes reproducing
    a file as an example safe without the file cooperating.
    """
    example = examples[scenario.example_id]
    swallowed = f"try:\n    {scenario.body}({{}})\nexcept BaseException:\n    pass\n"
    guard = 'if __name__ == "__main__":\n    main()\n'
    assert example.code.endswith(guard)

    before = run_example(
        dataclasses.replace(example, code=example.code.replace(guard, swallowed + guard))
    )
    assert not before.ok
    assert before.returncode == 1
    assert any("printed output does not match" in problem for problem in before.problems)

    after = run_example(
        dataclasses.replace(
            example, code=example.code + "    " + swallowed.replace("\n", "\n    ").rstrip(" ")
        )
    )
    assert not after.ok
    assert after.returncode == 0, after.stderr
    assert any(f"WA07-LEDGER ['__main__:{scenario.body}']" in p for p in after.problems)


@pytest.mark.parametrize("scenario", SCENARIO_TABLE, ids=SCENARIO_IDS)
def test_a_fix_block_asserts_its_own_ledger_because_the_sweep_does_not_reach_it(
    scenario: Scenario, examples: dict[str, DocExample]
) -> None:
    """The card's premise, observed: an imported scenario module is outside the trailer's sweep.

    A body tripped *after* the fix block's own assertion leaves the trailer's verdict clean —
    which is exactly why each block asserts and prints ``workflow.TRIPPED`` itself, and what
    this test records. Tripped before the assertion, the block exits 1.
    """
    fix = examples[scenario.fix_example_id]
    probe = f"try:\n    workflow.{scenario.body}({{}})\nexcept BaseException:\n    pass\n"
    own_assert = "assert workflow.TRIPPED == [], workflow.TRIPPED\n"
    assert own_assert in fix.code

    unreached = run_example(fix, probe=probe)
    assert unreached.ok, unreached.report()

    caught = run_example(
        dataclasses.replace(fix, code=fix.code.replace(own_assert, probe + own_assert))
    )
    assert not caught.ok
    assert caught.returncode == 1
    assert f"AssertionError: ['{scenario.body}']" in caught.stderr


# ── Registration and the honest-claims vocabulary ────────────────────────────────────────


def test_the_page_is_registered_everywhere_a_page_has_to_be() -> None:
    config = yaml.safe_load(MKDOCS.read_text(encoding="utf-8"))
    guides = next(
        entry["Guides"] for entry in config["nav"] if isinstance(entry, dict) and "Guides" in entry
    )

    assert {"Use cases": "guides/use-cases.md"} in guides
    assert "guides/use-cases.md" in WRITTEN_PAGES

    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert "](docs/guides/use-cases.md)" in readme
    assert "](examples/scenarios)" in readme
    assert "](guides/use-cases.md)" in (REPO_ROOT / "docs" / "index.md").read_text(encoding="utf-8")


def test_the_page_and_the_scenario_sources_stay_inside_the_honest_claims_vocabulary() -> None:
    """WA-06 over the tree the default lint scope leaves out — ``examples/`` — and the page."""
    phrases = load_phrases(REPO_ROOT / "tools" / "honest-claims-phrases.txt")
    include = (PAGE_PATH, "examples/scenarios/**/*.py", "examples/scenarios/**/*.md")
    covered = set(scan_files(REPO_ROOT, include, ()))

    expected = {PAGE_PATH, "examples/scenarios/__init__.py"} | {
        f"examples/scenarios/{scenario.slug}/{name}"
        for scenario in SCENARIO_TABLE
        for name in SCENARIO_FILES
    }
    assert expected <= covered
    report = scan(REPO_ROOT, phrases, include=include, exclude=())
    assert report.ok, [f"{v.path}:{v.line_no}: {v.detail}" for v in report.violations]
