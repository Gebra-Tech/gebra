"""Regenerate or verify the version-drift goldens — the WA-05 lifecycle tool (GOV-05).

The drift suite (``tests/version_drift/test_version_drift.py``) compares each fixture in
:data:`tests.version_drift.workflows.CASES` against committed goldens under
``tests/version_drift/golden/`` — canonical core-IR bytes byte-identical, ``graph_version``
string-equal (VERSION-COMPAT §3 golden-equality contract), plus, for ``drawable-fidelity``,
the drawable payload (node/edge counts + per-edge conditional booleans, path-id keyed).
This tool is the sanctioned way to (re)take those goldens when a justified change lands:

* ``--check`` re-extracts every fixture (and re-draws the drawable one) and reports, per
  case, whether the committed golden still holds. CI does **not** run this — the pytest
  suite owns the CI gate; this is the reviewer's and implementer's view.
* ``--write`` retakes the goldens for every case (or the named ``--only`` cases). WA-05:
  run it only in a commit that carries the justification — a drift-suite run citation
  (matrix extension) or a ratified IR change with its ``ir_version`` bump and decision
  record. An unjustified golden diff is drift by definition and blocks.

Unlike the conformance set, **no case here is substrate-gated**: every drift golden must
hold on every frozen matrix cell (the suite's composition rule), so there is nothing to
refuse behind a gate — but ``--write`` still extracts every case twice, in two orders, and
requires the results equal before touching a file, so an extraction-order dependence cannot
be committed as a golden.

WA-07: this tool extracts, draws and serializes only — it executes no workflow node, router
or subgraph, calls no model, and opens no network connection. Every fixture body is armed
(:data:`tests.version_drift.workflows.TRIPPED` is checked around each take).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:  # pragma: no cover - import plumbing, not behaviour
    sys.path.insert(0, str(REPO_ROOT))

from gebra.extraction import extract
from gebra.ir.canonical import canonical_bytes
from tests.version_drift import drawable, workflows

GOLDEN_DIR = REPO_ROOT / "tests" / "version_drift" / "golden"

#: The one case that carries a second golden: the drawable payload beside the core IR.
DRAWABLE_CASE = "drawable-fidelity"


class DriftToolError(RuntimeError):
    """A refusal this tool makes on purpose — armed fixture tripped, or unstable output."""


def _take(name: str) -> tuple[bytes, str, bytes | None]:
    """One case's golden set — build, extract (and draw), serialize — under the ledger.

    The ledger is checked after serialization, so the whole window a fixture body could
    run in (build, extraction, drawing, canonicalization, digest) is covered — the same
    span the suite's autouse fixture covers per test.
    """
    del workflows.TRIPPED[:]
    case = workflows.CASES[name]
    envelope = extract(case.build())
    payload, digest = canonical_bytes(envelope.ir), envelope.graph_version()
    drawn_payload: bytes | None = None
    if name == DRAWABLE_CASE:
        drawn = workflows.build_drawable_compiled().get_graph(xray=True)
        document = drawable.drawable_payload(drawn)
        drawn_payload = (json.dumps(document, indent=1, sort_keys=True) + "\n").encode("utf-8")
    if workflows.TRIPPED:
        raise DriftToolError(f"an armed fixture body was reached: {workflows.TRIPPED!r}")
    return payload, digest, drawn_payload


def _drawable_path() -> Path:
    return GOLDEN_DIR / f"{DRAWABLE_CASE}.drawable.json"


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
        payload, digest, drawn_payload = _take(name)
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
        elif drawn_payload is not None and _drawable_mismatch(drawn_payload):
            print(f"FAIL  {name}: the drawable payload differs from the committed golden")
            failures += 1
        else:
            print(f"OK    {name}: {len(payload)} bytes, {digest}")
    return failures


def _drawable_mismatch(drawn_payload: bytes) -> bool:
    """Whether the freshly drawn payload disagrees with the committed drawable golden.

    Parsed comparison, deliberately: the suite compares this golden as a document (its
    contract is counts + flags + path ids, not a canonical byte form), so the tool holds
    it to the same standard.
    """
    path = _drawable_path()
    if not path.is_file():
        return True
    fresh: Any = json.loads(drawn_payload)
    committed: Any = json.loads(path.read_text(encoding="utf-8"))
    return bool(fresh != committed)


def write(names: list[str]) -> int:
    """Retake the goldens for every (selected) case, after a determinism double-take."""
    first = {name: _take(name) for name in names}
    for name in reversed(names):
        if _take(name) != first[name]:
            raise DriftToolError(
                f"{name}: two takes of an unchanged fixture disagree — refusing to write "
                "a golden that would pin an unstable extraction or drawing"
            )
    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    for name in names:
        payload, digest, drawn_payload = first[name]
        (GOLDEN_DIR / f"{name}.canonical.json").write_bytes(payload)
        (GOLDEN_DIR / f"{name}.digest").write_text(digest + "\n", encoding="utf-8")
        if drawn_payload is not None:
            _drawable_path().write_bytes(drawn_payload)
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
