"""The API reference, built from the docstrings of the frozen surfaces (card DOC-17).

Three freeze records fix a Python surface each: `docs/governance/IR-MODELS-FREEZE.md`
(card IR-06, `gebra.ir`), `docs/governance/VALIDATOR-API-FREEZE.md` (VAL-12,
`gebra.verify`) and `docs/governance/EXTRACTOR-API-FREEZE.md` (EX-15, the top-level
`gebra` entry points plus `gebra.extraction` and `gebra.annotations`). This module renders
those surfaces into ``docs/reference/api.md`` out of the sources' own docstrings, and
checks in CI that the committed page is what a fresh render produces and that no public
symbol on those surfaces is undocumented.

**Why a generator rather than an autodoc plugin.** PD-051 ruled the site's toolchain —
MkDocs, stock theme, no plugins, one pinned pure-Python distribution — and left DOC-17 the
choice of whether to add `mkdocstrings`. The choice recorded in PD-053 is this file, for
three reasons the plugin route does not offer. It keeps the docs toolchain at one pinned
dependency, so the site still builds from `docs/requirements.txt` alone. It is **static**:
the reader below is `ast` over `src/`, importing nothing and executing nothing, so the
reference can be rendered without the substrate installed and cannot itself reach a node
body, a model or a socket (WA-07). And the same static model answers the card's second
acceptance box — :func:`undocumented` reports a public symbol with neither a docstring nor
a ``#:`` comment, which is a build failure rather than a silent hole in the page.

**What "built from the docstrings" means here, exactly.** Every entry's prose is the
defining docstring's own, with Sphinx roles rewritten to Markdown code spans and nothing
paraphrased — so the way to change the page is to change the docstring. What is rendered
differs by kind, and the split is deliberate. A **callable's** contract is its signature
plus the ``Args:``/``Returns:``/``Raises:``/``Attributes:`` sections it declares, so those
are rendered and the free prose after them — the design rationale most of them carry for
whoever maintains the code — is not. A **type's** contract is prose: that a ``GateOutcome``'s
word and its exit code never disagree, that a ``Location`` union resolves left to right. So
types, models, enumerations and constants carry their whole docstring, and their per-field
``#:`` comments with it.

Usage::

    python tools/api_reference.py --report         # counts, per surface
    python tools/api_reference.py --undocumented   # public symbols with no docstring
    python tools/api_reference.py --write          # regenerate the page
    python tools/api_reference.py --check          # both gates; exit 1 on either
"""

from __future__ import annotations

import argparse
import ast
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
from dataclasses import dataclass
from functools import cache
from itertools import pairwise
from pathlib import Path
from typing import Final

#: The repository root — this file lives in ``tools/``.
REPO_ROOT: Final = Path(__file__).resolve().parents[1]
SRC: Final = REPO_ROOT / "src"
PAGE: Final = REPO_ROOT / "docs" / "reference" / "api.md"

#: Where a module's source is read from on the forge, for the per-module links. Pinned to
#: ``main`` for the same reason ``mkdocs.yml``'s ``edit_uri`` is: the site is built from the
#: default branch. No line numbers — a link that moved every time an unrelated line above it
#: moved would make this page churn on edits it does not describe.
SOURCE_URL: Final = "https://github.com/Gebra-Tech/gebra/blob/main"


@dataclass(frozen=True)
class Surface:
    """One frozen surface: the package, and the record that froze it."""

    module: str
    card: str
    record: str
    section: str
    scope: str


#: The frozen surfaces, in the order an integrator meets them: the entry points first, then
#: what extraction produces, then what verifies it, then the two packages behind the entry
#: points. ``card``/``record``/``section`` name the freeze record that fixes each one, and
#: `tests/docs/test_api_reference.py` holds every one of those pointers to the record itself.
SURFACES: Final[tuple[Surface, ...]] = (
    Surface(
        module="gebra",
        card="EX-15",
        record="docs/governance/EXTRACTOR-API-FREEZE.md",
        section="§1.1",
        scope=(
            "The ten names the specifications spell at the top level. Each is resolved "
            "lazily out of the subpackage that defines it (PEP 562), so neither the "
            "extractor nor the substrate is in the closure of a bare `import gebra`."
        ),
    ),
    Surface(
        module="gebra.ir",
        card="IR-06",
        record="docs/governance/IR-MODELS-FREEZE.md",
        section="§1",
        scope=(
            "The IR document: its models, the node-identity grammar, the canonical form "
            "and the content hash, and the YAML/JSON loaders. This is the surface every "
            "other package in the pipeline reads and writes."
        ),
    ),
    Surface(
        module="gebra.verify",
        card="VAL-12",
        record="docs/governance/VALIDATOR-API-FREEZE.md",
        section="§1",
        scope=(
            "The result envelope, the condition-ID and property registry, the five wedge "
            "validators and the run-level aggregation. A finding is a model here, not a "
            "string: the same model the golden harness asserts on."
        ),
    ),
    Surface(
        module="gebra.extraction",
        card="EX-15",
        record="docs/governance/EXTRACTOR-API-FREEZE.md",
        section="§1.2",
        scope=(
            "What `gebra.extract()` is made of: the dispatch registry, the provenance "
            "envelope, the warnings taxonomy, the annotation-resolution bridge and the "
            "first-extract version check."
        ),
    ),
    Surface(
        module="gebra.annotations",
        card="EX-15",
        record="docs/governance/EXTRACTOR-API-FREEZE.md",
        section="§1.3",
        scope=(
            "How a node's contract is declared and resolved: the decorator family, the "
            "`gebra.toml` sidecar, shallow inference, and the four-tier precedence — "
            "decorator, tool-carried, sidecar, inference — that settles, slot by slot, "
            "which of them a value came from."
        ),
    ),
)

