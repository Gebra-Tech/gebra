"""Surface serialization — the YAML and JSON loaders and dumpers for the IR 1.0 models.

This module is the *surface* form of an IR document: what a person authors, what a file on
disk holds, and what a tool prints. It is deliberately **not** the canonical form. IR-SPEC
§6.1 step 1 says it outright — YAML is authoring-only and surface bytes are never hashed —
so the digest pipeline lives in :mod:`gebra.ir.canonical` and takes a *model*, never these
bytes. The two serve opposite ends:

* canonical serialization **collapses** representations (``entry`` to a scalar when the
  wired set is a singleton, an empty ``interrupts.before`` onto absence, a defaulted
  ``kind`` out) so that equivalent documents share one digest;
* this module **preserves** them, because SOW §2 criterion 6 is that every IR model
  reloads *equal to its source*, and those distinctions are real under model equality:
  ``Interrupts(before=())`` and ``Interrupts(before=None)`` are different models.

The round-trip contract, in both directions:

* ``load_yaml(T, dump_yaml(m)) == m`` and ``load_json(T, dump_json(m)) == m`` for every
  ``ir_version`` 1.0 model ``m`` whose content JSON can carry — the exceptions are the ones
  listed under *refused* below, and they raise rather than round-trip differently. ``==``
  is pydantic model equality: field-by-field value equality, never string equality of the
  serialized text;
* the two formats are interchangeable: a document loaded from YAML and one loaded from the
  JSON dump of that same model are equal.

**Ingestion path** (IR-SPEC §2.5 note 4). YAML payloads route through JSON-mode validation:
PyYAML's safe constructor set parses the surface, the parsed data is re-encoded as JSON, and
``model_validate_json`` validates it. The spec words this as a SHOULD; in practice it is
forced. The models are ``strict=True`` (A6 PC-3), and under strict Python-mode validation a
``list`` is not a ``tuple`` — a YAML sequence validates into the tuple-typed members only in
JSON mode. The JSON entry point goes through the same re-encoding rather than handing its
text straight to pydantic, so the two formats are **one validation path with two parsers in
front of it**: the same document is admitted, refused and reported on identically whichever
way it was spelled.

**Nothing is coerced on the way in or out.** The re-encoding *refuses* what JSON cannot
carry — a non-string mapping key, a YAML timestamp or binary scalar, NaN/Infinity, a
recursive anchor, a document past the size or depth ceilings — with an
:class:`IRSerializationError` naming the path, rather than quietly turning ``{1: "x"}`` into
``{"1": "x"}`` or ``Infinity`` into ``null``. Silent coercion in a loader is how a document
comes to mean something other than what it says, and downstream that is a digest that moves
for no visible reason. The single exception is Python's own sequence pair: JSON has one
sequence type, so a ``tuple`` is written as an array. Model members are tuples by convention
(A6 PC-2) and reload as tuples; a ``tuple`` placed inside the foreign ``args_schema`` *by
hand* is the one value that reloads as something else (a ``list``), and it can only get
there by Python construction, never by loading.

Nothing here executes anything (WA-07): the YAML parser is PyYAML's safe constructor set —
in a private subclass, so a tag another library registers on the shared ``SafeLoader`` cannot
change what a gebra document means — so no ``!!python/`` tag can construct an object, no
module is imported from document content, and no I/O happens beyond reading and writing the
file a caller names. Foreign content (``annotations.args_schema``) is read through unbound
built-in accessors, so no method of a foreign object is called; on the error path its
*type's* name is read, which is the one thing a sufficiently exotic metaclass could still
observe.

PyYAML is imported lazily, inside the YAML entry points: the JSON half of this module works
without it, and a missing PyYAML produces one actionable message instead of an import error
at ``import gebra``.
"""

from __future__ import annotations

import json
import math
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, TypeAlias, TypeVar

from gebra.ir.base import IRModel
from gebra.ir.models import WorkflowIR

if TYPE_CHECKING:
    import os

__all__ = [
    "JSON_SUFFIXES",
    "YAML_SUFFIXES",
    "IRSerializationError",
    "IRSerializationErrorReason",
    "dump_json",
    "dump_yaml",
    "load_json",
    "load_yaml",
    "read_ir",
    "write_ir",
]

#: Any ``ir_version`` 1.0 model — every entry point here is generic over the whole surface,
#: because SOW §2 criterion 6 is about *every* IR model, not only :class:`WorkflowIR`.
ModelT = TypeVar("ModelT", bound=IRModel)

