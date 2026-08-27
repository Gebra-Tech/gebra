"""VAL-06 — the P-02 form-(a) guard recognizer, TERMINATION-WITNESS-SPEC §3.

The card's two obligations, and where each is discharged:

* **the §3 fixture-validation table** — "the six recognized guard strings (``positive-01``,
  ``positive-02``, both ``positive-04`` guards, ``negative-02``'s inner guard,
  ``negative-03``'s counter guard) all derive ``guard`` with a ``bounded-comparison``
  conjunct, and the five deliberately-opaque conditions (``positive-03``, ``negative-01``,
  ``negative-02``'s router, ``negative-03``'s router, ``negative-04``) all fail L0 or R0".
  Every one of the eleven strings is read **off the vendored fixture**, never retyped here,
  so the test is against the corpus rather than against a transcription of it. The three
  fixtures whose ``expected:`` blocks name a counter key and a bound cross-check the
  recognizer's output against the vendored expectation, field for field;
* **no partial credit once L0 rejects** — every L0 clause is spoiled into a string that is
  otherwise recognized, and the result must carry no fragment of the guard it threw away.
  The negative control runs the unspoiled string, so the suite cannot pass by rejecting
  everything.

Everything beyond those two is coverage of §3's own text: each rule R0–R6 by name, each
member of the "Deliberate v1 exclusions" list, the whitespace discipline, and the §2.1
integer-compatibility enumeration with its fail-closed tail.

The corpus is a frozen contract surface (WA-04/WA-11): nothing here writes to it. Nothing
here executes a workflow node, calls a model, or opens a network connection (WA-07) —
:func:`test_recognizing_every_corpus_guard_creates_no_socket_and_resolves_no_name` proves it
in a fresh interpreter, import **and** call, and
:func:`test_the_recognizer_contains_no_evaluation_primitive` closes the hazard specific to a
module that parses text: reaching for ``eval``/``compile`` instead of a grammar.
"""

from __future__ import annotations

import ast
import doctest
import subprocess
import sys
import time
from collections.abc import Mapping
from pathlib import Path
from typing import NamedTuple, get_args

import pytest

from gebra.ir import StateField, WorkflowIR
from gebra.testing import load_corpus
from gebra.verify import guards
from gebra.verify.conditions import CONDITION_IDS
from gebra.verify.guards import (
    BOUND_DIRECTIONS,
    CMP_OPS,
    RESERVED_WORDS,
    BoundedComparison,
    GuardClassification,
    RecognizedGuard,
    classify_guard,
    is_integer_compatible,
    qualify_counter_guard,
    recognize_bounded_comparison,
)
from gebra.verify.witnesses import WitnessNoteKind
from tests.conftest import FIXTURES_DIR

_CORPUS = load_corpus(FIXTURES_DIR)

_TW = "termination-witness/"
_POSITIVE_01 = f"{_TW}positive-01-counter-guarded-retry-loop.yaml"
_POSITIVE_02 = f"{_TW}positive-02-justified-recursion-limit-refinement-loop.yaml"
_POSITIVE_03 = f"{_TW}positive-03-shrinking-worklist-hotel-quotes.yaml"
_POSITIVE_04 = f"{_TW}positive-04-nested-scc-dual-counter-witnesses.yaml"
_NEGATIVE_01 = f"{_TW}negative-01-unwitnessed-reflection-loop.yaml"
_NEGATIVE_02 = f"{_TW}negative-02-nested-scc-outer-only-witness.yaml"
_NEGATIVE_03 = f"{_TW}negative-03-counter-guard-without-wired-exit.yaml"
_NEGATIVE_04 = f"{_TW}negative-04-supervisor-delegation-scc-no-witness.yaml"
_NEGATIVE_05 = f"{_TW}negative-05-unwitnessed-self-loop.yaml"
_POSITIVE_05 = f"{_TW}positive-05-recursion-limit-only-scc-note.yaml"
_POSITIVE_06 = f"{_TW}positive-06-cycle-census-capped-overflow.yaml"
_MIXED_10 = "mixed/10-all-properties-pass-healthy-research-pipeline.yaml"
_DC_POSITIVE_04 = "dataflow-completeness/positive-04-cycle-entry-at-writer.yaml"
_DC_NEGATIVE_04 = "dataflow-completeness/negative-04-cycle-entry-at-reader.yaml"
_ES_NEGATIVE_05 = "effect-safety/negative-05-dangling-compensation-hook.yaml"


# ── Helpers ──────────────────────────────────────────────────────────────────────────────


def _ir(fixture_id: str) -> WorkflowIR:
    fixture = next(f for f in _CORPUS if f.fixture_id == fixture_id)
    assert fixture.ir is not None
    return fixture.ir


def _guard_string(fixture_id: str, source: str) -> str:
    """The declared ``condition`` of the conditional edge leaving ``source``, as vendored.

    Reading the string out of the corpus rather than restating it is the whole point: a typo
    here would test the typo, and the six recognized strings are §3's own evidence base.
    """
    ir = _ir(fixture_id)
    conditions = [
        edge.condition
        for edge in ir.edges
        if edge.kind == "conditional" and edge.from_ == source and edge.condition is not None
    ]
    assert len(conditions) == 1, f"{fixture_id}: {source} has {len(conditions)} guards"
    return conditions[0]


def _state(fixture_id: str) -> dict[str, str | StateField] | None:
    return _ir(fixture_id).state


class _CorpusGuard(NamedTuple):
    """One declared router guard, with the Σ of the snapshot that declares it."""

    fixture: str
    source: str
    condition: str
    state: Mapping[str, str | StateField] | None


def _corpus_guards() -> list[_CorpusGuard]:
    """Every conditional edge carrying a ``condition``, across the whole vendored corpus.

    Evolution pairs contribute both snapshots, keyed by the block they came from, so the
    sweep below covers the whole vendored surface and not just the single-snapshot fixtures.
    Each row carries its own snapshot's ``state`` because R1's Σ-side question is only ever
    meaningful against the schema the guard was authored beside.
    """
    rows: list[_CorpusGuard] = []
    for fixture in _CORPUS:
        blocks = (
            ("ir", fixture.ir),
            ("ir_before", fixture.ir_before),
            ("ir_after", fixture.ir_after),
        )
        for block, ir in blocks:
            if ir is None:
                continue
            key = fixture.fixture_id if block == "ir" else f"{fixture.fixture_id}#{block}"
            for edge in ir.edges:
                if edge.kind == "conditional" and edge.condition is not None:
                    rows.append(_CorpusGuard(key, edge.from_, edge.condition, ir.state))
    return rows


#: The §3 fixture-validation table's recognized half, as
#: ``(fixture, from-node, counter, operator, bound, then-label, else-label, conjunct index)``.
#: The condition strings themselves are never written here — :func:`_guard_string` reads each
#: one out of the vendored fixture at call time — and neither is R2's bound direction, which
#: the test derives from the operator through :data:`BOUND_DIRECTIONS` rather than restating.
_RECOGNIZED = [
    (_POSITIVE_01, "check_response", "retry_count", "<", 3, "retry", "done", 1),
    (_POSITIVE_02, "collect_feedback", "remaining_steps", ">", 2, "refine", "wrap_up", 1),
    (_POSITIVE_04, "validate_quote", "quote_retry_count", "<", 3, "requote", "accept", 1),
    (_POSITIVE_04, "assess_itinerary", "revision_round", "<", 5, "revise", "finalize", 1),
    (_NEGATIVE_02, "assess_itinerary", "revision_round", "<", 5, "revise", "finalize", 1),
    (_NEGATIVE_03, "throttle_check", "refresh_count", "<", 4, "immediate", "delayed", 0),
]

