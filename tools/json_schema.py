"""A dependency-free JSON Schema **draft-07 subset** validator.

Why this exists: card CLI-03 owes the evidence that gebra's SARIF emission "validates against
the SARIF 2.1.0 schema" (REPORT-FORMAT-SPEC §7). That schema is a draft-07 document
(``tests/schemas/sarif-2.1.0.json``), and validating against it needs a validator. Adding one
as a dependency is a locked-environment change no card owns; hand-writing a *check-list* of
SARIF's constraints would be a different, weaker claim. So this module validates against the
schema document itself, over the draft-07 keyword subset that document uses.

**The honesty guard is the refusal, not the coverage.** :func:`validate` walks every subschema
it is given and raises :class:`UnsupportedSchemaError` on any keyword outside
:data:`SUPPORTED_KEYWORDS` — so a schema using a construct this module does not implement fails
loudly instead of silently validating less than it claims. The same is true of ``$ref``: only
local pointers into the document are resolved, and a remote reference is a refusal. Growing
the supported set is a deliberate edit here, not something a new schema can do by accident.

Two draft-07 rules are implemented as the specification states them rather than as intuition
might: ``format`` is an **annotation**, not an assertion (draft-07 §7.2 makes assertion
behavior opt-in), and a JSON boolean is not a number, so ``True`` does not satisfy
``type: "integer"``.

It reads data structures and never imports, executes, or fetches anything (WA-07).

Usage::

    from tools.json_schema import validate

    errors = validate(instance, schema)   # [] when the instance conforms
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Final

__all__ = [
    "ANNOTATION_KEYWORDS",
    "SUPPORTED_KEYWORDS",
    "UnsupportedSchemaError",
    "ValidationIssue",
    "validate",
]


class UnsupportedSchemaError(RuntimeError):
    """The schema uses a draft-07 construct this validator does not implement."""


#: Keywords that carry no assertion in draft-07 and are skipped: documentation, identifiers,
#: the subschema container, and ``format`` (annotation-only unless a consumer opts in).
ANNOTATION_KEYWORDS: Final[frozenset[str]] = frozenset(
    {
        "$comment",
        "$id",
        "$schema",
        "default",
        "definitions",
        "description",
        "examples",
        "format",
        "readOnly",
        "title",
        "writeOnly",
    }
)

#: The assertion keywords this module implements. Anything else is a refusal.
SUPPORTED_KEYWORDS: Final[frozenset[str]] = frozenset(
    {
        "$ref",
        "additionalProperties",
        "allOf",
        "anyOf",
        "const",
        "enum",
        "exclusiveMaximum",
        "exclusiveMinimum",
        "items",
        "maxItems",
        "maxLength",
        "maximum",
        "minItems",
        "minLength",
        "minimum",
        "not",
        "oneOf",
        "pattern",
        "properties",
        "required",
        "type",
        "uniqueItems",
    }
)

_TYPES: Final[dict[str, tuple[type, ...]]] = {
    "null": (type(None),),
    "boolean": (bool,),
    "object": (dict,),
    "array": (list,),
    "number": (int, float),
    "integer": (int,),
    "string": (str,),
}


@dataclass(frozen=True)
class ValidationIssue:
    """One constraint the instance failed, with the JSON pointer where it failed."""

    path: str
    message: str

    def __str__(self) -> str:  # pragma: no cover - exercised through report rendering
        return f"{self.path or '/'}: {self.message}"


def _is_type(value: object, name: str) -> bool:
    """draft-07 type check, with the JSON boolean/number distinction Python does not make."""
    if name == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if name == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if name == "boolean":
        return isinstance(value, bool)
    expected = _TYPES.get(name)
    if expected is None:
        raise UnsupportedSchemaError(f"unknown JSON Schema type {name!r}")
    return isinstance(value, expected)


def _canonical(value: object) -> str:
    """A stable key for JSON equality — for ``enum``, ``const`` and ``uniqueItems``."""
    return json.dumps(value, sort_keys=True, default=repr)


def _resolve(ref: str, root: Any) -> Any:
    """Resolve a local ``$ref`` pointer. Remote references are a refusal, never a fetch."""
    if ref == "#":
        return root
    if not ref.startswith("#/"):
        raise UnsupportedSchemaError(
            f"only local JSON pointers are resolved; {ref!r} would need a remote lookup"
        )
    target = root
    for raw in ref[2:].split("/"):
        token = raw.replace("~1", "/").replace("~0", "~")
        if not isinstance(target, dict) or token not in target:
            raise UnsupportedSchemaError(f"{ref!r} resolves to nothing in this document")
        target = target[token]
    return target


def _check_keywords(schema: dict[str, Any]) -> None:
    unknown = sorted(set(schema) - SUPPORTED_KEYWORDS - ANNOTATION_KEYWORDS)
    if unknown:
        raise UnsupportedSchemaError(
            "this validator implements a draft-07 subset and the schema uses "
            f"{', '.join(unknown)}; extend tools/json_schema.py rather than validating less "
            "than the schema says"
        )


def _validate(
    instance: Any, schema: Any, root: Any, path: str, issues: list[ValidationIssue]
) -> None:
    if schema is True or schema == {}:
        return
    if schema is False:
        issues.append(ValidationIssue(path, "no instance is valid against `false`"))
        return
    if not isinstance(schema, dict):
        raise UnsupportedSchemaError(f"a schema is an object or a boolean, not {type(schema)}")
    _check_keywords(schema)

    if "$ref" in schema:
        assertions = set(schema) - ANNOTATION_KEYWORDS - {"$ref"}
        if assertions:
            raise UnsupportedSchemaError(
                f"draft-07 ignores keywords beside `$ref`; {sorted(assertions)} would be lost"
            )
        _validate(instance, _resolve(schema["$ref"], root), root, path, issues)
        return

    _validate_type(instance, schema, path, issues)
    _validate_values(instance, schema, path, issues)
    _validate_combinators(instance, schema, root, path, issues)
    if isinstance(instance, dict):
        _validate_object(instance, schema, root, path, issues)
    if isinstance(instance, list):
        _validate_array(instance, schema, root, path, issues)
    if isinstance(instance, str):
        _validate_string(instance, schema, path, issues)
    if isinstance(instance, (int, float)) and not isinstance(instance, bool):
        _validate_number(instance, schema, path, issues)


def _validate_type(
    instance: Any, schema: dict[str, Any], path: str, issues: list[ValidationIssue]
) -> None:
    declared = schema.get("type")
    if declared is None:
        return
    names = [declared] if isinstance(declared, str) else list(declared)
    if not any(_is_type(instance, name) for name in names):
        issues.append(
            ValidationIssue(path, f"expected type {' or '.join(names)}, got {_kind(instance)}")
        )


def _kind(instance: Any) -> str:
    for name in ("null", "boolean", "integer", "number", "string", "array", "object"):
        if _is_type(instance, name):
            return name
    return type(instance).__name__


def _validate_values(
    instance: Any, schema: dict[str, Any], path: str, issues: list[ValidationIssue]
) -> None:
    if "enum" in schema:
        allowed = {_canonical(option) for option in schema["enum"]}
        if _canonical(instance) not in allowed:
            issues.append(ValidationIssue(path, f"{instance!r} is not one of {schema['enum']!r}"))
    if "const" in schema and _canonical(instance) != _canonical(schema["const"]):
        issues.append(ValidationIssue(path, f"{instance!r} is not {schema['const']!r}"))


def _validate_combinators(
    instance: Any, schema: dict[str, Any], root: Any, path: str, issues: list[ValidationIssue]
) -> None:
    for subschema in schema.get("allOf", []):
        _validate(instance, subschema, root, path, issues)
    if "anyOf" in schema and not any(
        _conforms(instance, subschema, root) for subschema in schema["anyOf"]
    ):
        issues.append(ValidationIssue(path, "matches no branch of `anyOf`"))
    if "oneOf" in schema:
        matched = sum(1 for subschema in schema["oneOf"] if _conforms(instance, subschema, root))
        if matched != 1:
            issues.append(ValidationIssue(path, f"matches {matched} branches of `oneOf`, not 1"))
    if "not" in schema and _conforms(instance, schema["not"], root):
        issues.append(ValidationIssue(path, "matches a schema it must not match"))


def _validate_object(
    instance: dict[str, Any],
    schema: dict[str, Any],
    root: Any,
    path: str,
    issues: list[ValidationIssue],
) -> None:
    for name in schema.get("required", []):
        if name not in instance:
            issues.append(ValidationIssue(path, f"required property {name!r} is missing"))
    properties = schema.get("properties", {})
    for name, value in instance.items():
        if name in properties:
            _validate(value, properties[name], root, f"{path}/{name}", issues)
    additional = schema.get("additionalProperties")
    if additional is False:
        for name in instance:
            if name not in properties:
                issues.append(ValidationIssue(path, f"property {name!r} is not allowed here"))
    elif isinstance(additional, dict):
        for name, value in instance.items():
            if name not in properties:
                _validate(value, additional, root, f"{path}/{name}", issues)


def _validate_array(
    instance: list[Any],
    schema: dict[str, Any],
    root: Any,
    path: str,
    issues: list[ValidationIssue],
) -> None:
    items = schema.get("items")
    if isinstance(items, list):
        raise UnsupportedSchemaError("the tuple form of `items` is not implemented")
    if items is not None:
        for index, value in enumerate(instance):
            _validate(value, items, root, f"{path}/{index}", issues)
    minimum = schema.get("minItems")
    if minimum is not None and len(instance) < minimum:
        issues.append(ValidationIssue(path, f"expected at least {minimum} items"))
    maximum = schema.get("maxItems")
    if maximum is not None and len(instance) > maximum:
        issues.append(ValidationIssue(path, f"expected at most {maximum} items"))
    if schema.get("uniqueItems"):
        keys = [_canonical(value) for value in instance]
        if len(set(keys)) != len(keys):
            issues.append(ValidationIssue(path, "items are not unique"))


def _validate_string(
    instance: str, schema: dict[str, Any], path: str, issues: list[ValidationIssue]
) -> None:
    pattern = schema.get("pattern")
    if pattern is not None and re.search(pattern, instance) is None:
        issues.append(ValidationIssue(path, f"{instance!r} does not match {pattern!r}"))
    minimum = schema.get("minLength")
    if minimum is not None and len(instance) < minimum:
        issues.append(ValidationIssue(path, f"expected at least {minimum} characters"))
    maximum = schema.get("maxLength")
    if maximum is not None and len(instance) > maximum:
        issues.append(ValidationIssue(path, f"expected at most {maximum} characters"))


def _validate_number(
    instance: float, schema: dict[str, Any], path: str, issues: list[ValidationIssue]
) -> None:
    minimum = schema.get("minimum")
    if minimum is not None and instance < minimum:
        issues.append(ValidationIssue(path, f"{instance} is below the minimum {minimum}"))
    maximum = schema.get("maximum")
    if maximum is not None and instance > maximum:
        issues.append(ValidationIssue(path, f"{instance} is above the maximum {maximum}"))
    exclusive_minimum = schema.get("exclusiveMinimum")
    if exclusive_minimum is not None and instance <= exclusive_minimum:
        issues.append(ValidationIssue(path, f"{instance} is not above the exclusive minimum"))
    exclusive_maximum = schema.get("exclusiveMaximum")
    if exclusive_maximum is not None and instance >= exclusive_maximum:
        issues.append(ValidationIssue(path, f"{instance} is not below the exclusive maximum"))


def _conforms(instance: Any, schema: Any, root: Any) -> bool:
    """Whether ``instance`` satisfies ``schema`` — the branch test the combinators need."""
    branch: list[ValidationIssue] = []
    _validate(instance, schema, root, "", branch)
    return not branch


def validate(instance: Any, schema: Any) -> list[ValidationIssue]:
    """Validate ``instance`` against ``schema``; an empty list means it conforms.

    Args:
        instance: Parsed JSON data.
        schema: A parsed draft-07 schema document. It is also the resolution root for local
            ``$ref`` pointers.

    Returns:
        Every constraint the instance failed, each with the JSON pointer where it failed.

    Raises:
        UnsupportedSchemaError: if the schema reaches a construct outside the implemented
            subset. This is deliberate: a silent pass on an unimplemented keyword would make
            "validates against the schema" mean less than it says.
    """
    issues: list[ValidationIssue] = []
    _validate(instance, schema, schema, "", issues)
    return issues