#: JSON data: what a document is after parsing and before validation.
Json: TypeAlias = "None | bool | int | float | str | list[Json] | dict[str, Json]"

#: Where a value sits in the document — aliased member names, array indexes.
_Path: TypeAlias = tuple[str | int, ...]

#: File suffixes :func:`read_ir` / :func:`write_ir` read as YAML.
YAML_SUFFIXES: Final = (".yaml", ".yml")

#: File suffixes :func:`read_ir` / :func:`write_ir` read as JSON.
JSON_SUFFIXES: Final = (".json",)

#: Indentation of :func:`dump_json` output. Two spaces, matching ``.editorconfig``.
_JSON_INDENT: Final = 2

#: The one encoding an IR file is read and written in (IR-SPEC §6.1 step 6 is UTF-8, and a
#: surface file that could not be re-read as UTF-8 would not survive to be canonicalized).
_ENCODING: Final = "utf-8"

#: Characters that are ordinary text in JSON and *line breaks* (or a byte-order mark) in
#: YAML 1.1: NEL, LINE SEPARATOR, PARAGRAPH SEPARATOR, BOM. PyYAML writes them raw inside a
#: single-quoted scalar, and its own parser then folds them back as breaks — ``"\\x85x"``
#: returns as ``" x"``. A string carrying one is therefore emitted double-quoted, the one
#: style in which PyYAML escapes them (``\\N``, ``\\L``, ``\\P``, ``\\uFEFF``). Spelled as
#: escapes on purpose: three of the four are invisible in an editor, and this constant *is*
#: the fix for a silent-truncation bug.
_FORCE_DOUBLE_QUOTED: Final = "\x85\u2028\u2029\ufeff"

#: Ceilings on the re-encoding, set far above any real IR document. They exist because YAML
#: aliases let a *small* document expand into a huge one: ``safe_load`` returns a compact
#: object graph in which an alias is one shared object, and re-encoding it as JSON — which
#: has no aliases — writes every reference out in full. Without a ceiling the classic
#: "billion laughs" document (nine levels of nine aliases, some 200 bytes) becomes 10^8
#: values before validation is ever reached. The depth ceiling does the same job for a
#: deeply nested document, where the alternative is an unreason-coded ``RecursionError``.
_MAX_VALUES: Final = 1_000_000
_MAX_DEPTH: Final = 200


class IRSerializationErrorReason(str, Enum):
    """Why a document could not cross the surface boundary — a stable code to branch on.

    These describe the *surface*, never the model: a document that parses and re-encodes
    but does not satisfy the §2 model raises pydantic's own ``ValidationError`` instead, so
    the two failure kinds stay distinguishable. Like
    :class:`~gebra.ir.identity.NodeIdErrorReason` and
    :class:`~gebra.ir.canonical.CanonicalizationErrorReason` these are IR-validity codes;
    the PROPERTY-CATALOG-SPEC §0.4 registry neither contains nor needs them, and no
    verification envelope reports one.
    """

    YAML_SYNTAX = "yaml-syntax"
    JSON_SYNTAX = "json-syntax"
    NON_STRING_KEY = "non-string-key"
    NON_FINITE_NUMBER = "non-finite-number"
    UNSUPPORTED_TYPE = "unsupported-type"
    CIRCULAR_REFERENCE = "circular-reference"
    TOO_COMPLEX = "document-too-complex"
    UNKNOWN_SUFFIX = "unknown-suffix"


class IRSerializationError(ValueError):
    """A document (or a model) that cannot be carried across the YAML/JSON surface.

    Subclassing :class:`ValueError` mirrors :class:`~gebra.ir.identity.NodeIdError` and
    :class:`~gebra.ir.canonical.CanonicalizationError`.

    Attributes:
        reason: The :class:`IRSerializationErrorReason` code — match on this, not on text.
        path: Where the offending value sits, in authored shape: aliased member names
            (``"from"``), array indexes, foreign keys as written. Empty for a fault that
            belongs to the document as a whole (a YAML syntax error, an unknown suffix).
        value: The offending value itself, when there is one.
    """

    def __init__(
        self,
        message: str,
        *,
        reason: IRSerializationErrorReason,
        path: _Path = (),
        value: object = None,
    ) -> None:
        super().__init__(message)
        self.reason = reason
        self.path = path
        self.value = value


# ── Dumping: model → surface text ────────────────────────────────────────────────────────


