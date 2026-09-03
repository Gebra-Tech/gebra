"""``docs/guides/install-and-compatibility.md`` pinned to the sources it summarises (DOC-18).

The page answers "can I run gebra here, and what does a version change mean", and almost
every sentence in it is a fact about something else in the repository: a command a CI job
runs, a pin in the packaging metadata, a band the runtime check compares against, the text a
warning carries, a label the version engine derives. Prose cannot hold itself to any of that,
so this module does:

* every shell command on the page is one a named CI job runs, and the index command plus the
  three-line checkout block are the declared exceptions — the acceptance requirement that the
  page's install commands are executed in CI, made mechanical;
* the declared ranges are ``pyproject.toml``'s, and the matrix's pins are the
  ``compat-cell-N`` extras', both directions;
* the band table is checked **against the classifier itself** over a grid built from the
  table's own numbers, so a pairing the page calls tested that ``classify_substrate`` does
  not — or the reverse — fails here;
* the ``GebraVersionWarning`` transcript's message, its category and the warn-once policy are
  re-derived from the real check, and the out-of-range record from the real emitter;
* the V.S.F.E transcript's labels and counters are re-derived from ``EVOLUTION``'s recorded
  expectations, its P-12 deferral from the marker a real ``workflow_diff`` carries, and the one
  effect tag it names from that stage's own declared contract;
* the §4 policy paragraphs are pinned, and — where the development-process repository is
  checked out beside this one — the ranges, the pins, the cell counts and the F2 freeze
  citation are reconciled against the living document that rules them.

One consequence of the page, recorded here because this is where someone debugging it will
look. Its ``checking-your-own-install`` example classifies the **live** install and prints
``inside the declared ranges: True``, which holds on all twelve frozen cells but would print
``False`` on the ``--pre`` cell the day a langgraph or langchain-core 2.0 prerelease appears.
That is not a defect in the page: a red ``--pre`` pytest gate is exactly the signal
VERSION-COMPAT §4's 2.0 watch routes to a supported-range review, and the cell never blocks.
Every other example on the page is substrate-independent by construction — the transcripts
that name versions name simulated ones.

The module extracts from the sentinel-guarded travel-booking fixtures, whose bodies record
into the shared ledger and raise if anything calls them; every test asserts that ledger is
empty when it finishes, so a run in which a node executed could not report these results
(WA-07). Reading distribution metadata is not importing a package: nothing here imports
langgraph or langchain-core, and nothing opens a connection.
"""

from __future__ import annotations

import re
import subprocess
import sys
import warnings
from collections.abc import Iterator
from pathlib import Path
from typing import Any, Final

import pytest
import yaml

from gebra import extract
from gebra.diff import EVOLUTION_SAFETY_DEFERRED, workflow_diff
from gebra.extraction import (
    ExtractionWarningCode,
    GebraVersionWarning,
    SubstrateVersions,
    classify_substrate,
    compat,
    out_of_range_warning,
)
from gebra.extraction.compat import CompatClass
from gebra.extraction.compat import read_installed_versions as _the_real_reader
from gebra.verify import is_implemented
from gebra.versioning import Component, Version, changed_components, next_version
from tests.sample_workflows import travel_booking
from tests.sample_workflows.travel_booking_evolution import EVOLUTION
from tools.honest_claims_lint import load_phrases, scan

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - exercised on the 3.10 matrix cells
    import tomli as tomllib

REPO_ROOT: Final = Path(__file__).resolve().parents[2]
PAGE: Final = REPO_ROOT / "docs" / "guides" / "install-and-compatibility.md"
PYPROJECT: Final = REPO_ROOT / "pyproject.toml"
CI_WORKFLOW: Final = REPO_ROOT / ".github" / "workflows" / "ci.yml"
PHRASES: Final = REPO_ROOT / "tools" / "honest-claims-phrases.txt"

#: The commands the page shows that **no** CI job runs, and the reason the page gives for
#: showing them anyway. The index command is the install a reader performs against the
#: published package, and no job here installs gebra from an index, because every job checks
#: the tree it runs in (GOV-14 grew this tuple by exactly that line). The checkout lines are
#: the checkout a reader performs, and the build they trigger is the one the `build` job
#: performs a step later. Any other unmatched command is a failure — this tuple is the whole
#: licence, and growing it is a decision someone has to make on purpose.
NOT_RUN_IN_CI: Final[tuple[str, ...]] = (
    "pip install gebra",
    "git clone https://github.com/Gebra-Tech/gebra.git",
    "cd gebra",
    "pip install .",
)