#: How many conjuncts each recognized guard's ``test`` decomposes into (R3). Separate from
#: the table above only because ``negative-03`` is the one whose ``test`` is a bare bounded
#: comparison, and that asymmetry is easier to read as its own line than as a column.
_CONJUNCT_COUNTS = {(_NEGATIVE_03, "throttle_check"): 1}

#: The table's opaque half, with the L0 clause §3 lists *first* among those each violates.
#: The last two rows are DEC-16 gap fixtures (TE-14, vault ``e6ea366``): both of
#: ``positive-06``'s routers are plain prose with no ternary at all (the second also
#: carries an ``or`` token, but the ``if``-count clause runs first).
_OPAQUE = [
    (_POSITIVE_03, "check_worklist", "parenthesis and bracket"),
    (_NEGATIVE_01, "reflect", "exactly one `if` token"),
    (_NEGATIVE_02, "judge_fare", "exactly one `if` token"),
    (_NEGATIVE_03, "evaluate_rates", "only inside the two label-literal tokens"),
    (_NEGATIVE_04, "supervisor", "exactly one `if` token"),
    (_POSITIVE_06, "revise_itinerary", "exactly one `if` token"),
    (_POSITIVE_06, "audit_itinerary", "exactly one `if` token"),
]

#: The R1-opaque rows — DEC-16 gap fixtures whose guards DERIVE the §3 host ternary but
#: carry no ``bounded-comparison`` conjunct, so they are opaque under R1/R5 rather than L0:
#: the exit-edge-is-not-a-witness shape (``negative-01``'s rule) on the minimal grammar
#: surface. Kept apart from :data:`_OPAQUE` because the classifier names a different gate.
_OPAQUE_R1 = [
    (_NEGATIVE_05, "compose_reply"),
    (_POSITIVE_05, "research_specialist"),
]

_RECOGNIZED_IDS = [f"{fixture.split('/')[1][:12]}:{source}" for fixture, source, *_ in _RECOGNIZED]
_OPAQUE_IDS = [f"{fixture.split('/')[1][:12]}:{source}" for fixture, source, _ in _OPAQUE]
_OPAQUE_R1_IDS = [f"{fixture.split('/')[1][:12]}:{source}" for fixture, source in _OPAQUE_R1]


# ── The §3 fixture-validation table (acceptance box 1) ───────────────────────────────────


def test_the_termination_witness_corpus_carries_exactly_the_fifteen_guard_strings() -> None:
    """§3's "full ``termination-witness/`` corpus" — its 6 + 5 — plus the DEC-16 four.

    §3's fixture-validation paragraph names eleven strings; the DEC-16 gap-fixture extension
    (TE-14, vault ``e6ea366``) added four more routers to the directory, all deliberately
    opaque (two L0-rejected, two R1-rejected — a class §3's own corpus never exercised).
    Pinned so the tables below cannot quietly stop covering the corpus: a re-vendor that
    added a sixteenth router, or moved one, fails here rather than passing stale rows.
    """
    declared = {(fixture, source) for fixture, source, *_ in _RECOGNIZED}
    declared |= {(fixture, source) for fixture, source, _ in _OPAQUE}
    declared |= set(_OPAQUE_R1)
    found = {(row.fixture, row.source) for row in _corpus_guards() if row.fixture.startswith(_TW)}

    assert found == declared
    assert len(found) == 15


@pytest.mark.parametrize(
    ("fixture", "source", "counter", "operator", "bound", "then", "otherwise", "index"),
    _RECOGNIZED,
    ids=_RECOGNIZED_IDS,
)
def test_the_six_recognized_guards_derive_guard_with_a_bounded_comparison(
    fixture: str,
    source: str,
    counter: str,
    operator: str,
    bound: int,
    then: str,
    otherwise: str,
    index: int,
) -> None:
    """Half of acceptance box 1: every recognized string, classified field for field.

    Not just "recognized" — the counter position (R1), the operator and its bound direction
    (R2), the ``int-literal``, both labels (R6) and the conjunct decomposition (R3) are all
    pinned, because a matcher that recognized the right strings for the wrong reasons would
    hand VAL-07 the wrong witness.
    """
    condition = _guard_string(fixture, source)
    found = classify_guard(condition)

    assert found.recognized, found.reason
    assert found.rejected_by is None
    guard = found.guard
    assert guard is not None
    assert guard.condition == condition
    assert guard.counter_key == counter
    assert guard.comparison.operator == operator
    assert guard.bound == bound
    assert guard.comparison.direction == BOUND_DIRECTIONS[operator]
    assert guard.comparison.mirrored is False
    assert (guard.then_label, guard.else_label) == (then, otherwise)
    assert guard.comparison_index == index
    assert guard.comparison.text == guard.conjuncts[index]
    assert len(guard.conjuncts) == _CONJUNCT_COUNTS.get((fixture, source), 2)


@pytest.mark.parametrize(("fixture", "source", "clause"), _OPAQUE, ids=_OPAQUE_IDS)
def test_the_seven_l0_opaque_guards_fail_l0(fixture: str, source: str, clause: str) -> None:
    """Half of box 1's "all fail L0 or R0": §3's original five plus ``positive-06``'s two.

    All seven fail **L0**, which is a stronger and more useful fact than the disjunction §3
    states, so the gate is asserted rather than left open — and the clause each one trips is
    asserted with it, since "opaque" alone would pass for the wrong reason (an
    implementation that rejected every string would satisfy the weaker claim). The two
    R1-rejected DEC-16 guards are the test below.
    """
    found = classify_guard(_guard_string(fixture, source))

    assert not found.recognized
    assert found.guard is None
    assert found.rejected_by == "L0"
    assert clause in found.reason


@pytest.mark.parametrize(("fixture", "source"), _OPAQUE_R1, ids=_OPAQUE_R1_IDS)
def test_the_two_r1_opaque_guards_derive_the_ternary_but_carry_no_comparison(
    fixture: str, source: str
) -> None:
    """The DEC-16 additions exercise the gate §3's own eleven never reached: R1.

    Both guards derive the host ternary under L0/R0 — one ``if``, one ``else``, quotes only
    in the two label literals — but their ``test`` decomposes into opaque conjuncts alone,
    so R1 finds no ``bounded-comparison`` and R5 makes the whole string opaque with no
    partial credit and no diagnostic: an exit edge is not a witness (``negative-01``'s
    rule), here on the minimal grammar surface. Pinned by gate so an implementation that
    started granting partial credit for the derived ternary fails loudly.
    """
    found = classify_guard(_guard_string(fixture, source))

    assert not found.recognized
    assert found.guard is None
    assert found.rejected_by == "R1"
    assert "`bounded-comparison`" in found.reason


@pytest.mark.parametrize(
    ("fixture", "source", "counter"),
    [(row[0], row[1], row[2]) for row in _RECOGNIZED],
    ids=_RECOGNIZED_IDS,
)
def test_each_recognized_counter_is_integer_compatible_in_its_own_fixtures_sigma(
    fixture: str, source: str, counter: str
) -> None:
    """R1's second half against the fixture's own ``state`` block (§2.1).

    Recognition is syntax; qualification needs Σ. Every one of the six names a key its own
    fixture declares ``int``, which is why the §3 table calls them recognized *guards* and
    not merely recognized strings.
    """
    qualified = qualify_counter_guard(_guard_string(fixture, source), _state(fixture))

    assert qualified.outcome == "qualified"
    assert qualified.qualified
    assert qualified.guard is not None
    assert qualified.guard.counter_key == counter
    assert qualified.unmatched_identifier is None
    assert qualified.declared_type == "int"


