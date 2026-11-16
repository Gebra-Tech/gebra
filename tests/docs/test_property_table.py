"""The property table on "What gebra checks" is the registry's own, rendered (card DOC-21).

`tools/property_table.py` renders one row per catalog property from the registry — ID, slug,
claim class, severity, scope, and whether this release checks it — between two markers on
`docs/concepts/what-gebra-checks.md`, and the `docs` CI job runs its `--check`. These tests
are the same check in every cell of the matrix, plus what makes "generated from the registry"
a checked statement rather than an origin story: every committed row is read back against the
registry, a synthetic landing moves exactly its own row with no literal edited anywhere, and
a stale table fails the check. The hand-written "what it decides" table beside it is held to
the same registry by its row set.

The module imports `gebra.verify` and the generator, reads Markdown, and writes only into
`tmp_path`. It builds no workflow, runs no node and opens no connection (WA-07); the one
validator it registers is a throwaway that returns a fixed report.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

import pytest
import yaml

from gebra.verify import (
    MARKER_REASONS,
    PROPERTY_SLUGS,
    PropertySlug,
    deferred_slugs,
    is_implemented,
    not_implemented,
    property_entry,
    registry_counts,
)
from tests._registry import passing_validator, synthetic_catalog_row
from tests.docs.test_property_counts import unkept
from tools import docs_examples, property_table

REPO_ROOT: Final = Path(__file__).resolve().parents[2]
CI: Final = REPO_ROOT / ".github" / "workflows" / "ci.yml"


@pytest.fixture(scope="module")
def page() -> str:
    return property_table.PAGE.read_text(encoding="utf-8")


def _rows(page: str) -> list[list[str]]:
    """The committed table's body rows, cell by cell."""
    lines = page.split("\n")
    start, stop = lines.index(property_table.BEGIN), lines.index(property_table.END)
    assert lines[start + 1 : start + 3] == [property_table.HEADER, property_table.ALIGNMENT]
    return [
        [cell.strip() for cell in line.strip("|").split("|")] for line in lines[start + 3 : stop]
    ]


def _row_for(table: str, property_id: str) -> str:
    [row] = [line for line in table.split("\n") if line.startswith(f"| {property_id} ")]
    return row


# ── The committed table is the registry's ────────────────────────────────────────────────


def test_the_committed_table_is_what_the_registry_renders(page: str) -> None:
    """Box 2, as the `docs` job's `--check` asks it, in every matrix cell."""
    assert property_table.splice(page, property_table.render_table()) == page


def test_every_row_reads_back_as_its_registry_entry(page: str) -> None:
    """One row per catalog property, in catalog order, each cell the registry's own value."""
    rows = _rows(page)

    assert len(rows) == registry_counts().total
    for slug, cells in zip(PROPERTY_SLUGS, rows, strict=True):
        entry = property_entry(slug)
        identifier, shown_slug, claim, severity, scope, status = cells
        assert identifier == entry.property_id or identifier.startswith(f"[{entry.property_id}](")
        assert shown_slug == f"`{slug}`"
        assert claim == ", ".join(value.upper() for value in entry.claim_classes)
        assert severity == ", ".join(value.upper() for value in entry.severities)
        assert scope == f"`{entry.scope}`"
        if is_implemented(slug):
            assert status == property_table.CHECKED
        else:
            assert status == f"not checked — {MARKER_REASONS[not_implemented(slug).status]}"


def test_the_checked_rows_are_exactly_the_registered_validators(page: str) -> None:
    """The column a reader acts on, read against dispatch rather than against the scope."""
    checked = {cells[1].strip("`") for cells in _rows(page) if cells[5] == property_table.CHECKED}
    assert checked == {slug for slug in PROPERTY_SLUGS if is_implemented(slug)}
    assert len(checked) == registry_counts().registered


def test_a_checked_row_links_the_page_its_property_has(page: str) -> None:
    """Every link resolves, and every property with a page under `docs/validators/` is linked."""
    for slug, cells in zip(PROPERTY_SLUGS, _rows(page), strict=True):
        target = property_table.validator_page(property_entry(slug))
        if target.is_file():
            assert cells[0] == f"[{property_entry(slug).property_id}](../validators/{target.name})"
        else:
            assert "](" not in cells[0], cells[0]


def test_the_table_states_no_count_of_its_own(page: str) -> None:
    """The table states each property's standing row by row, and never sums them."""
    table = page[page.index(property_table.BEGIN) : page.index(property_table.END)]
    assert unkept(" ".join(table.split())) == []


# ── The table follows the registry ───────────────────────────────────────────────────────


def _a_deferred_one_snapshot_row() -> PropertySlug:
    """A row the synthetic landing can move: deferred, and registrable through `Validator`.

    Chosen when the test runs, never named here, so a real landing moves no literal in this
    module either; once no such row is left, the tests that need one skip and say why.
    """
    rows = [slug for slug in deferred_slugs() if property_entry(slug).arity == "one-snapshot"]
    if not rows:
        pytest.skip("no deferred one-snapshot row is left for a synthetic landing to move")
    return rows[-1]


def test_a_landing_moves_its_own_row_and_nothing_else() -> None:
    """The mutation test: a synthetic `catalog` row with a validator, and the table follows.

    A deferred row moves to `catalog` and registers a throwaway validator for the block; the
    rendered table changes in that row alone — scope and status — with no literal edited.
    On exit the registry is back, and so is the table.
    """
    slug = _a_deferred_one_snapshot_row()
    property_id = property_entry(slug).property_id
    before = property_table.render_table()
    with synthetic_catalog_row(slug, passing_validator(slug)):
        during = property_table.render_table()
    assert property_table.render_table() == before

    changed = [
        (old, new)
        for old, new in zip(before.split("\n"), during.split("\n"), strict=True)
        if old != new
    ]
    assert changed == [(_row_for(before, property_id), _row_for(during, property_id))]
    assert "`catalog` | checked |" in _row_for(during, property_id)
    assert "`deferred-to-phase-1` | not checked —" in _row_for(before, property_id)


