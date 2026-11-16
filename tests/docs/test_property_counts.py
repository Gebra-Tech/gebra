"""No page states how many properties are checked — the registry's table does (card DOC-21).

Phase 0 shipped prose that counted: "five properties", "the other eight", "5 reported | 8 produced
no verdict" in a sentence, "a green run is green on five". Each was true, and each would have
gone stale at the first Phase-1 landing — eight landings, each paying the same edit again and
leaving a stale count wherever it missed one. The catalog charter rules the other way: counts
derive from the registry (DEC-35 §3.5 (c)). For the documentation that means one table,
generated from the registry (`tools/property_table.py`, on `docs/concepts/what-gebra-checks.md`),
and prose that points at the table instead of a number.

This module holds that rule over everything a reader of the package meets: the README, every
page under `docs/` but the two internal trees named in :data:`EXCLUDED_TREES`, and every
string literal under `src/gebra/` that is not a docstring (error messages, report and plugin
copy). It also holds the second half of the card's copy work: the phrases that named Phase 0 as
the present are gone from the documentation, and the three pages that carried them now carry
the charter's own copy for a property with no validator (DEC-42 §3.1).

**What counts as a property count** is a number word or numeral that counts catalog properties,
their validators, slugs, verdicts, markers, outcomes or test items — "eight properties", "five
are implemented", "the other eight", "the wedge five", "all thirteen", "three of the five
properties", "implements five". A count of something else ("the five verbs", "four conditions",
"seven positives") is not one, and the scan's arming tests below show it tells the two apart on
the sentences this card rewrote and on the ones it left. The scan is a pattern, not a parser: a
count phrased some other way can slip past it, which is why the arming tests pin every phrasing
this card found rather than claim the pattern is complete.

**What is not scanned, and why.** An executed example's output block, and the README
quickstart's console transcript, are what a run printed — the examples harness compares them
byte for byte against that run, so their numbers are the run's, not an author's. HTML comments
render nowhere. And the generated table itself states each property's standing row by row,
rendered from the registry rather than written.

**What survives.** :data:`KEPT_LITERALS` names each number word that may still appear as a
property count, with its reason. There is one: "thirteen", the catalog's size, which no landing
moves; :func:`test_every_kept_literal_is_the_registrys_own` holds it to the registry.

The module reads Markdown and parses Python source with `ast`; it imports `gebra.verify` and
`tools.property_table`. It builds no workflow, runs no node and opens no connection (WA-07).
"""

from __future__ import annotations

import ast
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Final

import pytest

from gebra.verify import DEFERRED_READING, registry_counts
from tests.verify.test_registry import RETIRED_PHRASES
from tools import property_table

REPO_ROOT: Final = Path(__file__).resolve().parents[2]
DOCS: Final = REPO_ROOT / "docs"
SRC: Final = REPO_ROOT / "src" / "gebra"

#: How the documentation spells a count, indexed by value — a spelling table, not a count.
NUMBER_WORDS: Final[tuple[str, ...]] = (
    "zero",
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
    "eleven",
    "twelve",
    "thirteen",
)

#: The number words that may still appear as a property count, each with its reason. Every
#: other count of properties is the registry's to state, through the generated table.
KEPT_LITERALS: Final[dict[str, str]] = {
    "thirteen": (
        "the catalog's size — the property slug vocabulary, which no property's landing "
        "moves: a fourteenth property is a catalog change, not a landing (PD-070 §4). "
        "`test_every_kept_literal_is_the_registrys_own` holds the word to the registry's total."
    ),
}

#: The trees under `docs/` the scan leaves out, each with its reason. Both are excluded from the
#: published site by name (`mkdocs.yml`'s `exclude_docs`).
EXCLUDED_TREES: Final[dict[str, str]] = {
    "docs/specs/": (
        "the build's own contract specifications (CLI, report format, extension, diagram "
        "style), amended only by the cards that own them — CLI-12 moved their marker copy at "
        "report_format 1.4 — and never by a documentation sweep"
    ),
    "docs/governance/": (
        "dated records — freeze records, the fidelity matrix, the DoD scenario, sign-offs — "
        "that state what was true when they were signed; one of them carries the SOW §8 "
        "citation PD-072 §1 relies on"
    ),
}

# ── The pattern ──────────────────────────────────────────────────────────────────────────