#: Every other command on the page, with every job that runs it — the "which job runs which
#: command" table, as the workflow has to agree it is.
INSTALL_COMMANDS: Final[tuple[tuple[str, tuple[str, ...]], ...]] = (
    ("uv build --out-dir dist", ("build", "readme-quickstart")),
    ("python -m venv /tmp/wheelcheck", ("build",)),
    ("/tmp/wheelcheck/bin/pip install --no-cache-dir dist/*.whl", ("build",)),
    (
        "uv sync --extra dev --frozen",
        (
            "lint",
            "schema-lockstep",
            "corpus-lint",
            "golden-harness",
            "corpus-green",
            "typecheck",
            "test-locked",
        ),
    ),
    (
        'pip install -e ".[dev]" -c tools/matrix-constraints.txt',
        ("pip-editable", "docs", "test-matrix-pre"),
    ),
    ('pip install -e ".[dev,compat-cell-3]" -c tools/matrix-constraints.txt', ("dod",)),
)

#: The frozen cells as the page's pin table shows them: cell number → the three pins it names.
#: Held to ``pyproject.toml``'s extras in both directions below, never transcribed as truth.
CELLS: Final[tuple[str, ...]] = ("1", "2", "3")

#: The tested Python minors, as the page's line under the pin table shows them.
PAGE_PYTHONS: Final[tuple[str, ...]] = ("3.10", "3.11", "3.12", "3.13")

#: The two yanked langgraph releases the page names as excluded by the pins.
YANKED: Final[tuple[str, ...]] = ("1.1.7", "1.2.3")

#: The triple the page's two `GebraVersionWarning` examples simulate, and the one its
#: out-of-range example simulates. Both are re-run through the real code below.
UNTESTED_PAIRING: Final = SubstrateVersions(
    python=(3, 13),
    langgraph=(1, 0, 10),
    langchain_core=(1, 5, 3),
    langgraph_raw="1.0.10",
    langchain_core_raw="1.5.3",
)
OUT_OF_RANGE_INSTALL: Final = SubstrateVersions(
    python=(3, 13),
    langgraph=(2, 0, 0),
    langchain_core=(1, 5, 3),
    langgraph_raw="2.0.0",
    langchain_core_raw="1.5.3",
)

#: The sentences that carry this page's WA-06 boundary. Each is a claim the page would be
#: dishonest without, so each is pinned rather than trusted to survive an edit.
BOUNDARY_SENTENCES: Final[tuple[str, ...]] = (
    "It is a warning, not a failure.",
    "A bump is not a verdict.",
    "being untested is a fact about gebra's testing, not a defect in the document",
    "It never *runs* anything it reads",
)

#: The §4 policy the page restates, sentence by sentence, and the substring of the living
#: document's §4 that says the same thing where that repository is checked out. Matched
#: against the whitespace-collapsed page, so re-wrapping a paragraph is not a failure.
POLICY_CLAIMS: Final[tuple[tuple[str, str], ...]] = (
    (
        (
            "the matrix extends to include them, in one change that also carries the "
            "CHANGELOG entry citing the run that justified it"
        ),
        "extend the tested matrix to include it + changelog entry citing the drift-suite run",
    ),
    (
        "the tested ceiling is capped at the last green pair and a version-gap issue is opened",
        "open a version-gap issue + cap the tested ceiling at the last green pair",
    ),
    (
        "No assertion is weakened on either path",
        "No silent downgrade of assertions in either path.",
    ),
    (
        (
            "A prerelease appearing triggers an immediate run of the `--pre` cell and a "
            "review of the supported range"
        ),
        ("a 2.0 alpha on PyPI triggers an immediate `--pre` cell run and a supported-range review"),
    ),
)

# The development-process repository: present in a working checkout, absent in the library
# repository's own CI. Cross-repository assertions are skipped there rather than faked.
COMPANION: Final = REPO_ROOT.parent / "gebra-dev-doc"
VERSION_COMPAT: Final = COMPANION / "docs" / "specs" / "VERSION-COMPAT.md"

requires_the_living_document = pytest.mark.skipif(
    not VERSION_COMPAT.is_file(),
    reason="the development-process repository is not checked out beside this one",
)


@pytest.fixture(scope="module")
def page_text() -> str:
    return PAGE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def prose(page_text: str) -> str:
    """The page with every run of whitespace collapsed, for sentence-level assertions."""
    return re.sub(r"\s+", " ", page_text)


@pytest.fixture(scope="module")
def workflow() -> dict[str, Any]:
    parsed: dict[str, Any] = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))
    return parsed


@pytest.fixture(scope="module")
def extras() -> dict[str, list[str]]:
    with PYPROJECT.open("rb") as handle:
        optional: dict[str, list[str]] = tomllib.load(handle)["project"]["optional-dependencies"]
    return optional


@pytest.fixture(scope="module")
def project() -> dict[str, Any]:
    with PYPROJECT.open("rb") as handle:
        parsed: dict[str, Any] = tomllib.load(handle)["project"]
    return parsed


