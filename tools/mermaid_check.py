"""A strict validator for the Mermaid flowchart subset DIAGRAM-STYLE-GUIDE licenses.

This is the conformance checker the guide's §9 names. It exists for the same reason
``tools/json_schema.py`` does: an emission checked by a validator that silently skips what
it does not understand is not checked at all. So the posture is **refusal** — every line
must match a construct the guide licenses, every reference must resolve, and anything else
is a problem, never a pass-through. That makes the checker deliberately stricter than
Mermaid itself where Mermaid is forgiving in ways that would hide emitter defects:

* Mermaid **auto-vivifies** an undefined node id used in an edge (a typo'd id silently
  becomes a new unlabeled vertex in the render); here an edge, ``class`` or ``subgraph``
  member naming an id no node definition introduced is a problem.
* Mermaid accepts many arrow, shape and label forms; here exactly the guide's forms parse
  (§2–§5: rectangle and stadium definitions with double-quoted labels, ``-->`` and
  ``-.->`` arrows with optional ``|"label"|`` labels, one non-nested ``subgraph``,
  ``classDef``/``class``/``linkStyle`` with the §5 declaration vocabulary).
* A lowercase Mermaid keyword used as a node id breaks real renderers (``end`` is the
  documented footgun); here it is refused by name.

The checker is line-based two-pass: pass one collects definitions (node ids, link count,
``classDef`` names) so references may precede definitions the way Mermaid allows; pass two
validates every line and every reference. Problems carry 1-based line numbers.

Dependency-free, pure text: nothing here imports langgraph, executes anything, or opens a
socket (WA-07).
"""

from __future__ import annotations

import re
from typing import Final

__all__ = ["MermaidCheckError", "check_mermaid", "mermaid_problems"]

#: The flowchart header the guide's §1 fixes — the one drawing type this subset covers.
HEADER: Final = "flowchart TD"

#: Lowercase words Mermaid's flowchart parser treats specially; refused as element ids.
KEYWORDS: Final = frozenset(
    {
        "class",
        "classDef",
        "click",
        "default",
        "direction",
        "end",
        "flowchart",
        "graph",
        "linkStyle",
        "style",
        "subgraph",
    }
)

_ID: Final = r"[A-Za-z][A-Za-z0-9_]*"

#: A double-quoted label body: anything but a raw quote, checked further by ``_label_problem``.
_LABEL: Final = r'"([^"]*)"'

_NODE_RECT: Final = re.compile(rf"^({_ID})\[{_LABEL}\]$")
_NODE_STADIUM: Final = re.compile(rf"^({_ID})\(\[{_LABEL}\]\)$")
_EDGE: Final = re.compile(rf"^({_ID}) (-->|-\.->)(?:\|{_LABEL}\|)? ({_ID})$")
_SUBGRAPH: Final = re.compile(rf"^subgraph ({_ID})\[{_LABEL}\]$")
_CLASSDEF: Final = re.compile(rf"^classDef ({_ID}) (.+)$")
_CLASS: Final = re.compile(rf"^class ({_ID}(?:,{_ID})*) ({_ID})$")
_LINKSTYLE: Final = re.compile(r"^linkStyle (0|[1-9][0-9]*) (.+)$")

#: The §5 style-declaration vocabulary: key → value pattern.
_STYLE_VALUES: Final[dict[str, re.Pattern[str]]] = {
    "fill": re.compile(r"^#[0-9a-f]{6}$"),
    "stroke": re.compile(r"^#[0-9a-f]{6}$"),
    "color": re.compile(r"^#[0-9a-f]{6}$"),
    "stroke-width": re.compile(r"^[1-9][0-9]*px$"),
    "stroke-dasharray": re.compile(r"^ [1-9][0-9]*( [1-9][0-9]*)*$"),
}

#: A Mermaid decimal entity — the only ``#`` use the guide's §2.4 escape rules produce.
_ENTITY: Final = re.compile(r"#[0-9]+;")


class MermaidCheckError(ValueError):
    """The text is not in the licensed subset; ``problems`` carries every reason found."""

    def __init__(self, problems: list[str]) -> None:
        super().__init__("; ".join(problems))
        self.problems: Final[tuple[str, ...]] = tuple(problems)


def _label_problem(label: str) -> str | None:
    """Why a quoted label body is outside §2.4's escape rules, or ``None``.

    The guide escapes ``#``, ``"``, ``<``, ``>`` and control characters to decimal
    entities; a raw quote cannot reach here (the tokenizer would refuse the line), so the
    checks are the remaining four plus a well-formedness rule for ``#``.
    """
    for index, char in enumerate(label):
        if char in "<>":
            return f"raw {char!r} in label (escape to a decimal entity, guide §2.4)"
        if ord(char) < 0x20 or ord(char) == 0x7F:
            return f"raw control character U+{ord(char):04X} in label (guide §2.4)"
        if char == "#" and not _ENTITY.match(label, index):
            return "raw '#' in label: '#' may only begin a decimal entity (guide §2.4)"
    return None


def _style_problem(declarations: str, *, keys: frozenset[str]) -> str | None:
    """Why a comma-separated style declaration list is outside §5, or ``None``."""
    for declaration in declarations.split(","):
        key, colon, value = declaration.partition(":")
        if not colon:
            return f"style declaration {declaration!r} is not key:value"
        pattern = _STYLE_VALUES.get(key)
        if key not in keys or pattern is None:
            return f"style key {key!r} is outside the §5 vocabulary for this directive"
        if not pattern.match(value):
            return f"style value {value!r} does not match the §5 form for {key!r}"
    return None


