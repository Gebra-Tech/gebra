"""Behaviour tests for the schema-lockstep guard (IR-05, IR-SPEC §2.5 note 5).

The guard is the CI enforcement of one rule: ``WorkflowIR.model_json_schema()`` and the
vendored ``schema.yaml``'s ``gebra-ir`` ``$defs`` must agree on which fields exist at each of
14 conceptual locations. These tests pin what that means in practice — the real pair agrees
today, a field renamed or added in a sandbox copy of the vendored schema is reported (or, for
a whole nested object dropped, raises a clear error) rather than passing silently, and the two
already-ruled requiredness divergences (``RecursionLimit.justification``; the
``retry_policy``/``variant``/``compensation`` sub-fields) are *not* flagged, by design — this
guard never reads requiredness at all.

Everything here reads schema dictionaries and a sandboxed copy of ``schema.yaml``. The two
subprocess tests run the guard script itself — the exact command CI runs, so its exit status
is observed rather than assumed. No workflow node is executed, no LLM is called, no socket is
opened (WA-07).
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

from tools.schema_lockstep import (
    LOCATIONS,
    Mismatch,
    Report,
    SchemaLockstepError,
    check,
    compare,
    fixture_schema_vocabulary,
    format_report,
    model_vocabulary,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
GUARD = REPO_ROOT / "tools" / "schema_lockstep.py"
SCHEMA = REPO_ROOT / "tests" / "fixtures" / "properties" / "schema.yaml"
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"


@pytest.fixture
def sandbox_schema(tmp_path: Path) -> Path:
    """A throwaway copy of the vendored schema — tampering happens here, never on the real file."""
    copy = tmp_path / "schema.yaml"
    shutil.copy2(SCHEMA, copy)
    return copy


def _mutate(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    assert old in text, f"expected substring not found in {path}: {old!r}"
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def _run_guard(*args: str) -> subprocess.CompletedProcess[str]:
    """Run the guard exactly as CI does — as a script, on a clean interpreter."""
    return subprocess.run(
        [sys.executable, str(GUARD), *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


# ── The recorded state of this repository ──


def test_the_real_pair_agrees() -> None:
    """The premise of every other test: the model and the vendored schema agree right now."""
    report = check(SCHEMA)
    assert report.ok, report.mismatches
    assert report.locations_checked == len(LOCATIONS)


def test_model_vocabulary_covers_every_declared_location() -> None:
    assert set(model_vocabulary()) == set(LOCATIONS)


def test_fixture_vocabulary_covers_every_declared_location() -> None:
    assert set(fixture_schema_vocabulary(SCHEMA)) == set(LOCATIONS)


# ── The comparison strategy: field-name vocabulary, not requiredness ──


def test_compare_is_clean_on_two_identical_vocabularies() -> None:
    vocab = model_vocabulary()
    assert compare(vocab, vocab).ok


def test_compare_reports_a_field_present_only_in_the_schema() -> None:
    model_vocab = {"annotations": frozenset({"pure", "effect"})}
    fixture_vocab = {"annotations": frozenset({"pure", "effect", "args_schema"})}

    report = compare(model_vocab, fixture_vocab)

    assert not report.ok
    assert len(report.mismatches) == 1
    mismatch = report.mismatches[0]
    assert mismatch.location == "annotations"
    assert mismatch.missing_in_model == frozenset({"args_schema"})
    assert mismatch.missing_in_schema == frozenset()


def test_compare_reports_a_field_present_only_in_the_model() -> None:
    model_vocab = {"runtime": frozenset({"recursion_limit", "interrupts", "checkpointer"})}
    fixture_vocab = {"runtime": frozenset({"recursion_limit", "interrupts"})}

    report = compare(model_vocab, fixture_vocab)

    assert not report.ok
    assert report.mismatches[0].missing_in_schema == frozenset({"checkpointer"})
    assert report.mismatches[0].missing_in_model == frozenset()


def test_the_recursion_limit_justification_requiredness_divergence_is_not_flagged() -> None:
    """IR-01's recorded ruling: the model hardens ``justification`` to REQUIRED; the vendored
    schema requires only ``value``. This guard owns that divergence by never comparing
    requiredness — both sides still carry the member names ``value`` and ``justification``.
    """
    model_vocab = model_vocabulary()
    fixture_vocab = fixture_schema_vocabulary(SCHEMA)
    assert (
        model_vocab["recursion_limit"]
        == fixture_vocab["recursion_limit"]
        == {
            "value",
            "justification",
        }
    )
    assert compare(model_vocab, fixture_vocab).ok


@pytest.mark.parametrize("location", ["retry_policy", "variant", "compensation"])
def test_the_annotation_sub_object_requiredness_divergence_is_not_flagged(location: str) -> None:
    """IR-01 carry-forward: ``schema.yaml`` carries no ``required`` list for these three
    objects while every model field is required — a requiredness divergence this guard is
    designed not to see, since it only compares which member names exist.
    """
    model_vocab = model_vocabulary()
    fixture_vocab = fixture_schema_vocabulary(SCHEMA)
    assert model_vocab[location] == fixture_vocab[location]


def test_the_id_grammar_constraint_invisible_to_the_schema_is_not_flagged() -> None:
    """IR-02 carry-forward: ``nodes[].id`` carries a grammar ``AfterValidator`` invisible to
    ``model_json_schema()``; both sides declare a bare ``id`` string member, which is all this
    guard ever looks at.
    """
    assert (
        model_vocabulary()["node"]
        == fixture_schema_vocabulary(SCHEMA)["node"]
        == {
            "id",
            "annotations",
        }
    )


# ── What the guard rejects: seeded divergences on a sandboxed copy of the vendored schema ──


def test_a_field_renamed_in_the_vendored_schema_is_reported(sandbox_schema: Path) -> None:
    """The acceptance criterion: a seeded model/schema divergence is caught, not silently green."""
    _mutate(sandbox_schema, "hook: { type: string }", "hooks: { type: string }")

    report = check(sandbox_schema)

    assert not report.ok
    mismatch = next(m for m in report.mismatches if m.location == "compensation")
    assert mismatch.missing_in_model == frozenset({"hooks"})
    assert mismatch.missing_in_schema == frozenset({"hook"})
    rendered = format_report(report)
    assert "compensation" in rendered and "hooks" in rendered


def test_a_field_added_only_to_the_vendored_schema_is_reported(sandbox_schema: Path) -> None:
    _mutate(
        sandbox_schema,
        "                pure:\n                  type: boolean\n",
        "                pure:\n                  type: boolean\n"
        "                extra_field_not_on_the_model:\n                  type: string\n",
    )

    report = check(sandbox_schema)

    assert not report.ok
    mismatch = next(m for m in report.mismatches if m.location == "annotations")
    assert "extra_field_not_on_the_model" in mismatch.missing_in_model


def test_a_nested_object_dropped_entirely_from_the_schema_raises_a_clear_error(
    sandbox_schema: Path,
) -> None:
    """A whole location vanishing (not just a renamed member) is too structural to diff field
    by field; the guard fails loudly rather than reporting a hollow, misleading match.
    """
    text = sandbox_schema.read_text(encoding="utf-8")
    needle = (
        "                compensation:\n"
        "                  description: |\n"
        "                    v2.2 (DEC-09): compensation hook slot — slot now, semantics\n"
        "                    deferred; compensation-as-protection per DEC-05 D7. v2.3\n"
        "                    addendum (2026-08-20, DEC-30): required list added.\n"
        "                  type: object\n"
        "                  additionalProperties: false\n"
        "                  required: [hook]\n"
        "                  properties:\n"
        "                    hook: { type: string }\n"
    )
    assert needle in text
    sandbox_schema.write_text(text.replace(needle, ""), encoding="utf-8")

    with pytest.raises(SchemaLockstepError, match="compensation"):
        check(sandbox_schema)


def test_the_schema_yaml_file_is_never_written_by_this_guard() -> None:
    """WA-04/WA-11: the vendored fixture schema is read-only; this guard only ever loads it."""
    before = SCHEMA.read_bytes()
    check(SCHEMA)
    assert SCHEMA.read_bytes() == before


# ── The exit status CI actually observes ──


def test_the_ci_command_passes_on_the_working_tree() -> None:
    result = _run_guard()
    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout


def test_the_ci_command_fails_on_a_seeded_divergence(sandbox_schema: Path) -> None:
    _mutate(sandbox_schema, "hook: { type: string }", "hooks: { type: string }")

    result = _run_guard("--schema", str(sandbox_schema))

    assert result.returncode == 1
    assert "compensation" in result.stderr
    assert "FAILED" in result.stderr


def test_the_ci_command_fails_when_the_schema_is_missing(tmp_path: Path) -> None:
    result = _run_guard("--schema", str(tmp_path / "absent.yaml"))
    assert result.returncode == 1


# ── Wiring: the guard runs in CI ──


def _ci_run_steps() -> list[str]:
    workflow: dict[str, Any] = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))
    return [
        step["run"]
        for job in workflow["jobs"].values()
        for step in job["steps"]
        if isinstance(step.get("run"), str)
    ]


def test_ci_runs_the_schema_lockstep_guard() -> None:
    workflow: dict[str, Any] = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))
    assert "schema-lockstep" in workflow["jobs"], "the guard needs its own CI job"
    assert any("tools/schema_lockstep.py" in step for step in _ci_run_steps())


def test_report_ok_reflects_whether_any_mismatch_was_found() -> None:
    assert Report(locations_checked=14, mismatches=[]).ok
    assert not Report(
        locations_checked=1,
        mismatches=[Mismatch("annotations", frozenset({"x"}), frozenset())],
    ).ok
