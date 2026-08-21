"""Golden CLI output — CLI-04's second acceptance box, byte for byte.

One passing and one failing corpus fixture, verified through the whole entry point on all
three §4.1 surfaces, each compared to a committed golden with ``tool.version`` normalized
and nothing else (CLI-SPEC §7). What makes the bytes reproducible is stated rather than
hoped: the subject is a relative path in a per-session directory (so ``subject.source`` is
the bare name), the report itself is byte-reproducible for a fixed IR (REPORT-FORMAT-SPEC
§1.4 rule 5), and the conftest strips the terminal variables so the human surface renders
plain at 80 columns on every runner.

The goldens double as the §5.2 stream-discipline record: stdout is captured alone, and a
clean run's stderr is asserted empty beside it, so a diagnostic leaking onto the artifact
stream fails these tests rather than only the unit ones.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.cli.conftest import RunCli
from tests.cli.goldens import compare_golden

CASES = [
    ("pass.ir.yaml", 0, "pass"),
    ("fail.ir.yaml", 1, "fail"),
]

SURFACES = [("human", "txt"), ("json", "json"), ("sarif", "sarif.json")]


@pytest.mark.parametrize(("document", "expected_exit", "name"), CASES)
@pytest.mark.parametrize(("report_format", "suffix"), SURFACES)
def test_the_output_matches_its_golden(
    run_cli: RunCli,
    in_documents_dir: Path,
    document: str,
    expected_exit: int,
    name: str,
    report_format: str,
    suffix: str,
) -> None:
    result = run_cli("verify", document, "--format", report_format)
    assert result.exit_code == expected_exit
    assert result.stderr == ""
    compare_golden(f"{name}.{suffix}", result.stdout)


def test_the_no_flag_default_is_the_human_surface(run_cli: RunCli, in_documents_dir: Path) -> None:
    """§4.1/OI-6: the no-flag default is human, and ``--format human`` says the same."""
    bare = run_cli("verify", "pass.ir.yaml")
    explicit = run_cli("verify", "pass.ir.yaml", "--format", "human")
    assert bare.stdout == explicit.stdout
    compare_golden("pass.txt", bare.stdout)


def test_styled_and_plain_carry_the_same_facts(run_cli: RunCli, in_documents_dir: Path) -> None:
    """§5.1: degradation changes styling only — strip the escapes and it is the golden."""
    import re

    styled = run_cli("verify", "fail.ir.yaml", "--color")
    stripped = re.sub("\x1b\\[[0-9;]*m", "", styled.stdout)
    compare_golden("fail.txt", stripped)
