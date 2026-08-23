"""Shared plumbing for the display suite.

Hand-authored IRs go through the documented ingestion path (IR-SPEC §2.5 note 4), the same
idiom the verify and diff suites use; run reports come from ``verify()`` itself wherever a
test can use a real one, so overlay assertions are about reports the pipeline actually
produces rather than about shapes invented here.
"""

from __future__ import annotations

import json
from typing import Any

from gebra.ir import WorkflowIR
from gebra.ir.serialization import load_json

__all__ = ["ir_of", "nodes_of"]


def ir_of(document: dict[str, Any]) -> WorkflowIR:
    """A hand-authored IR through the documented ingestion path."""
    return load_json(WorkflowIR, json.dumps({"ir_version": "1.0", **document}))


def nodes_of(*ids: str) -> list[dict[str, str]]:
    return [{"id": node_id} for node_id in ids]
