"""Regenerate or verify the extractor-conformance goldens — the WA-05 lifecycle tool.

The conformance suite (``tests/extraction/test_conformance.py``) compares each workflow in
:data:`tests.sample_workflows.conformance.CASES` against committed goldens under
``tests/extraction/golden/conformance/`` — canonical bytes byte-identical, ``graph_version``
string-equal (IR-SPEC §1.2, extractor conformance; SOW §2 criterion 3). This tool is the
sanctioned way to (re)take those goldens when a justified change lands:

* ``--check`` re-extracts every workflow and reports, per case, whether the committed pair
  still holds. CI does **not** run this — the pytest suite owns the CI gate; this is the
  reviewer's and implementer's view.
* ``--write`` re-extracts and rewrites the golden pair for every case (or the named
  ``--only`` cases). WA-05: run it only in a commit that carries the justification — a
  drift-suite run citation or a ratified IR change with its ``ir_version`` bump and decision
  record. An unjustified golden diff is drift by definition and blocks.

Two guard rails, both refusals rather than options:

* A substrate-gated case (see ``ConformanceCase.gate``) is **skipped by** ``--check`` and
  **refused by** ``--write`` when its gate is closed: goldens are taken at the pinned
  development substrate, never at whatever happens to be installed.
* ``--write`` extracts every case twice in two orders and requires the two byte strings
  equal before touching a file — a cheap in-process determinism check so an
  extraction-order dependence cannot be committed as a golden.

WA-07: this tool extracts and serializes only — it executes no workflow node, router or
tool, calls no model, and opens no network connection. Every fixture body is armed
(:data:`tests.sample_workflows.conformance.TRIPPED` is checked after each extraction).
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:  # pragma: no cover - import plumbing, not behaviour
    sys.path.insert(0, str(REPO_ROOT))

from gebra.extraction import ExtractionEnvelope, extract
from gebra.ir.canonical import canonical_bytes
from tests.sample_workflows import conformance

GOLDEN_DIR = REPO_ROOT / "tests" / "extraction" / "golden" / "conformance"


class ConformanceToolError(RuntimeError):
    """A refusal this tool makes on purpose — armed fixture tripped, or gate closed."""


def _take(case: conformance.ConformanceCase) -> tuple[bytes, str]:
    """One case's golden pair — build, extract, serialize — under the armed-ledger check.

    The ledger is checked after serialization, not merely after ``extract()`` returns, so
    the whole window a fixture body could run in (build, extraction, canonicalization,
    digest) is covered — the same span the suite's autouse fixture covers per test.
    """
    del conformance.TRIPPED[:]
    workflow = case.build()
    if case.sidecar is None:
        envelope: ExtractionEnvelope = extract(workflow)
    else:
        with tempfile.TemporaryDirectory() as scratch:
            sidecar = Path(scratch) / "gebra.toml"
            sidecar.write_text(case.sidecar, encoding="utf-8")
            envelope = extract(workflow, sidecar=sidecar)
    pair = canonical_bytes(envelope.ir), envelope.graph_version()
    if conformance.TRIPPED:
        raise ConformanceToolError(f"an armed fixture body was reached: {conformance.TRIPPED!r}")
    return pair


def check(names: list[str]) -> int:
    """Compare every (selected) case against its committed pair; 0 iff all hold."""
    failures = 0
    for name in names:
        case = conformance.CASES[name]
        if case.gate is not None and not case.gate.available:
            print(f"SKIP  {name}: {case.gate.reason}")
            continue
        canonical_path = GOLDEN_DIR / f"{name}.canonical.json"
        digest_path = GOLDEN_DIR / f"{name}.digest"
        if not canonical_path.is_file() or not digest_path.is_file():
            print(f"FAIL  {name}: golden pair missing under {GOLDEN_DIR}")
            failures += 1
            continue
        payload, digest = _take(case)
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
        else:
            print(f"OK    {name}: {len(payload)} bytes, {digest}")
    return failures


def write(names: list[str]) -> int:
    """Retake the golden pair for every (selected) case. Refuses behind a closed gate."""
    first: dict[str, tuple[bytes, str]] = {}
    for name in names:
        case = conformance.CASES[name]
        if case.gate is not None and not case.gate.available:
            raise ConformanceToolError(
                f"{name}: refusing to take a golden behind its substrate gate — {case.gate.reason}"
            )
        first[name] = _take(case)
    # The determinism pass: every case again, in reverse, before anything is written.
    for name in reversed(names):
        payload, digest = _take(conformance.CASES[name])
        if (payload, digest) != first[name]:
            raise ConformanceToolError(
                f"{name}: two extractions of an unchanged workflow disagree — refusing to "
                "write a golden that would pin an unstable serialization"
            )
    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    for name in names:
        payload, digest = first[name]
        (GOLDEN_DIR / f"{name}.canonical.json").write_bytes(payload)
        (GOLDEN_DIR / f"{name}.digest").write_text(digest + "\n", encoding="utf-8")
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
    names = arguments.only or sorted(conformance.CASES)
    unknown = [name for name in names if name not in conformance.CASES]
    if unknown:
        parser.error(f"unknown case(s): {', '.join(unknown)}")
    if arguments.write:
        return write(names)
    return check(names)


if __name__ == "__main__":
    sys.exit(main())
