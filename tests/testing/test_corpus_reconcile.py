"""The TE-03 reconciliation pass, now landed: are the corpus's bytes the ones the ruling fixed?

The pass was ruled in DEC-17 and re-vendored from vault ``b2056e9``, so this module's job has
turned around. Before the ruling it asserted that the plan was *outstanding*; now it asserts
that the corpus **is** the plan's output, and it does so without ever taking the corpus's word
for it. Every reconciled value is re-derived from its own authority and compared:

* the two ``remediation`` paragraphs against what the shipped Appendix B §B.3 renderer
  produces, so the fixtures are aligned with the spec rather than with each other;
* every ``severity``/``claim_class`` against the §0.4 condition registry, so no grade is
  a choice;
* every rotated cycle against :func:`canonical_rotation` **and** against the pre-pass list,
  so a rotation can never silently have become a sort;
* every ``kind:`` against the discriminator its §P-nn.3 location subtype declares.

The central test is :func:`test_emitting_from_the_pre_pass_corpus_reproduces_the_vendored_bytes`:
a temporary corpus is built by *reverting* every revision, the tool is run on it, and the
result is required to be byte-identical to the vendored corpus. That is the whole claim in one
assertion — what landed is exactly what the plan proposed and R-05 ratified, neither more nor
less — and it keeps the emitter exercised in both directions now that there is nothing left
outstanding.

The outcome is proven the same way as before: the corpus lint is green, every wedge-directory
fixture composes into a §0.3 report, and all four P-08 fixtures are *model-equal* to what the
one shipped validator produces — checked against an implementation written from the spec
independently (VAL-04).

One invariant guards the corpus itself throughout: the vendored tree must be byte-identical
before and after every test in this module.
"""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path
from typing import Any

import pytest

from gebra.testing import FixtureError, load_corpus, load_fixture
from gebra.verify import check_determinism_replay, condition
from gebra.verify.properties.determinism_replay import render_remediation
from tests.conftest import FIXTURES_DIR
from tools import corpus_lint, corpus_reconcile
from tools.corpus_reconcile import (
    EXCLUSIONS,
    OPEN_CALLS,
    PLAN,
    VERIFICATIONS,
    Drift,
    ReconcileError,
    Revision,
    State,
    audit,
    canonical_rotation,
    emit,
    format_audit,
)

#: The five wedge directories. After the pass, every fixture in them must compose.
WEDGE_DIRECTORIES = frozenset(
    {
        "graph-well-formed",
        "termination-witness",
        "dataflow-completeness",
        "effect-safety",
        "determinism-replay",
    }
)

#: What the corpus lint reported before the pass landed, and what it reports now. Written out
#: rather than derived so that a change to either number is a visible diff.
COMPOSING_PRE_PASS = 25
COMPOSING_NOW = 33


