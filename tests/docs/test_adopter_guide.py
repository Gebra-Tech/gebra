"""``docs/guides/adopter-guide.md`` held to its card (DOC-22) and to the code it describes.

The guide takes five shapes an existing agent uses — a loop bounded only by the recursion limit,
a compiled graph mounted as a node, a key a ``Send`` hands its target, a router keyed by an
``Enum``, an approval gate in front of a write — and shows, for each, what gebra reads and what
to write. Its transcripts are held by the executable-examples harness; this module holds what a
transcript cannot:

* the page is the five sections the card names, in order, each carrying at least one executed
  example, and no code block on it is anything but an executed example or that example's output;
* the vocabulary its prose quotes — warning, disclosure, refusal and witness-note codes, the
  call's error reasons — is the library's own, read off the enums rather than transcribed;
* the enum section's example mirrors the ``AgentDecision`` shape with nothing imported from the
  toolkit that uses it;
* the gate section states the pattern's three conditions and its "what a pass does not show"
  box names both failure modes, beside the plain sentence that gebra does not check gate
  ordering as a rule of its own;
* P-02's wording stays at witness presence, and the phrase lint finds nothing on the page;
* the pages the card names link here, and the two page lists name it.

The module reads Markdown and the library's enums. It imports no workflow and runs no node
(WA-07); the examples themselves run under the guard in ``tools/docs_examples.py``.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

import pytest

from gebra.annotations import ContractErrorReason
from gebra.extraction import (
    ExtractionDisclosureCode,
    ExtractionErrorReason,
    ExtractionWarningCode,
)
from gebra.verify import CONDITION_IDS
from tools.docs_examples import FENCE_RE, closing_fence, parse_markdown
from tools.honest_claims_lint import load_phrases, scan

REPO_ROOT: Final = Path(__file__).resolve().parents[2]
DOCS: Final = REPO_ROOT / "docs"
PAGE: Final = DOCS / "guides" / "adopter-guide.md"
RELATIVE: Final = PAGE.relative_to(REPO_ROOT).as_posix()

#: The card's five sections, in its order, with the executed examples each carries.
SECTIONS: Final[tuple[tuple[str, tuple[str, ...]], ...]] = (
    (
        "A loop bounded only by the recursion limit",
        ("a-loop-with-no-declared-bound", "the-runtime-table"),
    ),
    ("A compiled graph mounted as a node", ("a-mounted-graph-is-disclosed",)),
    ("A key a `Send` hands its target", ("a-payload-read",)),
    ("A router keyed by an `Enum`", ("an-enum-keyed-router", "enum-forms-still-refused")),
    ("An approval gate in front of a write", ("a-gate-as-a-token",)),
)

#: The sentence the gate section states plainly, and the box repeats (PD-070 §2 B).
GATE_ORDERING: Final = "gebra does not check gate ordering as a rule of its own"


@pytest.fixture(scope="module")
def text() -> str:
    return PAGE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def prose(text: str) -> str:
    """The page with every run of whitespace folded, so a pin survives re-wrapping."""
    return re.sub(r"\s+", " ", text)


def _sections(text: str) -> dict[str, str]:
    """Each ``## `` heading's text, keyed by the heading."""
    parts = re.split(r"^## (.+)$", text, flags=re.MULTILINE)
    return {heading.strip(): body for heading, body in zip(parts[1::2], parts[2::2], strict=True)}


def test_the_page_is_the_five_sections_in_the_cards_order(text: str) -> None:
    headings = list(_sections(text))

    assert headings == [heading for heading, _ in SECTIONS] + ["Where this page is checked"]


def test_each_section_carries_its_executed_examples(text: str) -> None:
    sections = _sections(text)
    for heading, example_ids in SECTIONS:
        declared = [
            example.example_id for example in parse_markdown(sections[heading], path=RELATIVE)
        ]
        assert declared == list(example_ids), heading


def test_every_code_block_on_the_page_is_an_executed_example_or_its_output(text: str) -> None:
    """The card's first box: every example a CI-executed block, so no code is shown unrun."""
    examples = parse_markdown(text, path=RELATIVE)
    marked = {example.line for example in examples} | {
        example.output_line for example in examples if example.output_line is not None
    }
    lines = text.splitlines()
    opened = []
    index = 0
    while index < len(lines):
        fence = FENCE_RE.match(lines[index])
        if fence is not None and lines[index].startswith(fence.group("fence")):
            opened.append(index + 1)
            index = closing_fence(lines, index, fence.group("fence")) + 1
            continue
        index += 1

    assert opened, "the page shows no code"
    assert set(opened) == marked
    assert all(example.output_line is not None for example in examples)


def test_every_example_ends_by_printing_an_empty_ledger(text: str) -> None:
    """Each module the page writes keeps a `TRIPPED` ledger, and its transcript shows it empty."""
    for example in parse_markdown(text, path=RELATIVE):
        assert re.search(r'print\("nodes run:", \w+\.TRIPPED\)\n\Z', example.code), example.name
        assert example.expected_output.rstrip("\n").endswith("nodes run: []"), example.name