#: The docstring sections republished on the page, in this order. They are the ones that
#: state a contract a caller codes against. Everything else a docstring carries stays in the
#: source, where the reader it was written for already is.
SECTIONS: Final[tuple[str, ...]] = ("Args", "Returns", "Raises", "Attributes")

#: How each of them is labelled on the page.
SECTION_LABELS: Final[dict[str, str]] = {
    "Args": "Parameters",
    "Returns": "Returns",
    "Raises": "Raises",
    "Attributes": "Attributes",
}

#: Sections whose body is one block of prose rather than a ``name: description`` list.
PROSE_SECTIONS: Final[frozenset[str]] = frozenset({"Returns"})

#: Class-body assignments that are configuration rather than surface. `model_config` is
#: pydantic's own knob table; a caller neither reads nor sets it, and printing it in a class
#: header would read as a field.
NOT_A_FIELD: Final[frozenset[str]] = frozenset({"model_config"})

#: Base classes that make a class a pydantic model on one of these surfaces. Resolved
#: transitively, so a model that derives from another model is still one.
MODEL_BASES: Final[frozenset[str]] = frozenset(
    {"BaseModel", "IRModel", "ReportModel", "RunReportModel", "ExtractionModel", "StoreModel"}
)

#: Base classes that make a class an exception or a warning.
RAISED_BASES: Final[frozenset[str]] = frozenset(
    {
        "BaseException",
        "Exception",
        "ValueError",
        "TypeError",
        "KeyError",
        "LookupError",
        "RuntimeError",
        "NotImplementedError",
        "Warning",
        "UserWarning",
        "DeprecationWarning",
    }
)

#: The LaTeX the sources use inside `$…$`, and what it reads as in plain text. The site
#: declares no math extension, so a `$…$` span published as-is shows its dollar signs; the
#: honest rendering is the notation itself. `test_api_reference.py` asserts that no `$` and no
#: backslash survives into the page, so an unmapped command fails the build rather than
#: reaching a reader as an escape sequence.
MATH_SYMBOLS: Final[dict[str, str]] = {
    r"\cup": "∪",
    r"\cap": "∩",
    r"\setminus": "∖",
    r"\subseteq": "⊆",
    r"\subset": "⊂",
    r"\in": "∈",
    r"\times": "×",
    r"\{": "{",
    r"\}": "}",
}

_MATH_RE: Final = re.compile(r"\$([^$]+)\$")
_ROLE_RE: Final = re.compile(r":(?:class|func|meth|mod|data|attr|obj|exc|const):`~?([^`]+)`")
_DOUBLE_TICK_RE: Final = re.compile(r"``([^`]+)``")
_SECTION_RE: Final = re.compile(r"^(?P<name>[A-Z][A-Za-z]+):\s*$")
_ENTRY_RE: Final = re.compile(r"^(?P<name>\*{0,2}[^:\s][^:]*?):\s*(?P<text>.*)$")


# ── The static reader: `ast` over `src/`, importing nothing ──────────────────────────────


def module_file(module: str) -> Path:
    """Where a dotted module name's source lives, package or module."""
    base = SRC / Path(*module.split("."))
    return base / "__init__.py" if (base / "__init__.py").is_file() else base.with_suffix(".py")


@cache
def _source(module: str) -> str:
    return module_file(module).read_text(encoding="utf-8")


@cache
def _tree(module: str) -> ast.Module:
    return ast.parse(_source(module))


@cache
def _imported_from(module: str) -> dict[str, str]:
    """``name -> module it was imported from``, for every absolute ``from`` import.

    ``ast.walk`` rather than the module body, because the top-level package resolves its
    lazy exports through a ``if TYPE_CHECKING:`` block — the only statement of what
    ``gebra.extract`` *is* that a static reader can see, and the one a type checker uses too.
    """
    found: dict[str, str] = {}
    for node in ast.walk(_tree(module)):
        if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            for alias in node.names:
                found.setdefault(alias.asname or alias.name, node.module)
    return found


@cache
def exported(module: str) -> tuple[str, ...]:
    """A module's ``__all__``, in its own order — which ruff keeps canonical (RUF022)."""
    for node in _tree(module).body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "__all__" for target in node.targets
        ):
            listed = node.value
            if isinstance(listed, (ast.List, ast.Tuple)):
                return tuple(str(ast.literal_eval(item)) for item in listed.elts)
    raise LookupError(f"{module} declares no __all__")


