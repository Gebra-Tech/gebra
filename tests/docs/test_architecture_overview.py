"""The architecture overview against the system it describes (card DOC-17).

`docs/reference/architecture.md` is the one page whose subject is the shape of the package
rather than any one part of it, and every structural claim it makes is a fact something else
in this repository already fixes. This module holds it to those facts rather than to a
reviewer's memory of them.

Four claims are worth naming because each fails a different way. The **package table** could
list a package that no longer exists or miss one that now does — it is reconciled against the
live `__all__` lists in both directions. The **import-closure table** is the page's strongest
structural claim, and it is the one a refactor breaks silently, so it is not read off the
source: each package is imported in a fresh interpreter and the resulting `sys.modules` is
what the table is compared with, again in both directions. The **freeze table** could cite a
record that has moved or a count that has drifted. And the **1.x backlog appendix** is a
verbatim reproduction of another document's table, so it is compared cell for cell — a row
added to the freeze record and not to this page fails as loudly as a row invented here.

The module imports the public packages and reads Markdown; the closure probes run
`import <package>` in child interpreters. It builds no workflow, runs no node and opens no
connection (WA-07). The child interpreters import library packages only — the same import
`pytest` itself performs to collect this file — and assert on `sys.modules`.
"""

from __future__ import annotations

import ast
import importlib
import re
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Final

import pytest

from tests.sample_workflows import travel_booking

REPO_ROOT: Final = Path(__file__).resolve().parents[2]
PAGE: Final = REPO_ROOT / "docs" / "reference" / "architecture.md"
FREEZE_RECORD: Final = REPO_ROOT / "docs" / "governance" / "EXTRACTOR-API-FREEZE.md"

#: The packages the page's table lists, in its own order.
PACKAGES: Final[tuple[str, ...]] = (
    "gebra",
    "gebra.extraction",
    "gebra.annotations",
    "gebra.ir",
    "gebra.verify",
    "gebra.snapshot",
    "gebra.store",
    "gebra.versioning",
    "gebra.lineage",
    "gebra.diff",
    "gebra.audit",
    "gebra.report",
    "gebra.display",
    "gebra.testing",
    "gebra.pytest_plugin",
    "gebra.cli",
)

#: Modules under `src/gebra/` that declare an `__all__` and are still not one of the sixteen
#: the page calls public, with the reason each is left out. `gebra.naming` holds one function
#: (`type_identity`) that both `gebra.extraction` and `gebra.annotations` re-export, in a
#: module with no dependencies so that neither lane has to import the other; it is a shared
#: definition rather than a surface a reader imports, and both of its consumers list it.
#: A second entry here would be a decision someone has to make on purpose.
NOT_A_PUBLIC_PACKAGE: Final[dict[str, str]] = {
    "gebra.naming": "one shared function, re-exported by both surfaces that use it",
}

#: The two that read a live workflow, and therefore need the substrate to import.
SUBSTRATE_IMPORTERS: Final[frozenset[str]] = frozenset({"gebra.extraction", "gebra.snapshot"})

#: What "the substrate" means for the closure probe.
SUBSTRATE: Final[tuple[str, ...]] = ("langgraph", "langchain", "langchain_core", "langsmith")

#: The frozen surfaces the page tabulates, with the record that freezes each.
FROZEN: Final[dict[str, str]] = {
    "gebra.ir": "docs/governance/IR-MODELS-FREEZE.md",
    "gebra.verify": "docs/governance/VALIDATOR-API-FREEZE.md",
    "gebra": "docs/governance/EXTRACTOR-API-FREEZE.md",
    "gebra.extraction": "docs/governance/EXTRACTOR-API-FREEZE.md",
    "gebra.annotations": "docs/governance/EXTRACTOR-API-FREEZE.md",
}


@pytest.fixture(scope="module")
def page() -> str:
    return PAGE.read_text(encoding="utf-8")


@pytest.fixture(autouse=True)
def _ledger_is_clean() -> Iterator[None]:
    """WA-07: nothing in this module may run a node body, before or after (the TE-05 idiom).

    One test here hands a live workflow to the extractor, so the claim is asserted for the
    whole module rather than inside that one test: an entry-side failure says a *previous*
    test left a body run, which is exactly the case a single exit assertion cannot see.
    """
    assert travel_booking.TRIPPED == []
    yield
    assert travel_booking.TRIPPED == []


