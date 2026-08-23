"""The conformance checker's own suite — ``tools/mermaid_check.py``.

The checker is what makes the CLI-06 acceptance box mean what it says ("`display` emits
valid Mermaid … parse-checked"), so it gets the same two-direction discipline
``tools/json_schema.py``'s suite established: every licensed construct is shown to pass,
every refusal is shown to fire, and a negative control shows the checker refusing bad
input outright — a validator never observed to refuse anything demonstrates nothing.
"""

from __future__ import annotations

import pytest

from tools.mermaid_check import MermaidCheckError, check_mermaid, mermaid_problems

#: A minimal artifact using every licensed construct: comments, the header, both node
#: shapes, all three arrow forms, the legend subgraph, classDef/class/linkStyle.
COMPLETE = """\
%% a header comment
flowchart TD

  START(["START"])
  n_a["a"]
  n_b["b [F1]"]
  END(["END"])

  START --> n_a
  n_a -->|"go [F1]"| n_b
  n_a -.-> n_b
  n_b --> END

  subgraph gebra_findings["gebra findings overlay"]
    f_1["F1 error [defensible] - node b"]
  end

  classDef gebra_error fill:#fecaca,stroke:#dc2626,color:#7f1d1d
  classDef gebra_sentinel fill:#f3f4f6,stroke:#374151,color:#111827
  classDef gebra_unresolved fill:#f9fafb,stroke:#6b7280,stroke-dasharray: 4 3,color:#374151
  class n_b,f_1 gebra_error
  class START,END gebra_sentinel
  linkStyle 1 stroke:#dc2626,stroke-width:2px
"""


def test_the_complete_artifact_passes() -> None:
    assert mermaid_problems(COMPLETE) == []


def test_check_mermaid_raises_with_every_problem() -> None:
    """The negative control: the checker can fail, and it reports all reasons at once."""
    bad = 'flowchart TD\n\n  n_a["a"]\n  n_a --> n_ghost\n  linkStyle 9 stroke:#dc2626\n'
    with pytest.raises(MermaidCheckError) as excinfo:
        check_mermaid(bad)
    assert len(excinfo.value.problems) >= 2


def _problems_of(body: str) -> list[str]:
    """``body`` under the standard preamble, so cases state only what they test."""
    return mermaid_problems(f'flowchart TD\n\n  n_a["a"]\n  n_b["b"]\n{body}')


@pytest.mark.parametrize(
    ("line", "fragment"),
    [
        ("  n_a --> n_ghost\n", "auto-vivify"),
        ("  n_a -> n_b\n", "not a construct"),
        ("  n_a ==> n_b\n", "not a construct"),
        ("  n_a --> n_b --> n_a\n", "not a construct"),
        ('  n_a[)"x"]\n', "not a construct"),
        ('  end["end"]\n', "keyword"),
        ('  n_a["raw " quote"]\n', "not a construct"),
        ('  n_c["angle < bracket"]\n', "raw '<'"),
        ('  n_c["hash # sign"]\n', "raw '#'"),
        ('  n_c["ok #35; then # bad"]\n', "raw '#'"),
        ("  class n_ghost gebra_error\n", "not a defined node id"),
        ("  class n_a gebra_missing\n", "no classDef"),
        ("  linkStyle 0 stroke:#dc2626\n", "names a link the drawing does not have"),
        ("  classDef gebra_x background:#ffffff\n", "outside the §5 vocabulary"),
        ("  classDef gebra_x fill:#zzzzzz\n", "does not match the §5 form"),
        ("  classDef gebra_x fill\n", "not key:value"),
        ("%%{init: {}}%%\n", "directive blocks"),
        ('  subgraph legend["l"]\n    subgraph inner["i"]\n  end\n  end\n', "inside the legend"),
        ('n_c["indent"]\n', "indented 0"),
    ],
)
def test_constructs_outside_the_subset_are_refused(line: str, fragment: str) -> None:
    problems = _problems_of(line)
    assert problems, f"{line!r} passed but is outside the subset"
    assert any(fragment in problem for problem in problems), problems


def test_a_duplicate_node_definition_is_refused() -> None:
    problems = _problems_of('  n_a["again"]\n')
    assert any("defined twice" in problem for problem in problems)


def test_the_header_must_come_first() -> None:
    problems = mermaid_problems('  n_a["a"]\nflowchart TD\n')
    assert any("expected 'flowchart TD'" in problem for problem in problems)


def test_a_missing_header_is_reported() -> None:
    problems = mermaid_problems("%% only a comment\n")
    assert any("contains no 'flowchart TD'" in problem for problem in problems)


def test_an_unclosed_subgraph_is_reported() -> None:
    problems = mermaid_problems('flowchart TD\n\n  subgraph g["g"]\n    f_1["x"]\n')
    assert any("never closed" in problem for problem in problems)


def test_a_missing_trailing_newline_is_reported() -> None:
    problems = mermaid_problems("flowchart TD")
    assert problems == ["the artifact must end with a newline (guide §1.4)"]


def test_edges_may_reference_nodes_defined_later() -> None:
    """Definition order is the emitter's §3.2 rule, not the checker's: Mermaid resolves
    references document-wide, and so does the two-pass collection."""
    text = 'flowchart TD\n\n  n_a --> n_b\n  n_a["a"]\n  n_b["b"]\n'
    assert mermaid_problems(text) == []


def test_decimal_entities_are_the_licensed_escape() -> None:
    text = 'flowchart TD\n\n  n_a["quote #34; hash #35; lt #60; gt #62; nl #10;"]\n'
    assert mermaid_problems(text) == []


def test_problems_carry_line_numbers() -> None:
    problems = _problems_of("  n_a --> n_ghost\n")
    assert problems and problems[0].startswith("line 5: ")