def test_negative_03_is_recognized_which_is_what_routes_it_to_the_d4_check() -> None:
    """§3's own closing sentence, which is the reason ``negative-03`` is in the table twice.

    "In particular ``negative-03``'s ``'immediate' if refresh_count < 4 else 'delayed'`` IS
    recognized — which is what routes it to the D4 side-condition check where
    ``counter-guard-without-exit-edge`` fires (§4)." The same fixture's *router* is opaque,
    so the two halves of the table meet inside one fixture: recognizing the guard is what
    makes the D4 defect reportable at all, and the fixture's own ``expected:`` block names
    the counter key this recognizer must produce for that finding to be constructible.
    """
    counter_guard = classify_guard(_guard_string(_NEGATIVE_03, "throttle_check"))
    router = classify_guard(_guard_string(_NEGATIVE_03, "evaluate_rates"))

    assert counter_guard.recognized and not router.recognized
    assert counter_guard.guard is not None
    failure = next(f for f in _CORPUS if f.fixture_id == _NEGATIVE_03).expected["failure"]
    assert failure["property_condition"] == "counter-guard-without-exit-edge"
    assert counter_guard.guard.counter_key == failure["location"]["counter_key"]
    # R6: the gated label is the *first* of the guard's declared labels here, and the D4
    # location carries both — the recognizer names which one the comparison gates.
    assert counter_guard.guard.then_label in failure["location"]["guard_edge"]["labels"]
    assert counter_guard.guard.else_label in failure["location"]["guard_edge"]["labels"]


@pytest.mark.parametrize(
    ("fixture", "source"),
    [
        (_POSITIVE_01, "check_response"),
        (_POSITIVE_04, "validate_quote"),
        (_POSITIVE_04, "assess_itinerary"),
    ],
    ids=["positive-01", "positive-04:quote", "positive-04:itinerary"],
)
def test_the_recognized_counter_and_bound_match_the_fixtures_own_expected_inventory(
    fixture: str, source: str
) -> None:
    """The strongest available cross-check: recognizer output vs the vendored expectation.

    These three form-(a) inventory entries carry ``counter_key``, ``bound`` and
    ``guard_edge.label`` in the fixture's own ``expected:`` block — the §2.3 witness source
    shape. Nothing in this assertion is authored by this card: both sides come out of the
    corpus, one through the recognizer and one straight off the YAML. ``guard_edge.label``
    is R6's gated label, so agreement there is the corpus confirming the then-label reading.
    """
    guard = classify_guard(_guard_string(fixture, source)).guard
    assert guard is not None
    witness = next(f for f in _CORPUS if f.fixture_id == fixture).expected["witness"]
    entry = next(e for e in witness["inventory"] if e["source"]["guard_edge"]["source"] == source)

    assert entry["form"] == "a"
    assert guard.counter_key == entry["source"]["counter_key"]
    assert guard.bound == entry["source"]["bound"]
    assert guard.then_label == entry["source"]["guard_edge"]["label"]


# ── L0, and no partial credit (acceptance box 2) ─────────────────────────────────────────


#: A string that is recognized, and the four ways §3's L0 clauses spoil it. Each spoiler
#: leaves the ``retry_count < 3`` conjunct intact and fully recognizable in isolation, which
#: is the point: R5 says there is no partial credit, so none of them may yield any.
_BASE_GUARD = "'retry' if response is stale and retry_count < 3 else 'done'"
_L0_SPOILERS = [
    ("or", "'retry' if response is stale or retry_count < 3 else 'done'"),
    ("not", "'retry' if not response and retry_count < 3 else 'done'"),
    ("nested-ternary", "'retry' if retry_count < 3 else 'wait' if slow else 'done'"),
    ("no-else", "'retry' if retry_count < 3 'done'"),
    ("parenthesis", "'retry' if len(queue) and retry_count < 3 else 'done'"),
    ("bracket", "'retry' if queue[0] and retry_count < 3 else 'done'"),
    ("string-literal", "'retry' if status == 'stale' and retry_count < 3 else 'done'"),
    ("double-quote", "'retry' if sta\"tus and retry_count < 3 else 'done'"),
]


def test_the_no_partial_credit_check_is_not_vacuous() -> None:
    """The negative control for the suite below: unspoiled, the base string is recognized.

    Without this, every assertion in :func:`test_l0_rejection_yields_no_partial_credit` would
    pass against a recognizer that rejected everything.
    """
    found = classify_guard(_BASE_GUARD)

    assert found.recognized
    assert found.guard is not None
    assert (found.guard.counter_key, found.guard.bound) == ("retry_count", 3)


@pytest.mark.parametrize(
    "spoiled", [row[1] for row in _L0_SPOILERS], ids=[row[0] for row in _L0_SPOILERS]
)
def test_l0_rejection_yields_no_partial_credit(spoiled: str) -> None:
    """Acceptance box 2. L0 rejects "as opaque *wholesale* — no partial credit, per R5".

    Each input differs from :data:`_BASE_GUARD` by one L0 violation and still contains
    ``retry_count < 3`` verbatim, so a recognizer that salvaged the good conjunct would pass
    the §3 table and fail here. Three surfaces are checked, because "no partial credit" has
    to hold on all of them: the classification carries no guard, the qualification collapses
    to ``"opaque"`` with no identifier to report, and the catalog §2.4 entry point returns
    ``None``.
    """
    assert "retry_count < 3" in spoiled  # the salvageable fragment really is present
    found = classify_guard(spoiled)

    assert not found.recognized
    assert found.guard is None
    assert found.rejected_by == "L0"

    qualified = qualify_counter_guard(spoiled, {"retry_count": StateField(type="int")})
    assert qualified.outcome == "opaque"
    assert qualified.guard is None
    assert qualified.unmatched_identifier is None
    assert qualified.declared_type is None

    assert recognize_bounded_comparison(spoiled, {"retry_count": StateField(type="int")}) is None


@pytest.mark.parametrize(
    "spoiled", [row[1] for row in _L0_SPOILERS], ids=[row[0] for row in _L0_SPOILERS]
)
def test_an_l0_rejection_has_no_channel_to_leak_a_fragment_through(spoiled: str) -> None:
    """No partial credit as a *shape*, not only as a value.

    Every field of :class:`~gebra.verify.guards.GuardClassification` is enumerated and
    checked: the only members a rejection carries are the input, the gate and the reason.
    A future field able to hold a counter key or a label would fail here rather than
    silently reopening the door R5 closes.
    """
    found = classify_guard(spoiled)
    fields = {field.name for field in found.__dataclass_fields__.values()}

    assert fields == {"condition", "guard", "rejected_by", "reason"}
    assert found.condition == spoiled
    assert found.guard is None
    assert "retry_count" not in found.reason


def test_l0_reports_its_clauses_in_the_order_section_3_writes_them() -> None:
    """The four clauses, each isolated so that its own message is the one reported.

    §3 lists them in one sentence: the ``if``/``else`` multiplicity, then ``or``/``not``,
    then the quote rule, then parentheses and brackets. A string violating several reports
    the first, which is what makes the diagnostics stable.
    """
    assert "exactly one `if`" in classify_guard("'a' 'b'").reason
    assert "exactly one `else`" in classify_guard("'a' if x < 1 'b'").reason
    assert "`or` token" in classify_guard("'a' if x < 1 or y else 'b'").reason
    assert "`not` token" in classify_guard("'a' if not x else 'b'").reason
    assert "label-literal tokens" in classify_guard("'a' if 'x' < 1 else 'b'").reason
    assert "parenthesis and bracket" in classify_guard("'a' if (x) < 1 else 'b'").reason