@pytest.fixture(autouse=True)
def _ledger_is_clean() -> Iterator[None]:
    """WA-07: nothing in this module may run a node body, before or after (the TE-05 idiom)."""
    assert travel_booking.TRIPPED == []
    yield
    assert travel_booking.TRIPPED == []


@pytest.fixture(autouse=True)
def _restore_the_version_check() -> Iterator[None]:
    """Every test here starts *and* ends with the real reader and a cleared memo.

    Restoring on teardown alone would put back whatever was bound at setup, so a module that
    leaked a simulated reader would be preserved by this fixture rather than caught by it.
    The real function is captured at import instead — before any test has run — which is the
    idiom ``tests/extraction/test_compat.py``'s own autouse fixture uses.
    """
    compat.read_installed_versions = _the_real_reader
    compat.reset_version_check_cache()
    yield
    compat.read_installed_versions = _the_real_reader
    compat.reset_version_check_cache()


def _fenced_blocks(text: str, info: str) -> list[str]:
    """Every fenced block whose info string is ``info``, body only."""
    blocks = []
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        if lines[index].strip() == f"```{info}":
            closing = index + 1
            while closing < len(lines) and lines[closing].strip() != "```":
                closing += 1
            blocks.append("\n".join(lines[index + 1 : closing]))
            index = closing + 1
            continue
        index += 1
    return blocks


def _shell_commands(text: str) -> list[str]:
    """Every command line the page shows in a ``bash`` block, comments and blanks dropped."""
    commands = []
    for block in _fenced_blocks(text, "bash"):
        for line in block.splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                commands.append(stripped)
    return commands


def _run_steps(workflow: dict[str, Any], job: str) -> list[str]:
    return [step["run"] for step in workflow["jobs"][job]["steps"] if "run" in step]


def _every_run_step(workflow: dict[str, Any]) -> list[str]:
    return [step for job in workflow["jobs"] for step in _run_steps(workflow, job)]


def _table_rows(text: str, header: str) -> list[list[str]]:
    """The body cells of the first pipe table whose header line is ``header``, row by row."""
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if line.strip() != header:
            continue
        body = []
        for candidate in lines[index + 2 :]:  # +2 skips the alignment row
            if not candidate.startswith("|"):
                break
            body.append([cell.strip() for cell in candidate.strip("|").split("|")])
        return body
    raise AssertionError(f"no table with header {header!r}")


def _pins(requirements: list[str]) -> dict[str, str]:
    """The ``name == version`` pins in a requirement list, keyed by distribution name."""
    pinned: dict[str, str] = {}
    for requirement in requirements:
        name, separator, version = requirement.partition("==")
        if separator:
            pinned[name.strip()] = version.strip()
    return pinned


def _triple(raw: str) -> tuple[int, int, int]:
    parts = [int(part) for part in raw.split(".")]
    parts += [0] * (3 - len(parts))
    major, minor, micro = parts[:3]
    return major, minor, micro


def _install(
    python: tuple[int, int], langgraph: tuple[int, int, int], core: tuple[int, int, int]
) -> SubstrateVersions:
    return SubstrateVersions(
        python=python,
        langgraph=langgraph,
        langchain_core=core,
        langgraph_raw=".".join(str(part) for part in langgraph),
        langchain_core_raw=".".join(str(part) for part in core),
    )


# ── The install commands: every one is a command CI runs ──────────────────────────────────


def test_every_shell_command_on_the_page_is_one_ci_runs(
    page_text: str, workflow: dict[str, Any]
) -> None:
    """Acceptance box 1, first half — with exactly one declared exception.

    Verbatim membership in a job's ``run`` script, not a similarity check: a page that showed
    an install command CI does not perform would be describing an install nobody has run.
    """
    steps = "\n".join(_every_run_step(workflow))
    unmatched = [
        command
        for command in _shell_commands(page_text)
        if command not in NOT_RUN_IN_CI and command not in steps
    ]

    assert unmatched == [], f"the page shows install commands no CI job runs: {unmatched}"


def test_the_declared_exceptions_are_the_index_command_and_the_checkout_block(
    page_text: str, workflow: dict[str, Any]
) -> None:
    """The other direction: the licence is not vacuous, and it has not grown.

    Each declared line is really on the page (so a stale entry cannot quietly license a new
    command), really run by no job (so the licence never covers a command CI performs after
    all — the page's "no CI job installs gebra from an index" is this assertion), and no fifth
    command is exempt.
    """
    commands = _shell_commands(page_text)
    steps = _every_run_step(workflow)

    for command in NOT_RUN_IN_CI:
        assert command in commands, f"{command!r} is declared not-run-in-CI but is not shown"
        assert not any(command in step for step in steps), f"a CI job runs {command!r}"
    assert len(NOT_RUN_IN_CI) == 4