@cache
def _definitions(module: str) -> dict[str, ast.stmt]:
    """Every top-level name a module defines, mapped to the statement that defines it."""
    defined: dict[str, ast.stmt] = {}
    for node in _tree(module).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            defined[node.name] = node
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    defined[target.id] = node
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            defined[node.target.id] = node
    return defined


def resolve(module: str, name: str, seen: tuple[str, ...] = ()) -> tuple[str, ast.stmt]:
    """Follow re-exports to the module that actually defines ``name``.

    Raises:
        LookupError: if the name is defined nowhere the chain reaches, which means the
            surface re-exports something this reader cannot see — a hole, not a symbol.
    """
    if module in seen:
        raise LookupError(f"re-export cycle reaching {module}.{name}")
    local = _definitions(module).get(name)
    if local is not None:
        return module, local
    origin = _imported_from(module).get(name)
    if origin is None:
        raise LookupError(f"{module} exports {name!r}, which nothing it imports defines")
    return resolve(origin, name, (*seen, module))


def _comment_block(module: str, lineno: int) -> str:
    """The ``#:`` block documenting the assignment at ``lineno``, or ``""``.

    A block documents the whole run of assignments below it — three OpenInference attribute
    names under one sentence, the two I-JSON bounds under another — so the walk upwards
    steps over sibling statements and stops at the blank line that ends the run.
    """
    lines = _source(module).splitlines()
    index = lineno - 2
    while index >= 0:
        stripped = lines[index].lstrip()
        if stripped.startswith("#:"):
            break
        if not stripped or stripped.startswith("@"):
            return ""
        index -= 1
    collected: list[str] = []
    while index >= 0 and lines[index].lstrip().startswith("#:"):
        collected.append(lines[index].lstrip()[2:].strip())
        index -= 1
    return "\n".join(reversed(collected)).strip()


def _attribute_docstring(module: str, node: ast.stmt) -> str:
    """A PEP 258 attribute docstring — a bare string right below the assignment."""
    for previous, following in pairwise(_tree(module).body):
        if previous is not node:
            continue
        value = following.value if isinstance(following, ast.Expr) else None
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            return value.value.strip()
    return ""


def documentation(module: str, node: ast.stmt) -> str:
    """The documentation attached to a definition, whatever form it takes."""
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return (ast.get_docstring(node) or "").strip()
    return _attribute_docstring(module, node) or _comment_block(module, node.lineno)


# ── Classifying and rendering a definition ───────────────────────────────────────────────


@cache
def _base_names(module: str, class_name: str) -> frozenset[str]:
    """A class's base names, transitively, as far as this reader can follow them."""
    node = _definitions(module).get(class_name)
    if not isinstance(node, ast.ClassDef):
        return frozenset()
    names: set[str] = set()
    for base in node.bases:
        spelled = ast.unparse(base)
        simple = spelled.rsplit(".", 1)[-1]
        names.add(simple)
        if simple in _definitions(module):
            names |= _base_names(module, simple)
        else:
            origin = _imported_from(module).get(simple)
            if origin is not None and module_file(origin).is_file():
                names |= _base_names(origin, simple)
    return frozenset(names)


def kind_of(module: str, node: ast.stmt) -> str:
    """What a reader should expect the name to be: the word the page prints beside it."""
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return "function"
    if isinstance(node, ast.ClassDef):
        bases = _base_names(module, node.name)
        if bases & RAISED_BASES:
            return "warning" if "Warning" in bases else "exception"
        if "Enum" in bases:
            return "enumeration"
        if bases & MODEL_BASES:
            return "model"
        if "Protocol" in bases:
            return "protocol"
        return "class"
    annotation = node.annotation if isinstance(node, ast.AnnAssign) else None
    if annotation is not None and ast.unparse(annotation) == "TypeAlias":
        return "type alias"
    return "constant"


def _parameter(argument: ast.arg, default: ast.expr | None) -> str:
    rendered = argument.arg
    if argument.annotation is not None:
        rendered += f": {ast.unparse(argument.annotation)}"
        if default is not None:
            rendered += f" = {ast.unparse(default)}"
    elif default is not None:
        rendered += f"={ast.unparse(default)}"
    return rendered


def _parameters(args: ast.arguments) -> list[str]:
    """The parameter list, spelled the way the source spells it, PEP 8 spacing restored."""
    positional = [*args.posonlyargs, *args.args]
    padding: list[ast.expr | None] = [None] * (len(positional) - len(args.defaults))
    defaults: list[ast.expr | None] = [*padding, *args.defaults]
    rendered = [_parameter(arg, default) for arg, default in zip(positional, defaults)]
    if args.posonlyargs:
        rendered.insert(len(args.posonlyargs), "/")
    if args.vararg is not None:
        rendered.append(f"*{_parameter(args.vararg, None)}")
    elif args.kwonlyargs:
        rendered.append("*")
    for arg, default in zip(args.kwonlyargs, args.kw_defaults):
        rendered.append(_parameter(arg, default))
    if args.kwarg is not None:
        rendered.append(f"**{_parameter(args.kwarg, None)}")
    return rendered