_WORD = r"(?:two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen)"
#: A numeral standing alone — not a section (`§7.3`), an ID (`P-12`), a path or a version.
_DIGITS = r"(?<![\w§.\-/#])(?:1[0-3]|[2-9])(?![\w.\-/])"
_NUMBER = rf"(?:{_WORD}|{_DIGITS})"
_MODIFIER = (
    r"(?:catalog|implemented|non-wedge|deferred|wedge|other|remaining|property|per-validator|"
    r"topology-consuming|topology-reading|shipped|live|unimplemented|structured|reported|"
    r"checked|registered|Phase-0|green)"
)
_NOUN = (
    r"(?:propert(?:y|ies)|property\s+validators|validators|slugs|explainers|"
    r"(?:per-)?validator\s+pages|ticks)"
)

#: A count of properties wherever it appears.
_COUNT: Final = re.compile(
    "|".join(
        f"(?:{pattern})"
        for pattern in (
            rf"\b{_WORD}(?:[\s-]+{_MODIFIER})*[\s-]+{_NOUN}\b",
            rf"{_DIGITS}\s+(?:{_MODIFIER}\s+)*{_NOUN}\b",
            (
                rf"\b{_WORD}\s+(?:are|is)\s+(?:implemented|live|checked|not\s+checked|deferred"
                r"|shipped|not\s+implemented)\b"
            ),
            rf"{_NUMBER}\s+(?:produced\s+no\s+verdict|not\s+checked|answered|reported\s*\|)",
            rf"\b{_WORD}\s+(?:answer|come\s+back|it\s+does\s+not|produce\s+no)\b",
            rf"\bwedge[\s-]+{_WORD}\b",
            rf"\b{_WORD}[\s-]+wedge\b",
            r"\ball\s+(?:thirteen|1[0-3])\b",
            rf"\b{_WORD}\s+of\s+the\s+{_WORD}\s+(?:{_MODIFIER}\s+)*{_NOUN}",
            rf"\b{_WORD}-property\b",
            rf"\b(?:implements|checks|ships|registers)\s+{_WORD}\b",
            rf"\beach\s+of\s+the\s+{_WORD}\s+(?:reports|answers|passes|is|are|has|have)\b",
            rf"\bgreen\s+on\s+{_WORD}\b",
        )
    ),
    re.IGNORECASE,
)

#: Forms that are a count of properties only beside a word about properties: "the other
#: eight", "five verdicts", "eight markers", "thirteen outcomes", "five items". Each of these
#: words also counts other things on these pages — pre-review verdicts, pytest markers, a
#: binding's outcomes, a page's examples — so the context decides.
_COUNT_IN_CONTEXT: Final = re.compile(
    rf"\bother\s+{_WORD}\b|{_NUMBER}\s+(?:green\s+)?(?:verdicts|markers|outcomes|items)\b",
    re.IGNORECASE,
)
_PROPERTY_CONTEXT: Final = re.compile(
    r"propert|validator|not-implemented|not implemented|catalog|wedge|slug|no verdict"
    r"|not[- ]checked",
    re.IGNORECASE,
)


def property_counts(text: str) -> list[str]:
    """Every property count in ``text``, as matched; ``text`` should be folded to one line."""
    found = [match.group(0) for match in _COUNT.finditer(text)]
    for match in _COUNT_IN_CONTEXT.finditer(text):
        window = text[max(0, match.start() - 60) : match.end() + 60]
        if _PROPERTY_CONTEXT.search(window) and not any(match.group(0) in f for f in found):
            found.append(match.group(0))
    return found


def _numbers(phrase: str) -> set[str]:
    """The number words and numerals a matched phrase carries, lower-cased."""
    return {token.lower() for token in re.findall(rf"{_WORD}|\b\d+\b", phrase, re.IGNORECASE)}


def unkept(text: str) -> list[str]:
    """The property counts in ``text`` that carry a number :data:`KEPT_LITERALS` does not keep."""
    return [phrase for phrase in property_counts(text) if _numbers(phrase) - set(KEPT_LITERALS)]


# ── Reading a page ───────────────────────────────────────────────────────────────────────

_OUTPUT_DIRECTIVE: Final = re.compile(r"^\s*<!--\s*(?:gebra:output|gebra-quickstart:console)\b")
_FENCE: Final = re.compile(r"^\s*(`{3,}|~{3,})")
_COMMENT: Final = re.compile(r"<!--.*?-->", re.DOTALL)