@pytest.mark.parametrize(("command", "jobs"), INSTALL_COMMANDS)
def test_each_command_runs_in_every_job_the_page_names(
    workflow: dict[str, Any], command: str, jobs: tuple[str, ...]
) -> None:
    """The page's job table, checked job by job against the workflow's own steps."""
    for job in jobs:
        assert job in workflow["jobs"], f"the page names a job {job!r} the workflow does not have"
        assert any(command in step for step in _run_steps(workflow, job)), (
            f"job {job!r} does not run {command!r}"
        )


@pytest.mark.parametrize(("command", "jobs"), INSTALL_COMMANDS)
def test_no_other_job_runs_the_command(
    workflow: dict[str, Any], command: str, jobs: tuple[str, ...]
) -> None:
    """And the table names *every* job that runs it — so "and four more" stays a count."""
    running = {
        job
        for job in workflow["jobs"]
        if any(command in step for step in _run_steps(workflow, job))
    }

    assert running == set(jobs)


def test_the_locked_sync_count_the_page_gives_is_the_workflows(page_text: str) -> None:
    """ "`lint`, `typecheck`, `test-locked`, and four more" is seven jobs, and it is checked."""
    [(_command, jobs)] = [
        entry for entry in INSTALL_COMMANDS if entry[0] == "uv sync --extra dev --frozen"
    ]

    assert len(jobs) == 7
    assert "and four more" in page_text


def test_the_matrix_cells_install_the_extra_the_page_shows(workflow: dict[str, Any]) -> None:
    """The page says to swap the cell number; the twelve matrix cells do exactly that."""
    steps = _run_steps(workflow, "test-matrix")

    assert any(
        'pip install -e ".[dev,compat-cell-${{ matrix.cell }}]" '
        "-c tools/matrix-constraints.txt" in step
        for step in steps
    )


# ── The envelope: what the metadata declares ──────────────────────────────────────────────


def test_the_declared_ranges_table_is_the_packaging_metadata(
    page_text: str, project: dict[str, Any]
) -> None:
    """The installability envelope is read off ``pyproject.toml``, never transcribed."""
    declared = {
        requirement.split(">=")[0].strip(): requirement for requirement in project["dependencies"]
    }
    rows = {
        row[0]: row[1]
        for row in _table_rows(page_text, "| Axis | Declared | Where it comes from |")
    }

    assert rows["Python"] == f"`{project['requires-python']}`"
    for distribution in ("langgraph", "langchain-core"):
        floor, ceiling = re.findall(r"[<>]=?[\d.]+", declared[distribution])
        assert rows[f"`{distribution}`"] == f"`{floor},{ceiling}`"


def test_the_page_names_every_declared_substrate_axis(
    page_text: str, project: dict[str, Any]
) -> None:
    """The other direction: a third substrate axis appearing in the metadata must reach here."""
    rows = _table_rows(page_text, "| Axis | Declared | Where it comes from |")

    assert [row[0] for row in rows] == ["Python", "`langgraph`", "`langchain-core`"]
    assert "langgraph" in str(project["dependencies"])


# ── The tested matrix: the pins, the Pythons, the counts ──────────────────────────────────


def test_the_pin_table_is_the_compat_cell_extras(
    page_text: str, extras: dict[str, list[str]]
) -> None:
    """Cell for cell, pin for pin, in both directions — the page's central factual claim."""
    header = "| Cell | `langgraph` | `langchain-core` | `pydantic` (transitive) |"
    rows = _table_rows(page_text, header)

    assert [row[0] for row in rows] == list(CELLS)
    for row in rows:
        pinned = _pins(extras[f"compat-cell-{row[0]}"])
        assert row[1] == f"`{pinned['langgraph']}`"
        assert row[2] == f"`{pinned['langchain-core']}`"
        assert row[3] == f"`{pinned['pydantic']}`"


def test_the_page_shows_every_frozen_cell(extras: dict[str, list[str]]) -> None:
    """A fourth cell added to the metadata would leave this page describing three."""
    declared = {name.rpartition("-")[2] for name in extras if name.startswith("compat-cell-")}

    assert declared == set(CELLS)


def test_the_tested_pythons_are_the_workflow_matrix(
    page_text: str, workflow: dict[str, Any]
) -> None:
    matrix = workflow["jobs"]["test-matrix"]["strategy"]["matrix"]

    assert tuple(matrix["python-version"]) == PAGE_PYTHONS
    assert f"**{', '.join(PAGE_PYTHONS)}**" in page_text