def signature(name: str, module: str, node: ast.stmt) -> str:
    """The definition as source: a call signature, a class header, or an assignment."""
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        returns = f" -> {ast.unparse(node.returns)}" if node.returns is not None else ""
        parameters = _parameters(node.args)
        one_line = f"{name}({', '.join(parameters)}){returns}"
        if len(one_line) <= 88:
            return one_line
        joined = "".join(f"    {parameter},\n" for parameter in parameters)
        return f"{name}(\n{joined}){returns}"
    if isinstance(node, ast.ClassDef):
        bases = ", ".join(ast.unparse(base) for base in node.bases)
        header = f"class {name}({bases})" if bases else f"class {name}"
        members = _members(node)
        if not members:
            return header
        body = "".join(f"    {member}\n" for member in members)
        return f"{header}:\n{body}".rstrip("\n")
    annotation = ""
    value: ast.expr | None = None
    if isinstance(node, ast.AnnAssign):
        annotation = f": {ast.unparse(node.annotation)}"
        value = node.value
    elif isinstance(node, ast.Assign):
        value = node.value
    if value is None:
        return f"{name}{annotation}"
    spelled = ast.unparse(value)
    return f"{name}{annotation} = {spelled if len(spelled) <= 72 else '...'}"


def _members(node: ast.ClassDef) -> list[str]:
    """An enumeration's members or a model's fields — the shape a caller reads or builds.

    A default is never elided to ``...``: in pydantic's own idiom ``field: T = ...`` means
    the field is *required*, so eliding a long default that way would say the opposite of
    what is true. A default too long for a line is spelled ``= <default>`` instead, which is
    not valid Python and therefore cannot be misread as one.
    """
    members: list[str] = []
    for statement in node.body:
        if isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name):
            if statement.target.id in NOT_A_FIELD:
                continue
            rendered = f"{statement.target.id}: {ast.unparse(statement.annotation)}"
            if statement.value is not None:
                rendered += f" = {_short(ast.unparse(statement.value))}"
            members.append(rendered)
        elif isinstance(statement, ast.Assign) and len(statement.targets) == 1:
            target = statement.targets[0]
            if isinstance(target, ast.Name) and not target.id.startswith("_"):
                if target.id in NOT_A_FIELD:
                    continue
                members.append(f"{target.id} = {_short(ast.unparse(statement.value))}")
    return members


def _short(spelled: str) -> str:
    """A default value, or a placeholder that is visibly not one."""
    return spelled if len(spelled) <= 60 else "<default>"


def field_notes(module: str, node: ast.stmt) -> list[tuple[str, str]]:
    """A class's per-field ``#:`` comments, in declaration order.

    These carry rules a class docstring often does not repeat and a signature cannot show —
    that a `PropertyReport` holds a witness **or** a failure and never both, that a
    `remediation` is display-only prose no consumer parses, that an `exit_code` and an
    `outcome` never disagree. Rendering only the annotations would publish the shape of the
    envelope while dropping its invariants, so the entries carry these too.
    """
    if not isinstance(node, ast.ClassDef):
        return []
    lines = _source(module).splitlines()
    notes: list[tuple[str, str]] = []
    for statement in node.body:
        if not isinstance(statement, ast.AnnAssign) or not isinstance(statement.target, ast.Name):
            continue
        if statement.target.id in NOT_A_FIELD:
            continue
        collected: list[str] = []
        index = statement.lineno - 2
        while index >= 0 and lines[index].lstrip().startswith("#:"):
            collected.append(lines[index].lstrip()[2:].strip())
            index -= 1
        if collected:
            notes.append((statement.target.id, "\n".join(reversed(collected))))
    return notes


# ── Docstrings into Markdown ─────────────────────────────────────────────────────────────


def _role(match: re.Match[str]) -> str:
    """One Sphinx role as a Markdown code span.

    A shortened `:meth:` keeps its class — `ExtractionEnvelope.graph_version()`, not
    `graph_version()`, which on this page is already a module-level function of `gebra.ir`
    taking an IR. A shortened `:func:` keeps only the name, because a function's module is
    the entry's own heading.
    """
    target = match.group(1)
    role = match.group(0)[1:].split(":", 1)[0]
    if role in {"func", "meth"}:
        keep = 2 if role == "meth" else 1
        return f"`{'.'.join(target.split('.')[-keep:])}()`"
    if "~" in match.group(0):
        return f"`{target.rsplit('.', 1)[-1]}`"
    return f"`{target}`"


def _math(match: re.Match[str]) -> str:
    """A `$…$` span as plain notation — the site renders no math."""
    spelled = match.group(1)
    for command, symbol in MATH_SYMBOLS.items():
        spelled = spelled.replace(command, symbol)
    return spelled


def _escape_outside_code(text: str) -> str:
    """Make the prose safe for Markdown without touching what is inside a code span."""
    pieces = text.split("`")
    for index, piece in enumerate(pieces):
        if index % 2 == 0:
            pieces[index] = piece.replace("<", "&lt;")
    return "`".join(pieces)


