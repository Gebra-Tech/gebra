"""The API reference against the surfaces it is generated from (card DOC-17).

`docs/reference/api.md` is rendered by :mod:`tools.api_reference` out of the docstrings of
the five frozen surfaces. Two things could still go wrong, and this module is here for both.

The page could be **stale** — someone edits a docstring, or adds an export, and the committed
Markdown no longer says what the source says. That is what `--check` catches, and it runs
here as well as in the `docs` CI job, so a contributor without the documentation toolchain
installed still learns about it from `pytest`.

The generator itself could be **wrong** — resolving a re-export to the wrong module, missing
a `#:` block, silently dropping a name. A generator's output cannot check its generator, so
the assertions below go around it: the surfaces are read again here, from the live packages
rather than from the AST, and the page is held to *those* names, counts and kinds. The two
readings agreeing is the claim; either one alone is not.

The module imports the five frozen packages and reads Markdown. It builds no workflow, runs
no node and opens no connection (WA-07).
"""

from __future__ import annotations

import importlib
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Final

import pytest

from tools import api_reference

REPO_ROOT: Final = Path(__file__).resolve().parents[2]
PAGE: Final = REPO_ROOT / "docs" / "reference" / "api.md"
GOVERNANCE: Final = REPO_ROOT / "docs" / "governance"

#: The surfaces, read from the live packages rather than from the generator's static model.
LIVE_SURFACES: Final[tuple[str, ...]] = (
    "gebra",
    "gebra.ir",
    "gebra.verify",
    "gebra.extraction",
    "gebra.annotations",
)


@pytest.fixture(scope="module")
def page() -> str:
    return PAGE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def entries(page: str) -> dict[str, str]:
    """Every ``#### `qualified.name``` entry, mapped to the body under it."""
    found: dict[str, str] = {}
    parts = re.split(r"^#### `([^`]+)`$", page, flags=re.MULTILINE)
    for name, body in zip(parts[1::2], parts[2::2]):
        found[name] = body
    return found


def live_exports(module: str) -> tuple[str, ...]:
    return tuple(importlib.import_module(module).__all__)


# ── The gate the CI job runs ─────────────────────────────────────────────────────────────


def test_the_page_is_what_the_docstrings_render_to() -> None:
    """`--check`, run from the test suite as well as from the `docs` job."""
    assert api_reference.main(["--check"]) == 0


def test_the_page_is_a_fixed_point_of_the_repositorys_own_formatter() -> None:
    """Both gates have an opinion about this file, and they must be the same opinion.

    `ruff format` reformats the Python inside a Markdown fence, so a generator that emitted
    `ast.unparse`'s quote style would make `ruff format --check .` and
    `api_reference.py --check` demand different bytes of the same page, forever. The
    generator formats its output with ruff for that reason; this is the check that it did.
    """
    ruff = shutil.which("ruff") or str(Path(sys.executable).parent / "ruff")
    if not Path(ruff).is_file():  # pragma: no cover - the dev extra always provides it
        pytest.skip("ruff is not installed beside this interpreter")

    finished = subprocess.run(
        [ruff, "format", "--check", str(PAGE)],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        check=False,
    )

    assert finished.returncode == 0, finished.stdout


def test_no_public_symbol_on_a_frozen_surface_is_undocumented() -> None:
    """The card's second acceptance box, as an assertion rather than as an exit code."""
    missing = [symbol.qualified for symbol in api_reference.undocumented()]

    assert missing == []


def test_a_symbol_with_no_docstring_would_fail_the_check(monkeypatch: pytest.MonkeyPatch) -> None:
    """The probe: a gate nobody has seen refuse anything is not known to refuse anything."""
    real = api_reference.documentation

    def blank(module: str, node: object) -> str:
        text = real(module, node)  # type: ignore[arg-type]
        return "" if text.startswith("The content digest of") else text

    monkeypatch.setattr(api_reference, "documentation", blank)

    assert [symbol.name for symbol in api_reference.undocumented()] == ["graph_version"]


# ── The page against the live packages, in both directions ───────────────────────────────


def test_every_exported_name_has_an_entry(entries: dict[str, str]) -> None:
    """A name the package exports that the page does not describe is a hole in the page."""
    expected = {f"{module}.{name}" for module in LIVE_SURFACES for name in live_exports(module)}

    assert expected - set(entries) == set()


def test_every_entry_names_something_the_package_exports(entries: dict[str, str]) -> None:
    """The other direction: the page may not invent, misspell or keep a departed name."""
    expected = {f"{module}.{name}" for module in LIVE_SURFACES for name in live_exports(module)}

    assert set(entries) - expected == set()


