"""The draft-07 subset validator, and the schema it validates against (card CLI-03).

``tools/json_schema.py`` is load-bearing for CLI-03's second acceptance box: the claim "the
SARIF output validates against the SARIF 2.1.0 schema" is only worth what the validator is
worth. So this module tests the validator itself — each implemented keyword in both directions,
and the refusal that keeps an unimplemented keyword from passing silently — and pins the
vendored schema's digest so an edit to it fails here rather than quietly weakening the check.

Nothing here imports, executes or fetches anything (WA-07): the schema is read from disk.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Final

import pytest

from tools.json_schema import (
    ANNOTATION_KEYWORDS,
    SUPPORTED_KEYWORDS,
    UnsupportedSchemaError,
    validate,
)

REPO_ROOT: Final = Path(__file__).resolve().parents[1]
SARIF_SCHEMA: Final = REPO_ROOT / "tests" / "schemas" / "sarif-2.1.0.json"

#: Recorded in ``tests/schemas/README.md`` beside where the file came from.
SARIF_SCHEMA_SHA256: Final = "7c9688f0a1c4a4e1649ecc78521087e664729c1dff56ee8212ff195c7b16132a"


@pytest.fixture(scope="module")
def sarif_schema() -> Any:
    return json.loads(SARIF_SCHEMA.read_text(encoding="utf-8"))


# ── The vendored schema ──────────────────────────────────────────────────────────────────


def test_the_vendored_schema_is_the_recorded_bytes() -> None:
    """An unexplained edit to a third-party schema is drift, exactly like a golden's."""
    digest = hashlib.sha256(SARIF_SCHEMA.read_bytes()).hexdigest()
    assert digest == SARIF_SCHEMA_SHA256, (
        "tests/schemas/sarif-2.1.0.json changed; update the digest here and the row in "
        "tests/schemas/README.md in the same commit, with where the new bytes came from"
    )


def test_the_schema_readme_records_the_same_digest() -> None:
    readme = (SARIF_SCHEMA.parent / "README.md").read_text(encoding="utf-8")
    assert SARIF_SCHEMA_SHA256 in readme
    assert "json.schemastore.org/sarif-2.1.0.json" in readme


def test_the_validator_covers_every_keyword_the_sarif_schema_uses(sarif_schema: Any) -> None:
    """The refusal made positive: nothing in the document is outside the implemented subset."""
    used = _keywords(sarif_schema)
    unsupported = sorted(used - SUPPORTED_KEYWORDS - ANNOTATION_KEYWORDS)
    assert not unsupported, f"the SARIF schema uses {unsupported}, which the validator refuses"


def _keywords(node: Any, in_map: bool = False) -> set[str]:
    """Every schema keyword in ``node``, skipping the *names* inside keyword maps."""
    found: set[str] = set()
    if isinstance(node, dict):
        for key, value in node.items():
            if in_map:
                found |= _keywords(value)
                continue
            found.add(key)
            if key in ("properties", "definitions", "patternProperties", "dependencies"):
                found |= _keywords(value, in_map=True)
            elif key in ("items", "additionalProperties", "not", "contains", "propertyNames"):
                found |= _keywords(value)
            elif key in ("allOf", "anyOf", "oneOf"):
                for branch in value:
                    found |= _keywords(branch)
    return found


# ── The validator, keyword by keyword ────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("schema", "instance"),
    [
        ({"type": "string"}, "a"),
        ({"type": ["string", "null"]}, None),
        ({"type": "integer"}, 3),
        ({"type": "number"}, 3.5),
        ({"type": "boolean"}, True),
        ({"type": "array"}, []),
        ({"type": "object"}, {}),
        ({"enum": ["a", "b"]}, "b"),
        ({"const": 7}, 7),
        ({"minimum": 0, "maximum": 100}, 100.0),
        ({"exclusiveMinimum": 0}, 1),
        ({"exclusiveMaximum": 10}, 9),
        ({"minLength": 1, "maxLength": 3}, "ab"),
        ({"pattern": "^ge"}, "gebra"),
        ({"items": {"type": "string"}}, ["a", "b"]),
        ({"minItems": 1, "maxItems": 2}, ["a"]),
        ({"uniqueItems": True}, [{"a": 1}, {"a": 2}]),
        ({"required": ["a"]}, {"a": 1}),
        ({"properties": {"a": {"type": "integer"}}}, {"a": 1}),
        ({"properties": {"a": {}}, "additionalProperties": False}, {"a": 1}),
        ({"additionalProperties": {"type": "string"}}, {"b": "x"}),
        ({"allOf": [{"type": "integer"}, {"minimum": 2}]}, 3),
        ({"anyOf": [{"type": "string"}, {"type": "integer"}]}, 4),
        ({"oneOf": [{"type": "string"}, {"type": "integer"}]}, "s"),
        ({"not": {"type": "string"}}, 1),
        ({"format": "uri"}, "not a uri"),  # draft-07: format is an annotation
    ],
)
def test_conforming_instances_produce_no_issue(schema: Any, instance: Any) -> None:
    assert validate(instance, schema) == []


