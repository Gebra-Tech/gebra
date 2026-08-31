"""The IR concept page, held to the two sources it transcribes (card DOC-03).

`docs/concepts/ir-and-graph-version.md` explains the IR, node identity and `graph_version`
to users and contributors. Two of its claims are not the harness's to check — the harness
proves that the page's examples ran and printed what the page shows, but not that the
document they run on is the one the specification pinned, nor that the hash-scope table says
what the ruling says. Those are this module's:

- the worked example **is** golden vector 001 — the same authored document, the same
  canonical bytes, the same digest, reconciled against `tests/ir/golden/vector-001.*`, so a
  golden-file event that skipped the page fails the build rather than leaving a stale
  transcript in the documentation;
- the hash-scope table matches **DEC-10** field for field, in both directions, so a field
  that was dropped, added, or moved across the include/exclude line is caught rather than
  read past.

The module parses Markdown and one Python literal with :mod:`ast`. It imports no workflow,
runs no node, opens no connection (WA-07); the page's examples are executed by the DOC-01
harness, in its guarded child, not here.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from tools.docs_examples import DocExample, discover

REPO_ROOT = Path(__file__).resolve().parents[2]
PAGE_PATH = "docs/concepts/ir-and-graph-version.md"
PAGE = REPO_ROOT / PAGE_PATH
GOLDEN = REPO_ROOT / "tests" / "ir" / "golden"

#: The example that carries the pinned vector, and the two literals it is checked through.
WORKED_EXAMPLE = f"{PAGE_PATH}::golden-vector-001"
DOCUMENT_LITERAL = "AUTHORED"
DIGEST_LITERAL = "PINNED"

#: The page's hash-scope table and the ruling's, keyed by their header lines. The rows are
#: matched by their first cell, which is the same word on both sides.
PAGE_TABLE = "| In the digest? | What it covers |"
SPEC_TABLE = "| In digest? | Fields |"
SCOPE_ROWS = ("**INCLUDE**", "**EXCLUDE**")

# The development-process repository: present in a working checkout, absent in the library
# repository's own CI. Cross-repository assertions are skipped there rather than faked —
# the pattern tests/test_provenance_guard.py established and tests/docs/test_docs_site.py
# follows.
COMPANION = REPO_ROOT.parent / "gebra-dev-doc"
RULING = COMPANION / "docs" / "decisions" / "DEC-10-hash-scope-canonical-serialization.md"
IR_SPEC = COMPANION / "docs" / "specs" / "IR-SPEC.md"

requires_the_ruling = pytest.mark.skipif(
    not RULING.is_file(),
    reason="the vendored hash-scope ruling is not checked out beside this repository",
)

#: The one check below that reads the specification as well as the ruling. Gated on both,
#: because a checkout holding one and not the other should skip rather than raise.
requires_both_sources = pytest.mark.skipif(
    not (RULING.is_file() and IR_SPEC.is_file()),
    reason="the vendored ruling and its normative home are not both checked out",
)


def _example(name: str) -> DocExample:
    """The discovered example called `name` — discovery is text-only and runs nothing."""
    found = [item for item in discover(REPO_ROOT) if item.name == name]
    assert found, f"{name} is no longer a marked example on this page"
    return found[0]


def _literal(code: str, target: str) -> str:
    """The value of a module-level `target = "…"` assignment in `code`."""
    for node in ast.parse(code).body:
        if isinstance(node, ast.Assign) and any(
            isinstance(bound, ast.Name) and bound.id == target for bound in node.targets
        ):
            value = ast.literal_eval(node.value)
            assert isinstance(value, str), f"{target} is not a string literal"
            return value
    raise AssertionError(f"the example declares no {target}")


def _golden_document() -> str:
    """`vector-001.authored.yaml` without the header comment that explains what it is."""
    lines = (GOLDEN / "vector-001.authored.yaml").read_text(encoding="utf-8").splitlines(True)
    start = next(
        index for index, line in enumerate(lines) if line.strip() and not line.startswith("#")
    )
    return "".join(lines[start:])


def _table_row(text: str, header: str, first_cell: str) -> list[str]:
    """The cells of the row whose first cell is `first_cell`, in the table headed `header`."""
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if line.strip() != header:
            continue
        for candidate in lines[index + 2 :]:  # +2 skips the alignment row
            if not candidate.startswith("|"):
                break
            cells = [cell.strip() for cell in candidate.strip("|").split("|")]
            if cells[0] == first_cell:
                return cells
        raise AssertionError(f"no row {first_cell!r} under {header!r}")
    raise AssertionError(f"no table with header {header!r}")


def _fields(cell: str) -> list[str]:
    """Every code span in a table cell — the field names the row claims, sorted."""
    return sorted(re.findall(r"`([^`]+)`", cell))


# ── The worked example is the pinned vector ──────────────────────────────────────────────


def test_the_worked_example_runs_the_golden_vector_document() -> None:
    """Byte equality, not a resemblance: the page shows the vector, not a document like it."""
    assert _literal(_example(WORKED_EXAMPLE).code, DOCUMENT_LITERAL) == _golden_document()


def test_the_digest_the_example_checks_against_is_the_pinned_one() -> None:
    """The example asserts its own result, so the value it asserts against must be the golden.

    Without this the example would be free to check itself against whatever it computed.
    """
    pinned = (GOLDEN / "vector-001.digest").read_text(encoding="ascii").strip()

    assert _literal(_example(WORKED_EXAMPLE).code, DIGEST_LITERAL) == pinned


def test_the_transcript_shows_the_golden_canonical_form_and_digest() -> None:
    """What the page displays as the canonical form is the committed canonical form.

    The harness holds this transcript to what the example printed; this holds the transcript
    to the golden files. The two together are what make the page's numbers checkable rather
    than merely self-consistent.
    """
    canonical = (GOLDEN / "vector-001.canonical.json").read_bytes()
    digest = (GOLDEN / "vector-001.digest").read_text(encoding="ascii").strip()
    printed = _example(WORKED_EXAMPLE).expected_output.splitlines()

    assert canonical.decode("utf-8") in printed
    assert f"canonical bytes: {len(canonical)}" in printed
    assert f"graph_version: {digest}" in printed


def test_the_page_states_the_canonical_byte_count_the_vector_has() -> None:
    """The one number the prose repeats out of the transcript, derived rather than trusted."""
    byte_count = len((GOLDEN / "vector-001.canonical.json").read_bytes())

    assert f"{byte_count} bytes" in PAGE.read_text(encoding="utf-8")


# ── The hash scope is the ruling's ───────────────────────────────────────────────────────


@requires_the_ruling
def test_the_hash_scope_table_matches_the_ruling_field_for_field() -> None:
    """DOC-03's acceptance: the scope statement is DEC-10's, not a reading of it.

    Field names rather than whole cells, because the ruling's cells carry vault section
    numbers no reader of this site can follow. What must not drift is which fields the
    digest covers and which it does not, and that is exactly what this compares — in both
    directions, so a field dropped from the page and a field the page invented both fail.
    """
    ruling = RULING.read_text(encoding="utf-8")
    page = PAGE.read_text(encoding="utf-8")

    for row in SCOPE_ROWS:
        assert _fields(_table_row(page, PAGE_TABLE, row)[1]) == _fields(
            _table_row(ruling, SPEC_TABLE, row)[1]
        ), f"the page's {row} row no longer lists the fields DEC-10 rules"


@requires_the_ruling
def test_no_field_is_on_both_sides_of_the_line() -> None:
    """A field both included and excluded would make the table unreadable either way."""
    page = PAGE.read_text(encoding="utf-8")
    included, excluded = (set(_fields(_table_row(page, PAGE_TABLE, row)[1])) for row in SCOPE_ROWS)

    assert included & excluded == set()


@requires_both_sources
def test_the_ruling_and_its_normative_home_still_agree() -> None:
    """The page cites both; if the two vendored copies diverged, it could not cite both.

    IR-SPEC §6.4 is the normative home of the scope table and DEC-10 is the ruling that
    fixed it. The spec's exclude row names two further things in code spans — the model's
    `extra="forbid"` behaviour and the fixture schema — so the check is equality on the
    include row and containment on the exclude row.
    """
    ruling = RULING.read_text(encoding="utf-8")
    spec = IR_SPEC.read_text(encoding="utf-8")

    assert _fields(_table_row(spec, SPEC_TABLE, "**INCLUDE**")[1]) == _fields(
        _table_row(ruling, SPEC_TABLE, "**INCLUDE**")[1]
    )
    assert set(_fields(_table_row(ruling, SPEC_TABLE, "**EXCLUDE**")[1])) <= set(
        _fields(_table_row(spec, SPEC_TABLE, "**EXCLUDE**")[1])
    )