def to_markdown(text: str) -> str:
    """One block of docstring prose as one Markdown paragraph.

    Sphinx roles become code spans, RST's double backticks become Markdown's single ones,
    `$…$` spans become the notation they spell, and the hard-wrapped source lines are
    re-joined so that nothing in the middle of a sentence can land at the start of a line
    and be read as markup.
    """
    joined = " ".join(line.strip() for line in text.strip().splitlines() if line.strip())
    joined = _ROLE_RE.sub(_role, joined)
    joined = _DOUBLE_TICK_RE.sub(r"`\1`", joined)
    joined = _MATH_RE.sub(_math, joined)
    joined = re.sub(r"::(\s|$)", r":\1", joined)
    return _escape_outside_code(joined).strip()


def summary(doc: str) -> str:
    """A docstring's first paragraph — what the symbol *is*, in its author's words."""
    return to_markdown(doc.split("\n\n")[0]) if doc.strip() else ""


def body(doc: str) -> list[str]:
    """A docstring's prose *after* its opening paragraph, as Markdown blocks.

    Rendered for types and constants, not for functions. A callable's contract is its
    signature plus the sections it declares, and what follows those is written for whoever
    maintains it; a *type's* contract is prose — that a `GateOutcome`'s word and code never
    disagree, that a `Location` union resolves left to right — and dropping it would publish
    the shape of the envelope without its rules.

    Named sections are cut out (they are rendered as lists of their own). An indented
    paragraph is RST's literal block and is re-fenced rather than re-joined, and a paragraph
    of bullets stays a list.
    """
    lines = doc.splitlines()
    for index, line in enumerate(lines):
        header = _SECTION_RE.match(line)
        if header is not None and header.group("name") in SECTIONS:
            lines = lines[:index]
            break
    paragraphs = "\n".join(lines).split("\n\n")[1:]
    blocks: list[str] = []
    for paragraph in paragraphs:
        kept = [line for line in paragraph.splitlines() if line.strip()]
        if not kept:
            continue
        if all(line.startswith("    ") for line in kept):
            blocks += ["```text", *(line[4:].rstrip() for line in kept), "```"]
        elif any(line.lstrip().startswith(("- ", "* ")) for line in kept):
            blocks.append(_bullets(kept))
        else:
            blocks.append(to_markdown(paragraph))
    return blocks


def _bullets(lines: list[str]) -> str:
    """A paragraph whose lines are bullets, kept as a Markdown list."""
    items: list[list[str]] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(("- ", "* ")):
            items.append([stripped[2:]])
        elif items:
            items[-1].append(stripped)
        else:
            items.append([stripped])
    return "\n".join(f"- {to_markdown(' '.join(item))}" for item in items)


def sections(doc: str) -> dict[str, list[tuple[str, str]]]:
    """The ``Args:``/``Returns:``/``Raises:``/``Attributes:`` blocks a docstring carries.

    Each is a list of ``(name, description)`` pairs; a prose section such as ``Returns:``
    yields a single pair whose name is empty.
    """
    lines = doc.splitlines()
    found: dict[str, list[tuple[str, str]]] = {}
    index = 0
    while index < len(lines):
        header = _SECTION_RE.match(lines[index])
        if header is None or header.group("name") not in SECTIONS:
            index += 1
            continue
        name = header.group("name")
        index += 1
        body: list[str] = []
        while index < len(lines) and (not lines[index].strip() or lines[index].startswith("    ")):
            body.append(lines[index])
            index += 1
        found[name] = _prose(body) if name in PROSE_SECTIONS else _entries(body)
    return found


def _prose(body: list[str]) -> list[tuple[str, str]]:
    joined = to_markdown("\n".join(body))
    return [("", joined)] if joined else []


def _entries(body: list[str]) -> list[tuple[str, str]]:
    """``name: description`` items, with their continuation lines folded in."""
    entries: list[tuple[str, list[str]]] = []
    for line in body:
        if not line.strip():
            continue
        stripped = line.strip()
        indent = len(line) - len(line.lstrip())
        match = _ENTRY_RE.match(stripped)
        if indent <= 4 and match is not None:
            entries.append((match.group("name").strip(), [match.group("text")]))
        elif entries:
            entries[-1][1].append(stripped)
    return [(name, to_markdown(" ".join(text))) for name, text in entries]


# ── The symbol table ─────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Symbol:
    """One exported name, as this page describes it."""

    surface: str
    name: str
    module: str
    kind: str
    signature: str
    doc: str
    fields: tuple[tuple[str, str], ...] = ()

    @property
    def qualified(self) -> str:
        return f"{self.surface}.{self.name}"

    @property
    def anchor(self) -> str:
        return slug(self.qualified)


def slug(text: str) -> str:
    """Python-Markdown's own heading slug, so a link written here resolves on the site."""
    value = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^\w\s-]", "", value).strip().lower()
    return re.sub(r"[-\s]+", "-", value)