def test_the_surface_table_counts_what_the_packages_export(page: str) -> None:
    for module in LIVE_SURFACES:
        row = re.search(rf"^\| \[`{re.escape(module)}`\]\(#[^)]+\) \| (\d+) \|", page, re.MULTILINE)
        assert row is not None, f"{module} has no row in the surface table"
        assert int(row.group(1)) == len(live_exports(module))


def test_each_entry_says_where_the_name_is_defined(entries: dict[str, str]) -> None:
    """The module named on an entry is the module the live object actually comes from."""
    for module in LIVE_SURFACES:
        package = importlib.import_module(module)
        for name in live_exports(module):
            value = getattr(package, name)
            origin = getattr(value, "__module__", None)
            if origin is None or not origin.startswith("gebra"):
                continue  # a constant or a type alias, which carries no `__module__`
            assert f"defined in `{origin}`" in entries[f"{module}.{name}"], f"{module}.{name}"


def test_a_callable_entry_shows_its_own_parameters(entries: dict[str, str]) -> None:
    """Signatures are rendered from the source, so every declared parameter must appear."""
    import inspect

    for module in LIVE_SURFACES:
        package = importlib.import_module(module)
        for name in live_exports(module):
            value = getattr(package, name)
            if not inspect.isfunction(value):
                continue
            block = re.search(r"```python\n(.*?)\n```", entries[f"{module}.{name}"], re.DOTALL)
            assert block is not None, f"{module}.{name} has no signature block"
            rendered = block.group(1)
            for parameter in inspect.signature(value).parameters:
                assert parameter in rendered, f"{module}.{name} omits {parameter}"


def test_the_three_names_that_mean_two_things_say_so(entries: dict[str, str]) -> None:
    """`NodeId`, `to_data` and `to_json` are each two different objects on two surfaces.

    An integrator who reads one entry and imports the other gets a type error at best. The
    generator computes the warning from the surfaces themselves; this is the check that it
    is still computing it, and that the set has not silently grown.
    """
    homes: dict[str, list[str]] = {}
    for module in LIVE_SURFACES:
        for name in live_exports(module):
            homes.setdefault(name, []).append(module)

    shared = {
        name
        for name, modules in homes.items()
        if len({id(getattr(importlib.import_module(module), name)) for module in modules}) > 1
    }

    assert shared == {"NodeId", "to_data", "to_json"}
    for name in shared:
        for module in homes[name]:
            assert "shares the name only" in entries[f"{module}.{name}"], f"{module}.{name}"


# ── What the page says about the freeze records ──────────────────────────────────────────


def test_every_freeze_record_the_page_cites_exists_and_is_frozen(page: str) -> None:
    for surface in api_reference.SURFACES:
        record = REPO_ROOT / surface.record
        assert record.is_file(), f"{surface.module} cites a record that is not there"
        assert "**Status: FROZEN**" in record.read_text(encoding="utf-8")
        assert f"`{surface.record}` {surface.section}" in page


def test_the_freeze_cards_are_the_ones_the_records_name() -> None:
    """`gebra.ir` is IR-06's, `gebra.verify` is VAL-12's, the other three are EX-15's."""
    for surface in api_reference.SURFACES:
        text = (REPO_ROOT / surface.record).read_text(encoding="utf-8")
        assert f"card {surface.card}" in text, f"{surface.record} does not name {surface.card}"


def test_the_page_is_not_a_placeholder(page: str) -> None:
    assert "<!-- docs:placeholder -->" not in page
    assert page.startswith("# API reference\n")


def test_the_page_says_it_is_generated(page: str) -> None:
    """A reader who edits this file directly must find out before a reviewer tells them."""
    assert "Generated by tools/api_reference.py" in page
    assert "python tools/api_reference.py --write" in page


# ── The renderer's own reading of a docstring ────────────────────────────────────────────


def test_sphinx_roles_become_code_spans() -> None:
    rendered = api_reference.to_markdown(
        "See :class:`~gebra.ir.models.WorkflowIR`, :func:`gebra.ir.graph_version` "
        "and :mod:`gebra.verify` for ``details``."
    )

    assert rendered == "See `WorkflowIR`, `graph_version()` and `gebra.verify` for `details`."


def test_a_method_role_keeps_the_class_that_owns_it() -> None:
    """`graph_version` is a method of one model *and* a module-level function of `gebra.ir`.

    Both are documented on this page. Shortening the method to its bare name would put the
    same code span on two different callables with different signatures, so the method keeps
    the class and the function keeps only its name.
    """
    rendered = api_reference.to_markdown(
        ":meth:`~gebra.extraction.envelope.ExtractionEnvelope.graph_version` "
        "is not :func:`~gebra.ir.canonical.graph_version`."
    )

    assert rendered == "`ExtractionEnvelope.graph_version()` is not `graph_version()`."


