"""The documentation site's skeleton — the pages, the navigation, and what stays out of it.

Card DOC-01 lands a site with a page reserved for everything the documentation track plans
to write, so that "examples executed verbatim" and "no page describes unbuilt behaviour" are
enforceable for the whole track from the first page onward. These tests hold that skeleton to
three things. Every page in the navigation exists and every published page is in the
navigation, so a page cannot be added and left unreachable or removed and left dangling.
Every page that is still a placeholder says so in a machine-readable way and describes no
behaviour. And the repository-internal contract documents that share the `docs/` tree — the
CLI and report-format specifications, the governance records, the CI notes — are excluded
from the site by name, so the published documentation and the build's own contract documents
never mix.

The module parses YAML and reads Markdown. It imports no workflow, runs no node, opens no
connection (WA-07).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - exercised on the 3.10 matrix cells
    import tomli as tomllib

REPO_ROOT = Path(__file__).resolve().parents[2]
MKDOCS = REPO_ROOT / "mkdocs.yml"
DOCS = REPO_ROOT / "docs"
GITIGNORE = REPO_ROOT / ".gitignore"
DOCS_REQUIREMENTS = DOCS / "requirements.txt"

#: The marker a page carries while it is still only a reservation. A page that has been
#: written drops it; a page that has not must have it, so "is this documentation or a
#: promise?" is answerable by machine rather than by reading.
PLACEHOLDER_MARKER = "<!-- docs:placeholder -->"

#: Repository-internal trees that live under `docs/` and are not user documentation. They are
#: named here and in `mkdocs.yml`'s `exclude_docs`, and the two are held equal below.
INTERNAL_TREES = ("ci", "governance", "specs")

#: The site page(s) each documentation card is responsible for. This is the skeleton's
#: manifest: it is reconciled against the card board itself where the board is checked out,
#: so a card added to the track without a page reserved for it fails here.
PAGES_BY_CARD: dict[str, tuple[str, ...]] = {
    "DOC-02": ("concepts/what-gebra-checks.md",),
    "DOC-03": ("concepts/ir-and-graph-version.md",),
    "DOC-05": ("tutorials/extract-your-first-ir.md",),
    "DOC-06": ("tutorials/contracts-and-annotations.md",),
    "DOC-07": ("tutorials/verify-and-interpret.md",),
    "DOC-08": ("validators/p01-graph-well-formed.md",),
    "DOC-09": ("validators/p02-termination-witness.md",),
    "DOC-10": ("validators/p04-dataflow-completeness.md",),
    "DOC-11": ("validators/p06-effect-safety.md",),
    "DOC-12": ("validators/p08-determinism-replay.md",),
    "DOC-13": ("guides/pytest-plugin-and-ci-gating.md",),
    "DOC-14": ("guides/snapshot-diff-and-evolution.md",),
    "DOC-15": ("reference/cli.md",),
    "DOC-16": ("tutorials/travel-booking-end-to-end.md",),
    "DOC-17": ("reference/api.md", "reference/architecture.md"),
    "DOC-18": ("guides/install-and-compatibility.md",),
    "DOC-19": ("contributing/index.md",),
}

#: The two pages DOC-01 writes rather than reserves.
WRITTEN_PAGES = ("index.md", "contributing/executable-examples.md")

#: Reserved pages whose card has since written them. A page moves into this set in the same
#: change that drops its placeholder marker, and the two directions below hold it there: a
#: page in this set that still carries the marker fails, and a page outside it that has
#: dropped one fails. Landing a page is therefore an explicit edit here, never a silent one.
LANDED_PAGES = frozenset(
    {
        "concepts/what-gebra-checks.md",
        "concepts/ir-and-graph-version.md",
        "tutorials/extract-your-first-ir.md",
        "tutorials/contracts-and-annotations.md",
        "tutorials/verify-and-interpret.md",
        "validators/p01-graph-well-formed.md",
        "validators/p02-termination-witness.md",
    }
)

#: Cards whose output is not a page on this site: DOC-01 is the toolchain and the harness,
#: and DOC-04 is the repository README.
CARDS_WITHOUT_A_SITE_PAGE = frozenset({"DOC-01", "DOC-04"})

#: The tables `concepts/what-gebra-checks.md` transcribes from the property catalog rather
#: than paraphrases, keyed by their header line. Card DOC-02's acceptance is that they match
#: the specification exactly; the reconciliation below is that requirement made mechanical.
TRANSCRIBED_TABLES = (
    "| Claim class | Serialized value | Meaning |",
    "| Severity | Serialized value | Design-time meaning | Gate effect |",
    "| Exit code | Condition |",
)

#: The one cell the page deliberately does not carry verbatim, and why. The catalog's exit-`1`
#: row ends in a pointer to a vault note that is published nowhere a reader of this site can
#: follow, so the page keeps the rule and drops the pointer — the rule itself is already on the
#: page, in the severity table's FATAL row. Keyed by (table header, first cell, column index);
#: the value is the text the page omits from the end of the spec's cell. Nothing else may
#: differ, and a second entry here is a decision someone has to make on purpose.
DECLARED_OMISSIONS: dict[tuple[str, str, int], str] = {
    ("| Exit code | Condition |", "`1`", 1): " per Verification-Properties §1.2.",
}

# The development-process repository: present in a working checkout, absent in the library
# repository's own CI. Cross-repository assertions are skipped there rather than faked —
# the pattern tests/test_provenance_guard.py established.
COMPANION = REPO_ROOT.parent / "gebra-dev-doc"
DOC_BOARD = COMPANION / "docs" / "plan" / "boards" / "docs-tutorials.md"
PROPERTY_CATALOG = COMPANION / "docs" / "specs" / "PROPERTY-CATALOG-SPEC.md"

requires_companion = pytest.mark.skipif(
    not DOC_BOARD.is_file(),
    reason="the development-process repository is not checked out beside this one",
)

requires_the_catalog = pytest.mark.skipif(
    not PROPERTY_CATALOG.is_file(),
    reason="the vendored property catalog is not checked out beside this repository",
)


@pytest.fixture(scope="module")
def config() -> dict[str, Any]:
    parsed: dict[str, Any] = yaml.safe_load(MKDOCS.read_text(encoding="utf-8"))
    return parsed


def _nav_pages(entries: list[Any]) -> list[str]:
    """Every page path in a `nav:` tree, in navigation order."""
    pages: list[str] = []
    for entry in entries:
        if isinstance(entry, str):
            pages.append(entry)
        elif isinstance(entry, dict):
            for value in entry.values():
                if isinstance(value, str):
                    pages.append(value)
                elif isinstance(value, list):
                    pages += _nav_pages(value)
    return pages


def _published_pages() -> list[str]:
    """Every Markdown file under `docs/` that the site is meant to publish."""
    return sorted(
        path.relative_to(DOCS).as_posix()
        for path in DOCS.rglob("*.md")
        if path.relative_to(DOCS).parts[0] not in INTERNAL_TREES
    )


# ── The build configuration ──────────────────────────────────────────────────────────────


def test_the_site_builds_from_the_docs_tree_with_warnings_as_errors(
    config: dict[str, Any],
) -> None:
    """`strict` in the file, not only on the CI command line: a local build must fail alike."""
    assert config["docs_dir"] == "docs"
    assert config["strict"] is True
    assert config["site_name"] == "gebra"


def test_the_rendered_site_is_never_committed(config: dict[str, Any]) -> None:
    assert f"{config['site_dir']}/" in GITIGNORE.read_text(encoding="utf-8").splitlines()


def test_the_toolchain_is_pinned_outside_the_package_dependencies() -> None:
    """A site generator is not part of what the package needs, so it is in no dependency set.

    Keeping it out of `pyproject.toml` is what keeps it out of `uv.lock` and out of the
    resolution of every compatibility cell, for a tool exactly one CI job runs.
    """
    assert re.search(
        r"^mkdocs==\d+\.\d+", DOCS_REQUIREMENTS.read_text(encoding="utf-8"), re.MULTILINE
    )

    with (REPO_ROOT / "pyproject.toml").open("rb") as handle:
        project = tomllib.load(handle)["project"]
    declared = list(project["dependencies"])
    for extra in project["optional-dependencies"].values():
        declared += extra

    assert not [requirement for requirement in declared if "mkdocs" in requirement]


# ── The skeleton: pages, navigation, and the two held equal ──────────────────────────────


def test_every_page_in_the_navigation_exists(config: dict[str, Any]) -> None:
    missing = [page for page in _nav_pages(config["nav"]) if not (DOCS / page).is_file()]

    assert missing == []


def test_every_published_page_is_reachable_from_the_navigation(config: dict[str, Any]) -> None:
    """The other direction: a page nobody can navigate to is a page nobody reads."""
    assert sorted(_nav_pages(config["nav"])) == _published_pages()


def test_the_skeleton_reserves_a_page_for_every_planned_one(config: dict[str, Any]) -> None:
    reserved = {page for pages in PAGES_BY_CARD.values() for page in pages}

    assert reserved | set(WRITTEN_PAGES) == set(_nav_pages(config["nav"]))


def test_no_page_is_reserved_for_two_cards() -> None:
    reserved = [page for pages in PAGES_BY_CARD.values() for page in pages]

    assert len(reserved) == len(set(reserved))


# ── What is a placeholder, and what is documentation ─────────────────────────────────────


def test_every_reserved_page_declares_itself_a_placeholder() -> None:
    """A reservation must never read as documentation (WA-12)."""
    for card, pages in sorted(PAGES_BY_CARD.items()):
        for page in pages:
            if page in LANDED_PAGES:
                continue
            text = (DOCS / page).read_text(encoding="utf-8")
            assert text.startswith(PLACEHOLDER_MARKER), f"{card}: {page} lacks the marker"
            assert "placeholder" in text.lower()
            assert "Reserved for:" in text


def test_the_written_pages_are_not_placeholders() -> None:
    """The other direction: a page declared written may not still be a reservation."""
    for page in (*WRITTEN_PAGES, *sorted(LANDED_PAGES)):
        text = (DOCS / page).read_text(encoding="utf-8")
        assert PLACEHOLDER_MARKER not in text
        assert "Reserved for:" not in text


def test_every_landed_page_is_one_a_card_reserved() -> None:
    """`LANDED_PAGES` names pages out of the manifest — never one the site does not plan."""
    reserved = {page for pages in PAGES_BY_CARD.values() for page in pages}

    assert LANDED_PAGES <= reserved


def test_a_placeholder_shows_no_code() -> None:
    """Nothing executable hides in a page that documents nothing yet."""
    for pages in PAGES_BY_CARD.values():
        for page in pages:
            if page in LANDED_PAGES:
                continue
            assert "```" not in (DOCS / page).read_text(encoding="utf-8")


# ── The internal trees, which are not this site ──────────────────────────────────────────


def test_the_internal_document_trees_are_excluded_by_name(config: dict[str, Any]) -> None:
    excluded = {line.strip() for line in config["exclude_docs"].splitlines() if line.strip()}

    assert {f"{tree}/" for tree in INTERNAL_TREES} <= excluded
    assert "requirements.txt" in excluded


def test_the_exclusion_is_not_vacuous() -> None:
    """The trees it names are really there — an exclusion of nothing checks nothing."""
    for tree in INTERNAL_TREES:
        assert list((DOCS / tree).glob("*.md")), f"docs/{tree}/ holds no document to exclude"


def test_the_site_publishes_no_specification_page(config: dict[str, Any]) -> None:
    """The published documentation and the build's own contract documents never mix."""
    assert not [page for page in _nav_pages(config["nav"]) if page.startswith(INTERNAL_TREES)]
    assert not [page for page in _published_pages() if page.startswith(INTERNAL_TREES)]