def collect() -> list[Symbol]:
    """Every exported name of every frozen surface, resolved to where it is defined."""
    symbols: list[Symbol] = []
    for surface in SURFACES:
        for name in exported(surface.module):
            module, node = resolve(surface.module, name)
            symbols.append(
                Symbol(
                    surface=surface.module,
                    name=name,
                    module=module,
                    kind=kind_of(module, node),
                    signature=signature(name, module, node),
                    doc=documentation(module, node),
                    fields=tuple(field_notes(module, node)),
                )
            )
    return symbols


def undocumented(symbols: list[Symbol] | None = None) -> list[Symbol]:
    """The public symbols with neither a docstring nor a ``#:`` block — the card's box 2."""
    return [symbol for symbol in symbols or collect() if not symbol.doc.strip()]


# ── Rendering the page ───────────────────────────────────────────────────────────────────

GENERATED_NOTE: Final = (
    "<!-- Generated by tools/api_reference.py from the docstrings of the frozen surfaces.\n"
    "     Do not edit this file: edit the docstring, then run\n"
    "     `python tools/api_reference.py --write`. CI runs `--check`. -->"
)

LEDE: Final = """\
# API reference

This is the public Python surface of `gebra`: what you may import, what each name is, and
what its own docstring says about it. Every entry below is generated from that docstring —
`tools/api_reference.py` reads the sources statically and renders them, and CI fails if the
committed page is not what a fresh render produces. The way to correct something here is to
correct the docstring it came from.

Five surfaces are covered — the top-level `gebra` and four of its packages — and they have
one thing in common: each is **frozen**. A freeze record fixes the names, signatures and
field sets listed here, and says what changing one of them costs — for `gebra.ir` a decision
record plus an `ir_version` bump, for `gebra.verify` an R-05-routed decision, for the
extractor and annotation surfaces a decision record before anything new can be emitted. For
`gebra.verify` the freeze reaches past the code to the vocabulary: adding, renaming or
reclassifying a condition ID is a spec addendum, never a local change. The surface table
below names each record.

Packages outside those five — `gebra.store`, `gebra.diff`, `gebra.snapshot`,
`gebra.lineage`, `gebra.audit`, `gebra.report`, `gebra.display`, `gebra.versioning`,
`gebra.testing`, `gebra.cli` and the pytest plugin — are public, but are not under a freeze
record, and are documented by the pages that use them rather than here: the
[CLI reference](cli.md), [the pytest plugin and CI gating](../guides/pytest-plugin-and-ci-gating.md)
and [Snapshot, diff and evolution](../guides/snapshot-diff-and-evolution.md).

Reading an entry: the code block is the definition as the source spells it — a call
signature, a class header with its fields or members, or an assignment with its annotation.
The prose under it is the docstring's own. For a **function** that is its opening paragraph
plus the parameters, return value and exceptions it declares; the rest of a function's
docstring is design rationale addressed to a reader of the source, and is not republished
here. For a **type, model, enumeration or constant** it is the whole docstring, together
with the per-field `#:` comments the source carries — because a type's rules live in its
prose rather than in its signature. Every entry names the module to read the source in, and
`help()` prints any docstring in full.

Types are authoritative rather than decorative: the package ships `py.typed`, so the
annotations below are the ones your type checker enforces.
"""

BOUNDARY: Final = """\
## What this page does not say

It does not say what a finding *means* — [What gebra checks](../concepts/what-gebra-checks.md)
and the per-validator pages do. It does not describe the command line, which has
[its own reference](cli.md). It says nothing about the eight non-wedge properties beyond the
registry contract that answers for them: they are not implemented, and the registry returns a
structured not-implemented marker rather than a pass. And it is a reference, not a tour — for
how the packages fit together, read the [architecture overview](architecture.md).

The page itself is held to the sources by `tests/docs/test_api_reference.py` — every name in
both directions, every signature's declared parameters, every freeze record it cites — and by
`python tools/api_reference.py --check` in the `docs` CI job, which fails if this page is not
what a fresh render of those docstrings produces.
"""


def _resolution_example() -> str:
    """The page's one executed example: every name it lists, imported.

    Generated rather than written, and so is the output block under it — both come out of
    the same static model as the entries, so a surface that gains or loses a name moves the
    example, the expected output and the entry list together or the render is stale.
    """
    modules = "\n".join(f"import {surface.module}" for surface in SURFACES)
    surfaces = ",\n    ".join(surface.module for surface in SURFACES)
    code = (
        f"{modules}\n\n"
        f"SURFACES = [\n    {surfaces},\n]\n\n"
        "total = 0\n"
        "for surface in SURFACES:\n"
        "    resolved = [name for name in surface.__all__ if hasattr(surface, name)]\n"
        "    total += len(resolved)\n"
        '    print(f"{surface.__name__:20}{len(resolved):4}/{len(surface.__all__)} resolved")\n'
        'print(f"\\n{total} names across {len(SURFACES)} frozen surfaces, every one importable")'
    )
    lines = [
        f"{surface.module:20}{len(exported(surface.module)):4}/"
        f"{len(exported(surface.module))} resolved"
        for surface in SURFACES
    ]
    total = sum(len(exported(surface.module)) for surface in SURFACES)
    lines += ["", f"{total} names across {len(SURFACES)} frozen surfaces, every one importable"]
    return "\n".join(
        [
            "<!-- gebra:example id=every-name-on-this-page -->",
            "```python",
            code,
            "```",
            "",
            "<!-- gebra:output id=every-name-on-this-page -->",
            "```text",
            *lines,
            "```",
        ]
    )