def test_the_cell_counts_are_the_workflow_matrix(page_text: str, workflow: dict[str, Any]) -> None:
    """12 blocking cells and a 13th that never blocks — counted from the workflow itself."""
    matrix = workflow["jobs"]["test-matrix"]["strategy"]["matrix"]
    blocking = len(matrix["python-version"]) * len(matrix["cell"])

    assert blocking == 12
    assert "**12 blocking CI cells**" in page_text
    assert "= 13" in page_text
    assert "strategy" not in workflow["jobs"]["test-matrix-pre"], "the --pre cell is one cell"
    assert workflow["jobs"]["test-matrix-pre"]["continue-on-error"] is True


def test_the_gates_the_page_says_every_cell_runs_are_the_gates_it_runs(
    page_text: str, workflow: dict[str, Any]
) -> None:
    steps = "\n".join(_run_steps(workflow, "test-matrix"))

    for gate in ("ruff check", "ruff format --check", "mypy"):
        assert gate in steps
        assert f"`{gate}" in page_text


def test_the_yanked_releases_the_page_names_are_pinned_by_no_cell(
    page_text: str, extras: dict[str, list[str]]
) -> None:
    """§4: the exclusion is enforced by the pins, which is only true while they exclude them."""
    for version in YANKED:
        assert f"`{version}`" in page_text
        for cell in CELLS:
            assert _pins(extras[f"compat-cell-{cell}"])["langgraph"] != version


def test_the_pre_cell_the_page_describes_is_the_workflows(workflow: dict[str, Any]) -> None:
    """Newest prerelease of both packages, newest tested Python, nothing pinned."""
    steps = _run_steps(workflow, "test-matrix-pre")
    setups = [
        step
        for step in workflow["jobs"]["test-matrix-pre"]["steps"]
        if str(step.get("uses", "")).startswith("actions/setup-python")
    ]

    assert any(
        "--pre" in step and "langgraph" in step and "langchain-core" in step for step in steps
    )
    assert [step["with"]["python-version"] for step in setups] == [PAGE_PYTHONS[-1]]


# ── The bands: the page's table against the classifier, both directions ───────────────────


def _band_table(page_text: str) -> dict[str, tuple[str, str]]:
    header = "| Cell | `langgraph` | `langchain-core` |"
    return {
        row[0]: (row[1].strip("`"), row[2].strip("`")) for row in _table_rows(page_text, header)
    }


def _bounds(band: str) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    """``>=1.2, <1.3`` as its half-open pair of triples."""
    floor, ceiling = re.findall(r"[<>]=?\s*([\d.]+)", band)
    return _triple(floor), _triple(ceiling)


def test_the_band_table_calls_tested_exactly_what_the_classifier_does(page_text: str) -> None:
    """The runtime check is the authority; the table is held to it over a derived grid.

    The grid is built from the table's own numbers — every band's floor, the version just
    below its ceiling, and its ceiling — and every langgraph value is paired with every
    langchain-core value, so the cross-cell pairings the page calls untested are in it. For
    each of the 81 pairs the table's own verdict ("inside one row's two bands") is compared
    with :func:`classify_substrate`'s. A row the classifier disagrees with, in either
    direction, fails.
    """
    bands = _band_table(page_text)
    langgraphs: set[tuple[int, int, int]] = set()
    cores: set[tuple[int, int, int]] = set()
    for langgraph_band, core_band in bands.values():
        for band, values in ((langgraph_band, langgraphs), (core_band, cores)):
            floor, ceiling = _bounds(band)
            values.update({floor, (ceiling[0], ceiling[1], ceiling[2]), _just_below(ceiling)})

    checked = 0
    for langgraph in sorted(langgraphs):
        for core in sorted(cores):
            in_a_row = any(
                _bounds(langgraph_band)[0] <= langgraph < _bounds(langgraph_band)[1]
                and _bounds(core_band)[0] <= core < _bounds(core_band)[1]
                for langgraph_band, core_band in bands.values()
            )
            expected = CompatClass.TESTED if in_a_row else CompatClass.IN_RANGE_UNTESTED
            actual = classify_substrate(_install((3, 13), langgraph, core))
            if actual is CompatClass.OUT_OF_RANGE:
                continue  # a 2.0 endpoint: the envelope decides before any band does
            assert actual is expected, f"langgraph {langgraph}, core {core}: {actual}"
            checked += 1

    assert checked >= 40, "the derived grid stopped covering the table"


def _just_below(version: tuple[int, int, int]) -> tuple[int, int, int]:
    major, minor, micro = version
    if micro:
        return (major, minor, micro - 1)
    if minor:
        return (major, minor - 1, 999)
    return (major - 1, 999, 999)


def test_the_page_names_a_band_for_every_frozen_cell(page_text: str) -> None:
    assert set(_band_table(page_text)) == set(CELLS)