@pytest.mark.parametrize(
    ("schema", "instance"),
    [
        ({"type": "string"}, 1),
        ({"type": "integer"}, True),  # a JSON boolean is not a number
        ({"type": "number"}, False),
        ({"type": "null"}, 0),
        ({"enum": ["a"]}, "b"),
        ({"const": 7}, 8),
        ({"minimum": 0}, -1),
        ({"maximum": 100}, 101),
        ({"exclusiveMinimum": 0}, 0),
        ({"exclusiveMaximum": 10}, 10),
        ({"minLength": 2}, "a"),
        ({"maxLength": 1}, "ab"),
        ({"pattern": "^ge"}, "abra"),
        ({"items": {"type": "string"}}, ["a", 2]),
        ({"minItems": 2}, ["a"]),
        ({"maxItems": 1}, ["a", "b"]),
        ({"uniqueItems": True}, [{"a": 1}, {"a": 1}]),
        ({"required": ["a"]}, {}),
        ({"properties": {"a": {"type": "integer"}}}, {"a": "x"}),
        ({"properties": {"a": {}}, "additionalProperties": False}, {"b": 1}),
        ({"additionalProperties": {"type": "string"}}, {"b": 1}),
        ({"allOf": [{"type": "integer"}, {"minimum": 2}]}, 1),
        ({"anyOf": [{"type": "string"}, {"type": "integer"}]}, 1.5),
        ({"oneOf": [{"type": "integer"}, {"minimum": 0}]}, 1),
        ({"not": {"type": "string"}}, "s"),
    ],
)
def test_non_conforming_instances_are_caught(schema: Any, instance: Any) -> None:
    assert validate(instance, schema)


def test_local_refs_resolve() -> None:
    schema = {"$ref": "#/definitions/name", "definitions": {"name": {"type": "string"}}}
    assert validate("gebra", schema) == []
    assert validate(1, schema)


def test_a_remote_ref_is_refused_never_fetched() -> None:
    """WA-07 as a code path, not only as a promise."""
    with pytest.raises(UnsupportedSchemaError, match="remote lookup"):
        validate({}, {"$ref": "https://example.invalid/schema.json"})


def test_a_ref_that_resolves_to_nothing_is_refused() -> None:
    with pytest.raises(UnsupportedSchemaError, match="resolves to nothing"):
        validate({}, {"$ref": "#/definitions/absent"})


def test_an_unimplemented_keyword_is_refused_not_ignored() -> None:
    """The honesty guard: silently passing an unchecked constraint is the failure mode."""
    with pytest.raises(UnsupportedSchemaError, match="draft-07 subset"):
        validate({"a": 1}, {"patternProperties": {"^a": {"type": "string"}}})


def test_the_tuple_form_of_items_is_refused() -> None:
    with pytest.raises(UnsupportedSchemaError, match="tuple form"):
        validate([1], {"items": [{"type": "integer"}]})


def test_a_ref_beside_an_assertion_is_refused() -> None:
    """draft-07 ignores keywords beside ``$ref``; losing one silently would under-validate."""
    schema = {"$ref": "#/definitions/n", "type": "string", "definitions": {"n": {}}}
    with pytest.raises(UnsupportedSchemaError, match="beside `\\$ref`"):
        validate("x", schema)


def test_boolean_schemas_are_honored() -> None:
    assert validate(1, True) == []
    assert validate(1, False)


def test_an_issue_names_the_pointer_it_failed_at() -> None:
    schema = {"properties": {"runs": {"items": {"required": ["tool"]}}}}
    issues = validate({"runs": [{}]}, schema)
    assert [issue.path for issue in issues] == ["/runs/0"]
    assert "tool" in str(issues[0])