#: The one character the published appendix does not reproduce byte-for-byte, and why.
#: Backlog row 19 quotes a composite ``Flag`` name, ``"A|B"``, and a raw pipe inside a
#: Markdown table cell ends the cell. The freeze record is not a published page and does not
#: have to care; this page does, so it escapes that pipe. The escape is undone below before
#: the two are compared, which is what keeps "verbatim" an honest word — a *second* entry
#: here would be a decision someone has to make on purpose.
DECLARED_ESCAPES: Final[tuple[tuple[str, str], ...]] = ((r"\|", "|"),)

_CELL_SPLIT: Final = re.compile(r"(?<!\\)\|")


def _table_lines(text: str, header: str) -> list[str]:
    """The raw body lines of the first pipe table whose header line is ``header``."""
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if line.strip() != header:
            continue
        rows = []
        for candidate in lines[index + 2 :]:
            if not candidate.startswith("|"):
                break
            rows.append(candidate)
        return rows
    raise AssertionError(f"no table with header {header!r}")


def _table(text: str, header: str) -> list[list[str]]:
    """The body rows as cells, split on *unescaped* pipes and then unescaped.

    Splitting on escaped pipes is what a Markdown renderer does, so this is the table the
    reader sees rather than the one a naive `str.split` would produce.
    """
    rows = []
    for line in _table_lines(text, header):
        cells = [cell.strip() for cell in _CELL_SPLIT.split(line.strip("|"))]
        for escaped, plain in DECLARED_ESCAPES:
            cells = [cell.replace(escaped, plain) for cell in cells]
        rows.append(cells)
    return rows


def _example(text: str, identifier: str) -> tuple[str, str]:
    """One marked example's code and its declared output."""
    code = re.search(
        rf"<!-- gebra:example id={identifier} -->\n```python\n(.*?)\n```", text, re.DOTALL
    )
    output = re.search(
        rf"<!-- gebra:output id={identifier} -->\n```text\n(.*?)\n```", text, re.DOTALL
    )
    assert code is not None and output is not None, identifier
    return code.group(1), output.group(1)


# ── The packages ─────────────────────────────────────────────────────────────────────────


def test_the_package_table_lists_every_package_the_example_counts(page: str) -> None:
    rows = _table(page, "| Package | What it owns | Where it is documented |")
    listed = [row[0].strip("`") for row in rows]

    assert listed == list(PACKAGES)


def test_sixteen_is_the_whole_public_surface(page: str) -> None:
    """The page's "sixteen public packages" is a count, and a count is exactly what drifts.

    Every module and package directly under `src/gebra/` that declares an `__all__` is either
    on the page or in `NOT_A_PUBLIC_PACKAGE` with its reason — so a package added to the
    distribution and not to this page fails here rather than quietly making the number wrong.
    """
    source = REPO_ROOT / "src" / "gebra"
    declared = set()
    for path in sorted(source.iterdir()):
        module = f"gebra.{path.stem}" if path.suffix == ".py" else f"gebra.{path.name}"
        readable = path if path.suffix == ".py" else path / "__init__.py"
        if path.name.startswith(("_", ".")) and path.name != "__init__.py":
            continue
        if not readable.is_file() or "__all__" not in readable.read_text(encoding="utf-8"):
            continue
        declared.add("gebra" if path.name == "__init__.py" else module)

    assert declared - set(NOT_A_PUBLIC_PACKAGE) == set(PACKAGES)
    assert set(NOT_A_PUBLIC_PACKAGE) <= declared, "an exclusion that names nothing checks nothing"
    assert "Sixteen public packages" in page
    assert len(PACKAGES) == 16


def test_every_listed_package_exists_and_exports_what_the_example_prints(page: str) -> None:
    """The counts on the page are the live `__all__` lengths, package for package."""
    _, output = _example(page, "the-public-packages")
    printed = {
        line.split()[0]: int(line.split()[1])
        for line in output.splitlines()
        if line and not line.startswith(("-", " ", "exported"))
    }

    assert printed == {name: len(importlib.import_module(name).__all__) for name in PACKAGES}


def test_the_printed_total_is_the_sum_of_the_printed_rows(page: str) -> None:
    _, output = _example(page, "the-public-packages")
    rows = [
        int(line.split()[1])
        for line in output.splitlines()
        if line and not line.startswith(("-", " ", "exported"))
    ]
    total = int(output.splitlines()[-1].split()[-1])

    assert total == sum(rows)
    assert total == sum(len(importlib.import_module(name).__all__) for name in PACKAGES)


def test_every_package_the_table_points_at_a_page_for_points_at_one_that_exists(
    page: str,
) -> None:
    rows = _table(page, "| Package | What it owns | Where it is documented |")
    for row in rows:
        targets = re.findall(r"\]\(([^)#]+)(?:#[^)]*)?\)", row[2])
        assert targets, f"{row[0]} points nowhere"
        for target in targets:
            assert (PAGE.parent / target).resolve().is_file(), f"{row[0]} -> {target}"