def test_the_quote_clause_reading_is_not_verdict_bearing() -> None:
    """L0's third clause is implemented as *the first and last tokens*; the docstring says so.

    The alternative reading — "any token that is syntactically a label-literal" — would let
    ``'x'`` through L0 here. It cannot change any verdict, because ``plain-char`` and
    ``counter-ref`` both exclude quote characters, so a quoted token anywhere inside ``test``
    fails R0 under either reading. Pinned so the choice stays a diagnostic one.
    """
    mid_literal = classify_guard("'a' if 'x' < 1 and n < 2 else 'b'")
    assert not mid_literal.recognized
    # The same conjunct, quoted the other way, is unreachable by the grammar too.
    assert not classify_guard("'a' if x == \"1\" and n < 2 else 'b'").recognized


# ── The grammar, rule by rule ────────────────────────────────────────────────────────────


def test_r0_rejects_a_bare_comparison_because_the_gated_label_would_be_undefined() -> None:
    """R0: "A **bare comparison** with no label literals ... is deliberately NOT a v1 host
    shape: with no label literal in the string, the label selected on comparison-truth is not
    syntactically evident, so the gated label (R6) would be undefined — fail-closed."
    """
    assert not classify_guard("retry_count < 3").recognized
    # ... and the ternary shape with *unquoted* labels is the same exclusion, reached at R0
    # rather than at L0, because nothing lexical is wrong with it.
    unquoted = classify_guard("retry if retry_count < 3 else done")
    assert not unquoted.recognized
    assert unquoted.rejected_by == "R0"
    assert "then-label" in unquoted.reason
    assert classify_guard("'retry' if retry_count < 3 else done").rejected_by == "R0"


def test_r0_rejects_a_degenerate_or_misplaced_ternary() -> None:
    """The two host-shape failures L0 lets through, since it counts ``if``/``else`` tokens
    without caring where they sit.

    A five-token minimum is what ``guard`` needs — two labels, ``if``, ``else`` and a
    one-token ``test`` — and the two keywords have to be the second and second-to-last
    tokens. Neither string here has a quote in it, so L0 has nothing to object to and R0 is
    genuinely the gate that fires.
    """
    assert classify_guard("if else").rejected_by == "R0"
    assert "too few tokens" in classify_guard("if else").reason
    assert classify_guard("a b if c else d").rejected_by == "R0"
    assert "misplaced" in classify_guard("a b if c else d").reason
    assert "misplaced" in classify_guard("a if b else c d").reason


def test_r0_rejects_a_conjunct_that_derives_neither_production() -> None:
    """``test ::= conjunct { "and" conjunct }`` — *every* conjunct must derive, so a
    conjunct that is neither a ``bounded-comparison`` nor an ``opaque-conjunct`` sinks the
    whole derivation even when a perfectly good comparison sits beside it.

    The unreachable-by-tokenizer case is the one that matters: a newline is not ``ws`` (§3
    admits spaces and tabs, "no other whitespace"), so it never splits a token, and the token
    it sits inside derives no ``plain-token``.
    """
    found = classify_guard("'a' if we\nfailed and retry_count < 3 else 'b'")

    assert found.rejected_by == "R0"
    assert "derives neither" in found.reason
    assert classify_guard("'a' if and retry_count < 3 else 'b'").rejected_by == "R0"
    assert classify_guard("'a' if retry_count < 3 and else 'b'").rejected_by == "R0"


def test_r1_takes_the_leftmost_bounded_comparison_when_several_derive() -> None:
    """R1: "if several do, the **leftmost** is the recognized comparison (deterministic)"."""
    guard = classify_guard("'a' if first < 1 and second < 2 and third < 3 else 'b'").guard

    assert guard is not None
    assert (guard.counter_key, guard.bound, guard.comparison_index) == ("first", 1, 0)
    assert guard.conjuncts == ("first < 1", "second < 2", "third < 3")


def test_r1_normalizes_a_mirrored_comparison_to_counter_on_the_left() -> None:
    """R1: "Mirrored forms normalize to counter-on-left (``3 > retry_count`` ≡
    ``retry_count < 3``)"."""
    guard = classify_guard("'a' if 3 > retry_count else 'b'").guard

    assert guard is not None
    assert (guard.counter_key, guard.comparison.operator, guard.bound) == ("retry_count", "<", 3)
    assert guard.comparison.mirrored is True
    assert guard.comparison.direction == "upper"
    assert guard.comparison.text == "3 > retry_count"
    # The mirror is a bijection on the four operators, and the direction rides with it.
    mirrored = classify_guard("'a' if 2 <= steps else 'b'").guard
    assert mirrored is not None
    assert (mirrored.comparison.operator, mirrored.comparison.direction) == (">=", "lower")


def test_r1_rejects_a_host_shape_carrying_no_bounded_comparison() -> None:
    """R1's own gate: the derivation succeeded, and there is still nothing to bound.

    This is the one rejection that is neither lexical nor a parse failure, and it is where
    the corpus's six ``'label' if <prose> else 'label'`` routers land.
    """
    found = classify_guard("'book' if needs_booking else 'skip'")

    assert found.rejected_by == "R1"
    assert "bounded-comparison" in found.reason
    assert found.guard is None


def test_r2_reads_the_bound_direction_off_the_operator() -> None:
    """R2: ``<``/``<=`` declare an upper bound (increment-style), ``>``/``>=`` a lower bound
    (decrement-style, "the decrementing dual used by fixture ``positive-02``")."""
    for operator in CMP_OPS:
        guard = classify_guard(f"'a' if n {operator} 3 else 'b'").guard
        assert guard is not None
        assert guard.comparison.direction == BOUND_DIRECTIONS[operator]
    assert {BOUND_DIRECTIONS[operator] for operator in ("<", "<=")} == {"upper"}
    assert {BOUND_DIRECTIONS[operator] for operator in (">", ">=")} == {"lower"}


def test_r3_admits_opaque_conjuncts_beside_the_recognized_one() -> None:
    """R3: "The recognized ``bounded-comparison`` may appear conjoined (``and``) with opaque
    conjuncts ... which is the safe direction".

    The §3 text names ``positive-01``'s guard as the example, so the example is taken from
    the fixture rather than reproduced: an opaque conjunct on either side, and any number of
    them, leaves the recognized comparison untouched.
    """
    guard = classify_guard(_guard_string(_POSITIVE_01, "check_response")).guard
    assert guard is not None
    assert guard.conjuncts[0] == "response is transient-failure"
    assert guard.comparison_index == 1

    leading = classify_guard("'a' if n < 3 and it looks bad and worse still else 'b'").guard
    assert leading is not None
    assert leading.comparison_index == 0
    assert len(leading.conjuncts) == 3


def test_r6_gates_the_then_label_and_never_the_else_branch() -> None:
    """R6: the comparison gates "the **then-label only** — the first ``label-literal``".

    "Even when ``test`` is a bare bounded comparison (whose negation would itself be a
    bounded comparison), v1 does not discharge the else-label — fail-closed." So the value
    this module produces names both labels and marks neither as discharged: there is no
    discharge field on it at all, because assembling S is §4's and VAL-07's.
    """
    guard = classify_guard("'keep_going' if n < 3 else 'stop'").guard

    assert guard is not None
    assert (guard.then_label, guard.else_label) == ("keep_going", "stop")
    fields = {field.name for field in RecognizedGuard.__dataclass_fields__.values()}
    assert not any("discharge" in name for name in fields)


# ── The "Deliberate v1 exclusions" list, item by item ────────────────────────────────────


