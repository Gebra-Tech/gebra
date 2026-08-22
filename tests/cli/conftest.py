"""Shared plumbing for the CLI suite (card CLI-04).

Every test drives the CLI through :func:`gebra.cli.main` — the same function the ``gebra``
console script and ``python -m gebra.cli`` name — with the streams captured by pytest, so
the assertions are about the process surface (stdout artifact, stderr diagnostics, exit
code) rather than about internals. The environment fixture below removes the terminal
variables `rich` honours, so the human surface renders identically on every runner: plain,
80 columns, no escapes.

Subjects come from the vendored corpus: the two IR documents are the ``mixed/10`` all-pass
fixture and the ``mixed/01`` two-finding failure, written out with ``write_ir`` into a per-
session directory the tests ``chdir`` into — which keeps ``subject.source`` a bare relative
filename, and with it every golden byte-stable.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pytest

from gebra.cli import main
from gebra.ir import WorkflowIR, write_ir
from gebra.testing import load_fixture

FIXTURES = Path(__file__).parent.parent / "fixtures" / "properties"

#: The all-pass corpus subject (gate ``pass``, exit 0).
PASSING_FIXTURE = FIXTURES / "mixed" / "10-all-properties-pass-healthy-research-pipeline.yaml"

#: The failing corpus subject (one FATAL + one ERROR finding, gate ``fail``, exit 1).
FAILING_FIXTURE = FIXTURES / "mixed" / "01-witnessed-cycle-with-unkeyed-billable-node.yaml"

#: A pass-with-notes subject (two WARNING-grade records) — what ``--strict`` promotes.
NOTED_FIXTURE = FIXTURES / "mixed" / "03-parallel-reducerless-key-with-unpinned-llm-writers.yaml"


def fixture_ir(path: Path) -> WorkflowIR:
    """The fixture's IR block, asserted present — every fixture this suite names has one."""
    ir = load_fixture(path).ir
    assert ir is not None, f"{path} carries no ir block"
    return ir


@dataclass(frozen=True)
class CliResult:
    """One in-process CLI run: the §3 exit code and the two §5.2 streams."""

    exit_code: int
    stdout: str
    stderr: str


RunCli = Callable[..., CliResult]


@pytest.fixture(autouse=True)
def _stable_terminal(monkeypatch: pytest.MonkeyPatch) -> None:
    """Strip the terminal conventions `rich` honours, so renderings are runner-independent."""
    for name in ("NO_COLOR", "FORCE_COLOR", "TERM", "COLORTERM", "COLUMNS", "LINES"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def run_cli(capsys: pytest.CaptureFixture[str]) -> RunCli:
    """Run ``gebra.cli.main`` with captured streams and hand back all three surfaces."""

    def _run(*argv: str) -> CliResult:
        capsys.readouterr()  # drop anything a previous run in the same test left behind
        exit_code = main(list(argv))
        captured = capsys.readouterr()
        return CliResult(exit_code=exit_code, stdout=captured.out, stderr=captured.err)

    return _run


@pytest.fixture(scope="session")
def documents_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A directory holding the corpus-derived IR documents the suite verifies."""
    directory = tmp_path_factory.mktemp("cli-subjects")
    write_ir(fixture_ir(PASSING_FIXTURE), directory / "pass.ir.yaml")
    write_ir(fixture_ir(FAILING_FIXTURE), directory / "fail.ir.yaml")
    write_ir(fixture_ir(NOTED_FIXTURE), directory / "noted.ir.yaml")
    write_ir(fixture_ir(PASSING_FIXTURE), directory / "pass.ir.json")
    return directory


@pytest.fixture
def in_documents_dir(documents_dir: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Run the test from the documents directory, so targets are bare relative names."""
    monkeypatch.chdir(documents_dir)
    return documents_dir


@pytest.fixture
def project_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A fresh project directory to run from — corpus documents beside an unborn store.

    The store-facing verbs (CLI-05) write here, so unlike :func:`documents_dir` this one is
    per-test: no store state leaks between tests, and every path in an invocation — the
    documents, ``--store .gebra`` — stays a bare relative name, which is what keeps the
    goldens byte-stable.
    """
    monkeypatch.chdir(tmp_path)
    write_ir(fixture_ir(PASSING_FIXTURE), tmp_path / "pass.ir.yaml")
    write_ir(fixture_ir(FAILING_FIXTURE), tmp_path / "fail.ir.yaml")
    write_ir(fixture_ir(NOTED_FIXTURE), tmp_path / "noted.ir.yaml")
    return tmp_path


@pytest.fixture
def evolved_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A project holding the five-version lineage store, plus two working documents.

    The store is ``tests/lineage/stores.py``'s :func:`~tests.lineage.stores.evolved_store`
    — five versions (``1.0.0.0`` … ``1.2.2.1``), every label derived by the diff engine and
    every timestamp fixed — so listings and stored-pair diffs are functions of the fixture
    alone. ``final.ir.yaml`` holds the newest stage's content and ``base.ir.yaml`` the
    oldest's, for the mixed stored-versus-document cases.
    """
    from tests.lineage.stores import STAGES, evolved_store

    monkeypatch.chdir(tmp_path)
    evolved_store(tmp_path)
    write_ir(STAGES[0].build(), tmp_path / "base.ir.yaml")
    write_ir(STAGES[-1].build(), tmp_path / "final.ir.yaml")
    return tmp_path
