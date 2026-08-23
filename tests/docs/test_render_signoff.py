"""RENDER-SIGNOFF.md pinned to the record it claims to be (card CLI-07).

The sign-off's weight is its evidence pointers, and prose cannot hold itself to a file
tree: every repository path the note cites must exist, the two-way reference with the
validator-API freeze record must stay intact (that record defers the sign-off here by
naming CLI-07; this note must keep saying which record deferred it), and the scoping
sentences that keep the claim honest — witness-presence wording, the not-a-pass marker
rule, the external-viewer disclaimer — must stay on the page.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

import pytest

REPO_ROOT: Final = Path(__file__).parent.parent.parent
PAGE_PATH: Final = REPO_ROOT / "docs" / "governance" / "RENDER-SIGNOFF.md"
FREEZE_PATH: Final = REPO_ROOT / "docs" / "governance" / "VALIDATOR-API-FREEZE.md"


@pytest.fixture(scope="module")
def page_text() -> str:
    return PAGE_PATH.read_text(encoding="utf-8")


def test_the_record_exists_where_the_freeze_note_points(page_text: str) -> None:
    assert PAGE_PATH.is_file()
    assert "RECORDED" in page_text
    assert "CLI-07" in page_text


def test_every_cited_repository_path_exists(page_text: str) -> None:
    """A pointer to a moved or deleted suite would hollow the sign-off silently."""
    cited = {
        match.group(1)
        for match in re.finditer(r"`((?:tests|src|docs|tools)/[A-Za-z0-9_./-]+)`", page_text)
    }
    assert cited, "the note cites no repository paths at all"
    for path in sorted(cited):
        assert (REPO_ROOT / path).exists(), f"the sign-off cites {path}, which does not exist"


def test_the_two_way_reference_with_the_freeze_record_is_intact(page_text: str) -> None:
    """VALIDATOR-API-FREEZE §3 defers the sign-off to CLI-07; this note names that record."""
    assert "VALIDATOR-API-FREEZE.md" in page_text
    freeze_text = FREEZE_PATH.read_text(encoding="utf-8")
    assert "CLI-07" in freeze_text, "the freeze record no longer names the deferring card"
    assert "Every witness/failure variant renders cleanly" in freeze_text
    assert "Every witness/failure variant renders cleanly" in page_text


def test_the_scoping_sentences_stay_on_the_page(page_text: str) -> None:
    """The sentences that keep 'cleanly' a rendering claim, present verbatim in spirit."""
    assert "witness-presence wording" in page_text
    assert "never shown as a pass" in page_text
    assert "makes no verification claim" in page_text
    assert "licensed subset" in page_text  # the external-viewer disclaimer's ground
