"""Live corpus gate: every vendored property fixture parses and is well-formed.

Corpus: tests/fixtures/properties/ — vendored from Gebra-Tech/initial-documents
from the specification vault (read-only). Every fixture must YAML-parse, carry ``property`` and
``expected`` keys, and every embedded IR block must be pinned to the frozen
``ir_version`` 1.0.

This is the scaffold gate, kept as a dependency-light floor. The full corpus lint —
schema v2.2 conformance, one IR shape per fixture, per-directory minimums, serial
collisions, witness/failure presence — is ``tools/corpus_lint.py``, exercised by
``tests/testing/test_corpus_lint.py`` and run as its own CI job.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from tests.conftest import FIXTURES_DIR

IR_BLOCK_KEYS = ("ir", "ir_before", "ir_after")
MIN_FIXTURES = 71


def _fixture_files() -> list[Path]:
    return sorted(p for p in FIXTURES_DIR.rglob("*.yaml") if p.name != "schema.yaml")


def test_corpus_present() -> None:
    files = _fixture_files()
    assert len(files) >= MIN_FIXTURES, (
        f"expected at least {MIN_FIXTURES} fixture files under {FIXTURES_DIR}, "
        f"found {len(files)} — is the fixture corpus complete?"
    )


def test_corpus_parses() -> None:
    errors: list[str] = []
    for path in _fixture_files():
        rel = path.relative_to(FIXTURES_DIR)
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            errors.append(f"{rel}: YAML parse error: {exc}")
            continue
        if not isinstance(data, dict):
            errors.append(f"{rel}: top level is {type(data).__name__}, expected mapping")
            continue
        for key in ("property", "expected"):
            if key not in data:
                errors.append(f"{rel}: missing required key {key!r}")
        ir_blocks = {k: data[k] for k in IR_BLOCK_KEYS if k in data}
        if not ir_blocks:
            errors.append(f"{rel}: no ir / ir_before / ir_after block")
        for key, block in ir_blocks.items():
            if not isinstance(block, dict) or block.get("ir_version") != "1.0":
                errors.append(f"{rel}: {key} block does not carry ir_version == '1.0'")
    assert not errors, "corpus fixture defects:\n" + "\n".join(errors)