def test_a_shipped_row_with_no_validator_says_so_in_its_markers_words() -> None:
    """The build-order absence reads as its marker reads, never as *checked*."""
    slug = _a_deferred_one_snapshot_row()
    with synthetic_catalog_row(slug):
        row = _row_for(property_table.render_table(), property_entry(slug).property_id)
    assert row.endswith(f"| not checked — {MARKER_REASONS['not-yet-implemented']} |")


# ── The hand-written table beside it is held to the same registry ────────────────────────

#: The header of the concept page's hand-written "what it decides" table.
DECIDES_HEADER: Final = "| Property | What it decides | Claim class | Severity |"


def _decides_section(page: str) -> str:
    start = page.index("## What each checked property decides")
    return page[start : page.index("\n## ", start + 1)]


def test_the_what_it_decides_table_lists_exactly_the_checked_properties(page: str) -> None:
    """ "For each property this release checks" is held to the validators this build registers.

    The table beside the generated one is written by hand, because what a property decides is
    prose from its catalog section; so its row set is what this test holds instead. A landing
    that registers a validator fails here until the page gains the row — the landing
    checklist's docs item, made mechanical — and the classes and severities each row names are
    the registry's own, in its order.
    """
    lines = _decides_section(page).split("\n")
    start = lines.index(DECIDES_HEADER)
    body = [line for line in lines[start + 2 :] if line.startswith("|")]
    rows = [[cell.strip() for cell in line.strip("|").split("|")] for line in body]
    registered = [slug for slug in PROPERTY_SLUGS if is_implemented(slug)]

    assert [row[0] for row in rows] == [
        f"{property_entry(slug).property_id} `{slug}`" for slug in registered
    ]
    for slug, row in zip(registered, rows, strict=True):
        entry = property_entry(slug)
        assert re.findall(r"DEFENSIBLE-A|DEFENSIBLE|HEURISTIC", row[2]) == [
            c.upper() for c in entry.claim_classes
        ], row[0]
        assert re.findall(r"FATAL|ERROR|WARNING", row[3]) == [
            s.upper() for s in entry.severities
        ], row[0]


def test_the_what_it_decides_section_links_each_checked_propertys_page(page: str) -> None:
    """The sentence after the table links every registered property's page, and only those."""
    section = _decides_section(page)
    linked = set(re.findall(r"\]\(\.\./validators/([a-z0-9-]+\.md)\)", section))
    registered = {
        property_table.validator_page(property_entry(slug)).name
        for slug in PROPERTY_SLUGS
        if is_implemented(slug)
    }
    assert linked == registered


def test_a_row_is_linked_only_when_its_page_exists(tmp_path: Path) -> None:
    """Rendered against a tree with no validator pages, no row links anywhere."""
    table = property_table.render_table(root=tmp_path)
    assert "](" not in table


# ── The command line and the markers ─────────────────────────────────────────────────────


def test_check_passes_on_the_committed_page(capsys: pytest.CaptureFixture[str]) -> None:
    assert property_table.main(["--check"]) == 0
    assert "is current" in capsys.readouterr().out


def test_check_fails_on_a_stale_table_and_write_repairs_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, page: str
) -> None:
    """A doctored row is reported stale; `--write` puts the registry's row back."""
    copy = tmp_path / "what-gebra-checks.md"
    stale = page.replace("| `phase-0-wedge` | checked |", "| `phase-0-wedge` | maybe |", 1)
    assert stale != page
    copy.write_text(stale, encoding="utf-8")
    monkeypatch.setattr(property_table, "PAGE", copy)
    monkeypatch.setattr(property_table, "REPO_ROOT", tmp_path)

    assert property_table.main(["--check"]) == 1
    assert property_table.main(["--write"]) == 0
    assert copy.read_text(encoding="utf-8") == page
    assert property_table.main(["--check"]) == 0


@pytest.mark.parametrize(
    "broken",
    [
        "no markers at all\n",
        f"{property_table.BEGIN}\n{property_table.BEGIN}\n{property_table.END}\n",
        f"{property_table.END}\n{property_table.BEGIN}\n",
        f"text {property_table.BEGIN}\n{property_table.END}\n",
    ],
    ids=["missing", "doubled", "reversed", "not-on-its-own-line"],
)
def test_a_page_without_one_well_formed_marker_pair_is_refused(broken: str) -> None:
    with pytest.raises(property_table.PropertyTableError):
        property_table.splice(broken, property_table.render_table())


def test_the_markers_are_not_in_the_examples_harness_namespace(page: str) -> None:
    """`gebra:` directives the harness does not know are errors; these markers are not one."""
    for marker in (property_table.BEGIN, property_table.END):
        assert docs_examples.directive_pattern("gebra").match(marker) is None
    docs_examples.parse_markdown(page, path="docs/concepts/what-gebra-checks.md")


def test_the_docs_ci_job_runs_the_check() -> None:
    """Box 2's CI half: the `docs` job runs `--check` before it builds the site."""
    steps = yaml.safe_load(CI.read_text(encoding="utf-8"))["jobs"]["docs"]["steps"]
    commands = [step.get("run", "") for step in steps]
    check = commands.index("python tools/property_table.py --check")
    assert check < commands.index("mkdocs build --strict")
