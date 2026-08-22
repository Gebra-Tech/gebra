"""Second-golden document projections for drift tests 7 and 11 — pure functions.

Two §3 rows compare a substrate document beside the core-IR golden, the way row 4 compares
its drawable payload (``tests/version_drift/drawable.py``); this module holds those two
projections so the suite and the golden tool (``tools/drift_goldens.py``) build byte-for-byte
the same committed documents:

* **Row 7** — :func:`schema_payload`: the row's *named-key* hard projection of the two
  jsonschema getter results — ``title``, ``type``, and the ``properties`` key set with each
  key's ``type`` — for the input and output schema each. Everything else in the rendered
  schema (``required`` order, per-property ``title``, ``items``) is deliberately outside the
  hard document: §3 row 7 assigns full-dict equality to the **soft** half, because the full
  rendering churns with the (transitively pinned) pydantic.
* **Row 11** — :func:`lcel_payload`: the drawn LCEL graph as **names + topology**, the only
  stable reading — raw drawn ids are fresh ``uuid4`` per call (A1 §7) and must never key
  anything. Faithful only while drawn names are unique, so the projection **refuses** a
  drawing with duplicate names rather than aliasing two nodes into one; the committed
  golden holds counts, the sorted name set, and the name-keyed edge triples.

Both functions take already-fetched objects (the schema dicts, the drawn graph) and read
attributes and container members only; fetching — the getter calls, the drawing — happens
at the caller, under the suite's armed-fixture ledger (WA-07).
"""

from __future__ import annotations

from typing import Any

from tests.version_drift.drawable import drawn_edges


def schema_payload(input_schema: Any, output_schema: Any) -> dict[str, Any]:
    """The row-7 hard document: the named-key projection of both getter results."""
    return {
        "input": _named_keys(input_schema),
        "output": _named_keys(output_schema),
    }


def _named_keys(schema: Any) -> dict[str, Any]:
    """One schema's ``title``/``type`` plus its ``properties`` key set and per-key type."""
    if not isinstance(schema, dict):
        return {"malformed": type(schema).__name__}
    properties = schema.get("properties")
    per_key = (
        {
            str(key): (value.get("type") if isinstance(value, dict) else None)
            for key, value in properties.items()
        }
        if isinstance(properties, dict)
        else None
    )
    return {
        "properties": per_key,
        "title": schema.get("title"),
        "type": schema.get("type"),
    }


class DuplicateDrawnNames(AssertionError):
    """Two drawn nodes share a name, so a name-keyed reading would alias them."""


def lcel_payload(drawn: object) -> dict[str, Any]:
    """The row-11 golden document: counts, sorted names, and name-keyed edge triples.

    Node identity here is the drawn **name** — never the raw id, which is uuid-fresh per
    call. The reading is faithful exactly while names are unique in the drawing, so a
    duplicate name raises :class:`DuplicateDrawnNames` instead of producing a document that
    quietly merged two nodes.
    """
    names = drawn_names(drawn)
    if len(set(names.values())) != len(names):
        raise DuplicateDrawnNames(f"drawn names are not unique: {sorted(names.values())}")
    edges = [
        {"conditional": conditional, "from": names[source], "to": names[target]}
        for source, target, conditional in drawn_edges(drawn)
        if source in names and target in names
    ]
    edges.sort(key=lambda edge: (edge["from"], edge["to"], edge["conditional"]))
    return {
        "edge_count": len(edges),
        "edges": edges,
        "node_count": len(names),
        "nodes": sorted(names.values()),
    }


def drawn_names(drawn: object) -> dict[str, str]:
    """Raw drawn id → drawn node name, reading ``.nodes`` values' ``name`` members only."""
    nodes = getattr(drawn, "nodes", None)
    names: dict[str, str] = {}
    if isinstance(nodes, dict):
        for identifier, node in nodes.items():
            name = getattr(node, "name", None)
            if isinstance(identifier, str) and isinstance(name, str):
                names[identifier] = name
    return names