def _fold(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _blank(text: str, start: int, stop: int) -> str:
    """``text`` with ``[start, stop)`` replaced by its own newlines, so line numbers hold."""
    return text[:start] + "\n" * text.count("\n", start, stop) + text[stop:]


def scannable(page: str) -> Iterator[tuple[int, str]]:
    """Each paragraph and fenced block a reader sees, folded, with its first line number.

    Output blocks are skipped (they are a run's own print); HTML comments and the generated
    property table are blanked before anything is read.
    """
    if property_table.BEGIN in page and property_table.END in page:
        start = page.index(property_table.BEGIN)
        page = _blank(page, start, page.index(property_table.END) + len(property_table.END))
    lines = page.split("\n")
    skipped: set[int] = set()
    for index, line in enumerate(lines):
        if not _OUTPUT_DIRECTIVE.match(line):
            continue
        opening = next((i for i in range(index + 1, len(lines)) if lines[i].strip()), index)
        fence = _FENCE.match(lines[opening])
        assert fence is not None, f"line {index + 1}: an output directive with no block under it"
        closing = _closing(lines, opening, fence.group(1))
        skipped.update(range(opening, closing + 1))
    for match in reversed(list(_COMMENT.finditer(page))):
        page = _blank(page, match.start(), match.end())
    lines = page.split("\n")

    block: list[str] = []
    first = 0
    index = 0
    while index < len(lines):
        line = lines[index]
        fence = _FENCE.match(line)
        if fence is not None:
            if block:
                yield first + 1, _fold(" ".join(block))
                block = []
            closing = _closing(lines, index, fence.group(1))
            if index not in skipped:
                yield index + 1, _fold(" ".join(lines[index + 1 : closing]))
            index = closing + 1
            continue
        if line.strip():
            if not block:
                first = index
            block.append(line)
        elif block:
            yield first + 1, _fold(" ".join(block))
            block = []
        index += 1
    if block:
        yield first + 1, _fold(" ".join(block))


def _closing(lines: list[str], opening: int, fence: str) -> int:
    """The index of the line closing the fence opened at ``opening`` (or the last line)."""
    for index in range(opening + 1, len(lines)):
        stripped = lines[index].strip()
        if len(stripped) >= len(fence) and not stripped.strip(fence[0]):
            return index
    return len(lines) - 1


def scanned_pages() -> list[Path]:
    """The README and every page under `docs/` outside :data:`EXCLUDED_TREES`."""
    pages = [REPO_ROOT / "README.md"]
    for path in sorted(DOCS.rglob("*.md")):
        relative = path.relative_to(REPO_ROOT).as_posix()
        if not relative.startswith(tuple(EXCLUDED_TREES)):
            pages.append(path)
    return pages


def string_literals(path: Path) -> Iterator[tuple[int, str]]:
    """Every string literal in a module that is not a docstring, folded, with its line.

    Docstrings are left to the pages that publish them: the frozen surfaces' docstrings are
    rendered into `docs/reference/api.md`, which is scanned as a page, and the rest are written
    for a reader of the source. Messages, report copy and plugin output are string literals.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            first = node.body[0] if node.body else None
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                docstrings.add(id(first.value))
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in docstrings
        ):
            yield node.lineno, _fold(node.value)


# ── The rule, over the tree ──────────────────────────────────────────────────────────────


def test_no_page_states_a_property_count() -> None:
    """Box 1: the README and the documentation point at the table instead of a number."""
    found = [
        f"{path.relative_to(REPO_ROOT)}:{line}: {phrase!r}"
        for path in scanned_pages()
        for line, text in scannable(path.read_text(encoding="utf-8"))
        for phrase in unkept(text)
    ]
    assert found == []


def test_no_user_facing_string_states_a_property_count() -> None:
    """Box 1, the source half: no message or rendered copy under `src/gebra/` counts either."""
    found = [
        f"{path.relative_to(REPO_ROOT)}:{line}: {phrase!r}"
        for path in sorted(SRC.rglob("*.py"))
        for line, text in string_literals(path)
        for phrase in unkept(text)
    ]
    assert found == []


def test_every_kept_literal_is_the_registrys_own() -> None:
    """The allowlist is the catalog's size and nothing else, read off the registry."""
    assert set(KEPT_LITERALS) == {NUMBER_WORDS[registry_counts().total]}
    assert all(reason.strip() for reason in KEPT_LITERALS.values())


def test_the_kept_literal_is_still_in_use() -> None:
    """An allowlist entry that admits nothing would be a licence nobody needs — so it is used."""
    used = {
        number
        for path in scanned_pages()
        for _, text in scannable(path.read_text(encoding="utf-8"))
        for phrase in property_counts(text)
        for number in _numbers(phrase)
    }
    assert set(KEPT_LITERALS) <= used


def test_the_excluded_trees_hold_documents_and_say_why() -> None:
    """An exclusion of nothing checks nothing; an exclusion without a reason explains nothing."""
    for tree, reason in EXCLUDED_TREES.items():
        assert reason.strip(), tree
        assert list((REPO_ROOT / tree).glob("*.md")), f"{tree} holds no document"


def test_the_scan_covers_the_pages_it_claims_to() -> None:
    scanned = {path.relative_to(REPO_ROOT).as_posix() for path in scanned_pages()}
    for page in (
        "README.md",
        "docs/index.md",
        "docs/ci/github-action.md",
        "docs/concepts/what-gebra-checks.md",
        "docs/reference/api.md",
        "docs/reference/architecture.md",
    ):
        assert page in scanned, page
    assert not [page for page in scanned if page.startswith(tuple(EXCLUDED_TREES))]


# ── The scan, armed: it sees what this card rewrote, and passes what it left ─────────────

#: Count phrasings the documentation carried before this card, as written there.
RETIRED_COUNT_PHRASINGS: Final[tuple[str, ...]] = (
    "Three of the five properties read the topology",
    "The five property validators — P-01, P-02, P-04, P-06, P-08 — and `verify()`",
    "The other eight catalog properties (P-03, P-05, P-07, P-09…P-13)",
    "The catalog holds thirteen properties. Five are implemented here; the other eight are out",
    "The eight properties outside the Phase-0 wedge get no pytest item",
    "the five properties read the edge under one ruled convention",
    "The defects target four of the five properties",
    "Five properties are printed because five are implemented in this release.",
    "Each of the five reports `pass`. That is a statement about the definition",
    "that one function becomes five items — one per property this release can answer",
    "The catalog holds thirteen properties and this release implements five.",
    "A green run is green on five.",
    "a default `pytest` cannot show five green ticks and stay silent about the rest",
    "What the five implemented validators check is",
    "Thirteen catalog properties are listed, five answered and eight carrying their deferral",
    "The other four properties pass, so this is the run's only finding.",
    "running the five validators over a real agent",
    "One page for each of the five properties this release implements",
    "Five are implemented — the wedge five — and the other eight answer through the same",
    "It does not describe the eight non-wedge properties beyond the registry contract",
    "`5 reported | 8 produced no verdict` is not a partial pass.",
    "the five this release implements with a verdict, the eight it does not",
    "Eight catalog properties answer `not-implemented: deferred-to-phase-1`",
    "**Thirteen outcomes, five verdicts.** The catalog holds thirteen properties",
    "Of the five properties this release implements, P-06 is the only one",
    "the field is populated from a fixed list of the three topology-consuming properties",
    "This is the last of the five per-validator explainers",
    "The result envelope, the condition-ID and property registry, the five wedge validators",
    "The eight properties outside the wedge five (SOW §8 put them out of Phase-0 scope).",
    "All five per-validator pages are written",
)

#: Counts of something other than properties, and kept catalog-size counts, from the pages.
NOT_PROPERTY_COUNTS: Final[tuple[str, ...]] = (
    "All three severities and all three claim classes appear in that transcript",
    (
        "The corpus's P-01 directory is where the conditions are pinned: three positives and "
        "four negatives. Running the validator over all seven at once is the shortest tour"
    ),
    "The catalog carries exactly three (§0.1)",
    "INTROSPECTION-SPEC §7.3 item 2; IR-SPEC §8",
    "the same structured not-implemented marker for P-12 `evolution-safety`",
    "the five verbs, every flag each one takes",
    "Sixteen public packages. The first five are frozen",
    "against each of the five seeded-defect variants of the travel-booking agent",
    "answers for all thirteen catalog properties",
    "a slug outside the thirteen-property catalog is refused at configure time",
    (
        "the run always answers the whole catalog, so `gebra_verification` still carries "
        "thirteen outcomes"
    ),
    "P-01 reports `path-map-target-undefined`, the gate fails on that FATAL",
)


#: Counts this card retired that the pattern cannot tell from other counts on the same pages —
#: "three reports" also counts a page's fixture reports ("eight reports in all"), and "the
#: export's eight" names no noun at all — so each is held absent as an exact needle instead.
RETIRED_COUNT_NEEDLES: Final[tuple[str, ...]] = (
    "three reports become diagnostics",
    "three other reports become diagnostics",
    "the export's eight",
    "Three passes that mean less",
)


@pytest.mark.parametrize("sentence", RETIRED_COUNT_PHRASINGS, ids=lambda s: s[:40])
def test_the_scan_sees_each_count_this_card_retired(sentence: str) -> None:
    assert unkept(sentence), sentence


def test_no_page_carries_a_retired_count_the_pattern_cannot_see() -> None:
    found = [
        f"{path.relative_to(REPO_ROOT)}: {needle!r}"
        for path in scanned_pages()
        for needle in RETIRED_COUNT_NEEDLES
        if needle in _fold(path.read_text(encoding="utf-8"))
    ]
    assert found == []


@pytest.mark.parametrize("sentence", NOT_PROPERTY_COUNTS, ids=lambda s: s[:40])
def test_the_scan_passes_what_is_not_a_property_count(sentence: str) -> None:
    assert unkept(sentence) == [], sentence


def test_the_scan_reads_prose_and_example_code_and_skips_what_a_run_printed() -> None:
    """Output blocks, comments and the table are skipped; prose and example code are read."""
    lines = [
        "Five properties are checked here,",
        "and the other eight are not.",
        "",
        "<!-- gebra:example id=x -->",
        "```python",
        "# the eight properties this release does not check",
        "print(1)",
        "```",
        "",
        "<!-- gebra:output id=x -->",
        "```text",
        "5 reported | 8 produced no verdict",
        "```",
        "",
        "<!-- eight properties, in a comment -->",
        property_table.BEGIN,
        "| eight properties |",
        property_table.END,
    ]
    page = "\n".join(lines)
    hits = [(line, phrase) for line, text in scannable(page) for phrase in unkept(text)]
    assert [line for line, _ in hits] == [1, 1, 5]


def test_a_string_literal_is_scanned_and_a_docstring_is_not(tmp_path: Path) -> None:
    module = tmp_path / "copy.py"
    module.write_text(
        '"""The eight properties outside the wedge — a docstring."""\n'
        'MESSAGE = "the other eight come back as not-implemented markers"\n',
        encoding="utf-8",
    )
    assert [(line, unkept(text)) for line, text in string_literals(module)] == [
        (2, ["eight come back", "other eight"])
    ]


# ── The copy that named Phase 0 as the present (box 5) ───────────────────────────────────

#: The three phrases PD-063 §2.3 and PD-072 §3 found on published pages, each naming Phase 0 as
#: the present. Exact needles, matched with line breaks folded.
PHASE_0_PRESENT_PHRASES: Final[tuple[str, ...]] = (
    "The eight properties outside the Phase-0 wedge",
    "out of scope for this phase (SOW §8)",
    "outside Phase-0 scope (SOW §8)",
)

#: The pages that carried them, which now carry the charter's copy instead.
PAGES_THAT_NAMED_PHASE_0: Final[tuple[str, ...]] = (
    "docs/ci/github-action.md",
    "docs/concepts/what-gebra-checks.md",
    "docs/tutorials/verify-and-interpret.md",
)


def _documentation_pages() -> list[Path]:
    """Every page under `docs/` outside the two internal trees — box 5's scope."""
    return [path for path in scanned_pages() if path.is_relative_to(DOCS)]


def test_no_page_still_names_phase_0_as_the_present() -> None:
    """The three phrases, and every phrase the registry tests retired from `src/`, are gone.

    `docs/specs/` is CLI-12's (the specifications moved at `report_format` 1.4) and
    `docs/governance/` keeps the SOW §8 citation PD-072 §1 reads the acceptance checklist
    against, so both are outside this scan — :data:`EXCLUDED_TREES` says so.
    """
    found = [
        f"{path.relative_to(REPO_ROOT)}: {phrase!r}"
        for path in _documentation_pages()
        for phrase in (*PHASE_0_PRESENT_PHRASES, *RETIRED_PHRASES)
        if phrase in _fold(path.read_text(encoding="utf-8"))
    ]
    assert found == []


def test_the_pages_that_named_phase_0_carry_the_charters_copy() -> None:
    """Each of the three says what DEC-42 §3.1 rules a marker says: *has no validator in this
    release*."""
    for page in PAGES_THAT_NAMED_PHASE_0:
        text = _fold(_COMMENT.sub(" ", (REPO_ROOT / page).read_text(encoding="utf-8")))
        assert DEFERRED_READING in text.replace("*", ""), page


def test_the_retired_scan_sees_the_three_phrases_folded() -> None:
    """Arms the scan above on the sentences as the pages wrapped them."""
    wrapped = (
        "never more than that. The eight properties outside the Phase-0 wedge get no pytest\n"
        "item; the other eight are out of\nscope for this phase (SOW §8) and are answered;\n"
        "the other eight are outside Phase-0 scope (SOW §8) and answer with a marker"
    )
    assert [phrase for phrase in PHASE_0_PRESENT_PHRASES if phrase in _fold(wrapped)] == list(
        PHASE_0_PRESENT_PHRASES
    )