@pytest.mark.parametrize(
    ("exclusion", "condition", "gate"),
    [
        ("non-ascii identifier", "'a' if café < 3 else 'b'", "R1"),
        ("negative literal", "'a' if n < -1 else 'b'", "R1"),
        ("equality", "'a' if n == 3 else 'b'", "R1"),
        ("inequality", "'a' if n != 3 else 'b'", "R1"),
        ("bare comparison", "n < 3", "L0"),
        ("nested ternary", "'a' if n < 3 else 'b' if m else 'c'", "L0"),
        ("parenthesized", "'a' if (n) < 3 else 'b'", "L0"),
        ("quoted", "'a' if s == 'x' else 'b'", "L0"),
        ("bracketed", "'a' if xs[0] < 3 else 'b'", "L0"),
        ("worklist emptiness", "'next' if len(xs) > 0 else 'done'", "L0"),
        ("newline inside test", "'a' if n\n< 3 else 'b'", "R0"),
        ("newline in the host shape", "'a'\nif n < 3 else 'b'", "L0"),
    ],
)
def test_every_deliberate_v1_exclusion_is_opaque_and_never_mis_recognized(
    exclusion: str, condition: str, gate: str
) -> None:
    """§3's "Deliberate v1 exclusions (all fail-closed — an excluded shape is opaque, never
    mis-recognized)", enumerated.

    The gate each one trips is asserted too, so the list stays a statement about *why* each
    is excluded and not just that it is. ``non-ascii identifier`` and the two equality forms
    land at R1 rather than L0 because they derive perfectly good ``opaque-conjunct``\\ s —
    they are excluded for having no bound, not for being lexically dirty. The newline pair
    shows the same exclusion reached from both sides: a newline is not ``ws``, so it never
    splits a token — inside ``test`` that leaves a token deriving no ``plain-token`` (R0),
    and across the host shape it glues ``'a'`` to ``if`` so there is no ``if`` token at all
    (L0).
    """
    found = classify_guard(condition)

    assert not found.recognized, exclusion
    assert found.guard is None
    assert found.rejected_by == gate, f"{exclusion}: {found.reason}"


def test_worklist_guards_are_excluded_for_the_reason_r5_gives() -> None:
    """R5: "``len(hotel_shortlist) > 0`` is opaque via the L0 parenthesis rule, and
    shrinking-ness is not IR-decidable; the attested ``variant`` slot (form (c)) is the
    sanctioned carrier for worklist loops (fixture ``positive-03``)."

    Taken from the fixture, and paired with the same guard *without* the call: the exclusion
    is about the parenthesis, so removing it recognizes a comparison — and the key it names
    is still not integer-compatible, which is the second, independent reason ``positive-03``
    is a form-(c) fixture and not a form-(a) one.
    """
    declared = _guard_string(_POSITIVE_03, "check_worklist")
    assert classify_guard(declared).rejected_by == "L0"

    without_the_call = declared.replace("len(hotel_shortlist)", "hotel_shortlist")
    assert classify_guard(without_the_call).recognized
    qualified = qualify_counter_guard(without_the_call, _state(_POSITIVE_03))
    assert qualified.outcome == "counter-type-not-integer-compatible"
    assert qualified.declared_type == "list"


# ── Whitespace discipline (§3: "`ws` admits spaces and tabs; no other whitespace") ───────


def test_ws_admits_spaces_and_tabs_and_may_be_empty_inside_a_comparison() -> None:
    """``ws ::= { " " | TAB }`` is possibly-empty inside ``bounded-comparison`` and
    ``ws1`` is one-or-more everywhere else, so all three spellings are the same guard."""
    spaced = classify_guard("'a' if n < 3 else 'b'").guard
    tabbed = classify_guard("'a'\tif\tn\t<\t3\telse\t'b'").guard
    tight = classify_guard("'a' if n<3 else 'b'").guard

    assert spaced is not None and tabbed is not None and tight is not None
    for guard in (spaced, tabbed, tight):
        assert (guard.counter_key, guard.comparison.operator, guard.bound) == ("n", "<", 3)
    assert classify_guard("'a'  if   n  <=  30   else  'b'").guard is not None


def test_an_identifier_is_never_split_across_whitespace() -> None:
    """``counter-ref ::= identifier`` is one lexical unit — ``ws`` appears in
    ``bounded-comparison`` only around ``cmp-op``.

    The failure this pins is a real implementation temptation: matching the comparison
    against the conjunct's tokens *joined* rather than against its source slice would make
    ``retry _count < 3`` a bounded comparison on a key nothing declares.
    """
    found = classify_guard("'a' if retry _count < 3 else 'b'")

    assert found.rejected_by == "R1"
    assert found.guard is None
    assert classify_guard("'a' if retry_count < 3 else 'b'").recognized


def test_an_over_long_int_literal_is_opaque_rather_than_a_hang_or_a_raise() -> None:
    """The one narrowing this module makes to §3, and the three defects it exists to avoid.

    §3's ``int-literal ::= digit { digit }`` is unbounded and has no conforming
    implementation: ``int()`` raises past ``sys.get_int_max_str_digits()``; accumulating the
    digits by hand reproduces the quadratic cost the cap exists to prevent
    (**measured before this narrowing landed: 1.3 s at 100 000 digits, 5.3 s at 200 000, 21 s
    at 400 000** — a declared string, so unbounded input); and a value that *is* accumulated
    cannot be rendered, so ``repr()`` and JSON serialization of any report carrying it raise
    later and further from the cause. So an over-long literal is not recognized, the conjunct
    falls through to ``opaque-conjunct``, and R1 reports no bound — fail-closed, which can
    only remove witnesses.

    The boundary is asserted on both sides, because a cap nobody tests is a cap nobody keeps.
    """
    budget = sys.int_info.str_digits_check_threshold

    at_the_limit = classify_guard("'a' if n < " + "9" * budget + " else 'b'").guard
    assert at_the_limit is not None
    assert at_the_limit.bound == 10**budget - 1
    assert len(str(at_the_limit.bound)) == budget  # renderable, which is the whole criterion

    one_too_many = classify_guard("'a' if n < " + "9" * (budget + 1) + " else 'b'")
    assert not one_too_many.recognized
    assert one_too_many.rejected_by == "R1"  # opaque conjunct, no bound — never a raise
    assert one_too_many.guard is None
    assert classify_guard("'a' if " + "9" * (budget + 1) + " > n else 'b'").guard is None


def test_no_declared_condition_makes_the_recognizer_hang_or_raise() -> None:
    """Adversarial declared strings, including ones that reach the literal path.

    The two comparison patterns put no quantifier over overlapping classes, so ``fullmatch``
    fails in one pass and adversarially long tokens stay linear. The first two inputs are
    near-misses of the literal path (no digits; a trailing ``x`` that fails the match), the
    third is many short conjuncts, and the last two **land on it** — a 200 000-digit literal
    in each operand order, the shape that cost 5.3 s before the cap and is now rejected on a
    length check. The budget below is a hang detector, not a performance budget, and must not
    be tightened into one.
    """
    near_misses = [
        "'a' if " + "z" * 40_000 + " else 'b'",
        "'a' if " + "z" * 20_000 + "<" + "9" * 20_000 + "x else 'b'",
    ]
    on_the_literal_path = [
        "'a' if n < " + "9" * 200_000 + " else 'b'",
        "'a' if " + "9" * 200_000 + " > n else 'b'",
    ]
    many_conjuncts = "'a' if " + " and ".join(["n < 3"] * 5_000) + " else 'b'"

    started = time.perf_counter()
    for condition in near_misses + on_the_literal_path:
        assert not classify_guard(condition).recognized
    # Recognized, and that is correct — 5 000 well-formed conjuncts is not an attack, it is a
    # long guard. What is asserted about it is that it comes back at all.
    assert classify_guard(many_conjuncts).recognized
    assert time.perf_counter() - started < 5.0