# ── The import closure, measured rather than read ────────────────────────────────────────


def _closure(package: str) -> frozenset[str]:
    """Which substrate distributions importing ``package`` pulls in, in a fresh interpreter."""
    script = (
        "import importlib, sys\n"
        f"importlib.import_module({package!r})\n"
        f"print(sorted({{n.split('.')[0] for n in sys.modules}} & set({list(SUBSTRATE)!r})))"
    )
    finished = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=True,
        cwd=REPO_ROOT,
    )
    # `literal_eval`, never `eval`: this repository arms `eval` and `compile` as WA-07
    # raisers, and a bare evaluator over subprocess output in the never-invokes-relevant
    # suite is the exact shape those tripwires exist to refuse.
    return frozenset(ast.literal_eval(finished.stdout.strip()))


@pytest.mark.parametrize("package", PACKAGES)
def test_the_import_closure_is_what_the_page_says_it_is(page: str, package: str) -> None:
    """Both directions in one assertion: the page's two-package claim, package by package."""
    pulled = _closure(package)

    assert bool(pulled) is (package in SUBSTRATE_IMPORTERS), (
        f"{package} pulls {sorted(pulled)}, which the page does not say it does"
    )


def test_the_page_names_exactly_the_two_that_pull_the_substrate(page: str) -> None:
    rows = _table(page, "| Import closure | Packages |")
    pulls = {cell.strip("`") for cell in rows[0][1].split(", ")}
    clean = {cell.strip("`") for cell in rows[1][1].split(", ")}

    assert pulls == set(SUBSTRATE_IMPORTERS)
    assert pulls | clean == set(PACKAGES)
    assert pulls & clean == set()


def test_a_bare_import_gebra_reaches_neither_the_extractor_nor_the_substrate() -> None:
    """The lazy top-level claim, which is the reader-facing half of the closure table."""
    script = "import gebra, sys; print('gebra.extraction' in sys.modules)"
    finished = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, check=True, cwd=REPO_ROOT
    )

    assert finished.stdout.strip() == "False"
    assert _closure("gebra") == frozenset()


# ── What is frozen ───────────────────────────────────────────────────────────────────────


def test_the_freeze_table_names_a_record_that_exists_and_is_frozen(page: str) -> None:
    rows = _table(page, "| Surface | Names | Freeze record | Changing its shape requires |")
    listed = {row[0].strip("`"): row for row in rows}

    assert set(listed) == set(FROZEN)
    for surface, row in listed.items():
        assert int(row[1]) == len(importlib.import_module(surface).__all__)
        assert FROZEN[surface] in row[2]
        record = REPO_ROOT / FROZEN[surface]
        assert "**Status: FROZEN**" in record.read_text(encoding="utf-8")


def test_the_frozen_surfaces_are_the_ones_the_api_reference_documents(page: str) -> None:
    from tools import api_reference

    rows = _table(page, "| Surface | Names | Freeze record | Changing its shape requires |")

    assert {row[0].strip("`") for row in rows} == {s.module for s in api_reference.SURFACES}


# ── The appendix, cell for cell against the record it reproduces ─────────────────────────


def test_the_backlog_appendix_is_the_freeze_records_own_table(page: str) -> None:
    """Verbatim, both directions, line for line — the card's acceptance made mechanical.

    Compared as whole rows rather than as parsed cells, because the record's row 19 carries
    the raw pipe this page has to escape: reversing the escape and comparing the text is the
    strongest form of "verbatim" available, and it checks the escape itself.
    """
    header = "| # | Item | What it would carry | Spec anchor | Status |"
    published = _table_lines(page, header)
    recorded = _table_lines(FREEZE_RECORD.read_text(encoding="utf-8"), header)

    assert len(published) == len(recorded), "the page and the record carry different row counts"
    for index, (shown, source) in enumerate(zip(published, recorded, strict=True), start=1):
        unescaped = shown
        for escaped, plain in DECLARED_ESCAPES:
            unescaped = unescaped.replace(escaped, plain)
        assert unescaped == source, f"backlog row {index} differs from the freeze record"


def test_the_appendix_escapes_exactly_the_pipe_it_declares(page: str) -> None:
    """One declared escape, used once — a second would be an undeclared divergence."""
    header = "| # | Item | What it would carry | Spec anchor | Status |"
    published = "\n".join(_table_lines(page, header))

    assert published.count(r"\|") == 1
    assert r'`"A\|B"`' in published
    assert all(len(row) == 5 for row in _table(page, header))