def test_prose_outside_a_code_span_cannot_open_a_tag() -> None:
    """A bare `<hex>` in a docstring must not be swallowed as HTML by the renderer."""
    rendered = api_reference.to_markdown('renders as "sha256:<hex>" but `<kept>` is code')

    assert rendered == 'renders as "sha256:&lt;hex>" but `<kept>` is code'


def test_a_hard_wrapped_paragraph_becomes_one_line() -> None:
    """Re-joining is what stops a wrapped `#` or `-` from being read as markup."""
    rendered = api_reference.to_markdown("first line\n# second line\n- third")

    assert rendered == "first line # second line - third"


def test_a_shared_comment_block_documents_the_whole_run() -> None:
    """Three OpenInference names under one `#:` sentence are three documented symbols."""
    documented = {
        symbol.name: symbol.doc
        for symbol in api_reference.collect()
        if symbol.name.startswith("OPENINFERENCE_")
    }

    assert set(documented) == {"OPENINFERENCE_ID", "OPENINFERENCE_NAME", "OPENINFERENCE_PARENT_ID"}
    assert len({text for text in documented.values()}) == 1
    assert "OpenInference attribute names" in next(iter(documented.values()))


def test_the_google_sections_are_parsed_into_pairs() -> None:
    doc = (
        "Summary.\n\n"
        "Args:\n"
        "    first: the first one,\n"
        "        continued.\n"
        "    second: the second.\n\n"
        "Returns:\n"
        "    a thing.\n\n"
        "Raises:\n"
        "    ValueError: never.\n"
    )

    found = api_reference.sections(doc)

    assert found["Args"] == [("first", "the first one, continued."), ("second", "the second.")]
    assert found["Returns"] == [("", "a thing.")]
    assert found["Raises"] == [("ValueError", "never.")]


def test_a_render_with_two_headings_of_one_name_is_refused() -> None:
    """The anchor guard: Markdown would suffix the second, sending links to the first."""
    with pytest.raises(ValueError, match="claimed by both"):
        api_reference._assert_unique_anchors("## `gebra.ir`\n\n#### `gebra.ir`\n")


# ── The links the page writes to itself ──────────────────────────────────────────────────


def test_every_internal_link_resolves_to_a_heading_on_the_page(page: str) -> None:
    """The same check `mkdocs build --strict` makes, run without the documentation toolchain."""
    anchors = {
        api_reference.slug(text.replace("`", ""))
        for _, text in re.findall(r"^(#{1,6}) (.+)$", page, re.MULTILINE)
    }
    links = set(re.findall(r"\]\(#([^)]+)\)", page))

    assert links - anchors == set()


def test_no_two_headings_claim_the_same_anchor(page: str) -> None:
    headings = [text for _, text in re.findall(r"^(#{1,6}) (.+)$", page, re.MULTILINE)]
    anchors = [api_reference.slug(text.replace("`", "")) for text in headings]

    assert len(anchors) == len(set(anchors))


def test_the_page_links_out_to_the_pages_that_own_the_unfrozen_surfaces(page: str) -> None:
    """A surface this page declines to document must say where it *is* documented."""
    for link in ("cli.md", "../guides/pytest-plugin-and-ci-gating.md"):
        assert f"]({link})" in page


def test_the_page_states_the_never_invokes_boundary(page: str) -> None:
    assert "not implemented" in page
    assert "structured not-implemented marker rather than a pass" in page


def test_no_non_emittable_condition_id_reaches_the_page(page: str) -> None:
    """The registry's closure, as a property of the page rather than of a length threshold.

    A RESERVED or unratified PROPOSED ID printed here would read as something a validator
    emits. Today none is on the page — but only because the constants that hold them render
    as `...` for being too long to fit a line, which is an accident of formatting rather than
    a rule. This is the rule.

    The two PROPOSED-tier IDs that *are* on the page are the record-ratified pair, which
    `EMITTABLE_CONDITION_IDS` contains: emittability is what this asserts on, never tier.
    """
    from gebra.verify import CONDITION_IDS, EMITTABLE_CONDITION_IDS

    held_back = set(CONDITION_IDS) - set(EMITTABLE_CONDITION_IDS)

    assert held_back, "an assertion over an empty set checks nothing"
    assert [identifier for identifier in sorted(held_back) if identifier in page] == []


def test_no_latex_survives_into_the_page(page: str) -> None:
    """A `$…$` span the site cannot render would reach a reader as its own dollar signs.

    The generator rewrites the notation into the symbols it spells; an unmapped command
    would leave a backslash behind. Both are checked outside code, so extending
    `MATH_SYMBOLS` is what a new command costs. Inside a code span a backslash is ordinary
    — `G \\ S` is set difference, written as itself — so code is excluded rather than
    exempted by exception.
    """
    prose = re.sub(r"```.*?```", "", page, flags=re.DOTALL)
    prose = re.sub(r"`[^`]*`", "", prose)

    assert "$" not in prose
    assert "\\" not in prose
