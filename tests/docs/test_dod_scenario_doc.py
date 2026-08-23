"""DOD-SCENARIO.md pinned to the harness that claims to implement it (card SD-09).

The page states what the dedicated DoD CI job runs and what artifacts a scenario run
leaves in the store, and prose cannot hold itself to code, so this module does: the
five-defect table is held to the recorded ``DEFECTS`` expectations, the lineage-document
step to the harness's own file name and API, the designated cell and budget to the
workflow's `dod` job, and the page's code fence is parsed — never executed, the
tests/docs rule — so a snippet that stopped being Python fails here.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Final

import pytest

from tests.dod.conftest import LINEAGE_EXPORT_NAME
from tests.dod.test_dod_job import DESIGNATED_CELL
from tests.sample_workflows.travel_booking_defects import DEFECTS

REPO_ROOT: Final = Path(__file__).parent.parent.parent
PAGE_PATH: Final = REPO_ROOT / "docs" / "governance" / "DOD-SCENARIO.md"


@pytest.fixture(scope="module")
def page_text() -> str:
    return PAGE_PATH.read_text(encoding="utf-8")


def test_the_page_is_in_the_library_repo_beside_the_code() -> None:
    assert PAGE_PATH.is_file(), f"{PAGE_PATH} is missing"


def test_the_defect_table_matches_the_recorded_expectations(page_text: str) -> None:
    """Every condition ID and named property in the page is the harness's own — a defect
    construction that moved without the page fails here, and vice versa."""
    for defect in DEFECTS:
        assert f"`{defect.condition}`" in page_text, defect.name
        assert f"`{defect.property}`" in page_text, defect.name
    assert "`fanout: send`" in page_text
    assert "`--gebra-strict=determinism-replay`" in page_text


def test_the_lineage_step_names_the_harness_artifact(page_text: str) -> None:
    """The PD-047 mitigation as documented: same file name, same API, same directory."""
    assert f"`reports/{LINEAGE_EXPORT_NAME}`" in page_text
    assert "dump_lineage" in page_text and "from gebra.lineage import" in page_text
    assert "`.report.json`" in page_text  # the stated non-collision reason


def test_the_job_facts_match_the_workflow(page_text: str) -> None:
    """Cell, budget and invocation as the `dod` job actually declares them."""
    assert DESIGNATED_CELL in page_text
    assert "`timeout-minutes: 5`" in page_text
    assert "pytest tests/dod tests/evolution" in page_text


def test_the_code_fences_parse(page_text: str) -> None:
    """Parsed, never executed — a fence that stopped being Python fails the page."""
    fences = re.findall(r"```python\n(.*?)```", page_text, flags=re.DOTALL)
    assert fences, "the page lost its lineage-export snippet"
    for fence in fences:
        ast.parse(fence)


def test_the_page_keeps_the_honest_boundary(page_text: str) -> None:
    """WA-06 on the page's own copy: witness presence and structural classes, stated."""
    assert "presence" in page_text
    assert "never a statement about whether a run halts" in page_text
    assert "no safe/breaking classification is emitted" in page_text