def _surface_table() -> str:
    rows = ["| Surface | Names | Frozen by | Freeze record |", "|---|---|---|---|"]
    for surface in SURFACES:
        rows.append(
            f"| [`{surface.module}`](#{slug(surface.module)}) "
            f"| {len(exported(surface.module))} "
            f"| card {surface.card} "
            f"| `{surface.record}` {surface.section} |"
        )
    return "\n".join(rows)


def _package_opening(module: str) -> str:
    return summary(ast.get_docstring(_tree(module)) or "")


def _module_heading(module: str, surface: str) -> str:
    """A per-module heading whose slug can never be a symbol's.

    Two things force the wording. A module and a symbol can share a dotted name — the
    `contract` function `gebra.annotations` exports is spelled exactly like the
    `gebra.annotations.contract` module it lives in — so a heading that were only the dotted
    name would give the two the same anchor. And a module can supply names to two surfaces,
    so where it is not the surface's own, the heading says which surface is re-exporting it.
    :func:`_assert_unique_anchors` is what holds both, rather than this reasoning.
    """
    if _owning_surface(module) == surface:
        return f"Defined in `{module}`"
    return f"Defined in `{module}`, re-exported by `{surface}`"


def _owning_surface(module: str) -> str:
    """The frozen surface a module belongs to — the longest one that is a prefix of it.

    ``gebra.extraction.dispatch`` is under both `gebra` and `gebra.extraction`; the longer
    one owns it, which is why the top-level surface's headings all read as re-exports. That
    is not a formality: the ten names it carries are defined in the two subpackages, and the
    lazy resolution that keeps them out of a bare `import gebra` is the reason they are.
    """
    candidates = [
        surface.module
        for surface in SURFACES
        if module == surface.module or module.startswith(f"{surface.module}.")
    ]
    return max(candidates, key=len) if candidates else ""


def _assert_unique_anchors(page: str) -> None:
    """Refuse to emit a page on which two headings would claim the same anchor.

    Python-Markdown resolves a duplicate by suffixing the second one, which would silently
    send a link written here to the wrong section. Better to fail the render.
    """
    slugs: dict[str, str] = {}
    for level, text in re.findall(r"^(#{1,6}) (.+)$", page, re.MULTILINE):
        anchor = slug(text.replace("`", ""))
        clash = slugs.get(anchor)
        if clash is not None:
            raise ValueError(f"heading anchor {anchor!r} is claimed by both {clash!r} and {text!r}")
        slugs[anchor] = f"{level} {text}"


def _entry(symbol: Symbol, also: list[str], distinct: list[str]) -> str:
    lines = [f"#### `{symbol.qualified}`", ""]
    lines += ["```python", symbol.signature, "```", ""]
    detail = [f"*{symbol.kind}*, defined in `{symbol.module}`."]
    if also:
        detail.append("Also exported as " + ", ".join(f"`{name}`" for name in also) + ".")
    if distinct:
        joined = ", ".join(f"`{name}`" for name in distinct)
        detail.append(f"Not the same object as {joined}, which shares the name only.")
    lines += [" ".join(detail), ""]
    text = summary(symbol.doc)
    if text:
        lines += [text, ""]
    if symbol.kind != "function":
        for block in body(symbol.doc):
            lines += [block, ""]
    if symbol.fields:
        lines += ["**Fields**", ""]
        lines += [f"- `{field}` — {to_markdown(note)}" for field, note in symbol.fields]
        lines.append("")
    for name in SECTIONS:
        entries = sections(symbol.doc).get(name)
        if not entries:
            continue
        label = SECTION_LABELS[name]
        if name in PROSE_SECTIONS:
            lines += [f"**{label}** — {entries[0][1]}", ""]
            continue
        lines += [f"**{label}**", ""]
        lines += [f"- `{item}` — {description}" for item, description in entries]
        lines.append("")
    return "\n".join(lines)