def dump_json(model: IRModel, *, indent: int | None = _JSON_INDENT) -> str:
    """Serialize ``model`` as JSON text, in surface (not canonical) form.

    The output is ready to write to a file: UTF-8-encodable, non-ASCII characters kept as
    themselves rather than ``\\u`` escapes, members in the model's declaration order, and
    exactly one trailing newline. ``indent=None`` produces the compact single-line form.

    Optional members holding ``None`` are omitted — every optional member of the 1.0 surface
    defaults to ``None``, so absence and ``null`` reload identically and dropping them
    costs nothing under model equality. Members of the foreign ``args_schema`` object are
    *not* touched, ``null``-valued ones included: it is carried verbatim.

    These bytes are never hashed. ``graph_version`` is computed from
    :func:`~gebra.ir.canonical.canonical_bytes`, over the model — IR-SPEC §6.1 step 1.

    Raises:
        IRSerializationError: if the model carries content JSON cannot represent — a
            non-finite float, a non-string key or a non-JSON type inside ``args_schema``, a
            container that contains itself, or a value past a written-form limit.
    """
    return _encode(_surface(model), indent) + "\n"


def dump_yaml(model: IRModel) -> str:
    """Serialize ``model`` as YAML text, in surface (not canonical) form.

    Block style, members in the model's declaration order (never alphabetized), non-ASCII
    kept as itself. As with :func:`dump_json` the output ends in a newline, and these bytes
    are never hashed — YAML has no canonical byte form at all (IR-SPEC §6.1 step 1).

    Raises:
        IRSerializationError: as for :func:`dump_json`.
        ImportError: if PyYAML is not installed.
    """
    yaml = _yaml_module()
    surface = _surface(model)
    try:
        dumped: str = yaml.dump(
            surface,
            Dumper=_surface_dumper(),
            sort_keys=False,
            allow_unicode=True,
            default_flow_style=False,
        )
    except ValueError as exc:
        raise _unwritable(exc) from exc
    return dumped


# ── Loading: surface text → model ────────────────────────────────────────────────────────


def load_json(model_type: type[ModelT], source: str | bytes) -> ModelT:
    """Validate JSON text as ``model_type`` — the JSON-mode ingestion path (§2.5 note 4).

    Args:
        model_type: The model class to validate against, e.g. :class:`WorkflowIR`.
        source: JSON text, as ``str`` or UTF-8 ``bytes``.

    Raises:
        IRSerializationError: if the text is not well-formed JSON, or carries what JSON has
            no form for. ``Infinity``, ``-Infinity`` and ``NaN`` are the ones worth naming:
            Python's parser and pydantic's both accept those non-standard literals, RFC 8259
            has none of them, and IR-SPEC §6.1 step 5 forbids them in an IR document — so
            they are
            refused here rather than loaded into a document that could never be written back
            out or hashed. A document past the size or depth ceilings is refused as
            ``document-too-complex``.
        UnicodeDecodeError: (a ``ValueError``) if ``source`` is ``bytes`` that are not UTF-8.
        pydantic.ValidationError: if the document does not satisfy the §2 model.
    """
    text = _text(source)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise IRSerializationError(
            f"the document is not well-formed JSON: {exc}",
            reason=IRSerializationErrorReason.JSON_SYNTAX,
        ) from exc
    except RecursionError as exc:
        raise _too_deep(exc) from exc
    except ValueError as exc:  # e.g. an integer past the interpreter's digit limit
        raise _unwritable(exc) from exc
    return _validate(model_type, data)


def load_yaml(model_type: type[ModelT], source: str | bytes) -> ModelT:
    """Validate YAML text as ``model_type``, via the JSON re-encoding (§2.5 note 4).

    PyYAML's safe constructor set parses the surface — so no tag can construct a Python
    object — and the parsed data is re-encoded as JSON so that validation runs in JSON mode,
    where a sequence validates into the tuple-typed members under strict semantics.

    Args:
        model_type: The model class to validate against, e.g. :class:`WorkflowIR`.
        source: YAML text, as ``str`` or UTF-8 ``bytes``.

    Raises:
        IRSerializationError: if the text is not well-formed YAML, or parses to data JSON
            cannot carry (a timestamp or binary scalar, a non-string mapping key,
            ``.nan``/``.inf``, a recursive anchor, or a document past the size or depth
            ceilings).
        UnicodeDecodeError: (a ``ValueError``) if ``source`` is ``bytes`` that are not UTF-8.
        pydantic.ValidationError: if the document does not satisfy the §2 model.
        ImportError: if PyYAML is not installed.
    """
    yaml = _yaml_module()
    text = _text(source)
    try:
        data = yaml.load(text, _surface_loader())
    except yaml.YAMLError as exc:
        raise IRSerializationError(
            f"the document is not well-formed YAML: {exc}",
            reason=IRSerializationErrorReason.YAML_SYNTAX,
        ) from exc
    except RecursionError as exc:
        raise _too_deep(exc) from exc
    except ValueError as exc:  # e.g. an integer past the interpreter's digit limit
        raise _unwritable(exc) from exc
    return _validate(model_type, data)