_NODE_STYLE_KEYS: Final = frozenset({"fill", "stroke", "color", "stroke-dasharray"})
_LINK_STYLE_KEYS: Final = frozenset({"stroke", "stroke-width"})


def _collect(lines: list[str]) -> tuple[set[str], set[str], int]:
    """Pass one: defined node ids, classDef names, and the link count."""
    node_ids: set[str] = set()
    class_names: set[str] = set()
    links = 0
    for raw in lines:
        line = raw.strip()
        for pattern in (_NODE_RECT, _NODE_STADIUM):
            match = pattern.match(line)
            if match:
                node_ids.add(match.group(1))
        if _EDGE.match(line):
            links += 1
        match = _CLASSDEF.match(line)
        if match:
            class_names.add(match.group(1))
    return node_ids, class_names, links


def mermaid_problems(text: str) -> list[str]:
    """Every way ``text`` leaves the licensed subset, each with its 1-based line number.

    An empty list is the pass: every line parsed as a licensed construct and every
    reference resolved.
    """
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()  # the guide's §1.4 trailing newline
    else:
        return ["the artifact must end with a newline (guide §1.4)"]
    node_ids, class_names, total_links = _collect(lines)
    problems: list[str] = []
    defined: set[str] = set()
    header_seen = False
    in_subgraph = False

    def problem(number: int, message: str) -> None:
        problems.append(f"line {number}: {message}")

    def check_id(number: int, element_id: str) -> None:
        if element_id in KEYWORDS:
            problem(number, f"id {element_id!r} is a Mermaid keyword (guide §2.3)")

    def check_label(number: int, label: str) -> None:
        reason = _label_problem(label)
        if reason is not None:
            problem(number, reason)

    for number, raw in enumerate(lines, start=1):
        stripped = raw.strip()
        if stripped == "":
            continue
        if stripped.startswith("%%"):
            if stripped.startswith("%%{"):
                problem(number, "directive blocks ('%%{') are outside the licensed subset")
            continue
        if not header_seen:
            if stripped == HEADER and raw == HEADER:
                header_seen = True
                continue
            problem(number, f"expected {HEADER!r} before any drawing line (guide §1.1)")
            header_seen = True  # report the header once, then keep reading
        indent = len(raw) - len(raw.lstrip(" "))
        expected_indent = 4 if in_subgraph and stripped != "end" else 2
        node_match = _NODE_RECT.match(stripped) or _NODE_STADIUM.match(stripped)
        if node_match:
            node_id, label = node_match.group(1), node_match.group(2)
            check_id(number, node_id)
            check_label(number, label)
            if node_id in defined:
                problem(number, f"node {node_id!r} is defined twice")
            defined.add(node_id)
            if indent != expected_indent:
                problem(number, f"node definition indented {indent}, expected {expected_indent}")
            continue
        if in_subgraph:
            if stripped == "end":
                in_subgraph = False
                if indent != 2:
                    problem(number, f"'end' indented {indent}, expected 2")
                continue
            problem(number, "only node definitions may appear inside the legend subgraph")
            continue
        if indent != 2:
            problem(number, f"line indented {indent}, expected 2 (guide §1.4)")
        edge_match = _EDGE.match(stripped)
        if edge_match:
            source, _, label, target = edge_match.groups()
            for endpoint in (source, target):
                check_id(number, endpoint)
                if endpoint not in node_ids:
                    problem(
                        number,
                        f"edge endpoint {endpoint!r} is not a defined node id — Mermaid "
                        "would silently auto-vivify it (guide §9)",
                    )
            if label is not None:
                check_label(number, label)
            continue
        subgraph_match = _SUBGRAPH.match(stripped)
        if subgraph_match:
            subgraph_id, label = subgraph_match.groups()
            check_id(number, subgraph_id)
            check_label(number, label)
            if subgraph_id in node_ids:
                problem(number, f"subgraph id {subgraph_id!r} collides with a node id")
            in_subgraph = True
            continue
        classdef_match = _CLASSDEF.match(stripped)
        if classdef_match:
            name, declarations = classdef_match.groups()
            check_id(number, name)
            reason = _style_problem(declarations, keys=_NODE_STYLE_KEYS)
            if reason is not None:
                problem(number, reason)
            continue
        class_match = _CLASS.match(stripped)
        if class_match:
            members, name = class_match.groups()
            for member in members.split(","):
                if member not in node_ids:
                    problem(number, f"class member {member!r} is not a defined node id")
            if name not in class_names:
                problem(number, f"class {name!r} has no classDef")
            continue
        linkstyle_match = _LINKSTYLE.match(stripped)
        if linkstyle_match:
            index_text, declarations = linkstyle_match.groups()
            if int(index_text) >= total_links:
                problem(
                    number,
                    f"linkStyle {index_text} names a link the drawing does not have "
                    f"({total_links} links)",
                )
            reason = _style_problem(declarations, keys=_LINK_STYLE_KEYS)
            if reason is not None:
                problem(number, reason)
            continue
        problem(number, f"{stripped!r} is not a construct the licensed subset contains")

    if not header_seen:
        problems.append(f"the artifact contains no {HEADER!r} line")
    if in_subgraph:
        problems.append("a subgraph is never closed ('end' missing)")
    return problems


def check_mermaid(text: str) -> None:
    """Validate ``text`` against the licensed subset.

    Raises:
        MermaidCheckError: with every problem found, when the text is outside the subset.
    """
    problems = mermaid_problems(text)
    if problems:
        raise MermaidCheckError(problems)
