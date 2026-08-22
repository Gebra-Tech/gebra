"""Regenerate or verify the version-drift goldens — the WA-05 lifecycle tool (GOV-05/06).

The drift suite (``tests/version_drift/test_version_drift.py``) compares each fixture in
:data:`tests.version_drift.workflows.CASES` against committed goldens under
``tests/version_drift/golden/`` — canonical core-IR bytes byte-identical, ``graph_version``
string-equal (VERSION-COMPAT §3 golden-equality contract) — plus, for the three cases that
carry one, a committed **document golden** beside the pair: the ``drawable-fidelity``
drawable payload, the ``schema-getters`` named-key schema projection, and the
``lcel-fragment`` name-keyed drawn topology. This tool is the sanctioned way to (re)take
those goldens when a justified change lands:

* ``--check`` re-extracts every fixture (and re-takes each document golden) and reports,
  per case, whether the committed golden still holds. CI does **not** run this — the pytest
  suite owns the CI gate; this is the reviewer's and implementer's view.
* ``--write`` retakes the goldens for every case (or the named ``--only`` cases). WA-05:
  run it only in a commit that carries the justification — a drift-suite run citation
  (matrix extension) or a ratified IR change with its ``ir_version`` bump and decision
  record. An unjustified golden diff is drift by definition and blocks.

Unlike the conformance set, **no case here is substrate-gated**: every drift golden must
hold on every frozen matrix cell (the suite's composition rule), so there is nothing to
refuse behind a gate — but ``--write`` still takes every case twice, in two orders, and
requires the results equal before touching a file, so an extraction-order dependence (or a
per-call drawing instability) cannot be committed as a golden.

WA-07: this tool extracts, draws, renders schemas and serializes only — it executes no
workflow node, router, reducer or subgraph, calls no model, and opens no network
connection. Every fixture body is armed (:data:`tests.version_drift.workflows.TRIPPED` is
checked around each take).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:  # pragma: no cover - import plumbing, not behaviour
    sys.path.insert(0, str(REPO_ROOT))

from gebra.extraction import extract
from gebra.ir.canonical import canonical_bytes
from tests.version_drift import documents, drawable, workflows

GOLDEN_DIR = REPO_ROOT / "tests" / "version_drift" / "golden"


class DriftToolError(RuntimeError):
    """A refusal this tool makes on purpose — armed fixture tripped, or unstable output."""


def _take_drawable_document() -> dict[str, Any]:
    """The row-4 document: the xray'd drawing's counts + flags, path-id keyed."""
    drawn = workflows.build_drawable_compiled().get_graph(xray=True)
    return drawable.drawable_payload(drawn)


def _take_schemas_document() -> dict[str, Any]:
    """The row-7 document: the named-key projection of both jsonschema getters."""
    compiled = workflows.build_schema_getters().compile()
    return documents.schema_payload(
        compiled.get_input_jsonschema(), compiled.get_output_jsonschema()
    )


def _take_lcel_document() -> dict[str, Any]:
    """The row-11 document: the drawn chain as names + topology (never raw ids)."""
    return documents.lcel_payload(workflows.build_lcel_fragment().get_graph())


#: The cases that carry a document golden beside the canonical/digest pair: committed
#: filename → taker. Filenames are also pinned by the suite's golden-directory test.
DOCUMENT_GOLDENS: dict[str, tuple[str, Callable[[], dict[str, Any]]]] = {
    "drawable-fidelity": ("drawable-fidelity.drawable.json", _take_drawable_document),
    "schema-getters": ("schema-getters.schemas.json", _take_schemas_document),
    "lcel-fragment": ("lcel-fragment.drawable.json", _take_lcel_document),
}


def _take(name: str) -> tuple[bytes, str, bytes | None]:
    """One case's golden set — build, extract (and take its document), serialize — under
    the ledger.

    The ledger is checked after serialization, so the whole window a fixture body could
    run in (build, extraction, drawing or rendering, canonicalization, digest) is covered —
    the same span the suite's autouse fixture covers per test.
    """
    del workflows.TRIPPED[:]
    case = workflows.CASES[name]
    envelope = extract(case.build())
    payload, digest = canonical_bytes(envelope.ir), envelope.graph_version()
    document_payload: bytes | None = None
    if name in DOCUMENT_GOLDENS:
        _, taker = DOCUMENT_GOLDENS[name]
        document = taker()
        document_payload = (json.dumps(document, indent=1, sort_keys=True) + "\n").encode("utf-8")
    if workflows.TRIPPED:
        raise DriftToolError(f"an armed fixture body was reached: {workflows.TRIPPED!r}")
    return payload, digest, document_payload


def _document_path(name: str) -> Path:
    return GOLDEN_DIR / DOCUMENT_GOLDENS[name][0]


def check(names: list[str]) -> int:
    """Compare every (selected) case against its committed goldens; 0 iff all hold."""
    failures = 0
    for name in names:
        canonical_path = GOLDEN_DIR / f"{name}.canonical.json"
        digest_path = GOLDEN_DIR / f"{name}.digest"
        if not canonical_path.is_file() or not digest_path.is_file():
            print(f"FAIL  {name}: golden pair missing under {GOLDEN_DIR}")
            failures += 1
            continue
        payload, digest, document_payload = _take(name)
        committed = canonical_path.read_bytes()
        committed_digest = digest_path.read_text(encoding="utf-8").strip()
        if payload != committed:
            print(f"FAIL  {name}: canonical bytes differ ({len(payload)} vs {len(committed)})")
            failures += 1
        elif digest != committed_digest:
            print(f"FAIL  {name}: graph_version differs ({digest} vs {committed_digest})")
            failures += 1
        elif f"sha256:{hashlib.sha256(committed).hexdigest()}" != committed_digest:
            print(f"FAIL  {name}: the committed pair is not self-consistent")
            failures += 1
        elif document_payload is not None and _document_mismatch(name, document_payload):
            print(f"FAIL  {name}: the document golden differs from the committed one")
            failures += 1
        else:
            print(f"OK    {name}: {len(payload)} bytes, {digest}")
    return failures


def _document_mismatch(name: str, document_payload: bytes) -> bool:
    """Whether the freshly taken document disagrees with the committed document golden.

    Parsed comparison, deliberately: the suite compares these goldens as documents (their
    contract is counts, flags, names and key sets — not a canonical byte form), so the
    tool holds them to the same standard.
    """
    path = _document_path(name)
    if not path.is_file():
        return True
    fresh: Any = json.loads(document_payload)
    committed: Any = json.loads(path.read_text(encoding="utf-8"))
    return bool(fresh != committed)


def write(names: list[str]) -> int:
    """Retake the goldens for every (selected) case, after a determinism double-take."""
    first = {name: _take(name) for name in names}
    for name in reversed(names):
        if _take(name) != first[name]:
            raise DriftToolError(
                f"{name}: two takes of an unchanged fixture disagree — refusing to write "
                "a golden that would pin an unstable extraction, drawing or rendering"
            )
    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    for name in names:
        payload, digest, document_payload = first[name]
        (GOLDEN_DIR / f"{name}.canonical.json").write_bytes(payload)
        (GOLDEN_DIR / f"{name}.digest").write_text(digest + "\n", encoding="utf-8")
        if document_payload is not None:
            _document_path(name).write_bytes(document_payload)
        print(f"WROTE {name}: {len(payload)} bytes, {digest}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="verify the committed goldens")
    mode.add_argument("--write", action="store_true", help="retake the goldens (WA-05!)")
    parser.add_argument(
        "--only",
        action="append",
        metavar="NAME",
        help="restrict to the named case (repeatable); default is every case",
    )
    arguments = parser.parse_args(argv)
    names = arguments.only or sorted(workflows.CASES)
    unknown = [name for name in names if name not in workflows.CASES]
    if unknown:
        parser.error(f"unknown case(s): {', '.join(unknown)}")
    if arguments.write:
        return write(names)
    return check(names)


if __name__ == "__main__":
    sys.exit(main())