def render() -> str:
    """The whole page."""
    symbols = collect()
    by_name: dict[tuple[str, str], list[Symbol]] = {}
    for symbol in symbols:
        by_name.setdefault((symbol.module, symbol.name), []).append(symbol)
    same_name: dict[str, set[str]] = {}
    for symbol in symbols:
        same_name.setdefault(symbol.name, set()).add(symbol.module)

    out = [
        LEDE,
        GENERATED_NOTE,
        "",
        "## The frozen surfaces",
        "",
        _surface_table(),
        "",
        (
            "Every name below is one this list resolves, and CI runs that check as an "
            "example on this page:"
        ),
        "",
        _resolution_example(),
        "",
    ]
    for surface in SURFACES:
        mine = [symbol for symbol in symbols if symbol.surface == surface.module]
        out += [f"## `{surface.module}`", ""]
        opening = _package_opening(surface.module)
        if opening:
            out += [opening, ""]
        out += [surface.scope, ""]
        out += [
            (
                f"Frozen by card {surface.card}, recorded in `{surface.record}` "
                f"{surface.section} — {len(mine)} names."
            ),
            "",
        ]
        index = " · ".join(f"[`{symbol.name}`](#{symbol.anchor})" for symbol in mine)
        out += [index, ""]
        for module in sorted({symbol.module for symbol in mine}):
            relative = module_file(module).relative_to(REPO_ROOT).as_posix()
            out += [
                f"### {_module_heading(module, surface.module)}",
                "",
                f"Source: [`{relative}`]({SOURCE_URL}/{relative})",
                "",
            ]
            for symbol in [item for item in mine if item.module == module]:
                also = [
                    other.qualified
                    for other in by_name[(symbol.module, symbol.name)]
                    if other.surface != symbol.surface
                ]
                distinct = [
                    f"{other}.{symbol.name}"
                    for other in sorted(
                        {
                            item.surface
                            for item in symbols
                            if item.name == symbol.name and item.module != symbol.module
                        }
                    )
                ]
                out.append(_entry(symbol, sorted(also), distinct))
    out.append(BOUNDARY)
    page = _ruff_formatted("\n".join(out).rstrip() + "\n")
    _assert_unique_anchors(page)
    return page


def _ruff_binary() -> str:
    """The formatter, preferring the one beside the interpreter that is running this."""
    beside = Path(sys.executable).parent / "ruff"
    if beside.is_file():
        return str(beside)
    found = shutil.which("ruff")
    if found is None:
        raise RuntimeError(
            "ruff is not installed, and this generator formats its output with it. "
            "Install the development extra (`pip install -e '.[dev]'`) and try again."
        )
    return found


def _ruff_formatted(page: str) -> str:
    """The page as `ruff format` leaves it — the repository's own formatter, not a guess.

    ruff formats the Python inside a Markdown fence, which means `ruff format --check .` has
    an opinion about this page. Reimplementing that opinion here — quote style, operator
    hugging, where a long line wraps — would be a second formatter to keep in step with the
    first, and the two would disagree the first time either changed. Handing the rendered
    page to the formatter the repository already gates on makes the two agree by
    construction: what this returns is a fixed point of `ruff format`.

    The flags are passed explicitly rather than read from ``pyproject.toml``, because the
    file being formatted is a temporary one outside the project; they are that file's
    settings, and `tests/docs/test_api_reference.py` checks the result against the real gate.
    """
    with tempfile.TemporaryDirectory() as directory:
        scratch = Path(directory) / PAGE.name
        scratch.write_text(page, encoding="utf-8")
        finished = subprocess.run(
            [
                _ruff_binary(),
                "format",
                "--quiet",
                "--isolated",
                "--line-length",
                "100",
                "--target-version",
                "py310",
                str(scratch),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if finished.returncode != 0:
            raise RuntimeError(f"ruff format refused the rendered page: {finished.stderr.strip()}")
        return scratch.read_text(encoding="utf-8")


# ── The command line ─────────────────────────────────────────────────────────────────────


def _report() -> int:
    symbols = collect()
    for surface in SURFACES:
        mine = [symbol for symbol in symbols if symbol.surface == surface.module]
        kinds = sorted({symbol.kind for symbol in mine})
        print(f"{surface.module:20} {len(mine):4} names  ({', '.join(kinds)})")
    print(f"{'total':20} {len(symbols):4} names on {len(SURFACES)} frozen surfaces")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--report", action="store_true", help="count what the surfaces export")
    group.add_argument(
        "--undocumented", action="store_true", help="list public symbols with no docstring"
    )
    group.add_argument("--write", action="store_true", help="regenerate docs/reference/api.md")
    group.add_argument(
        "--check", action="store_true", help="fail if the page is stale or a symbol is undocumented"
    )
    args = parser.parse_args(argv)

    if args.report:
        return _report()

    symbols = collect()
    missing = undocumented(symbols)
    if args.undocumented or args.check:
        for symbol in missing:
            print(f"undocumented: {symbol.qualified} ({symbol.kind}, in {symbol.module})")
        if args.undocumented:
            print(f"{len(symbols) - len(missing)}/{len(symbols)} public symbols documented")
            return 1 if missing else 0

    if args.write:
        if missing:
            print(f"refusing to write: {len(missing)} undocumented public symbol(s)")
            return 1
        PAGE.write_text(render(), encoding="utf-8")
        print(f"wrote {PAGE.relative_to(REPO_ROOT)} — {len(symbols)} symbols")
        return 0

    current = PAGE.read_text(encoding="utf-8")
    fresh = render()
    if current != fresh:
        print(
            f"{PAGE.relative_to(REPO_ROOT)} is not what the docstrings render to. "
            "Run `python tools/api_reference.py --write`."
        )
        return 1
    print(f"{PAGE.relative_to(REPO_ROOT)} is current — {len(symbols)} symbols, none undocumented")
    return 1 if missing else 0


if __name__ == "__main__":  # pragma: no cover - exercised through `main` in the test suite
    raise SystemExit(main())