# ── The manifest against the board that owns it ──────────────────────────────────────────


def _table_rows(text: str, header: str) -> list[list[str]]:
    """The body cells of the first pipe table whose header line is `header`, row by row."""
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


def _without_wiki_links(cell: str) -> str:
    """Drop the vault's `[[target|label]]` notation, which published prose cannot carry."""
    cell = re.sub(r"\[\[[^\]|]*\|([^\]]*)\]\]", r"\1", cell)
    return re.sub(r"\[\[([^\]]*)\]\]", r"\1", cell).strip()


@requires_the_catalog
def test_the_transcribed_tables_match_the_property_catalog_cell_for_cell() -> None:
    """DOC-02's central claim: those tables are the specification, not a reading of it.

    Cell equality, not a similarity check — a paraphrase that softened "no proof claim" or
    dropped a gate effect is exactly what this is here to catch. The only tolerated
    differences are the vault's own wiki-link notation and the omissions declared above.
    """
    spec = PROPERTY_CATALOG.read_text(encoding="utf-8")
    page = (DOCS / "concepts" / "what-gebra-checks.md").read_text(encoding="utf-8")

    for header in TRANSCRIBED_TABLES:
        spec_rows = _table_rows(spec, header)
        page_rows = _table_rows(page, header)
        assert len(page_rows) == len(spec_rows), f"{header}: row count differs"
        for spec_row, page_row in zip(spec_rows, page_rows, strict=True):
            for column, (spec_cell, page_cell) in enumerate(zip(spec_row, page_row, strict=True)):
                expected = _without_wiki_links(spec_cell)
                omitted = DECLARED_OMISSIONS.get((header, page_row[0], column))
                if omitted is not None:
                    assert expected.endswith(omitted), (
                        f"{header} {page_row[0]} col {column}: the declared omission "
                        f"{omitted!r} is no longer what the specification says"
                    )
                    expected = expected[: -len(omitted)] + "."
                assert page_cell == expected, f"{header} {page_row[0]} col {column}"


@requires_the_catalog
def test_every_declared_omission_names_a_cell_that_exists() -> None:
    """A stale entry would silently license a real divergence, so it must not survive."""
    spec = PROPERTY_CATALOG.read_text(encoding="utf-8")

    for header, first_cell, column in DECLARED_OMISSIONS:
        rows = [row for row in _table_rows(spec, header) if row[0] == first_cell]
        assert len(rows) == 1, f"{header}: no unique row {first_cell!r}"
        assert column < len(rows[0]), f"{header} {first_cell}: no column {column}"


@requires_companion
def test_every_documentation_card_has_a_page_or_a_reason_not_to() -> None:
    """The anti-drift check: a card added to the track without a page reserved fails here."""
    board = DOC_BOARD.read_text(encoding="utf-8")
    cards = set(re.findall(r"^### (DOC-\d+) —", board, re.MULTILINE))

    assert cards, "no cards parsed from the documentation board"
    assert cards == set(PAGES_BY_CARD) | CARDS_WITHOUT_A_SITE_PAGE
