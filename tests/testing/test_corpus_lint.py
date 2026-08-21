"""Behaviour tests for the corpus lint (``tools/corpus_lint.py``) — the repo's fixture gate.

Three things are pinned here.

**The vendored corpus is clean**, through the exact command the CI job runs — as a script, on
a clean interpreter, so its exit status is observed rather than assumed.

**Every rule fires.** :data:`SEEDS` seeds one violation per rule of the lint's closed
:data:`~tools.corpus_lint.RULES` vocabulary into a *copy* of the corpus and asserts the rule
is reported; the suite as a whole asserts it covers every rule, so a rule that stops working
cannot hide behind a green run. Every seeded document is written under ``tmp_path``: the
corpus is a read-only vendored contract surface (WA-04/WA-11), and one test watches its bytes
across a lint run to keep that honest.

**The lint's own inputs stay in lockstep** with the vendored files they mirror — the
directory minimums against the README's *Counts* table, and the schema's ``property`` enum
against the envelope's own slug type.

Nothing here executes a workflow node, calls a model, or opens a socket (WA-07).
"""

from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml

from gebra.testing import PROPERTY_SLUGS, yaml_loader
from tests.conftest import FIXTURES_DIR
from tools.corpus_lint import (
    CORPUS_FLOOR,
    DIRECTORY_MINIMUMS,
    RULES,
    CorpusLintError,
    CorpusReport,
    check,
    format_report,
    read_schema_rules,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
LINT = REPO_ROOT / "tools" / "corpus_lint.py"
README = FIXTURES_DIR / "README.md"
SCHEMA = FIXTURES_DIR / "schema.yaml"

#: Fixtures the seeds mutate. Stable choices: one wedge positive, one wedge negative, one
#: evolution pair, and one fixture from another directory to import.
GWF_POS = "graph-well-formed/positive-01-linear-document-pipeline.yaml"
GWF_NEG = "graph-well-formed/negative-01-unreachable-escalation-node.yaml"
EVO_POS = "evolution-safety/positive-01-hotel-upsell-branch-added.yaml"
DET_POS = "determinism-replay/positive-01-pinned-seed-zero-temp-classifier.yaml"

#: A mutation applied to a *copy* of the corpus, rooted at the copied corpus directory.
Mutation = Callable[[Path], None]


# ── Seeding helpers ──────────────────────────────────────────────────────────────────────


def _read(path: Path) -> dict[str, Any]:
    document: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    return document


def _write(path: Path, document: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")


def _patch(relative: str, **members: Any) -> Mutation:
    """Set top-level members on a fixture."""

    def mutate(root: Path) -> None:
        path = root / relative
        document = _read(path)
        document.update(members)
        _write(path, document)

    return mutate


def _patch_expected(relative: str, **members: Any) -> Mutation:
    """Set members inside a fixture's ``expected:`` block."""

    def mutate(root: Path) -> None:
        path = root / relative
        document = _read(path)
        document["expected"].update(members)
        _write(path, document)

    return mutate


def _drop(relative: str, dotted: str) -> Mutation:
    """Delete a member named by a dotted path (``expected.failure.property_condition``)."""

    def mutate(root: Path) -> None:
        path = root / relative
        document = _read(path)
        target: Any = document
        parts = dotted.split(".")
        for part in parts[:-1]:
            target = target[part]
        del target[parts[-1]]
        _write(path, document)

    return mutate


def _to_pair(relative: str) -> Mutation:
    """Rewrite a single-snapshot fixture into the ``ir_before`` + ``ir_after`` pair form."""

    def mutate(root: Path) -> None:
        path = root / relative
        document = _read(path)
        document["ir_before"] = document["ir"]
        document["ir_after"] = document.pop("ir")
        _write(path, document)

    return mutate


def _to_single(relative: str) -> Mutation:
    """Rewrite a snapshot pair into the single-``ir`` form."""

    def mutate(root: Path) -> None:
        path = root / relative
        document = _read(path)
        document["ir"] = document.pop("ir_before")
        document.pop("ir_after")
        _write(path, document)

    return mutate


def _add_third_ir_block(relative: str) -> Mutation:
    """Leave ``ir`` in place and add the pair members beside it — no admitted shape."""

    def mutate(root: Path) -> None:
        path = root / relative
        document = _read(path)
        document["ir_before"] = document["ir"]
        document["ir_after"] = document["ir"]
        _write(path, document)

    return mutate


def _bump_ir_version(relative: str, version: str) -> Mutation:
    def mutate(root: Path) -> None:
        path = root / relative
        document = _read(path)
        document["ir"]["ir_version"] = version
        _write(path, document)

    return mutate


def _rename(relative: str, new_name: str) -> Mutation:
    def mutate(root: Path) -> None:
        source = root / relative
        source.rename(source.parent / new_name)

    return mutate


def _duplicate(relative: str, new_relative: str) -> Mutation:
    def mutate(root: Path) -> None:
        destination = root / new_relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / relative, destination)

    return mutate


def _delete(relative: str) -> Mutation:
    def mutate(root: Path) -> None:
        (root / relative).unlink()

    return mutate


def _delete_directory(name: str) -> Mutation:
    def mutate(root: Path) -> None:
        shutil.rmtree(root / name)

    return mutate


def _raw(relative: str, text: str) -> Mutation:
    """Overwrite (or create) a fixture with literal text."""

    def mutate(root: Path) -> None:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    return mutate


def _append(relative: str, text: str) -> Mutation:
    def mutate(root: Path) -> None:
        path = root / relative
        path.write_text(path.read_text(encoding="utf-8") + text, encoding="utf-8")

    return mutate


# ── One seed per rule ────────────────────────────────────────────────────────────────────

#: ``(rule, mutation)`` — every member of :data:`~tools.corpus_lint.RULES` appears at least
#: once, and ``test_the_seed_suite_covers_every_rule`` asserts that.
SEEDS: tuple[tuple[str, Mutation], ...] = (
    ("yaml-unreadable", _raw(GWF_POS, "property: [unclosed\n")),
    ("document-not-a-mapping", _raw(GWF_POS, "- not\n- a\n- fixture\n")),
    ("non-json-value", _append(GWF_POS, "\nnotes: 2026-07-31\n")),
    ("missing-key", _drop(GWF_POS, "polarity")),
    ("unknown-key", _patch(GWF_POS, invented_member="x")),
    ("property-not-a-slug", _patch(GWF_POS, property="not-a-catalog-property")),
    ("property-list-too-short", _patch(GWF_POS, property=["graph-well-formed"])),
    ("polarity-not-in-enum", _patch(GWF_POS, polarity="sideways")),
    ("description-too-short", _patch(GWF_POS, description="short")),
    ("axiom-basis-malformed", _patch(GWF_POS, axiom_basis=["not-an-axiom"])),
    ("ir-shape", _add_third_ir_block(GWF_POS)),
    ("pair-form-not-evolution-safety", _to_pair(GWF_POS)),
    ("evolution-safety-without-pair-form", _to_single(EVO_POS)),
    ("ir-invalid", _bump_ir_version(GWF_POS, "0.1")),
    ("expected-not-a-mapping", _patch(GWF_POS, expected="pass")),
    ("expected-unknown-key", _patch_expected(GWF_POS, invented_member="x")),
    ("expected-result-not-in-enum", _patch_expected(GWF_POS, result="maybe")),
    ("witness-missing-on-pass", _drop(GWF_POS, "expected.witness")),
    ("failure-missing-on-fail", _drop(GWF_NEG, "expected.failure")),
    ("failure-missing-property-condition", _drop(GWF_NEG, "expected.failure.property_condition")),
    ("witness-present-on-fail", _patch_expected(GWF_NEG, witness={"kind": "well-formedness"})),
    (
        "failure-present-on-pass",
        _patch_expected(GWF_POS, failure={"property_condition": "orphan-node"}),
    ),
    ("polarity-result-mismatch", _patch(GWF_POS, polarity="negative")),
    ("unknown-directory", _duplicate(GWF_POS, "invented-directory/positive-01-imported.yaml")),
    (
        "directory-property-mismatch",
        _duplicate(DET_POS, "graph-well-formed/positive-09-imported.yaml"),
    ),
    ("filename-malformed", _rename(GWF_POS, "an-unconventional-name.yaml")),
    ("filename-polarity-mismatch", _rename(GWF_POS, "negative-09-mislabelled-polarity.yaml")),
    (
        "serial-collision",
        _duplicate(GWF_POS, "graph-well-formed/positive-01-duplicate-serial.yaml"),
    ),
    ("directory-missing", _delete_directory("parallel-safety")),
    ("directory-minimum-unmet", _delete(GWF_POS)),
    ("corpus-below-floor", _delete(GWF_POS)),
    ("fixture-unloadable", _patch(GWF_POS, notes=["a", "list", "where", "a", "string", "belongs"])),
)


@pytest.fixture
def corpus_copy(tmp_path: Path) -> Path:
    """A working copy of the vendored corpus — the only corpus any seed is applied to."""
    root = tmp_path / "properties"
    shutil.copytree(FIXTURES_DIR, root)
    return root


def _lint(root: Path) -> CorpusReport:
    return check(root, root / "schema.yaml")


def _run_lint(*args: str) -> subprocess.CompletedProcess[str]:
    """Run the lint exactly as CI does — as a script, on a clean interpreter."""
    return subprocess.run(
        [sys.executable, str(LINT), *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


# ── The vendored corpus ──────────────────────────────────────────────────────────────────


def test_the_vendored_corpus_is_clean() -> None:
    report = check(FIXTURES_DIR, SCHEMA)
    assert report.violations == []
    assert report.ok
    assert report.fixtures_checked == CORPUS_FLOOR
    assert report.directories_checked == len(DIRECTORY_MINIMUMS)


def test_the_gate_command_ci_runs_exits_zero() -> None:
    """``python tools/corpus_lint.py`` with no arguments — the CI job's exact command."""
    result = _run_lint()
    assert result.returncode == 0, result.stderr
    assert "corpus lint: OK" in result.stdout


def test_a_seeded_violation_fails_the_gate_command(corpus_copy: Path) -> None:
    """The card's second acceptance, through the process CI runs rather than an in-process call."""
    _drop(GWF_POS, "expected.witness")(corpus_copy)
    result = _run_lint("--corpus", str(corpus_copy))
    assert result.returncode == 1
    assert "corpus lint: FAILED" in result.stderr
    assert "witness-missing-on-pass" in result.stderr
    assert GWF_POS in result.stderr


def test_the_lint_never_writes_to_the_vendored_corpus() -> None:
    """WA-04/WA-11: the corpus is read-only, and the gate over it is a reader."""
    before = _digest(FIXTURES_DIR)
    check(FIXTURES_DIR, SCHEMA)
    assert _digest(FIXTURES_DIR) == before


def _digest(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


# ── Every rule fires ─────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(("rule", "mutation"), SEEDS, ids=[rule for rule, _ in SEEDS])
def test_a_seeded_violation_reports_its_rule(
    corpus_copy: Path, rule: str, mutation: Mutation
) -> None:
    mutation(corpus_copy)
    report = _lint(corpus_copy)
    reported = {violation.rule for violation in report.violations}
    assert rule in reported, f"expected {rule!r}, got {sorted(reported)}"
    assert reported <= set(RULES), (
        f"reported outside the closed vocabulary: {reported - set(RULES)}"
    )
    assert not report.ok


def test_the_seed_suite_covers_every_rule() -> None:
    """A rule with no seed is a rule nothing proves still works."""
    assert {rule for rule, _ in SEEDS} == set(RULES)


def test_the_rule_vocabulary_has_no_duplicates() -> None:
    assert len(RULES) == len(set(RULES))


def test_a_clean_report_renders_without_violations() -> None:
    rendered = format_report(check(FIXTURES_DIR, SCHEMA))
    assert rendered.startswith("corpus lint: OK")
    assert "[" not in rendered.splitlines()[0]


def test_a_failing_report_names_the_remediation_route(corpus_copy: Path) -> None:
    """A violation must never read as an invitation to edit a fixture (WA-04)."""
    _drop(GWF_POS, "expected.witness")(corpus_copy)
    rendered = format_report(_lint(corpus_copy))
    assert "corpus lint: FAILED" in rendered
    assert "R-05 sign-off" in rendered


# ── The envelope ledger ──────────────────────────────────────────────────────────────────


def test_the_envelope_ledger_covers_every_loadable_fixture() -> None:
    report = check(FIXTURES_DIR, SCHEMA)
    assert len(report.envelope) == CORPUS_FLOOR
    assert len(report.composing) + len(report.not_composing) == CORPUS_FLOOR
    assert report.composing, "no fixture composes — the envelope ledger is not being filled"


def test_the_envelope_ledger_is_reported_and_never_gated() -> None:
    """Gating it would demand a fixture edit, and WA-04 forbids one — revisions route vault-first."""
    report = check(FIXTURES_DIR, SCHEMA)
    assert report.not_composing, "the ledger's pending list is the state this test is about"
    assert report.ok
    for status in report.not_composing:
        assert status.reason
        assert status.detail


def test_the_envelope_ledger_flag_lists_the_pending_fixtures() -> None:
    result = _run_lint("--envelope-ledger")
    assert result.returncode == 0, result.stderr
    report = check(FIXTURES_DIR, SCHEMA)
    for status in report.not_composing:
        assert status.fixture in result.stdout


# ── The lint's inputs stay in lockstep with the vendored files ───────────────────────────


def test_the_directory_minimums_match_the_vendored_readme_counts_table() -> None:
    """:data:`DIRECTORY_MINIMUMS` mirrors the README table; a re-vendor must move both."""
    positives, negatives, totals, grand_total = _readme_counts()
    assert grand_total == CORPUS_FLOOR
    assert set(totals) == set(DIRECTORY_MINIMUMS)
    for directory, minimum in DIRECTORY_MINIMUMS.items():
        assert minimum.total == totals[directory], directory
        assert minimum.positive == positives[directory], directory
        assert minimum.negative == negatives[directory], directory


def _readme_counts() -> tuple[dict[str, int], dict[str, int], dict[str, int], int]:
    """Parse the README *Counts* table: per-directory positive/negative/subtotal, and the total."""
    row = re.compile(r"^\|(?P<cells>.*)\|\s*$")
    slug = re.compile(r"P-\d+ `(?P<slug>[a-z-]+)`")
    positives: dict[str, int] = {}
    negatives: dict[str, int] = {}
    totals: dict[str, int] = {}
    grand_total = 0
    for line in README.read_text(encoding="utf-8").splitlines():
        match = row.match(line.strip())
        if match is None:
            continue
        cells = [cell.strip() for cell in match.group("cells").split("|")]
        if len(cells) != 4:
            continue
        label, positive, negative, subtotal = cells
        if "Grand total" in label:
            grand_total = _floor(subtotal)
            continue
        named = slug.search(label)
        if named is not None:
            directory = named.group("slug")
        elif label.startswith("Mixed"):
            directory = "mixed"
        else:
            continue
        positives[directory] = _floor(positive)
        negatives[directory] = _floor(negative)
        totals[directory] = _floor(subtotal)
    assert totals, "the README Counts table was not found"
    return positives, negatives, totals, grand_total


def _floor(cell: str) -> int:
    """``"3+"`` -> 3, ``"**60+**"`` -> 60, ``"varies"`` -> 0."""
    digits = re.search(r"\d+", cell)
    return int(digits.group()) if digits else 0


def test_the_schema_property_enum_matches_the_envelope_slug_type() -> None:
    """The vendored schema's catalog and the §0.3 ``PropertySlug`` Literal are one list."""
    rules = read_schema_rules(SCHEMA)
    assert rules.property_slugs == PROPERTY_SLUGS


def test_the_schema_rules_are_read_off_the_vendored_file() -> None:
    rules = read_schema_rules(SCHEMA)
    assert rules.required == frozenset({"property", "polarity", "description", "expected"})
    assert {"ir", "ir_before", "ir_after", "source_snippet", "notes"} <= rules.allowed
    assert rules.polarities == ("positive", "negative")
    assert rules.results == ("pass", "fail")
    assert rules.expected_required == frozenset({"result"})
    assert rules.failure_required == frozenset({"property_condition"})
    assert rules.description_min_length == 20
    assert rules.property_list_min_items == 2
    assert rules.axiom_basis_min_items == 1


def test_a_schema_missing_a_rule_this_lint_reads_is_refused(tmp_path: Path) -> None:
    """Structural divergence must be loud: the gate may not quietly check less."""
    document: Any = yaml.safe_load(SCHEMA.read_text(encoding="utf-8"))
    del document["properties"]["polarity"]
    stripped = tmp_path / "schema.yaml"
    stripped.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    with pytest.raises(CorpusLintError, match="diverged structurally"):
        read_schema_rules(stripped)


def test_an_absent_corpus_root_is_refused(tmp_path: Path) -> None:
    with pytest.raises(CorpusLintError, match="no such corpus directory"):
        check(tmp_path / "nowhere", SCHEMA)


def test_an_unreadable_schema_is_refused(tmp_path: Path) -> None:
    missing = tmp_path / "schema.yaml"
    with pytest.raises(CorpusLintError, match="cannot read the fixture schema"):
        read_schema_rules(missing)


def test_the_schema_is_parsed_through_the_hardened_loader(tmp_path: Path) -> None:
    """``--schema`` names an arbitrary path, so it gets the fixtures' parser, not the shared one.

    Warming the snapshot first is the documented order of the guarantee (see
    ``gebra.testing.yaml_loader``): a tag registered afterwards cannot reach a gebra document,
    schema included.
    """

    def _explode(loader: object, node: object) -> str:  # pragma: no cover - never reached
        return "injected"

    yaml_loader()
    tagged = tmp_path / "schema.yaml"
    tagged.write_text(
        SCHEMA.read_text(encoding="utf-8") + "\ninjected: !injected x\n", encoding="utf-8"
    )
    yaml.SafeLoader.add_constructor("!injected", _explode)
    try:
        assert yaml.safe_load(tagged.read_text(encoding="utf-8"))["injected"] == "injected"
        with pytest.raises(CorpusLintError, match="cannot read the fixture schema"):
            read_schema_rules(tagged)
    finally:
        del yaml.SafeLoader.yaml_constructors["!injected"]


def test_the_cli_reports_an_unusable_input_without_a_traceback(tmp_path: Path) -> None:
    result = _run_lint("--corpus", str(tmp_path / "nowhere"))
    assert result.returncode == 1
    assert "no such corpus directory" in result.stderr
    assert "Traceback" not in result.stderr
