"""The deterministic emitter — SD-01 acceptance 1, "round-trip is byte-stable across runs".

Normative authority: PD-012's emitter rules (model declaration order, block style,
``allow_unicode``, UTF-8, LF, one trailing newline, ``None``-valued members omitted) and its
finding 6, which is what "byte-stable" can honestly mean here: **the same document object
serializes to the same bytes**. It is not a claim that two extractions of unchanged source
produce identical files — an ``extracted_at`` moves between them by design — and whether an
unchanged workflow is re-snapshot at all is SD-03's policy.

"Across runs" is checked where it can actually fail: in child interpreters under four
different ``PYTHONHASHSEED`` values. Nothing else in one process would distinguish a run from
a repeat.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

from gebra.ir.models import Annotations, Node, WorkflowIR
from gebra.ir.serialization import IRSerializationError, IRSerializationErrorReason
from gebra.store import (
    Snapshot,
    SnapshotRecord,
    StoreMeta,
    dump_meta,
    dump_snapshot,
    load_meta,
    load_snapshot,
)
from tests.store.hand_built import (
    ALL_IRS,
    GOLDEN_VECTOR_DIGEST,
    YAML_BREAK_CHARACTERS,
    awkward_ir,
    extracted_from,
    golden_vector_ir,
    minimal_ir,
    snapshot_of,
)

REPO_ROOT = Path(__file__).resolve().parents[2]

ALL_IR_CASES = pytest.mark.parametrize("build", ALL_IRS.values(), ids=ALL_IRS.keys())


def _meta() -> StoreMeta:
    return StoreMeta().appended(
        SnapshotRecord(
            version="1.0.0.0",
            graph_version=GOLDEN_VECTOR_DIGEST,
            created_at="2026-08-04T09:00:00Z",
        )
    )


# ── Round trip ───────────────────────────────────────────────────────────────────────────


@ALL_IR_CASES
def test_a_snapshot_reloads_equal_to_its_source(build: Callable[[], WorkflowIR]) -> None:
    """SOW §2 criterion 6, at the store's surface: ``==`` is pydantic model equality, field
    by field, never string equality of the text."""
    snapshot = snapshot_of(build())

    assert load_snapshot(dump_snapshot(snapshot)) == snapshot


def test_the_index_reloads_equal_to_its_source() -> None:
    meta = _meta()

    assert load_meta(dump_meta(meta)) == meta


def test_an_empty_index_round_trips_through_an_omitted_pointer() -> None:
    """A6 PC-4: an omitted optional member round-trips to omitted rather than to ``null``."""
    text = dump_meta(StoreMeta())

    assert "current" not in text
    assert load_meta(text) == StoreMeta()


def test_the_bytes_survive_a_utf8_round_trip_through_a_file(tmp_path: Path) -> None:
    text = dump_snapshot(snapshot_of(awkward_ir()))
    path = tmp_path / "1.0.0.0.yaml"
    path.write_text(text, encoding="utf-8", newline="\n")

    assert load_snapshot(path.read_bytes()) == snapshot_of(awkward_ir())


def test_the_yaml_break_characters_survive_the_round_trip() -> None:
    """The store inherits IR-04's string-quoting correction rather than owning a second copy.
    Left uncorrected, PyYAML writes NEL / LINE SEPARATOR / PARAGRAPH SEPARATOR / BOM raw
    inside a single-quoted scalar and its own parser folds them back as line breaks — a
    silent truncation of a ``condition`` or a ``justification``."""
    reloaded = load_snapshot(dump_snapshot(snapshot_of(awkward_ir())))

    limit = reloaded.ir.runtime.recursion_limit if reloaded.ir.runtime else None
    assert limit is not None
    assert YAML_BREAK_CHARACTERS in limit.justification


def test_foreign_json_schema_content_is_carried_verbatim() -> None:
    """``args_schema`` is a foreign JSON Schema object 1.0 imposes no algebra on (IR-SPEC
    §3.1), including its authored array order (§6.2's last row)."""
    reloaded = load_snapshot(dump_snapshot(snapshot_of(awkward_ir())))
    schema = (
        reloaded.ir.nodes[0].annotations.args_schema if reloaded.ir.nodes[0].annotations else None
    )

    assert schema is not None
    assert schema["prefixItems"] == [{"type": "integer"}, {"type": "string"}]
    assert schema["required"] == []


# ── The emitter rules (PD-012) ───────────────────────────────────────────────────────────


def test_the_envelope_is_emitted_in_declaration_order_never_alphabetized() -> None:
    """PD-012 Option C rejected: nothing reads a snapshot expecting JCS/alphabetical order,
    since the digest is computed from the parsed model and never from these bytes (IR-SPEC
    §6.1 step 1). Alphabetical order would put ``extracted_from`` first and ``version`` last."""
    lines = dump_snapshot(snapshot_of(golden_vector_ir())).splitlines()
    top_level = [line.split(":")[0] for line in lines if line and not line[0].isspace()]

    assert top_level == ["version", "extracted_from", "graph_version", "ir"]


def test_the_nested_ir_keeps_the_workflowir_declaration_order() -> None:
    lines = dump_snapshot(snapshot_of(golden_vector_ir())).splitlines()
    nested = [line[2:].split(":")[0] for line in lines if line.startswith("  ") and line[2] != " "]
    ir_keys = [key for key in nested if key in set(WorkflowIR.model_fields)]

    assert ir_keys == ["ir_version", "entry", "finish", "state", "nodes", "edges", "runtime"]


def test_the_index_is_emitted_in_declaration_order() -> None:
    lines = dump_meta(_meta()).splitlines()
    top_level = [
        line.split(":")[0] for line in lines if line and not line[0].isspace() and line[0] != "-"
    ]
    row = [line.lstrip("- ").split(":")[0] for line in lines if line.startswith(("- ", "  "))]

    assert top_level == ["store_version", "current", "history"]
    assert row == ["version", "graph_version", "created_at"]


@ALL_IR_CASES
def test_the_text_is_block_style_lf_terminated_with_exactly_one_trailing_newline(
    build: Callable[[], WorkflowIR],
) -> None:
    text = dump_snapshot(snapshot_of(build()))

    assert "\r" not in text
    assert text.endswith("\n")
    assert not text.endswith("\n\n")
    assert not text.startswith("{")  # block style, never flow


def test_non_ascii_is_written_as_itself_rather_than_escaped() -> None:
    """``allow_unicode=True`` — the git-diff reason D-11 states directly: a snapshot a person
    can read in a review is one whose content is not ``\\uXXXX``.

    The four characters of :data:`YAML_BREAK_CHARACTERS` are the deliberate exception: they
    are escaped precisely so they survive, and the round-trip test above is what holds that.
    """
    text = dump_snapshot(snapshot_of(awkward_ir()))

    assert "début" in text
    assert "résultat" in text
    assert "«prêt»" in text
    assert "\\u00e9" not in text  # é, escaped, is what ensure_ascii would have written


def test_an_absent_optional_member_leaves_no_line_behind() -> None:
    text = dump_snapshot(snapshot_of(minimal_ir()))

    assert "sidecar_path" not in text
    assert "null" not in text


# ── Determinism — acceptance 1 ───────────────────────────────────────────────────────────


@ALL_IR_CASES
def test_the_same_snapshot_emits_identical_bytes_twice(build: Callable[[], WorkflowIR]) -> None:
    snapshot = snapshot_of(build())

    assert dump_snapshot(snapshot) == dump_snapshot(snapshot)


@ALL_IR_CASES
def test_two_equal_snapshots_built_independently_emit_identical_bytes(
    build: Callable[[], WorkflowIR],
) -> None:
    """The stronger in-process form: not the same object twice, but two objects that compare
    equal — so nothing identity-derived (an ``id()``, a memo address) can be reaching the
    bytes."""
    one, other = snapshot_of(build()), snapshot_of(build())

    assert one == other
    assert dump_snapshot(one) == dump_snapshot(other)


@ALL_IR_CASES
def test_a_reloaded_snapshot_re_emits_the_bytes_it_was_read_from(
    build: Callable[[], WorkflowIR],
) -> None:
    """Write → read → write is the fixed point that keeps ``git diff`` on ``.gebra/`` clean:
    re-storing an unchanged snapshot changes no byte."""
    text = dump_snapshot(snapshot_of(build()))

    assert dump_snapshot(load_snapshot(text)) == text


def test_the_index_re_emits_the_bytes_it_was_read_from() -> None:
    text = dump_meta(_meta())

    assert dump_meta(load_meta(text)) == text


_ACROSS_RUNS = """\
import hashlib
from gebra.store import dump_meta, dump_snapshot, SnapshotRecord, StoreMeta
from tests.store.hand_built import ALL_IRS, GOLDEN_VECTOR_DIGEST, snapshot_of

digest = hashlib.sha256()
for name, build in sorted(ALL_IRS.items()):
    digest.update(dump_snapshot(snapshot_of(build(), version="1.0.0.0")).encode("utf-8"))
meta = StoreMeta().appended(
    SnapshotRecord(
        version="1.0.0.0",
        graph_version=GOLDEN_VECTOR_DIGEST,
        created_at="2026-08-04T09:00:00Z",
    )
)
digest.update(dump_meta(meta).encode("utf-8"))
print(digest.hexdigest())
"""


def test_the_bytes_are_identical_across_runs_under_different_hash_seeds() -> None:
    """Acceptance 1's "across runs", checked where a run differs from a repeat.

    One interpreter cannot observe the failure modes that word is about: a ``set`` iterates in
    ``PYTHONHASHSEED`` order, and ``id()``-derived text differs per process. Four child
    interpreters under four seeds emit every fixture and must print one digest.

    Platform independence is not simulable here. What is checked instead is the property it
    rests on — the emitter is a function of the document's values, and the two process-varying
    inputs these seeds move are the ones that could make it otherwise.
    """
    runs = {
        seed: subprocess.run(
            [sys.executable, "-c", _ACROSS_RUNS],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
            env={**os.environ, "PYTHONHASHSEED": seed},
        )
        for seed in ("0", "1", "777", "12345")
    }

    for seed, run in runs.items():
        assert run.returncode == 0, (seed, run.stderr)
    printed = {run.stdout.strip() for run in runs.values()}
    assert len(printed) == 1, runs
    assert len(next(iter(printed))) == len(hashlib.sha256().hexdigest())


# ── Refusals: the surface guards the store inherits ──────────────────────────────────────


def test_a_document_that_is_not_yaml_is_refused_by_reason() -> None:
    with pytest.raises(IRSerializationError) as caught:
        load_snapshot("version: [unclosed\n")

    assert caught.value.reason is IRSerializationErrorReason.YAML_SYNTAX


def test_a_non_string_key_inside_foreign_content_is_refused_never_coerced() -> None:
    """The IR surface path's guard, reached through the store: ``{1: "x"}`` becoming
    ``{"1": "x"}`` is how a document silently changes meaning on the way in."""
    text = dump_snapshot(snapshot_of(minimal_ir())).replace(
        "  - id: only\n",
        "  - id: only\n    annotations:\n      args_schema:\n        1: x\n",
    )

    with pytest.raises(IRSerializationError) as caught:
        load_snapshot(text)

    assert caught.value.reason is IRSerializationErrorReason.NON_STRING_KEY


def test_a_non_finite_number_inside_foreign_content_is_refused() -> None:
    text = dump_snapshot(snapshot_of(minimal_ir())).replace(
        "  - id: only\n",
        "  - id: only\n    annotations:\n      args_schema:\n        maximum: .nan\n",
    )

    with pytest.raises(IRSerializationError) as caught:
        load_snapshot(text)

    assert caught.value.reason is IRSerializationErrorReason.NON_FINITE_NUMBER


def test_a_yaml_scalar_json_cannot_carry_is_refused() -> None:
    text = dump_snapshot(snapshot_of(minimal_ir())).replace(
        "  - id: only\n",
        "  - id: only\n    annotations:\n      args_schema:\n        seen: 2026-08-04\n",
    )

    with pytest.raises(IRSerializationError) as caught:
        load_snapshot(text)

    assert caught.value.reason is IRSerializationErrorReason.UNSUPPORTED_TYPE


def test_a_document_nested_past_the_parser_is_refused_rather_than_overflowing() -> None:
    """A store file is not trusted input just because it sits under ``.gebra/``: the ceiling
    that keeps a short document from expanding without bound applies on the way in."""
    with pytest.raises(IRSerializationError) as caught:
        load_snapshot("version: 1.0.0.0\ngraph_version: " + "[" * 20_000 + "]" * 20_000 + "\n")

    assert caught.value.reason is IRSerializationErrorReason.TOO_COMPLEX


def test_a_snapshot_document_that_is_not_a_snapshot_is_refused_by_validation() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        load_snapshot("version: '1.0.0.0'\ngraph_version: not-a-digest\n")


def test_an_index_breaking_a_history_invariant_is_refused_on_load() -> None:
    """A hand-edited ``meta.yaml`` is refused at the boundary rather than believed."""
    from pydantic import ValidationError

    doubled = dump_meta(_meta()).replace(
        "history:\n",
        "history:\n- version: 1.0.0.0\n  graph_version: "
        f"{GOLDEN_VECTOR_DIGEST}\n  created_at: '2026-08-04T09:00:00Z'\n",
    )

    with pytest.raises(ValidationError, match="append-only"):
        load_meta(doubled)


def test_the_emitter_refuses_ir_content_json_cannot_represent() -> None:
    """The refusal reaches the *write* side too: a model hand-built with a value JSON has no
    form for cannot be smuggled into the store by dumping it."""
    ir = WorkflowIR(
        ir_version="1.0",
        entry="plan",
        finish="plan",
        nodes=(Node(id="plan", annotations=Annotations(args_schema={"maximum": float("inf")})),),
        edges=(),
    )

    with pytest.raises(IRSerializationError) as caught:
        dump_snapshot(
            Snapshot(
                version="1.0.0.0",
                extracted_from=extracted_from(),
                graph_version=GOLDEN_VECTOR_DIGEST,
                ir=ir,
            )
        )

    assert caught.value.reason is IRSerializationErrorReason.NON_FINITE_NUMBER