def test_a_conjunct_must_derive_the_comparison_in_full() -> None:
    """``conjunct ::= bounded-comparison | opaque-conjunct`` — one or the other, whole.

    A comparison with anything trailing it is an ``opaque-conjunct`` at best, so R1 finds no
    bound; it is never a bounded comparison with a tail.
    """
    assert classify_guard("'a' if n < 3 tail else 'b'").rejected_by == "R1"
    assert classify_guard("'a' if head n < 3 else 'b'").rejected_by == "R1"


# ── §2.1 integer compatibility, fail-closed ──────────────────────────────────────────────


@pytest.mark.parametrize(
    "declared",
    [
        "int",
        StateField(type="int"),
        StateField(type="int", reducer="operator.add"),
        StateField(type="int", optional=True),
    ],
    ids=["bare", "object", "with-reducer", "with-optional"],
)
def test_the_integer_compatible_enumeration_admits_exactly_what_section_2_1_lists(
    declared: str | StateField,
) -> None:
    """§2.1: "the bare type-name string ``"int"``, or an object whose ``type`` member is
    ``"int"`` (the ``reducer`` and ``optional`` members are irrelevant to qualification —
    fixture ``positive-01``'s ``retry_count: {type: int, reducer: "operator.add"}``
    qualifies)"."""
    assert is_integer_compatible(declared)


@pytest.mark.parametrize(
    "declared",
    [
        "float",
        "number",
        "str",
        "list",
        "Int",
        "INT",
        "int32",
        "Optional[int]",
        "integer",
        "",
        None,
        StateField(type="float"),
        StateField(type="number"),
    ],
)
def test_nothing_else_is_integer_compatible(declared: str | StateField | None) -> None:
    """§2.1: "**Nothing else qualifies** — not ``"float"``, ``"number"``, ``"str"``,
    ``"list"``, or any other type expression. Fail-closed: an unrecognized type expression
    makes the guard contribute no witness."

    The four §2.1 names are the parametrization's spine; the rest are the near-spellings a
    permissive implementation would let through — a widened alias, a case fold, a sized
    integer, an ``Optional`` wrapper.
    """
    assert not is_integer_compatible(declared)


def test_positive_01s_own_state_block_is_the_reducer_case_section_2_1_names() -> None:
    """The §2.1 parenthetical, read out of the fixture it cites rather than restated."""
    declared = _state(_POSITIVE_01)
    assert declared is not None
    retry_count = declared["retry_count"]

    assert isinstance(retry_count, StateField)
    assert (retry_count.type, retry_count.reducer) == ("int", "operator.add")
    assert is_integer_compatible(retry_count)


# ── The §4 qualification-failure paths this module can see ───────────────────────────────


def test_a_counter_key_absent_from_sigma_is_a_near_miss_not_a_silent_drop() -> None:
    """§4 path 1: "the guard is treated as opaque (no witness) and the checker MUST emit a
    structured advisory identifying $g$ and the unmatched identifier (the likely-misspelled-
    counter case)".

    The witness contribution is the same as for an opaque string — none — and the *report*
    is not, which is why the two outcomes are distinct here. "A misspelled key never silently
    shrinks coverage."
    """
    misspelled = "'retry' if retry_conut < 3 else 'done'"
    qualified = qualify_counter_guard(misspelled, {"retry_count": StateField(type="int")})

    assert qualified.outcome == "counter-key-not-in-state"
    assert qualified.unmatched_identifier == "retry_conut"
    assert qualified.guard is None
    assert qualified.classification.recognized  # the syntax was fine; Σ was not
    assert recognize_bounded_comparison(misspelled, {"retry_count": StateField(type="int")}) is None


def test_a_wrongly_typed_counter_is_the_other_half_of_path_1() -> None:
    """§4 path 1's second limb: "``counter-ref`` ∉ keys(Σ) **or its type is not
    integer-compatible** (§2.1)". The declared type is carried so the advisory can name it."""
    qualified = qualify_counter_guard("'a' if n < 3 else 'b'", {"n": StateField(type="float")})

    assert qualified.outcome == "counter-type-not-integer-compatible"
    assert qualified.unmatched_identifier == "n"
    assert qualified.declared_type == "float"
    assert qualified.guard is None


def test_an_ir_with_no_state_block_makes_every_recognized_guard_a_near_miss() -> None:
    """Σ is optional in the IR models; an absent ``state`` block is the empty schema, in
    which no counter key can be a member. Fail-closed, and reported rather than dropped."""
    qualified = qualify_counter_guard("'a' if n < 3 else 'b'", None)

    assert qualified.outcome == "counter-key-not-in-state"
    assert qualified.unmatched_identifier == "n"


def test_an_opaque_string_is_not_a_near_miss() -> None:
    """§4 enumerates the paths by which a *declared* ingredient fails to qualify. An opaque
    string declared no counter, so there is no identifier to report and no advisory owed."""
    qualified = qualify_counter_guard("'a' if len(xs) < 3 else 'b'", {"xs": "int"})

    assert qualified.outcome == "opaque"
    assert qualified.unmatched_identifier is None
    assert qualified.classification.rejected_by == "L0"


def test_no_qualification_outcome_is_a_condition_id_or_a_note_kind() -> None:
    """This module emits nothing, and its vocabulary must not be mistaken for one that does.

    The outcome labels are this module's own diagnostic names: not §0.4 condition IDs, and —
    since DEC-23 resolved §4's delegation by adding ``counter-key-not-qualified`` to the
    §2.3 note vocabulary — not note kinds either. The near word-collision is the trap the
    VAL-07 card warns about: ``counter-key-not-in-state`` (diagnostic, here) sits one word
    from ``variant-key-not-in-state`` (a real note kind), and the mapping between the two
    vocabularies lives in the validator's explicit table, never in a rename.
    """
    outcomes = {
        "qualified",
        "counter-key-not-in-state",
        "counter-type-not-integer-compatible",
        "opaque",
    }
    note_kinds = set(get_args(WitnessNoteKind))

    assert outcomes.isdisjoint(set(CONDITION_IDS))
    assert {"L0", "R0", "R1"}.isdisjoint(set(CONDITION_IDS))
    assert outcomes.isdisjoint(note_kinds)
    assert "counter-key-not-qualified" in note_kinds


# ── The corpus, swept ────────────────────────────────────────────────────────────────────


def test_the_recognizer_accepts_exactly_twelve_of_the_fifty_five_corpus_guards() -> None:
    """Over-recognition is the failure mode the §3 table cannot catch on its own.

    The table fixes fifteen strings in one directory; this sweeps every conditional edge in
    all seventy-one fixtures, both snapshots of each evolution pair included, and pins the
    accepted set exactly. Six guards outside ``termination-witness/`` are recognized, and
    all six are right to be: ``mixed/08`` is the A7 E1 bypass fixture whose name ends
    "and-witnessed-exit", ``mixed/09``'s retry router carries a declared counter its Σ
    types ``int``, ``mixed/10``'s publish-retry router joined the set when DEC-23 (PD-037
    Q3) reworded its guard to the prose-conjunct style — its declared ``attempts < 3``
    bound is now inside the grammar, which is exactly what that fixture's expected
    form-(a) witness needs — and the three DEC-16 gap fixtures (TE-14, vault ``e6ea366``)
    each carry the counter guard their own P-02 witness needs: the cycle-entry pair's
    ``refresh_round < 3`` and the dangling-hook fixture's ``adjust_round < 2``.
    """
    accepted = {
        (row.fixture, row.source)
        for row in _corpus_guards()
        if classify_guard(row.condition).recognized
    }

    assert accepted == {
        (_POSITIVE_01, "check_response"),
        (_POSITIVE_02, "collect_feedback"),
        (_POSITIVE_04, "validate_quote"),
        (_POSITIVE_04, "assess_itinerary"),
        (_NEGATIVE_02, "assess_itinerary"),
        (_NEGATIVE_03, "throttle_check"),
        ("mixed/08-express-path-skips-gate-writer-and-witnessed-exit.yaml", "quality_gate"),
        ("mixed/09-send-fanout-billable-no-idempotency-in-retry.yaml", "check_bookings"),
        (_MIXED_10, "verify_publish"),
        (_DC_POSITIVE_04, "review_quote"),
        (_DC_NEGATIVE_04, "fetch_fare_quote"),
        (_ES_NEGATIVE_05, "review_hold"),
    }
    assert len(_corpus_guards()) == 55