def _text(source: str | bytes) -> str:
    """The characters of ``source``, so that both formats see the same document.

    ``bytes`` are UTF-8, and a leading byte-order mark is dropped rather than handed to a
    parser as content — a UTF-8 BOM is what a Windows editor leaves behind, and neither
    parser has a use for it. Left to themselves the two parsers would disagree here: PyYAML
    selects UTF-16 from a BOM in a ``bytes`` stream while ``json`` assumes UTF-8.

    Raises:
        UnicodeDecodeError: (a :class:`ValueError`) if ``source`` is not UTF-8.
    """
    text = source.decode(_ENCODING) if isinstance(source, bytes) else source
    return text.removeprefix("﻿")


def _validate(model_type: type[ModelT], data: object) -> ModelT:
    """The one validation path both entry points share: re-encode, then validate in JSON
    mode (§2.5 note 4). Parsing is the only thing the two formats do differently."""
    return model_type.model_validate_json(_encode(_json_ready(data, (), frozenset(), _Budget())))


def _encode(tree: Json, indent: int | None = None) -> str:
    """JSON text for an already-vetted tree.

    The vetting has ruled out everything about the *content*; what is left is the written
    form running into an interpreter limit, which is a refusal with a reason like any other
    rather than a bare ``ValueError`` escaping a documented contract.
    """
    try:
        return json.dumps(tree, indent=indent, ensure_ascii=False)
    except ValueError as exc:
        raise _unwritable(exc) from exc


def _too_deep(exc: RecursionError) -> IRSerializationError:
    """A parser that ran out of stack met a document deeper than anything IR admits."""
    return IRSerializationError(
        f"the document is nested too deeply to parse ({exc})",
        reason=IRSerializationErrorReason.TOO_COMPLEX,
    )


def _unwritable(exc: ValueError) -> IRSerializationError:
    """A value past an interpreter limit on its written form — an integer of more digits
    than ``sys.set_int_max_str_digits`` allows is the one that exists in practice."""
    return IRSerializationError(
        f"the document holds a value that cannot be written out ({exc})",
        reason=IRSerializationErrorReason.TOO_COMPLEX,
    )


# ── Files ────────────────────────────────────────────────────────────────────────────────


def read_ir(path: str | os.PathLike[str]) -> WorkflowIR:
    """Load the :class:`WorkflowIR` held in the file at ``path``, YAML or JSON by suffix.

    ``.yaml``/``.yml`` are read as YAML and ``.json`` as JSON; the choice is the suffix's
    and nothing sniffs the content. The file is read as UTF-8.

    Raises:
        IRSerializationError: if the suffix is neither, or the surface is unreadable as for
            :func:`load_yaml`.
        pydantic.ValidationError: if the document does not satisfy the §2 model.
        OSError: if the file cannot be read.
    """
    file = Path(path)
    is_yaml = _suffix_of(file) in YAML_SUFFIXES
    text = file.read_text(encoding=_ENCODING)
    return load_yaml(WorkflowIR, text) if is_yaml else load_json(WorkflowIR, text)


def write_ir(ir: WorkflowIR, path: str | os.PathLike[str]) -> None:
    """Write ``ir`` to ``path`` in surface form, YAML or JSON by suffix.

    The file is written as UTF-8 with LF line endings and a trailing newline, so a
    round-tripped file is stable under ``git diff`` and under ``.editorconfig``. The written
    bytes are surface bytes: they are never hashed (IR-SPEC §6.1 step 1).

    Raises:
        IRSerializationError: if the suffix is recognized by neither format, or the model
            carries content the format cannot represent (see :func:`dump_json`).
        OSError: if the file cannot be written.
    """
    file = Path(path)
    text = dump_yaml(ir) if _suffix_of(file) in YAML_SUFFIXES else dump_json(ir)
    file.write_text(text, encoding=_ENCODING, newline="\n")