def test_the_cross_cell_pairing_the_page_calls_untested_is(page_text: str) -> None:
    """The page's worked case: cell 1's langgraph with cell 3's langchain-core."""
    bands = _band_table(page_text)
    langgraph, _ = _bounds(bands["1"][0])
    _, core_band = bands["3"]
    core, _ = _bounds(core_band)

    assert classify_substrate(_install((3, 13), langgraph, core)) is CompatClass.IN_RANGE_UNTESTED


def test_each_cells_pins_land_inside_that_cells_band(
    page_text: str, extras: dict[str, list[str]]
) -> None:
    """The two tables are separately derived — the pins from §3's rule, the bands from §1 —
    and they have to agree, or CI would install a substrate ``extract()`` warns about."""
    bands = _band_table(page_text)

    for cell in CELLS:
        pinned = _pins(extras[f"compat-cell-{cell}"])
        langgraph_band, core_band = bands[cell]
        for band, pin in (
            (langgraph_band, pinned["langgraph"]),
            (core_band, pinned["langchain-core"]),
        ):
            floor, ceiling = _bounds(band)
            assert floor <= _triple(pin) < ceiling, f"cell {cell}: {pin} is outside {band}"


@pytest.mark.parametrize("python", PAGE_PYTHONS)
def test_every_tested_python_makes_every_cells_pins_tested(
    extras: dict[str, list[str]], python: str
) -> None:
    """The whole matrix, through the check ``extract()`` calls: twelve tested cells."""
    major, minor = (int(part) for part in python.split("."))
    for cell in CELLS:
        pinned = _pins(extras[f"compat-cell-{cell}"])
        versions = _install(
            (major, minor), _triple(pinned["langgraph"]), _triple(pinned["langchain-core"])
        )
        assert classify_substrate(versions) is CompatClass.TESTED


# ── The three classes ─────────────────────────────────────────────────────────────────────


def test_the_class_table_is_the_enumeration(page_text: str) -> None:
    """Three classes on the page, three in the code, same words, same order."""
    rows = _table_rows(page_text, "| Class | What it is | What gebra does |")

    assert [row[0] for row in rows] == [f"`{member.value}`" for member in CompatClass]


def test_the_transcript_of_six_installs_is_what_the_classifier_returns(page_text: str) -> None:
    """Every ``->`` line in the page's first transcript, re-derived from its own inputs."""
    [block] = [
        body
        for body in _fenced_blocks(page_text, "text")
        if "->  tested" in body and "->  out-of-range" in body
    ]
    lines = [line for line in block.splitlines() if "->" in line]

    assert len(lines) == 6
    for line in lines:
        described, _, expected = line.partition("  ->  ")
        python, langgraph, core = (part.strip() for part in described.split(","))
        versions = _install(
            tuple(int(part) for part in python.split(".")),  # type: ignore[arg-type]
            _triple(langgraph.removeprefix("langgraph ")),
            _triple(core.removeprefix("core ")),
        )
        assert classify_substrate(versions).value == expected.strip()


def test_a_python_below_the_floor_is_out_of_range_as_the_page_says(prose: str) -> None:
    """The page's asymmetry paragraph: below the floor is out-of-range, above it is untested."""
    below = _install((3, 9), (1, 2, 10), (1, 5, 3))
    above = _install((3, 14), (1, 2, 10), (1, 5, 3))

    assert classify_substrate(below) is CompatClass.OUT_OF_RANGE
    assert classify_substrate(above) is CompatClass.IN_RANGE_UNTESTED
    assert "A Python *below* the floor is different" in prose


# ── GebraVersionWarning ───────────────────────────────────────────────────────────────────


def _simulate(versions: SubstrateVersions) -> None:
    """Point the check at ``versions`` and clear the memo — what the page's examples do."""
    compat.read_installed_versions = lambda: versions
    compat.reset_version_check_cache()


def test_the_warning_message_on_the_page_is_the_one_the_check_emits(page_text: str) -> None:
    """The transcript's last line, re-derived by running the real check on the same triple."""
    _simulate(UNTESTED_PAIRING)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        compat.check_version_once()

    [warned] = caught
    assert str(warned.message) in page_text


def test_the_warn_once_policy_the_page_claims_holds(prose: str) -> None:
    """Two extractions, one warning — the page's "once per process, not once per call"."""
    _simulate(UNTESTED_PAIRING)
    agent = travel_booking.build_travel_booking_agent()

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        first = extract(agent)
        second = extract(agent)

    version_warnings = [w for w in caught if issubclass(w.category, GebraVersionWarning)]
    assert len(version_warnings) == 1
    assert first.warnings == () and second.warnings == ()
    assert first.graph_version() == second.graph_version()
    assert "Once per process, not once per call." in prose