def test_every_corpus_guard_the_recognizer_accepts_also_qualifies_against_its_own_sigma() -> None:
    """No recognized corpus guard is an R1 near-miss: every counter it names is declared
    ``int`` in the fixture that declares the guard. Recorded because the opposite would be a
    corpus defect worth routing (WA-04), not a recognizer bug."""
    recognized = [row for row in _corpus_guards() if classify_guard(row.condition).recognized]

    assert len(recognized) == 12  # not vacuous: the sweep really did find guards to qualify
    for row in recognized:
        outcome = qualify_counter_guard(row.condition, row.state).outcome
        assert outcome == "qualified", (row.fixture, row.source, outcome)


def _declares_a_bound_the_grammar_cannot_reach(condition: str) -> bool:
    """Whether ``test`` holds a conjunct that *is* a ``bounded-comparison`` in a string the
    recognizer nonetheless calls opaque.

    Built from the module's own tokenizer and conjunct splitter rather than from a second
    notion of "token", so the question asked is exactly the one §3 asks.
    """
    if classify_guard(condition).recognized:
        return False
    tokens = guards._tokenize(condition)
    spellings = [token.text for token in tokens]
    if spellings.count("if") != 1 or spellings.count("else") != 1:
        return False
    inner = tokens[spellings.index("if") + 1 : spellings.index("else")]
    conjuncts = guards._split_conjuncts(inner)
    if conjuncts is None:
        return False
    return any(
        guards._match_comparison(guards._slice(condition, one)) is not None for one in conjuncts
    )


def test_the_quoted_string_literal_router_idiom_puts_declared_bounds_out_of_reach() -> None:
    """A finding, pinned rather than written down: §3 cannot recognize ``== 'value'`` guards.

    ``plain-char`` excludes ``'`` and ``"``, so a quoted string literal inside ``test``
    derives no ``opaque-conjunct``, and L0's third clause rejects the same shape earlier for
    the stated reason ("rejects string literals that could smuggle ``and``/``or`` past the
    token scan"). **Fourteen corpus routers declare a bounded comparison the grammar
    therefore never reaches** — every one of them because a sibling conjunct quotes a
    literal, and none of their ``expected:`` blocks claims a P-02 witness, so the gap costs
    no fixture its verdict.

    ``mixed/10`` used to be the fifteenth and the one exception — the only router whose
    ``expected:`` block declared a form-(a) inventory entry (``counter_key: attempts``,
    ``bound: 3``) behind a quoted comparison. DEC-23 (PD-037 Q3) resolved it on the WA-04
    route: the guard was reworded to the corpus's prose-conjunct style, so its declared
    bound is now inside the grammar, asserted below. The idiom's prevalence across the
    remaining fourteen is registered as a candidate Phase-1 grammar widening
    (PHASE-1-NOTES), never a Phase-0 change. Asserted here so that it is a red test the day
    either side changes, rather than a paragraph nobody re-reads.
    """
    unreachable = [
        (row.fixture, row.source)
        for row in _corpus_guards()
        if _declares_a_bound_the_grammar_cannot_reach(row.condition)
    ]

    assert len(unreachable) == 14
    assert (_MIXED_10, "verify_publish") not in unreachable

    condition = _guard_string(_MIXED_10, "verify_publish")
    found = classify_guard(condition)
    assert found.recognized and found.guard is not None
    assert (found.guard.counter_key, found.guard.bound) == ("attempts", 3)
    assert (found.guard.then_label, found.guard.else_label) == ("retry", "done")
    expected = next(f for f in _CORPUS if f.fixture_id == _MIXED_10).expected
    entry = expected["witness"]["properties"]["termination-witness"]["inventory"][0]
    assert entry["form"] == "a"
    assert entry["source"]["counter_key"] == "attempts"
    assert entry["source"]["bound"] == 3


# ── Documentation, and WA-07 ─────────────────────────────────────────────────────────────


def test_the_module_docstring_examples_run() -> None:
    """WA-12 in the small: the examples in :mod:`gebra.verify.guards` are executed, so they
    cannot describe behaviour the module does not have."""
    results = doctest.testmod(guards, verbose=False)

    assert results.failed == 0
    assert results.attempted >= 7  # the recognized example and the no-partial-credit one