def _suffix_of(file: Path) -> str:
    """The lowercased suffix of ``file``, refused unless it names a supported format."""
    suffix = file.suffix.lower()
    if suffix not in YAML_SUFFIXES and suffix not in JSON_SUFFIXES:
        raise IRSerializationError(
            f"{file.name!r} has suffix {suffix!r}, which names no IR surface format "
            f"(expected one of {', '.join((*YAML_SUFFIXES, *JSON_SUFFIXES))}); call "
            "load_yaml()/load_json() directly to read a file named otherwise",
            reason=IRSerializationErrorReason.UNKNOWN_SUFFIX,
            value=file.name,
        )
    return suffix


# ── The surface tree ─────────────────────────────────────────────────────────────────────


def _surface(model: IRModel) -> Json:
    """``model`` as JSON data: by alias, ``None``-valued members dropped, tuples as arrays.

    Python-mode ``model_dump`` is deliberate. JSON-mode dumping coerces whatever it finds in
    the ``Any``-typed ``args_schema`` interior — an integer key becomes a string, a
    ``datetime`` becomes text, ``Infinity`` becomes ``null`` — all silently. Dumping in
    Python mode and converting here means the conversion is this module's, so foreign
    content is either carried exactly or refused by name.

    The one conversion this does apply to foreign content is Python's own: a ``tuple`` is
    written as a JSON array, since JSON has one sequence type. That is why a ``tuple`` placed
    inside ``args_schema`` *by hand* reloads as a ``list`` — the documented boundary of the
    round-trip claim. Model members are tuples by convention (A6 PC-2) and reload as tuples,
    and a loaded document never carries a tuple in its foreign content.
    """
    dumped = model.model_dump(mode="python", by_alias=True, exclude_none=True)
    return _json_ready(dumped, (), frozenset(), _Budget())


class _Budget:
    """The remaining value allowance of one re-encoding (see :data:`_MAX_VALUES`)."""

    __slots__ = ("remaining",)

    def __init__(self) -> None:
        self.remaining = _MAX_VALUES

    def spend(self, path: _Path) -> None:
        self.remaining -= 1
        if self.remaining < 0:
            raise IRSerializationError(
                f"the document expands to more than {_MAX_VALUES} values (a YAML alias is "
                "one shared object when parsed and a full copy once re-encoded, so a short "
                f"document can expand without bound); refused at {_at(path)}",
                reason=IRSerializationErrorReason.TOO_COMPLEX,
                path=path,
            )


def _json_ready(value: object, path: _Path, seen: frozenset[int], budget: _Budget) -> Json:
    """``value`` as JSON data, or an :class:`IRSerializationError` saying why it is not.

    Containers are traversed through unbound built-in accessors so no foreign subclass hook
    runs (WA-07), and every scalar is copied through its exact built-in accessor, so a
    ``str`` subclass never reaches the encoder — nor an error message.

    ``seen`` holds the ids of the containers on the path from the root: its membership turns
    a recursive YAML anchor into a named error rather than a :class:`RecursionError`, and its
    size is the nesting depth. ``budget`` bounds the whole expansion.
    """
    budget.spend(path)
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        return int.__index__(value)
    if isinstance(value, float):
        number = float.__float__(value)
        if not math.isfinite(number):
            raise IRSerializationError(
                f"{_at(path)} is {number}, which JSON has no form for (IR-SPEC §6.1 "
                "step 5 forbids NaN and Infinity in an IR document)",
                reason=IRSerializationErrorReason.NON_FINITE_NUMBER,
                path=path,
                value=number,
            )
        return number
    if isinstance(value, str):
        return str.__str__(value)
    if isinstance(value, (dict, list, tuple)):
        marker = id(value)
        if marker in seen:
            raise IRSerializationError(
                f"{_at(path)} contains itself; a JSON document is a tree "
                "(a recursive YAML anchor cannot be re-encoded)",
                reason=IRSerializationErrorReason.CIRCULAR_REFERENCE,
                path=path,
            )
        if len(seen) >= _MAX_DEPTH:
            raise IRSerializationError(
                f"{_at(path)} is nested more than {_MAX_DEPTH} levels deep, which no IR "
                "document is; re-encoding it would end in a RecursionError",
                reason=IRSerializationErrorReason.TOO_COMPLEX,
                path=path,
            )
        seen = seen | {marker}
        if isinstance(value, dict):
            return _json_object(value, path, seen, budget)
        items = list.__iter__(value) if isinstance(value, list) else tuple.__iter__(value)
        return [_json_ready(item, (*path, index), seen, budget) for index, item in enumerate(items)]
    raise IRSerializationError(
        f"{_at(path)} is of type {type(value).__name__}, which JSON cannot carry "
        "(a YAML timestamp, binary or set scalar has no JSON form; write it as a string)",
        reason=IRSerializationErrorReason.UNSUPPORTED_TYPE,
        path=path,
        value=value,
    )


