"""Schema-lockstep guard — ``WorkflowIR.model_json_schema()`` vs ``schema.yaml`` (IR-SPEC §2.5
note 5: "CI MUST assert ``WorkflowIR.model_json_schema()`` stays consistent with the
``gebra-ir`` ``$defs`` of ``schema.yaml`` (A6 PC-5)").

**Comparison strategy: field-name vocabulary, not full JSON-Schema equivalence.** The two
schemas are structurally different by design — the model's discriminated edge union renders
as three ``$defs`` entries plus a ``oneOf``/``discriminator``, while ``schema.yaml`` encodes
the same three kinds as one flat object with an ``allOf``/``if``/``then`` conditional
requirement; the model uses ``$ref``/``$defs`` indirection, the fixture schema nests inline.
Comparing the two byte-for-byte is neither feasible nor meaningful. What both sides must
agree on is *which fields exist* at each conceptual location of the document — the exact
category of risk IR-SPEC §3's nine new-in-1.0 slots motivate (a slot landing in one surface
and not the other). So this guard extracts, per named location, the set of member names each
schema admits there, and diffs the two sets.

This comparison **deliberately never reads requiredness**, because two divergences there are
already ruled, not accidental drift:

* ``RecursionLimit.justification`` is REQUIRED on the model but only ``value`` is required in
  ``schema.yaml`` — IR-01's recorded ruling is that the model is the hardened surface and
  ``schema.yaml`` is the looser vendored one (see ``tests/ir/test_spec_surface.py::
  test_recursion_limit_requires_its_justification``, which names this guard as the owner of
  that divergence).
* ``retry_policy``/``variant``/``compensation`` carry no ``required`` list in ``schema.yaml``
  (so ``variant: {}`` is schema-valid) while their model fields are all required — an IR-01
  carry-forward, left to the owner as a possible spec-defect, but in any case not something a
  *field-name* comparison could ever hide, since it only speaks about presence, not
  requiredness.

It also never reads type details or string patterns, so ``nodes[].id``'s node-identity-grammar
constraint (an ``AfterValidator``, invisible to ``model_json_schema()`` per IR-02's
carry-forward) is correctly a non-issue: both schemas say ``id: {type: string}`` and the
vocabulary check only asks whether the member ``id`` exists.

The walk (``_deref``, ``_first_with``, ``_union_props``) is generic JSON Schema traversal —
no ``$ref`` target or ``oneOf`` branch index is hardcoded — so the identical code walks both
schemas despite their different shapes. Nothing here executes a workflow, a node, or an LLM
(WA-07): it reads schema dictionaries.

Usage::

    python tools/schema_lockstep.py                          # verify, using the defaults
    python tools/schema_lockstep.py --schema some/schema.yaml

Exit status is 0 when every location's vocabulary agrees, 1 otherwise.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from gebra.ir import WorkflowIR

#: The conceptual locations both schemas describe, in the order this guard reports them.
LOCATIONS: tuple[str, ...] = (
    "workflow",
    "node",
    "annotations",
    "idempotent_key",
    "deterministic_spec",
    "retry_policy",
    "variant",
    "compensation",
    "edge",
    "runtime",
    "recursion_limit",
    "interrupts",
    "checkpointer",
    "state_field",
)


class SchemaLockstepError(RuntimeError):
    """The schema shape itself is unusable (a location this guard expects is entirely absent)."""


@dataclass(frozen=True)
class Mismatch:
    """One location whose member-name vocabulary diverges between the two schemas."""

    location: str
    missing_in_model: frozenset[str]
    missing_in_schema: frozenset[str]


@dataclass
class Report:
    """What the comparison found. An empty mismatch list means the two schemas agree."""

    locations_checked: int = 0
    mismatches: list[Mismatch] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.mismatches


def _deref(node: dict[str, Any], defs: dict[str, Any]) -> dict[str, Any]:
    """Chase a ``$ref`` chain to the schema it names; a no-op on a ``$ref``-free node."""
    while "$ref" in node:
        name = str(node["$ref"]).rsplit("/", 1)[-1]
        node = defs[name]
    return node


def _first_with(node: dict[str, Any], defs: dict[str, Any], key: str) -> dict[str, Any]:
    """The first ``oneOf``/``anyOf`` branch (after ``$ref`` resolution) carrying ``key``.

    Used where exactly one branch of an ``Optional[...]``-shaped union carries the object
    shape of interest (the other branches being e.g. ``{"type": "null"}``).
    """
    resolved = _deref(node, defs)
    if key in resolved:
        return resolved
    for branch in (*resolved.get("oneOf", ()), *resolved.get("anyOf", ())):
        try:
            return _first_with(branch, defs, key)
        except KeyError:
            continue
    raise KeyError(f"no branch of {resolved!r} carries {key!r}")


def _union_props(node: dict[str, Any], defs: dict[str, Any]) -> frozenset[str]:
    """The member-name vocabulary of ``node``, unioned across every ``oneOf``/``anyOf`` branch.

    A plain object schema (``{"properties": {...}}``) yields its own property names. A
    union — an ``Optional`` wrapper, a bool-or-object annotation slot, or the three-kind
    discriminated edge union — yields the union of every branch's names (a branch with no
    object shape, e.g. ``{"type": "boolean"}`` or ``{"type": "null"}``, contributes nothing).
    This is what lets one location (``edge``) stand for a discriminated union on one side and
    a single flat conditionally-required object on the other.
    """
    resolved = _deref(node, defs)
    if "properties" in resolved:
        return frozenset(resolved["properties"])
    names: set[str] = set()
    for branch in (*resolved.get("oneOf", ()), *resolved.get("anyOf", ())):
        names |= _union_props(branch, defs)
    return frozenset(names)


def build_vocabulary(root: dict[str, Any], defs: dict[str, Any]) -> dict[str, frozenset[str]]:
    """The 14-location field-name vocabulary of a ``gebra-ir``-shaped JSON Schema document.

    ``root`` is the schema carrying the seven top-level properties directly (``WorkflowIR``'s
    own ``model_json_schema()``, or ``schema.yaml``'s ``$defs.gebra-ir``); ``defs`` is where
    a ``$ref`` in ``root`` resolves (``model_json_schema()["$defs"]``, or ``{}`` — the fixture
    schema nests every sub-object inline and never uses ``$ref``).
    """
    try:
        root_props: dict[str, Any] = root["properties"]
        vocab: dict[str, frozenset[str]] = {"workflow": frozenset(root_props)}

        node_obj = _first_with(root_props["nodes"]["items"], defs, "properties")
        vocab["node"] = frozenset(node_obj["properties"])

        annotations_obj = _first_with(node_obj["properties"]["annotations"], defs, "properties")
        ann_props: dict[str, Any] = annotations_obj["properties"]
        vocab["annotations"] = frozenset(ann_props)

        vocab["idempotent_key"] = _union_props(ann_props["idempotent"], defs)
        vocab["deterministic_spec"] = _union_props(ann_props["deterministic"], defs)
        vocab["retry_policy"] = _union_props(ann_props["retry_policy"], defs)
        vocab["variant"] = _union_props(ann_props["variant"], defs)
        vocab["compensation"] = _union_props(ann_props["compensation"], defs)

        vocab["edge"] = _union_props(root_props["edges"]["items"], defs)

        runtime_obj = _first_with(root_props["runtime"], defs, "properties")
        runtime_props: dict[str, Any] = runtime_obj["properties"]
        vocab["runtime"] = frozenset(runtime_props)
        vocab["recursion_limit"] = _union_props(runtime_props["recursion_limit"], defs)
        vocab["interrupts"] = _union_props(runtime_props["interrupts"], defs)
        vocab["checkpointer"] = _union_props(runtime_props["checkpointer"], defs)

        state_obj = _first_with(root_props["state"], defs, "additionalProperties")
        vocab["state_field"] = _union_props(state_obj["additionalProperties"], defs)
    except KeyError as exc:
        raise SchemaLockstepError(f"schema is missing an expected member: {exc}") from exc

    assert set(vocab) == set(LOCATIONS), "build_vocabulary must fill every declared location"
    return vocab


def model_vocabulary() -> dict[str, frozenset[str]]:
    """The vocabulary of ``WorkflowIR.model_json_schema()`` — the model side of the lockstep."""
    schema = WorkflowIR.model_json_schema()
    return build_vocabulary(schema, schema.get("$defs", {}))


def fixture_schema_vocabulary(schema_path: Path) -> dict[str, frozenset[str]]:
    """The vocabulary of ``schema.yaml``'s ``$defs.gebra-ir`` — the vendored side."""
    document: Any = yaml.safe_load(schema_path.read_text(encoding="utf-8"))
    try:
        gebra_ir = document["$defs"]["gebra-ir"]
    except (KeyError, TypeError) as exc:
        raise SchemaLockstepError(f"{schema_path}: no $defs.gebra-ir found") from exc
    return build_vocabulary(gebra_ir, {})


def compare(
    model_vocab: dict[str, frozenset[str]], fixture_vocab: dict[str, frozenset[str]]
) -> Report:
    """Diff the two vocabularies location by location."""
    report = Report()
    for location in sorted(set(model_vocab) | set(fixture_vocab)):
        report.locations_checked += 1
        model_fields = model_vocab.get(location, frozenset())
        fixture_fields = fixture_vocab.get(location, frozenset())
        missing_in_model = fixture_fields - model_fields
        missing_in_schema = model_fields - fixture_fields
        if missing_in_model or missing_in_schema:
            report.mismatches.append(Mismatch(location, missing_in_model, missing_in_schema))
    return report


def check(schema_path: Path) -> Report:
    """Run the full lockstep check: the live model against the vendored fixture schema."""
    return compare(model_vocabulary(), fixture_schema_vocabulary(schema_path))


def format_report(report: Report) -> str:
    if report.ok:
        return (
            f"schema lockstep: OK — {report.locations_checked} location(s) agree between "
            "WorkflowIR.model_json_schema() and schema.yaml's gebra-ir $defs"
        )

    lines = [f"schema lockstep: FAILED — {report.locations_checked} location(s) checked"]
    for mismatch in report.mismatches:
        if mismatch.missing_in_model:
            lines.append(
                f"  {mismatch.location}: in schema.yaml but not the model: "
                f"{sorted(mismatch.missing_in_model)}"
            )
        if mismatch.missing_in_schema:
            lines.append(
                f"  {mismatch.location}: in the model but not schema.yaml: "
                f"{sorted(mismatch.missing_in_schema)}"
            )
    lines.append("")
    lines.append(
        "WorkflowIR.model_json_schema() and the vendored schema.yaml's gebra-ir $defs must "
        "agree on which fields exist at each location (IR-SPEC §2.5 note 5). schema.yaml is "
        "read-only (WA-04/WA-11) — never edit it here. If the model is right and the fixture "
        "schema needs a field added, that routes through R-05 vault sign-off (WA-04); if the "
        "model is missing a field the schema already carries, add it to the model."
    )
    return "\n".join(lines)


def build_parser(default_schema: Path) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="schema_lockstep.py",
        description=(
            "Verify WorkflowIR.model_json_schema() stays consistent with schema.yaml's "
            "gebra-ir $defs (IR-SPEC §2.5 note 5)."
        ),
    )
    parser.add_argument(
        "--schema",
        type=Path,
        default=default_schema,
        help=f"vendored fixture schema to compare against (default: {default_schema})",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    here = Path(__file__).resolve().parent
    default_schema = here.parent / "tests" / "fixtures" / "properties" / "schema.yaml"
    parser = build_parser(default_schema)
    args = parser.parse_args(argv)

    try:
        report = check(args.schema)
    except SchemaLockstepError as exc:
        print(f"schema lockstep: {exc}", file=sys.stderr)
        return 1

    print(format_report(report), file=sys.stdout if report.ok else sys.stderr)
    return 0 if report.ok else 1


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
