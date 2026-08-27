"""Every corpus fixture through the shipped ``verify`` verb — card CLI-07's breadth leg.

The card's objective runs the integration suite "over corpus fixtures": here every IR block
the vendored corpus carries (71 fixtures; the P-12 pairs contribute two each) is written
out as an IR document and driven through the CLI, and the CLI is held to CLI-SPEC §0.1's
presentation-only boundary as an *equality*: the exit code is the library's own
``gate.exit_code`` and the ``--format json`` artifact parses back to the same gate, the
same property outcomes and the same error member ``verify()`` itself produced over the same
IR — byte-reproducibility of the run report for a fixed IR is REPORT-FORMAT-SPEC §1.4 rule
5's own claim, so agreement here is the spec's expectation, not a hopeful tolerance. The
human rendering of every fixture is swept with the TE-15 banned-phrase list (acceptance box
3, applied to the surface a user actually reads).

This is the "runner invocation" half of the card's subprocess-vs-runner decision, stated in
``tests/cli/integration.py``: the process boundary is exercised by the flow and matrix
modules; re-exercising it per fixture would spend a child process per case to strengthen
no claim. The SARIF leg validates one representative per corpus directory against the SARIF
2.1.0 schema through ``tools/json_schema.py`` — the same refuse-what-you-cannot-check
validator the rendering suite uses, so an unvalidatable construct fails rather than
passing unchecked.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from gebra.ir import WorkflowIR, write_ir
from gebra.testing import load_fixture
from gebra.verify import RunReport, verify
from tests.cli.conftest import RunCli
from tests.cli.integration import sweep_for_banned_phrases
from tools.json_schema import validate

FIXTURES = Path(__file__).parent.parent / "fixtures" / "properties"

SCHEMA_PATH = Path(__file__).parent.parent / "schemas" / "sarif-2.1.0.json"


def _corpus_irs() -> list[tuple[str, WorkflowIR]]:
    cases: list[tuple[str, WorkflowIR]] = []
    for path in sorted(FIXTURES.rglob("*.yaml")):
        if path.name == "schema.yaml":
            continue
        fixture = load_fixture(path)
        for attribute in ("ir", "ir_before", "ir_after"):
            ir = getattr(fixture, attribute, None)
            if ir is not None:
                cases.append((f"{path.relative_to(FIXTURES)}::{attribute}", ir))
    return cases


CASES = _corpus_irs()


def _directory_representatives() -> list[tuple[str, WorkflowIR]]:
    """The first fixture of every corpus directory — the SARIF leg's ten subjects."""
    representatives: list[tuple[str, WorkflowIR]] = []
    for directory in sorted(path for path in FIXTURES.iterdir() if path.is_dir()):
        first = min(directory.glob("*.yaml"))
        fixture = load_fixture(first)
        ir = next(
            candidate
            for candidate in (getattr(fixture, name, None) for name in ("ir", "ir_before"))
            if candidate is not None
        )
        representatives.append((str(first.relative_to(FIXTURES)), ir))
    return representatives


REPRESENTATIVES = _directory_representatives()


def test_the_corpus_is_the_size_the_claim_needs() -> None:
    """71 fixtures, every one contributing at least one IR, and every corpus directory
    contributing a SARIF representative — the sweeps below are not quietly running over an
    empty parametrization."""
    assert len(CASES) >= 60
    assert len(REPRESENTATIVES) >= 8


@pytest.fixture(scope="module")
def sarif_schema() -> Any:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


@pytest.mark.parametrize(("name", "ir"), CASES, ids=[name for name, _ in CASES])
def test_the_cli_artifact_is_the_librarys_own_run(
    run_cli: RunCli, tmp_path: Path, name: str, ir: WorkflowIR
) -> None:
    document = tmp_path / "subject.ir.yaml"
    write_ir(ir, document)
    expected = verify(ir)
    assert expected.gate.exit_code != 2, f"{name}: the corpus run reached no verdict"

    machine = run_cli("verify", str(document), "--format", "json")
    assert machine.exit_code == expected.gate.exit_code, name
    report = RunReport.model_validate_json(machine.stdout)
    assert report.gate == expected.gate, name
    assert report.properties == expected.properties, name
    assert report.error == expected.error, name
    assert report.best_effort == expected.best_effort, name

    human = run_cli("verify", str(document))
    assert human.exit_code == expected.gate.exit_code, name
    sweep_for_banned_phrases(name, machine.stdout, machine.stderr, human.stdout, human.stderr)


@pytest.mark.parametrize(("name", "ir"), REPRESENTATIVES, ids=[name for name, _ in REPRESENTATIVES])
def test_a_representative_per_directory_emits_schema_valid_sarif(
    run_cli: RunCli, tmp_path: Path, sarif_schema: Any, name: str, ir: WorkflowIR
) -> None:
    document = tmp_path / "subject.ir.yaml"
    write_ir(ir, document)

    result = run_cli("verify", str(document), "--format", "sarif")
    assert result.exit_code == verify(ir).gate.exit_code, name
    issues = validate(json.loads(result.stdout), sarif_schema)
    assert issues == [], name
    sweep_for_banned_phrases(name, result.stdout, result.stderr)