def test_the_category_is_the_plain_user_warning_the_page_describes(prose: str) -> None:
    assert issubclass(GebraVersionWarning, UserWarning)
    assert "`GebraVersionWarning` subclasses `UserWarning`" in prose


def test_the_warning_can_be_escalated_and_filtered_as_the_page_shows() -> None:
    """Both directions of the second example, through the real check."""
    _simulate(UNTESTED_PAIRING)
    with warnings.catch_warnings():
        warnings.filterwarnings("error", category=GebraVersionWarning)
        with pytest.raises(GebraVersionWarning):
            compat.check_version_once()

    _simulate(UNTESTED_PAIRING)
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=GebraVersionWarning)
        assert compat.check_version_once().compat is CompatClass.IN_RANGE_UNTESTED


def test_importing_gebra_neither_warns_nor_reads_a_version(prose: str) -> None:
    """The page's "nothing about it happens at import", in a fresh interpreter.

    ``-W error`` turns any warning into a failure, and the child reports whether the version
    check's module was reached at all. Both halves are the page's sentence.
    """
    finished = subprocess.run(
        [
            sys.executable,
            "-W",
            "error",
            "-c",
            "import gebra, sys; print('gebra.extraction.compat' in sys.modules)",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert finished.returncode == 0, finished.stderr
    assert finished.stdout.strip() == "False"
    assert "`import gebra` never warns and never fails on version grounds" in prose


# ── Out of range ──────────────────────────────────────────────────────────────────────────


def test_the_out_of_range_record_on_the_page_is_the_one_the_emitter_builds(
    page_text: str,
) -> None:
    """Code, message and every detail key — re-derived, in the order the page prints them."""
    record = out_of_range_warning(OUT_OF_RANGE_INSTALL)

    assert record.code is ExtractionWarningCode.UNSUPPORTED_CONSTRUCT
    assert record.node is None
    assert record.message in page_text
    for key, value in record.detail.items():
        assert f"  {key:15} {value!r}" in page_text


def test_an_out_of_range_install_warns_nothing_and_marks_every_envelope(prose: str) -> None:
    """The two counts the page calls "the whole design", re-derived from two extractions."""
    _simulate(OUT_OF_RANGE_INSTALL)
    agent = travel_booking.build_travel_booking_agent()

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        first = extract(agent)
        second = extract(agent)

    assert [w for w in caught if issubclass(w.category, GebraVersionWarning)] == []
    assert len(first.warnings) == 1 and len(second.warnings) == 1
    assert first.warnings[0].detail["ir_partial"] is False
    assert first.warnings[0].detail["location"] == {}
    assert "**Both envelopes carry the record**" in prose


# ── V.S.F.E ───────────────────────────────────────────────────────────────────────────────


def test_the_vsfe_transcript_is_the_recorded_evolution(page_text: str) -> None:
    """Every label, every counter and every summary line, against ``EVOLUTION`` itself."""
    [block] = [body for body in _fenced_blocks(page_text, "text") if "no counter" in body]
    rows = [line for line in block.splitlines() if line and not line.startswith("an unedited")]
    rows = [line for line in rows if not line.startswith("and keeps") and "node bodies" not in line]

    assert len(rows) == len(EVOLUTION) - 1
    for line, stage in zip(rows, EVOLUTION[1:], strict=True):
        label, _, remainder = line.partition("  ")
        counters = " ".join(part.value for part in Component if part in stage.expected_bump)
        assert label == stage.expected_version
        assert remainder.strip().startswith(counters)
        assert remainder.strip().endswith(stage.summary)


def test_the_labels_are_what_the_comparator_derives(page_text: str) -> None:
    """Not transcribed from the sequence's record either: re-run through the real engine."""
    label = Version.parse(EVOLUTION[0].expected_version)
    previous = extract(EVOLUTION[0].build()).ir
    derived = []
    for stage in EVOLUTION[1:]:
        working = extract(stage.build()).ir
        moved = changed_components(previous, working)
        label = next_version(label, previous, working)
        derived.append((str(label), frozenset(moved)))
        previous = working

    for (rendered, moved), stage in zip(derived, EVOLUTION[1:], strict=True):
        assert rendered == stage.expected_version
        assert moved == stage.expected_bump
        assert f"{rendered}  " in page_text

    assert changed_components(previous, previous) == frozenset()
    assert str(next_version(label, previous, previous)) == str(label)


def test_the_page_does_not_re_teach_the_counter_table(page_text: str) -> None:
    """DOC-14 owns the field-by-field table; this page links to it rather than forking it."""
    assert "snapshot-diff-and-evolution.md" in page_text
    assert "FIELD_COMPONENTS" not in page_text


def test_the_p12_deferral_the_page_states_is_the_one_every_diff_carries(prose: str) -> None:
    """ "A bump is not a verdict" rests on the marker; the marker is read, not transcribed.

    The slug, the deferred status and the fact that the marker is what a diff carries in the
    classification slot are all the registry's and the diff engine's own, so a property that
    stopped being deferred could not leave this sentence standing.
    """
    marker = EVOLUTION_SAFETY_DEFERRED
    diff = workflow_diff(extract(EVOLUTION[0].build()).ir, extract(EVOLUTION[1].build()).ir)

    assert diff.evolution_safety is marker
    assert not is_implemented(marker.property)
    assert f"is property {marker.property_id} `{marker.property}`, which is outside this" in prose


def test_the_p06_clause_describes_the_edit_and_names_the_trigger_tag(prose: str) -> None:
    """The one property the transcript's own summary names, and the page's gloss of it.

    The summary line comes from the evolution sequence; the page adds that it describes the
    edit rather than a verdict. Both halves are pinned, and the tag it names is checked to be
    a real declared effect on that stage's node rather than a word.
    """
    [stage] = [stage for stage in EVOLUTION if "billable" in stage.summary]
    node = next(node for node in extract(stage.build()).ir.nodes if node.id == "check_booking")
    annotations = node.annotations
    assert annotations is not None

    assert "billable" in (annotations.effect or ())
    assert "trigger set contains" in prose
    assert "That is a statement about the *edit*, not a verdict" in prose
    assert "../validators/p06-effect-safety.md" in prose


# ── The policy, and the boundary ──────────────────────────────────────────────────────────


@pytest.mark.parametrize("sentence", BOUNDARY_SENTENCES)
def test_the_boundary_sentences_are_on_the_page(prose: str, sentence: str) -> None:
    assert sentence in prose


@pytest.mark.parametrize(("claim", "_source"), POLICY_CLAIMS)
def test_the_policy_paragraphs_are_on_the_page(prose: str, claim: str, _source: str) -> None:
    assert claim in prose


def test_the_page_says_where_the_pins_live_and_it_is_where_they_live(
    prose: str, extras: dict[str, list[str]]
) -> None:
    assert "`compat-cell-{1,2,3}` extras of `pyproject.toml`" in prose
    assert {"compat-cell-1", "compat-cell-2", "compat-cell-3"} <= set(extras)


def test_the_phrase_lint_runs_over_this_page() -> None:
    """WA-06 on the page itself, in the same run that checks its facts."""
    report = scan(
        root=REPO_ROOT,
        include=("docs/guides/install-and-compatibility.md",),
        exclude=(),
        phrases=load_phrases(PHRASES),
    )

    assert report.violations == []
    assert report.checked == 1


# ── The living document, where it is checked out beside this repository ───────────────────


@requires_the_living_document
def test_the_declared_ranges_are_the_specifications() -> None:
    """§1's range block, against the page's envelope table."""
    spec = VERSION_COMPAT.read_text(encoding="utf-8")
    page = PAGE.read_text(encoding="utf-8")

    assert "python           >=3.10, tested 3.10–3.13" in spec
    assert "langgraph        >=1.0.0, <2.0.0" in spec
    assert "langchain-core   >=1.0.0, <2.0.0" in spec
    assert "`>=3.10`" in page
    assert page.count("`>=1.0,<2.0`") >= 2


@requires_the_living_document
def test_the_frozen_matrix_is_the_specifications(extras: dict[str, list[str]]) -> None:
    """The F2 freeze banner names the same pins, the same Pythons and the same cell counts."""
    spec = VERSION_COMPAT.read_text(encoding="utf-8")

    for cell in CELLS:
        pinned = _pins(extras[f"compat-cell-{cell}"])
        # The banner spells cell 1 in full and the other two in its own short form.
        spellings = (
            f"{pinned['langgraph']} + langchain-core {pinned['langchain-core']}",
            f"cell {cell} — {pinned['langgraph']} + {pinned['langchain-core']}",
        )
        assert any(spelling in spec for spelling in spellings), f"cell {cell} pins"
    assert f"pydantic {_pins(extras['compat-cell-3'])['pydantic']} transitively" in spec
    assert "Python 3.10 · 3.11 · 3.12 · 3.13" in spec
    assert "12 blocking cells" in spec
    assert "13 cells total" in spec or "one `--pre` early-warning cell" in spec


@requires_the_living_document
@pytest.mark.parametrize(("_claim", "source"), POLICY_CLAIMS)
def test_every_policy_claim_restates_a_section_four_bullet(_claim: str, source: str) -> None:
    """The page's policy paragraphs against the §4 text they restate, phrase by phrase."""
    spec = VERSION_COMPAT.read_text(encoding="utf-8")

    assert source in spec