@pytest.fixture(scope="module")
def pre_pass(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A temporary corpus with every revision *reverted* — the bytes as they were pre-DEC-17.

    Built by replacing each revision's ``after`` block with its ``before``, which is only
    possible because the plan carries both halves. It is what keeps the emitter honest now
    that nothing is outstanding: the tool run over this corpus must reproduce the vendored one.
    """
    root = tmp_path_factory.mktemp("pre-pass") / "properties"
    shutil.copytree(FIXTURES_DIR, root)
    for revision in PLAN:
        path = root / revision.fixture
        text = path.read_text()
        assert text.count(revision.after) == 1, revision.fixture
        path.write_text(text.replace(revision.after, revision.before, 1))
    return root


@pytest.fixture(autouse=True)
def _corpus_untouched() -> Any:
    """WA-04, enforced per test: nothing in this module may change a vendored byte."""
    before = _digest(FIXTURES_DIR)
    yield
    assert _digest(FIXTURES_DIR) == before, "a test modified the vendored corpus"


def _digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if path.is_file():
            digest.update(str(path.relative_to(root)).encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()


def _revision(fixture_id_fragment: str) -> Revision:
    matches = [revision for revision in PLAN if fixture_id_fragment in revision.fixture]
    assert len(matches) == 1, f"{fixture_id_fragment} matched {len(matches)} revisions"
    return matches[0]


# ── The plan describes the corpus that exists ────────────────────────────────────────────


def test_every_revision_names_a_vendored_fixture() -> None:
    for revision in PLAN:
        assert (FIXTURES_DIR / revision.fixture).is_file(), revision.fixture


def test_the_whole_plan_has_landed_in_the_vendored_corpus() -> None:
    """The pass is complete: every revision applied, every verification holding.

    This is the assertion that makes TE-03's first acceptance box observable rather than
    asserted — and it stays as a regression gate, since a re-vendor that reverted any of the
    twenty-two items would land back on ``OUTSTANDING`` here.
    """
    report = audit(FIXTURES_DIR)
    assert [status.state for status in report.revisions] == [State.APPLIED] * len(PLAN)
    assert report.ambiguous == ()
    assert report.failed_verifications == ()
    assert report.complete


def test_every_post_pass_block_occurs_exactly_once_in_its_fixture() -> None:
    """The reconciled block is present once, and no trace of the pre-pass one is left."""
    for revision in PLAN:
        text = (FIXTURES_DIR / revision.fixture).read_text()
        assert text.count(revision.after) == 1, revision.fixture
        assert revision.before not in text, revision.fixture


def test_item_ids_are_unique_and_every_item_carries_its_authority() -> None:
    items = [item for revision in PLAN for item in revision.items]
    assert len(items) == len({item.item_id for item in items})
    assert len(items) == 22
    assert len(PLAN) == 12
    for item in items:
        assert item.spec_ref.strip(), item.item_id
        assert len(item.rationale) > 40, item.item_id


def test_no_wedge_record_in_the_corpus_is_left_unreconciled(pre_pass: Path) -> None:
    """Derived from the corpus, not from the plan — so a record the pass missed fails here.

    Walks every failure record the corpus states and keeps the ones §0.4 assigns to a wedge
    property: each must now carry its §0.3 discriminator and its grades. The pre-pass corpus is
    the control, and it is what stops this from being a test that would pass on any corpus:
    the same walk over the pre-pass bytes must find exactly the nine fixtures the plan names.
    """
    assert _unreconciled(FIXTURES_DIR) == set()
    assert _unreconciled(pre_pass) == {revision.fixture for revision in PLAN} - {
        # The three P-06 witness-side revisions carry no failure record at all.
        revision.fixture
        for revision in PLAN
        if all(item.drift in {Drift.REGION_NAMING, Drift.CYCLE_ROTATION} for item in revision.items)
    }


def _unreconciled(root: Path) -> set[str]:
    """Fixtures under ``root`` with a wedge-owned record missing a discriminator or grades."""
    found = set()
    for fixture in load_corpus(root):
        failure = fixture.expected_failure
        if failure is None:
            continue
        records: list[Any] = [failure, *(failure.get("co_failures") or ())]
        records.extend(failure.get("advisories") or ())
        for record in records:
            owner = _owner_of(record.get("property_condition"))
            if owner not in WEDGE_DIRECTORIES:
                continue
            location = record.get("location") or {}
            if "kind" in location and "severity" in record and "claim_class" in record:
                continue
            found.add(fixture.fixture_id)
    return found


def _owner_of(condition_id: object) -> str | None:
    if not isinstance(condition_id, str):
        return None
    try:
        return condition(condition_id).property_slug
    except Exception:  # noqa: BLE001 - an unregistered string is simply not wedge-owned
        return None


# ── Every proposed value is re-derived from its own authority ────────────────────────────


@pytest.mark.parametrize(
    ("fragment", "condition_id"),
    [
        ("determinism-replay/negative-01", "deterministic-llm-seed-unpinned"),
        ("determinism-replay/negative-02", "deterministic-llm-temperature-unpinned"),
    ],
)
def test_the_reconciled_remediation_is_the_appendix_b_closing_paragraph(
    fragment: str, condition_id: str
) -> None:
    """§8.3 (d): the target is §B.3's closing paragraph, not a tidied version of the old one."""
    revision = _revision(fragment)
    fixture = load_fixture(FIXTURES_DIR / revision.fixture)
    failure = fixture.expected_failure
    assert failure is not None
    assert failure["remediation"] == render_remediation(condition_id)  # type: ignore[arg-type]
    assert not failure["remediation"].endswith("\n"), "`>-` strips; `>` would keep a newline"


def test_every_reconciled_grade_is_the_registry_row_not_a_choice() -> None:
    """§0.4 fixes one severity and one claim class per condition; nothing here picks them."""
    checked = 0
    for revision in PLAN:
        fixture = load_fixture(FIXTURES_DIR / revision.fixture)
        failure = fixture.expected_failure
        if failure is None:
            continue
        for record in (failure, *(failure.get("co_failures") or ())):
            entry = _registry_entry(record.get("property_condition"))
            if entry is None or "severity" not in record:
                continue
            assert record["severity"] == entry.severity, revision.fixture
            assert record["claim_class"] == entry.claim_class, revision.fixture
            checked += 1
    assert checked >= 8


def _registry_entry(condition_id: object) -> Any:
    if not isinstance(condition_id, str):
        return None
    try:
        entry = condition(condition_id)
    except Exception:  # noqa: BLE001 - RESERVED/unregistered strings carry no grades
        return None
    return entry if entry.severity is not None else None


def test_every_rotation_is_a_rotation_and_the_canonical_one() -> None:
    """A rotation preserves the cycle; a sort would silently invent a different one."""
    rotations = [
        (revision, item)
        for revision in PLAN
        for item in revision.items
        if item.drift is Drift.CYCLE_ROTATION
    ]
    assert len(rotations) == 3
    for revision, _ in rotations:
        for before, after in zip(
            _cycles_of(revision.before), _cycles_of(revision.after), strict=True
        ):
            assert after == canonical_rotation(before)
            assert after in _all_rotations(before), "not a rotation of the authored cycle"


def _cycles_of(block: str) -> list[list[str]]:
    """Every cycle-keyed ``[a, b, c]`` flow sequence in a block, in document order.

    Keyed on the field name rather than on "looks like a list", so an ``effect:`` tuple —
    which §6.3 set-compares and this pass never reorders — cannot be mistaken for a cycle.
    """
    cycles = []
    for line in block.splitlines():
        stripped = line.strip().lstrip("- ")
        key, separator, tail = stripped.partition(":")
        if separator and key not in {"cycle", "cycles", "representative_cycle"}:
            continue
        head, bracket, _ = (tail if separator else stripped).partition("[")[2].partition("]")
        if bracket:
            cycles.append([item.strip() for item in head.split(",")])
    return cycles


def _all_rotations(cycle: list[str]) -> list[list[str]]:
    return [[*cycle[index:], *cycle[:index]] for index in range(len(cycle))]


def test_each_added_discriminator_is_the_one_its_location_subtype_declares() -> None:
    """``state-key`` for P-04, ``node`` for P-06 and P-08 — read off the models, not typed."""
    expected = {
        "dataflow-completeness": "state-key",
        "effect-safety": "node",
        "determinism-replay": "node",
    }
    for revision in PLAN:
        fixture = load_fixture(FIXTURES_DIR / revision.fixture)
        failure = fixture.expected_failure
        if failure is None:
            continue
        for record in (failure, *(failure.get("co_failures") or ())):
            owner = _owner_of(record.get("property_condition"))
            if owner in expected:
                assert (record.get("location") or {}).get("kind") == expected[owner]


def test_the_region_normalization_matches_the_spec_pinned_value() -> None:
    """§6.3 item 1 names the fixture, the field and the target — all three are asserted."""
    revision = _revision("effect-safety/positive-01")
    assert "region: cycle" in revision.before
    assert "region: retry" in revision.after
    assert revision.before.replace("region: cycle", "region: retry") == revision.after


# ── The revision state machine ───────────────────────────────────────────────────────────


def test_the_vendored_corpus_reads_as_applied_and_reapplying_is_a_no_op() -> None:
    revision = PLAN[0]
    text = (FIXTURES_DIR / revision.fixture).read_text()
    assert revision.state_in(text) is State.APPLIED
    assert revision.apply_to(text) == text


def test_applying_a_revision_twice_changes_nothing_the_second_time(pre_pass: Path) -> None:
    revision = PLAN[0]
    text = (pre_pass / revision.fixture).read_text()
    assert revision.state_in(text) is State.OUTSTANDING
    once = revision.apply_to(text)
    assert once != text
    assert revision.state_in(once) is State.APPLIED
    assert revision.apply_to(once) == once


def test_a_corpus_in_neither_state_is_an_error_not_a_guess(pre_pass: Path) -> None:
    revision = PLAN[0]
    mangled = (pre_pass / revision.fixture).read_text().replace(revision.before, "expected:\n")
    assert revision.state_in(mangled) is State.AMBIGUOUS
    with pytest.raises(ReconcileError, match="neither the pre-pass nor the post-pass"):
        revision.apply_to(mangled)


def test_a_doubled_block_is_refused_rather_than_half_applied(pre_pass: Path) -> None:
    revision = PLAN[0]
    text = (pre_pass / revision.fixture).read_text()
    with pytest.raises(ReconcileError, match="occurs 2 times"):
        revision.apply_to(text + revision.before)


def test_audit_reports_a_missing_fixture_instead_of_skipping_it(tmp_path: Path) -> None:
    (tmp_path / "mixed").mkdir()
    with pytest.raises((ReconcileError, FixtureError)):
        audit(tmp_path)


# ── Emitting the candidate, and never the vendored corpus ────────────────────────────────


@pytest.mark.parametrize(
    "destination",
    [
        FIXTURES_DIR,
        FIXTURES_DIR / "mixed",
        FIXTURES_DIR / "new" / "deeper",
        FIXTURES_DIR.parent,
        # The spellings a guard that only compared strings would miss.
        FIXTURES_DIR / ".." / "properties",
        FIXTURES_DIR / "mixed" / ".." / ".." / "properties" / "graph-well-formed",
        Path(str(FIXTURES_DIR).upper()),
    ],
)
def test_emitting_into_the_vendored_corpus_is_refused(destination: Path) -> None:
    """WA-04 as a guard, not a convention: the tool cannot be pointed at the corpus.

    The uppercase spelling is the one worth naming, and what it tests depends on the
    filesystem. Where case folds (macOS, Windows) it is the same directory under a different
    string — the guard must refuse it, which is why it asks the filesystem (``samefile``) and
    not only the path algebra. Where case distinguishes (the Linux CI runners) the same
    spelling names a directory that does not exist, and the claim inverts: the guard must
    *not* call a genuinely different path a vendored surface. That leg exercises the guard
    directly rather than ``emit`` — emitting to ``/HOME/…`` would attempt the write the guard
    correctly declined to block. Alias *recall* on case-sensitive filesystems is owned by the
    symlink test below, which every filesystem can build.
    """
    if destination == Path(str(FIXTURES_DIR).upper()) and not destination.exists():
        corpus_reconcile._refuse_vendored(destination, FIXTURES_DIR)
        return
    with pytest.raises(ReconcileError, match="read-only vendored contract surface"):
        emit(FIXTURES_DIR, destination)


def test_emitting_through_a_symlink_into_the_corpus_is_refused(tmp_path: Path) -> None:
    link = tmp_path / "looks-harmless"
    link.symlink_to(FIXTURES_DIR, target_is_directory=True)
    with pytest.raises(ReconcileError, match="read-only vendored contract surface"):
        emit(FIXTURES_DIR, link / "mixed")


def test_emitting_into_a_non_empty_directory_is_refused(tmp_path: Path) -> None:
    (tmp_path / "occupied.txt").write_text("x")
    with pytest.raises(ReconcileError, match="not empty"):
        emit(FIXTURES_DIR, tmp_path)


def test_emitting_from_the_pre_pass_corpus_reproduces_the_vendored_bytes(
    pre_pass: Path, tmp_path: Path
) -> None:
    """The whole claim in one assertion: what landed is exactly what the plan proposed.

    Run the tool over a corpus with every revision reverted and the result must be the vendored
    corpus, file for file, byte for byte — no file added, none missing, and nothing outside the
    twelve ``expected:`` blocks moved. If the ratifying re-vendor had carried so much as a
    reflowed comment beyond the ruling, this would fail.
    """
    destination = tmp_path / "reconstructed"
    copied, applied = emit(pre_pass, destination)
    assert applied == len(PLAN)

    vendored = {
        path.relative_to(FIXTURES_DIR).as_posix(): path.read_bytes()
        for path in sorted(FIXTURES_DIR.rglob("*"))
        if path.is_file()
    }
    produced = {
        path.relative_to(destination).as_posix(): path.read_bytes()
        for path in sorted(destination.rglob("*"))
        if path.is_file()
    }
    assert copied == len(vendored)
    assert produced == vendored


def test_the_pre_pass_corpus_differs_from_the_vendored_one_in_exactly_the_planned_files(
    pre_pass: Path,
) -> None:
    changed = {
        str(path.relative_to(pre_pass))
        for path in sorted(pre_pass.rglob("*"))
        if path.is_file()
        and path.read_bytes() != (FIXTURES_DIR / path.relative_to(pre_pass)).read_bytes()
    }
    assert changed == {revision.fixture for revision in PLAN}
    assert len(list(pre_pass.rglob("*.yaml"))) == len(list(FIXTURES_DIR.rglob("*.yaml")))


def test_the_pass_changed_only_the_expected_block_of_each_fixture(pre_pass: Path) -> None:
    """No reformatting anywhere else: comments, snippets and notes are byte-identical."""
    for revision in PLAN:
        original = (pre_pass / revision.fixture).read_text()
        vendored = (FIXTURES_DIR / revision.fixture).read_text()
        assert vendored == original.replace(revision.before, revision.after, 1)


def test_emitting_from_the_reconciled_corpus_is_a_plain_copy(tmp_path: Path) -> None:
    """Nothing outstanding means nothing to apply — the emitter degrades to a byte copy."""
    destination = tmp_path / "copy"
    copied, applied = emit(FIXTURES_DIR, destination)
    assert applied == 0
    assert copied == sum(1 for path in FIXTURES_DIR.rglob("*") if path.is_file())
    for path in destination.rglob("*"):
        if path.is_file():
            assert path.read_bytes() == (FIXTURES_DIR / path.relative_to(destination)).read_bytes()


# ── The outcome ──────────────────────────────────────────────────────────────────────────


def test_the_vendored_corpus_is_lint_green() -> None:
    report = corpus_lint.check(FIXTURES_DIR, FIXTURES_DIR / "schema.yaml")
    assert report.ok, [violation.rendered() for violation in report.violations]
    assert report.fixtures_checked == 60


def test_every_wedge_directory_fixture_composes_after_the_pass() -> None:
    """The pass's whole point, stated as an outcome rather than as a diff."""
    failures = []
    checked = 0
    for fixture in load_corpus(FIXTURES_DIR):
        if fixture.directory not in WEDGE_DIRECTORIES:
            continue
        checked += 1
        try:
            fixture.expected_report()
        except FixtureError as exc:
            failures.append(f"{fixture.fixture_id}: {exc}")
    assert checked == 30
    assert failures == []


def test_the_pass_moved_the_envelope_count_by_exactly_eight(pre_pass: Path) -> None:
    before = corpus_lint.check(pre_pass, pre_pass / "schema.yaml")
    now = corpus_lint.check(FIXTURES_DIR, FIXTURES_DIR / "schema.yaml")
    assert len(before.composing) == COMPOSING_PRE_PASS
    assert len(now.composing) == COMPOSING_NOW
    gained = set(now.composing) - set(before.composing)
    assert not set(before.composing) - set(now.composing), "nothing stopped composing"
    assert gained == {revision.fixture for revision in PLAN} - {
        # mixed/05 stays non-composing by design, for two independent reasons: its primary
        # finding is P-12's, whose shape §0.3 does not model yet, and the `snapshot: ir_after`
        # key its wedge co-failures carry is refused by every `extra="forbid"` location — so
        # even a drafted §P-12 would not make this block validate while Q-03 keeps that key.
        "mixed/05-evolution-drops-witness-and-state-field.yaml",
        # The three P-06 positives already composed; the pass corrects their content.
        "effect-safety/positive-01-keyed-idempotent-billable-retry.yaml",
        "effect-safety/positive-02-irreversible-outside-cycle.yaml",
        "effect-safety/positive-03-compensated-billable-hold-loop.yaml",
    }


def test_the_reconciled_p08_fixtures_are_model_equal_to_the_shipped_validator() -> None:
    """VAL-04's deviation ledger is retired — checked here, not asserted in prose.

    The validator was written from §8.4 without reference to this plan, so agreement between
    the two is independent evidence that the reconciled bytes are the catalog's shape.
    """
    fixtures = sorted((FIXTURES_DIR / "determinism-replay").glob("*.yaml"))
    assert len(fixtures) == 4
    for path in fixtures:
        fixture = load_fixture(path)
        assert fixture.ir is not None
        assert check_determinism_replay(fixture.ir) == fixture.expected_report(), path.name


def test_the_audit_reads_complete_on_the_vendored_corpus() -> None:
    report = audit(FIXTURES_DIR)
    assert report.complete
    assert report.landed == report.revisions
    assert report.composing_before == COMPOSING_NOW
    assert report.composing_after == COMPOSING_NOW


# ── Verifications: the "verified, not migrated" half ─────────────────────────────────────


def test_every_verification_holds_on_the_vendored_corpus() -> None:
    """The DEC-09 slots and the DEC-11 pins already applied in the vault, re-checked here."""
    report = audit(FIXTURES_DIR)
    assert len(report.verifications) == 14
    assert [status.verification.check_id for status in report.failed_verifications] == []


def test_a_verification_can_fail(tmp_path: Path) -> None:
    """A check nobody can trip proves nothing: break one carrier, watch its check fail."""
    seeded = tmp_path / "seeded"
    emit(FIXTURES_DIR, seeded)
    target = seeded / "effect-safety/positive-03-compensated-billable-hold-loop.yaml"
    target.write_text(
        target.read_text().replace(
            "compensation: { hook: release_hotel_hold }", "effect: [compensated_by_release]"
        )
    )
    failed = {status.verification.check_id for status in audit(seeded).failed_verifications}
    assert "V-04" in failed


def test_an_unplanned_p06_rotation_is_caught_rather_than_assumed_absent(tmp_path: Path) -> None:
    """V-14 is what makes the rotation half of the plan corpus-derived instead of list-derived.

    §6.3 item 2 names three fixtures. If a re-vendor ever introduced a fourth non-canonical
    P-06 cycle list, a plan built from that list alone would miss it silently — so seed one in
    a fixture the plan does not rotate and require the check to say so.
    """
    seeded = tmp_path / "seeded"
    emit(FIXTURES_DIR, seeded)
    target = seeded / "effect-safety/negative-01-billable-in-unguarded-retry.yaml"
    target.write_text(
        target.read_text().replace(
            "cycle: [book_flight, check_booking]", "cycle: [check_booking, book_flight]"
        )
    )
    failed = {status.verification.check_id for status in audit(seeded).failed_verifications}
    assert "V-14" in failed


# ── The audit report ─────────────────────────────────────────────────────────────────────


def test_the_audit_report_names_every_item_call_and_exclusion() -> None:
    rendered = format_audit(audit(FIXTURES_DIR))
    for revision in PLAN:
        assert revision.fixture in rendered
        for item in revision.items:
            assert item.item_id in rendered
    for call in OPEN_CALLS:
        assert call.call_id in rendered
    for exclusion in EXCLUSIONS:
        assert exclusion.spec_ref in rendered
    for verification in VERIFICATIONS:
        assert verification.check_id in rendered
    assert "read-only vendored contract surface" in rendered


def test_the_report_marks_exactly_the_two_items_that_need_an_r05_answer() -> None:
    flagged = {item.item_id for revision in PLAN for item in revision.items if item.needs_r05_call}
    assert flagged == {"R-P04-mixed05-kind", "R-P04-mixed05-grades"}
    assert len(OPEN_CALLS) == 4


# ── The documented commands, run as documented (WA-12) ───────────────────────────────────


def test_the_status_command_runs_and_reports_the_completed_pass(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert corpus_reconcile.main([]) == 0
    out = capsys.readouterr().out
    assert "corpus reconciliation: COMPLETE" in out
    assert f"{len(PLAN)}/{len(PLAN)} fixture revision(s) landed" in out
    assert f"{len(VERIFICATIONS)}/{len(VERIFICATIONS)} verification(s) hold" in out


def test_the_audit_command_prints_the_markdown_report(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert corpus_reconcile.main(["--audit"]) == 0
    assert "# TE-03 corpus reconciliation — audit report" in capsys.readouterr().out


def test_the_diff_command_prints_nothing_once_the_pass_has_landed(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert corpus_reconcile.main(["--diff"]) == 0
    assert capsys.readouterr().out == ""


def test_the_diff_command_prints_every_revision_on_a_pre_pass_corpus(
    pre_pass: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert corpus_reconcile.main(["--corpus", str(pre_pass), "--diff"]) == 0
    out = capsys.readouterr().out
    assert out.count("--- a/") == len(PLAN)
    assert "+      kind: state-key" in out
    assert "+    claim_class: defensible-a" in out


def test_the_check_command_passes_on_the_corpus_and_gates_a_regressed_one(
    pre_pass: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The regression gate: green on the landed bytes, red if any revision were reverted."""
    assert corpus_reconcile.main(["--check"]) == 0
    assert "COMPLETE" in capsys.readouterr().out

    assert corpus_reconcile.main(["--corpus", str(pre_pass), "--check"]) == 1
    assert "OUTSTANDING" in capsys.readouterr().err


def test_the_emit_command_writes_a_candidate_and_says_what_it_applied(
    pre_pass: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    destination = tmp_path / "candidate"
    assert corpus_reconcile.main(["--corpus", str(pre_pass), "--emit", str(destination)]) == 0
    out = capsys.readouterr().out
    assert f"{len(PLAN)} revision(s) applied" in out
    assert corpus_reconcile.main(["--corpus", str(destination), "--check"]) == 0


def test_the_cli_reports_a_refused_emit_instead_of_raising(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert corpus_reconcile.main(["--emit", str(FIXTURES_DIR / "mixed")]) == 1
    assert "read-only vendored contract surface" in capsys.readouterr().err


def test_canonical_rotation_is_a_rotation_by_utf16_code_units() -> None:
    assert canonical_rotation([]) == []
    assert canonical_rotation(["b", "c", "a"]) == ["a", "b", "c"]
    assert canonical_rotation(["a", "b", "c"]) == ["a", "b", "c"]
    assert canonical_rotation(canonical_rotation(["c", "a", "b"])) == ["a", "b", "c"]
    # U+E000 sorts *above* a non-BMP character in UTF-16 code units and below it in code
    # points — the ledger §6 comparator is the former (RFC 8785 §3.2.3).
    pair = ["", "\U0001f600"]
    assert canonical_rotation(pair) == ["\U0001f600", ""]
    assert sorted(pair) == pair


def test_the_module_docstring_states_the_routing_rule() -> None:
    """WA-06/WA-04: the tool's own copy may not read as though it could just edit the corpus."""
    assert corpus_reconcile.__doc__ is not None
    assert "never writes inside the vendored corpus" in corpus_reconcile.__doc__.lower()