def test_the_recognizer_contains_no_evaluation_primitive() -> None:
    """WA-07's module-specific hazard: a grammar is not an interpreter.

    The tempting shortcut for "parse this condition" is ``eval``, ``compile`` or
    ``ast.literal_eval`` over declared user text — which would execute exactly the opaque
    Python §1.1 says is beyond the boundary.

    Every ``ast.Name`` is collected, in any context, not just call targets: ``_e = eval``
    followed by ``_e(text)`` records only ``_e`` at the call site, so a callee-only scan would
    miss the aliased form. The teeth, though, are the exact-set assertion on imports —
    ``ast.walk`` reaches function-local imports too, so pulling in ``ast``, ``importlib`` or
    ``builtins`` anywhere in the file fails here, and that is what closes
    ``ast.literal_eval(...)``, whose callee is an ``Attribute`` and not a ``Name`` at all.

    Two residuals, contrived rather than accidental, named so they are not mistaken for
    covered: ``__builtins__.eval(x)`` and ``globals()['eval'](x)`` reach a builtin through an
    attribute or a subscript and evade a name scan (``getattr`` being forbidden closes the
    third spelling). Both also evade ``tests/testing/test_hermeticity.py``'s repo-wide
    execution-primitive regex, whose lookbehind rejects the dotted form; neither is reachable
    by accident, and the import-set equality above is the load-bearing check regardless.
    """
    source = Path(guards.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    named = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    imported = {
        (node.module or "").split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    } | {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }

    assert named.isdisjoint(
        {"eval", "exec", "compile", "literal_eval", "__import__", "getattr", "globals", "vars"}
    )
    assert imported == {"__future__", "re", "sys", "collections", "dataclasses", "typing", "gebra"}
    assert "source_snippet" not in source


#: VAL-05's eleven, plus the four underscore-suffix siblings its `m.split('.')[0]` scan reads
#: verbatim and therefore never matched (`langchain_core` was in the set; `langchain_openai`
#: and friends were not). Kept spelled out rather than imported from another test module so
#: this file stands alone; the shared-helper consolidation the never-invokes pre-review
#: recommended at VAL-05 is a TE/TOOL follow-up, not this card's — widening one list in the
#: safe direction is, since the divergence is a superset.
_FORBIDDEN = (
    "{'langgraph', 'langgraph_sdk', 'langchain', 'langchain_core', 'langchain_openai', "
    "'langchain_anthropic', 'langsmith', 'litellm', 'networkx', 'openai', "
    "'anthropic', 'httpx', 'requests', 'aiohttp', 'urllib3'}"
)


def _tripwire_script(probe: str = "") -> str:
    """The guarded child: patch, import, classify every corpus guard, report.

    ``probe`` arms the raiser. Shared by the tripwire and its negative controls so that a
    control cannot drift onto a different raiser from the one the real test relies on.

    Σ reaches ``qualify_counter_guard`` as a validated :class:`~gebra.ir.WorkflowIR`'s
    ``state``, not as the raw YAML mapping: an object-form state field parsed straight out of
    the document is a ``dict``, which takes the wrongly-typed branch and never exercises the
    :class:`~gebra.ir.StateField` path a validator will actually hand it. The point of the
    call leg is that it is the real call.
    """
    return (
        "import glob, json, socket, sys\n"
        "attempts = []\n"
        "class _TripSocket(socket.socket):\n"
        "    def __new__(cls, *a, **k):\n"
        "        attempts.append('socket'); print('WA07-TRIP', file=sys.stderr)\n"
        "        raise AssertionError('socket created on the guard-recognizer path')\n"
        "def _trip(name):\n"
        "    def _raise(*a, **k):\n"
        "        attempts.append(name); print('WA07-TRIP', file=sys.stderr)\n"
        "        raise AssertionError(name + ' reached on the guard-recognizer path')\n"
        "    return _raise\n"
        "socket.socket = _TripSocket\n"
        "socket.getaddrinfo = _trip('getaddrinfo')\n"
        "socket.gethostbyname = _trip('gethostbyname')\n"
        "socket.create_connection = _trip('create_connection')\n"
        "import yaml\n"
        "from gebra.ir import WorkflowIR\n"
        "from gebra.verify.guards import classify_guard, qualify_counter_guard\n"
        "seen = qualified = 0\n"
        f"for path in sorted(glob.glob({str(FIXTURES_DIR)!r} + '/*/*.yaml')):\n"
        "    with open(path, encoding='utf-8') as handle:\n"
        "        document = yaml.safe_load(handle)\n"
        "    for key in ('ir', 'ir_before', 'ir_after'):\n"
        "        block = document.get(key)\n"
        "        if not block:\n"
        "            continue\n"
        "        ir = WorkflowIR.model_validate_json(json.dumps(block))\n"
        "        for edge in ir.edges:\n"
        "            if edge.condition is None:\n"
        "                continue\n"
        "            classify_guard(edge.condition)\n"
        "            found = qualify_counter_guard(edge.condition, ir.state)\n"
        "            qualified += found.outcome == 'qualified'\n"
        "            seen += 1\n"
        "assert (seen, qualified) == (55, 12), (seen, qualified)\n"
        f"{probe}"
        f"print([m for m in sys.modules if m.split('.')[0] in {_FORBIDDEN}] + attempts)\n"
    )


def test_recognizing_every_corpus_guard_creates_no_socket_and_resolves_no_name() -> None:
    """WA-07 on the recognizer path, import **and** call, to the VAL-13 tripwire standard.

    A fresh interpreter, because another test in this session may have imported anything.
    Three claims, separately enforced: no execution-substrate or HTTP/LLM-client package
    enters the import closure; no socket is created and no name resolved, either while
    importing the module or while running it over every declared ``condition`` in the
    vendored corpus — every edge kind, not only the routers, since ``normal`` and ``send``
    edges admit an inert ``condition`` too; and a swallowed exception still fails the run,
    because every attempt is recorded before the raise and also announced on stderr. The
    child asserts its own counts (55 conditions, 12 qualifying) so that a glob that silently
    stopped matching would fail the tripwire rather than pass it vacuously.

    One residual, named rather than left implicit, the same one VAL-03 and VAL-05 recorded:
    the package leg is a post-hoc ``sys.modules`` scan, not an import blocker, so a swallowed
    substrate import in an environment where the package is absent would go unrecorded here.
    ``tests/testing/test_hermeticity.py`` installs a real blocker on the wider path.
    """
    completed = subprocess.run(
        [sys.executable, "-c", _tripwire_script()], capture_output=True, text=True, check=True
    )

    assert completed.stdout.strip() == "[]", completed.stdout
    assert "WA07-TRIP" not in completed.stderr, completed.stderr


@pytest.mark.parametrize(
    "probe",
    (
        "socket.socket()\n",
        "socket.getaddrinfo('example.invalid', 80)\n",
        "socket.gethostbyname('example.invalid')\n",
        "socket.create_connection(('example.invalid', 80))\n",
    ),
    ids=("socket", "getaddrinfo", "gethostbyname", "create_connection"),
)
def test_the_tripwire_fires_when_the_guarded_path_is_armed(probe: str) -> None:
    """The negative control: prove the raiser is live, on the *same* script the tripwire runs.

    Without this, a patch that silently stopped installing ``_TripSocket`` would leave the
    tripwire passing for the wrong reason — the one failure mode a tripwire must not have.
    Arming it after the sweep has already run isolates the raiser: the green run above got
    that far too, so a non-zero exit here can only come from the probe.
    """
    completed = subprocess.run(
        [sys.executable, "-c", _tripwire_script(probe)],
        capture_output=True,
        text=True,
        check=False,  # a non-zero exit is the expected result here, not an error
    )

    assert completed.returncode != 0, completed.stdout
    assert "WA07-TRIP" in completed.stderr, completed.stderr


# ── Housekeeping the public surface owes ─────────────────────────────────────────────────


def test_the_reserved_words_are_the_five_section_3_names() -> None:
    """L0: "The **reserved words** are ``if``, ``else``, ``and``, ``or``, ``not`` — reserved
    only when they occur as whole tokens", which is what lets ``transient-failure`` through.
    """
    assert RESERVED_WORDS == frozenset({"if", "else", "and", "or", "not"})
    assert classify_guard("'a' if notice and n < 3 else 'b'").recognized
    assert classify_guard("'a' if fortitude and n < 3 else 'b'").recognized


def test_the_plain_token_predicate_refuses_a_reserved_word() -> None:
    """``plain-token ::= plain-char { plain-char }`` "(* not a reserved word *)".

    Exercised directly because it is unreachable through a condition string: L0 leaves
    exactly one ``if`` and one ``else``, both consumed by the host shape, bans ``or`` and
    ``not``, and ``and`` is the conjunct separator — so no conjunct token is ever reserved.
    The production says it anyway, so the implementation does, and this is where that is
    checked rather than left as an unexecuted branch.
    """
    assert guards._is_plain_token("transient-failure")
    assert not guards._is_plain_token("and")
    assert not guards._is_plain_token("")
    assert not guards._is_plain_token("has space")
    assert not guards._is_plain_token("has'quote")
    assert not guards._is_plain_token("has(paren")


def test_the_public_surface_is_re_exported_from_the_package() -> None:
    """Every name this module owns reaches consumers as ``from gebra.verify import ...``,
    which is how P-02's validator (VAL-07) will take it."""
    import gebra.verify as package

    for name in guards.__all__:
        assert name in package.__all__, name
        assert getattr(package, name) is getattr(guards, name)


def test_a_classification_is_immutable() -> None:
    """The results are frozen values: a consumer cannot edit a verdict into existence."""
    found = classify_guard(_BASE_GUARD)

    with pytest.raises(AttributeError):
        found.guard = None  # type: ignore[misc]
    assert isinstance(found, GuardClassification)
    assert isinstance(found.guard, RecognizedGuard)
    assert isinstance(found.guard.comparison, BoundedComparison)


def test_an_absent_condition_is_opaque_rather_than_an_error() -> None:
    """``ConditionalEdge.condition`` is optional in the IR models, so ``None`` has to be a
    verdict and not a crash — it has no tokens, so L0's first clause rejects it."""
    found = classify_guard(None)

    assert found.condition == ""
    assert found.rejected_by == "L0"
    assert recognize_bounded_comparison(None, {"n": "int"}) is None