def test_every_backlog_row_needs_a_future_decision_record(page: str) -> None:
    """The page's own framing sentence must be true of every row it prints."""
    rows = _table(page, "| # | Item | What it would carry | Spec anchor | Status |")

    assert rows, "the appendix carries no rows"
    for row in rows:
        assert "needs future DEC" in row[4], f"row {row[0]} does not say it needs a DEC"
    assert "Every row needs a future decision record" in page


def test_the_appendix_says_where_it_came_from(page: str) -> None:
    assert "docs/governance/EXTRACTOR-API-FREEZE.md` §2" in page
    assert "card EX-15" in page


def test_the_appendix_repeats_the_records_own_disclaimer(page: str) -> None:
    """The record does not claim the rows are complete, and neither may this page."""
    assert "not a complete account" in page
    assert "not a claimed-complete one" in FREEZE_RECORD.read_text(
        encoding="utf-8"
    ) or "the *complete* set" in FREEZE_RECORD.read_text(encoding="utf-8")


# ── The rest of the page ─────────────────────────────────────────────────────────────────


def test_the_page_is_not_a_placeholder(page: str) -> None:
    assert "<!-- docs:placeholder -->" not in page
    assert page.startswith("# Architecture overview\n")


def test_the_pipeline_example_ends_with_an_empty_ledger(page: str) -> None:
    """The example's last line is the never-invokes claim, printed rather than asserted."""
    _, output = _example(page, "the-pipeline-in-one-run")

    assert output.splitlines()[-1] == "node bodies run: []"


def test_the_pipeline_examples_digest_is_the_one_the_agent_has(page: str) -> None:
    """The identity line is a real digest of the real sample agent, not a stand-in.

    The one test in this module that reaches a live workflow object. It builds the
    sentinel-guarded travel-booking agent and extracts it in process; `_ledger_is_clean` is
    what says no body ran, on entry and on exit.
    """
    import gebra
    from gebra.ir import graph_version

    _, output = _example(page, "the-pipeline-in-one-run")
    printed = next(line for line in output.splitlines() if line.startswith("2  identity"))
    envelope = gebra.extract(travel_booking.build_travel_booking_agent())

    assert printed.split()[-1] == graph_version(envelope.ir)
    assert travel_booking.TRIPPED == []


def test_the_property_counts_are_the_registrys_own(page: str) -> None:
    """Thirteen slugs, five wedge, eight not — the three numbers stage 3 states in words."""
    from gebra.verify import NON_WEDGE_SLUGS, PROPERTY_SLUGS, WEDGE_SLUGS

    assert (len(PROPERTY_SLUGS), len(WEDGE_SLUGS), len(NON_WEDGE_SLUGS)) == (13, 5, 8)
    assert "thirteen property slugs" in page
    assert "Five are implemented — the wedge five — and the other eight" in page


def test_the_diff_stage_names_the_deferred_marker(page: str) -> None:
    """The diff carries a not-implemented marker for P-12, and the page must say so."""
    from gebra.diff import EVOLUTION_SAFETY_DEFERRED

    assert "evolution-safety" in repr(EVOLUTION_SAFETY_DEFERRED)
    assert "`evolution-safety`" in page
    assert "says *not checked* rather than implying a clean bill" in page


def test_the_six_stages_each_have_a_section(page: str) -> None:
    for stage in ("1 — Extraction", "2 — The IR", "3 — Verification", "4 — Snapshot and version"):
        assert f"**{stage}" in page
    assert "**5 — Diff and lineage" in page
    assert "**6 — Surfaces" in page


def test_the_page_states_the_never_invokes_boundary_and_all_three_concessions(page: str) -> None:
    """All three places non-gebra code runs are named, or the boundary sentence overstates.

    The third — that reading a node's type hints evaluates its annotation expressions — is
    the one a reader cannot find for themselves, and the one an earlier draft of this page
    left out. `tests/never_invokes_audit.md` is the document that carries them in full, and
    the page must point at it rather than imply its own list is the whole account.
    """
    assert "calls no node function, no router, no tool and no model" in page
    assert "three places where code that is not gebra's runs" in page
    assert "`--call`" in page
    assert "Importing a module runs that module's" in page
    assert "evaluates its annotation *expressions*" in page
    assert "tests/never_invokes_audit.md" in page
    assert "Nothing here is a claim about what\nyour agent does at run time." in page


def test_the_page_does_not_grade_a_change(page: str) -> None:
    """The diff section must keep saying that the classification is the reviewer's."""
    assert "It is the evidence, not the judgement" in page
    assert "safe to ship is the reviewer's" in page