def _json_object(
    mapping: dict[Any, Any], path: _Path, seen: frozenset[int], budget: _Budget
) -> dict[str, Json]:
    """A mapping as a JSON object. A non-string key is refused, never coerced.

    YAML admits ``1: x`` and ``true: x``; JSON does not, and ``json.dumps`` would turn both
    into strings without a word. Refusing keeps the loader from being the place a document
    silently changes meaning.
    """
    members: dict[str, Json] = {}
    for key, member in dict.items(mapping):
        if not isinstance(key, str):
            # `repr()` on a foreign object would run its own code; describe the exact
            # built-ins and name the type of anything else (WA-07).
            described = repr(key) if type(key) in (bool, int, float) else type(key).__name__
            raise IRSerializationError(
                f"{_at(path)} has the non-string key {described}; a JSON object member "
                "name is a string, and coercing one would silently change the document",
                reason=IRSerializationErrorReason.NON_STRING_KEY,
                path=path,
                value=key,
            )
        name = str.__str__(key)
        members[name] = _json_ready(member, (*path, name), seen, budget)
    return members


def _at(path: _Path) -> str:
    """Render a path for an error message: ``nodes[0].annotations.args_schema.maximum``."""
    if not path:
        return "the document"
    rendered = ""
    for part in path:
        if isinstance(part, int):
            rendered += f"[{part}]"
        elif rendered:
            rendered += f".{part}"
        else:
            rendered = part
    return rendered


@lru_cache(maxsize=1)
def _surface_loader() -> Any:
    """PyYAML's safe loader, in a subclass of this package's own.

    ``yaml.safe_load`` uses the process-wide ``SafeLoader``, and ``add_constructor`` mutates
    that shared class — so any library in the same interpreter that registers a tag on it
    (``!ENV``, ``!include`` and friends are common) would change what a gebra document means,
    and an ``!include``-shaped constructor opens a file named *in the document*. Subclassing
    keeps this package's ingestion semantics its own (WA-07). Nothing is registered on the
    subclass: its constructor table is ``SafeLoader``'s as PyYAML ships it.
    """
    import yaml

    class _SurfaceLoader(yaml.SafeLoader):
        pass

    # A bare subclass would still *inherit* the shared tables, so a tag registered later
    # would reach it. The two tables that run code are snapshotted instead.
    _SurfaceLoader.yaml_constructors = dict(yaml.SafeLoader.yaml_constructors)
    _SurfaceLoader.yaml_multi_constructors = dict(yaml.SafeLoader.yaml_multi_constructors)
    return _SurfaceLoader


@lru_cache(maxsize=1)
def _surface_dumper() -> Any:
    """PyYAML's safe dumper, with the one string style it gets wrong corrected.

    ``SafeDumper`` decides quoting per scalar and prefers the unquoted or single-quoted
    form. That choice is lossy for the characters in :data:`_FORCE_DOUBLE_QUOTED`, so those
    strings are emitted double-quoted, where PyYAML escapes them. Nothing else about the
    dumper changes: it is still the *safe* dumper, so no Python object can be represented.

    The import is repeated here rather than taken as an argument so that the base class is
    the declared ``SafeDumper`` rather than an opaque attribute of a module object.
    """
    import yaml

    class _SurfaceDumper(yaml.SafeDumper):
        pass

    def represent_str(dumper: Any, data: str) -> Any:
        style = '"' if any(char in data for char in _FORCE_DOUBLE_QUOTED) else None
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style=style)

    _SurfaceDumper.add_representer(str, represent_str)
    return _SurfaceDumper


def _yaml_module() -> Any:
    """PyYAML, imported on use.

    It is not a declared dependency of this package — it arrives with ``langchain-core``,
    and the test suite declares it — so the failure mode of a stripped environment is one
    sentence naming the fix, at the call, rather than an import error at ``import gebra``.
    """
    try:
        import yaml
    except ImportError as exc:
        raise ImportError(
            "reading or writing IR as YAML requires PyYAML, which is not installed; "
            "install it (`pip install PyYAML`) or use the JSON entry points "
            "gebra.ir.load_json / gebra.ir.dump_json"
        ) from exc
    return yaml