def test_the_vocabulary_the_prose_quotes_is_the_librarys_own(prose: str) -> None:
    """Every code the page names is read off its enum, so a renamed member fails here."""
    quoted = {
        ExtractionDisclosureCode.SUBGRAPH_READ_AS_ONE_NODE.value,
        ExtractionDisclosureCode.RECURSION_LIMIT_BOUND_WITHOUT_JUSTIFICATION.value,
        ExtractionWarningCode.ANNOTATION_CONFLICT.value,
        ExtractionWarningCode.ANNOTATION_INVALID.value,
        ContractErrorReason.DUPLICATE_SLOT.value,
        ContractErrorReason.SLOT_VALUE_INVALID.value,
        "cycle-without-termination-witness",
        "read-key-never-written-on-path",
    }
    for code in sorted(quoted):
        assert f"`{code}`" in prose, code
    assert {"cycle-without-termination-witness", "read-key-never-written-on-path"} <= set(
        CONDITION_IDS
    )


def test_the_refusals_the_enum_section_prints_are_extraction_reasons(text: str) -> None:
    [example] = [
        item
        for item in parse_markdown(text, path=RELATIVE)
        if item.example_id == "enum-forms-still-refused"
    ]
    printed = set(re.findall(r"refused: ([a-z-]+)$", example.expected_output, re.MULTILINE))

    assert printed == {
        ExtractionErrorReason.CONSTRUCT_NOT_CARRIED.value,
        ExtractionErrorReason.LABEL_COLLISION.value,
        ExtractionErrorReason.UNREPRESENTABLE_NODE_ID.value,
    }


def test_the_enum_example_mirrors_the_agent_decision_shape_and_imports_no_toolkit(
    text: str,
) -> None:
    [example] = [
        item
        for item in parse_markdown(text, path=RELATIVE)
        if item.example_id == "an-enum-keyed-router"
    ]

    assert "class AgentDecision(Enum):" in example.code
    assert 'TOOL = "tool"' in example.code
    assert 'END = "finished"' in example.code
    assert "react_agent.build(AgentDecision.TOOL, AgentDecision.END)" in example.code
    assert "path_map: {'tool': 'tool', 'finished': 'END'}" in example.expected_output
    for example in parse_markdown(text, path=RELATIVE):
        assert not re.search(r"\bnvidia\b|\bnat\b", example.code, re.IGNORECASE), example.name


def test_the_gate_section_states_the_pattern_and_what_a_pass_does_not_show(text: str) -> None:
    section = re.sub(r"\s+", " ", _sections(text)["An approval gate in front of a write"])

    assert section.count(GATE_ORDERING) == 2
    for condition in (
        "1. **The token is not a graph input.**",
        "2. **The guarded write declares the token as a read**",
        "3. **The token is written on the allow branch alone.**",
    ):
        assert condition in section
    box = section[section.index('!!! warning "What a pass does not show"') :]
    assert "**The token written before the gate.**" in box
    assert "**The proposal changed after the allow branch.**" in box
    assert GATE_ORDERING in box


def test_the_p02_wording_stays_at_witness_presence(prose: str) -> None:
    """Form (b) is a global step budget, never a bound on one loop (TERMINATION-WITNESS-SPEC §2.2)."""
    assert "A declared limit is a recorded bound, not a statement that the loop halts" in prose
    assert "recorded bound for the loop" not in prose
    assert "P-02 records the number and the justification and evaluates neither" in prose
    assert "The declaration records that limit; it does not set the one a run is given." in prose


def test_the_page_never_offers_a_counter_guard_it_cannot_extract(prose: str) -> None:
    """A live graph's router `condition` is its name, never its body, so form (a) is not offered."""
    assert "extraction fills that slot with the router's name rather than its body" in prose
    assert "a counter guard or a loop variant on a loop takes it off the list" not in prose


def test_the_phrase_lint_finds_nothing_on_the_page() -> None:
    """The phrase lint, on this page specifically, on every run."""
    phrases = load_phrases(REPO_ROOT / "tools" / "honest-claims-phrases.txt")
    report = scan(REPO_ROOT, phrases, include=(RELATIVE,), exclude=())

    assert report.ok, [f"{v.path}:{v.line_no}: {v.detail}" for v in report.violations]


def test_the_release_note_names_what_is_new_since_the_published_release(prose: str) -> None:
    """The first four sections' surfaces are not in `gebra 0.1.1`; the page says so plainly.

    Worded of what a reader has installed rather than of "today", so it stays true after a later
    release: an installed `0.1.1` still has none of them. Measured when the page landed — the
    fifth section's example printed its transcript byte for byte against the published `0.1.1`,
    and the first section's stopped at `gebra.recursion_limit`, which `0.1.1` does not export.
    """
    assert "The first four sections use surfaces merged after `gebra 0.1.1`" in prose
    assert "An installed `0.1.1` has none of them" in prose
    assert "The fifth section uses only what `0.1.1` already has." in prose


@pytest.mark.parametrize(
    "page",
    [
        "validators/p02-termination-witness.md",
        "validators/p04-dataflow-completeness.md",
        "guides/pytest-plugin-and-ci-gating.md",
        "index.md",
    ],
)
def test_the_pages_the_card_names_link_here(page: str) -> None:
    """The P-02 and P-04 pages and the CI-gating guide (the card's third box), and the home page."""
    linking = (DOCS / page).read_text(encoding="utf-8")
    pattern = r"\]\((?:\.\./)?(?:guides/)?adopter-guide\.md(?:#[a-z0-9-]+)?\)"

    assert re.search(pattern, linking), f"{page} does not link to the guide"


def test_the_readme_documentation_list_names_the_guide() -> None:
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    documentation = readme[readme.index("## Documentation") :]

    assert "- [Adopter guide](docs/guides/adopter-guide.md)" in documentation
