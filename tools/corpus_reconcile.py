"""Corpus reconciliation — the single DEC-09/DEC-11-mandated pass over the vendored corpus.

DEC-11 *Consequences* mandates one — exactly one — reconciliation pass: "the single corpus
pass normalizes witness/failure/location shapes to these pins (P-01 5-key, P-02 discriminated
forms, P-04 ``location.kind`` + ``severity``/``claim_class``, P-06/P-08 callout items)
together with the DEC-09-mandated ``ir_version`` bump, gated by the corpus lint".
This module is that pass expressed as data: every edit it would make, every claim it verifies
instead of editing, every question it refuses to answer locally, and every shape it leaves
alone — each with the frozen passage that fixes it.

**The pass has landed.** The plan below was ratified as PD-016 and filed in the vault as
**DEC-17**, and the reconciled bytes were re-vendored from vault ``b2056e9`` — so ``--check``
now exits 0 against ``tests/fixtures/properties/`` and this module's live role is the
**record** of what changed and the **regression gate** that keeps it changed. Point it at any
corpus and it will say whether these twenty-two items are present in it.

**It never writes inside the vendored corpus.** ``tests/fixtures/properties/`` is a read-only
contract surface (WA-04/WA-11): a revision routes proposal → R-05 sign-off recorded as a
vault DEC/addendum → re-vendor commit citing the new vault hash → corpus lint green. So this
tool *emits a candidate corpus* somewhere else — which is how the bytes DEC-17 ratified were
produced for review — and refuses by construction to write over the vendored one. That refusal
is not softened now that the ruling has landed: the next corpus revision routes exactly the
same way.

**Why textual edits and not a YAML round-trip.** Each revision is a *(before, after)* pair of
the fixture's literal ``expected:`` block. Re-emitting a parsed document would rewrite comment
lines, folded scalars, flow mappings and key order across every file it touched, which would
make the re-vendor diff unreviewable and "byte-copy vendored" (WA-11) an empty phrase. A
before/after pair is also its own precondition: a revision that cannot find its ``before`` and
cannot find its ``after`` is *ambiguous* and stops the run rather than guessing, and one that
finds its ``after`` is already applied — which is what makes ``--check`` and ``--emit`` the
same table read two ways.

What is **out of scope** here, and why (:data:`EXCLUSIONS` carries the same list with its
citations): the eight non-wedge properties' witness and location shapes, which ``schema.yaml``
marks "provisional until their catalog sections are drafted"; P-03's three condition IDs that
§0.4 deliberately holds back (DEC-05 D6); ``mixed/10``'s run-level wrapper, which §0.3's own
scope boundary assigns to REPORT-FORMAT-SPEC; and new fixtures, which are DEC-16's
authorization and TE-14's card, not this pass's.

Nothing here imports langgraph or langchain, executes a workflow node, calls a model, or opens
a socket (WA-07). Fixtures are read through :mod:`gebra.testing.fixtures`, whose parser is
PyYAML's safe constructor set in a private subclass; ``source_snippet`` is never compiled or
executed, and no fixture text is ever passed to ``exec``, ``eval`` or ``compile``.

Usage::

    python tools/corpus_reconcile.py                     # status summary of the pass
    python tools/corpus_reconcile.py --audit             # the full audit report (markdown)
    python tools/corpus_reconcile.py --check             # the regression gate: exit 1 if reverted
    python tools/corpus_reconcile.py --diff              # unified diff of anything outstanding
    python tools/corpus_reconcile.py --emit out/corpus   # write a candidate corpus for review

``--diff`` and ``--emit`` are silent no-ops against the vendored corpus now that every revision
has landed; they stay because ``--corpus`` can point anywhere, which is what lets the test
suite reconstruct the pre-pass bytes and require this tool to reproduce the vendored ones
from them.

Exit status is 0 unless ``--check`` is given and revisions are outstanding, or the corpus is in
a state no revision recognises (which is always an error, never a silent pass).
"""

from __future__ import annotations

import argparse
import difflib
import shutil
import sys
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Final

import yaml

from gebra.ir import WorkflowIR
from gebra.testing import (
    FixtureError,
    PropertyFixture,
    fixture_from_document,
    load_corpus,
    yaml_loader,
)

#: The one corpus this tool may never write into (WA-04/WA-11). Named here rather than
#: derived at the call site so the guard is a fact of the module, not of an argument.
VENDORED_CORPUS: Final = (
    Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "properties"
)


class Drift(str, Enum):
    """The drift classes DEC-11 *Consequences* and the §P-nn.3 callouts enumerate.

    A closed vocabulary on purpose, like the corpus lint's rule codes: a drift class is what
    the audit report, the R-05 proposal and a fidelity-matrix entry all refer to.
    """

    LOCATION_DISCRIMINATOR = "location-discriminator"
    """A ``location`` block predating its §P-nn.3 discriminated subtype (§0.3 Location note)."""

    RECORD_GRADES = "record-grades"
    """``severity``/``claim_class`` absent from a failure record (§0.1/§0.3 per-record rule)."""

    REGION_NAMING = "region-naming"
    """A ``P06EffectRecord.region`` that does not match §6.4's region rule (§6.3 item 1)."""

    CYCLE_ROTATION = "cycle-rotation"
    """A cycle list in traversal order rather than §0.3 canonical rotation (§6.3 item 2)."""

    REMEDIATION_TEXT = "remediation-text"
    """A condensed ``remediation`` clause, not the Appendix B §B.3 closing paragraph (§8.3 d)."""


class State(str, Enum):
    """Where one revision stands in the corpus it is measured against."""

    OUTSTANDING = "outstanding"
    """The pre-pass bytes are present: this revision has not landed yet."""

    APPLIED = "applied"
    """The post-pass bytes are present: this revision has landed."""

    AMBIGUOUS = "ambiguous"
    """Neither, or both — the corpus is in a state this plan does not describe."""


@dataclass(frozen=True)
class DriftItem:
    """One drift the pass resolves, inside one fixture.

    Attributes:
        item_id: Stable identifier, cited by the audit report and the R-05 proposal.
        drift: Which :class:`Drift` class this is.
        spec_ref: The frozen passage that fixes the target shape.
        change: One line, ``before -> after``, for the audit table.
        rationale: Why this is the target shape, in the spec's own terms.
        needs_r05_call: Whether the item is a judgment call rather than a mechanical
            normalization, and so needs an explicit R-05 answer before it may land.
    """

    item_id: str
    drift: Drift
    spec_ref: str
    change: str
    rationale: str
    needs_r05_call: bool = False


@dataclass(frozen=True)
class Revision:
    """One fixture's complete ``expected:`` block, before and after the pass.

    The whole block is carried rather than a line-level anchor for three reasons: it is
    unambiguous (a block starts at a column-0 ``expected:`` and there is one per fixture), it
    is order-independent when several drift items land in the same file, and it is what an
    R-05 reviewer actually needs to see.

    Attributes:
        fixture: Corpus-root-relative id, e.g. ``"effect-safety/negative-02-….yaml"``.
        items: The drift items this revision resolves — one row each in the audit table.
        before: The literal pre-pass block, newline-terminated.
        after: The literal post-pass block, newline-terminated.
    """

    fixture: str
    items: tuple[DriftItem, ...]
    before: str
    after: str

    def state_in(self, text: str) -> State:
        """Where this revision stands in ``text`` — the whole fixture file."""
        has_before = self.before in text
        has_after = self.after in text
        if has_before and not has_after:
            return State.OUTSTANDING
        if has_after and not has_before:
            return State.APPLIED
        return State.AMBIGUOUS

    def apply_to(self, text: str) -> str:
        """``text`` with the pass applied, or ``text`` unchanged when it already is.

        Raises:
            ReconcileError: if the block is not found exactly once, or the file is in a state
                this revision does not describe. Never a partial or guessed edit.
        """
        state = self.state_in(text)
        if state is State.APPLIED:
            return text
        if state is State.AMBIGUOUS:
            raise ReconcileError(
                f"{self.fixture}: the `expected:` block matches neither the pre-pass nor the "
                "post-pass bytes this plan carries (or matches both). The corpus is in a "
                "state TE-03 does not describe — re-derive the plan against it rather than "
                "editing either side."
            )
        occurrences = text.count(self.before)
        if occurrences != 1:
            raise ReconcileError(
                f"{self.fixture}: the pre-pass `expected:` block occurs {occurrences} times; "
                "exactly one was expected."
            )
        return text.replace(self.before, self.after, 1)


@dataclass(frozen=True)
class Verification:
    """A claim the pass *verifies* instead of editing — the "verified or migrated" half.

    DEC-09's corpus migration and several DEC-11 pins were applied in the vault before the
    2026-07-20 vendoring (corpus README banner). Re-applying them would be an edit with no
    ruling behind it; asserting them is the honest discharge, and it fails loudly if a future
    re-vendor undoes one.

    Attributes:
        check_id: Stable identifier, cited by the audit report.
        claim: What must hold, in one line.
        spec_ref: The record that mandates it.
        predicate: Takes the loaded corpus, returns ``(holds, detail)``.
    """

    check_id: str
    claim: str
    spec_ref: str
    predicate: Callable[[Sequence[PropertyFixture]], tuple[bool, str]]


@dataclass(frozen=True)
class OpenCall:
    """A question this pass refuses to answer locally — an explicit R-05 call.

    ``decisions_to_implementer`` for TE-03 includes "which ambiguous fixtures need explicit
    R-05 calls"; this table is that answer, and every entry states the recommendation rather
    than leaving the owner to reconstruct it.
    """

    call_id: str
    fixture: str
    question: str
    spec_ref: str
    recommendation: str


@dataclass(frozen=True)
class Exclusion:
    """A shape this pass deliberately leaves alone, with the passage that scopes it out."""

    scope: str
    reason: str
    spec_ref: str


class ReconcileError(RuntimeError):
    """The corpus is in a state the plan does not describe, or a path guard refused."""


# ── The plan ─────────────────────────────────────────────────────────────────────────────
#
# One entry per fixture whose `expected:` block the pass rewrites. Twelve fixtures, twenty-two
# drift items. Every `after` block below is derived from a frozen passage, never authored:
# the P-04/P-06/P-08 discriminators and grades from the §P-nn.3 contracts and the §0.4
# registry rows, the P-06 region from §6.4's `retry_region` rule, the canonical rotations from
# §0.3 `CycleLocation` (which §6.4's `anchor_cycle` also returns), and the two remediation
# paragraphs verbatim from Appendix B §B.3 — `tests/testing/test_corpus_reconcile.py` asserts
# each of those against its source rather than trusting this file.

_P04_GRADES: Final = (
    "PROPERTY-CATALOG-SPEC §4.3 (fields), §0.4 registry row "
    "(read-key-never-written-on-path: FATAL, DEFENSIBLE-A)"
)
_P06_LOCATION: Final = "PROPERTY-CATALOG-SPEC §6.3 [!todo] item 4, §6.3 condition table"
_P08_LOCATION: Final = "PROPERTY-CATALOG-SPEC §8.3 [!todo] marker (a)"
_P08_REMEDIATION: Final = "PROPERTY-CATALOG-SPEC §8.3 [!todo] marker (d), Appendix B §B.3"


def _p04_items(serial: str) -> tuple[DriftItem, ...]:
    """The two drift items every ``dataflow-completeness`` negative carries (§4.3)."""
    return (
        DriftItem(
            item_id=f"R-P04-{serial}-kind",
            drift=Drift.LOCATION_DISCRIMINATOR,
            spec_ref="PROPERTY-CATALOG-SPEC §4.3 (DataflowLocation), §0.3 Location note",
            change="location: (flat) -> location.kind: state-key",
            rationale=(
                "DataflowLocation extends the §0.3 state-key anchor, so its discriminator is "
                "`state-key`; §4.3 names these blocks flat and sends them to this pass. The "
                "corpus already spells it that way on every reconciled P-04 record "
                "(mixed/02, mixed/04, mixed/08)."
            ),
        ),
        DriftItem(
            item_id=f"R-P04-{serial}-grades",
            drift=Drift.RECORD_GRADES,
            spec_ref=_P04_GRADES,
            change="failure: (no grades) -> severity: fatal, claim_class: defensible-a",
            rationale=(
                "§4.3: 'the P-04 negatives omit severity/claim_class'. The grades are the "
                "§0.4 registry's for this condition, read off the table rather than chosen; "
                "§0.1 requires every record to classify its own claim."
            ),
        ),
    )


def _p06_grade_items(serial: str, severity: str) -> tuple[DriftItem, ...]:
    """The two drift items every ``effect-safety`` negative carries (§6.3)."""
    return (
        DriftItem(
            item_id=f"R-P06-{serial}-kind",
            drift=Drift.LOCATION_DISCRIMINATOR,
            spec_ref=_P06_LOCATION,
            change="location: (flat) -> location.kind: node",
            rationale=(
                "§6.3 item 4: 'Fixture `location` blocks gain `kind: node` in the same pass'; "
                "P06NodeLocation extends the §0.3 node anchor."
            ),
        ),
        DriftItem(
            item_id=f"R-P06-{serial}-grades",
            drift=Drift.RECORD_GRADES,
            spec_ref=_P06_LOCATION,
            change=f"failure: (no grades) -> severity: {severity}, claim_class: defensible-a",
            rationale=(
                "The §6.3 condition table and the §0.4 registry row grade this condition "
                f"{severity.upper()}/DEFENSIBLE-A; §6.4 Phase 4 constructs the Failure with "
                "exactly those, and §0.1 requires every record to carry them."
            ),
        ),
    )


PLAN: Final[tuple[Revision, ...]] = (
    Revision(
        fixture="dataflow-completeness/negative-01-express-path-skips-writer.yaml",
        items=_p04_items("neg01"),
        before="""expected:
  result: fail
  failure:
    property_condition: "read-key-never-written-on-path"
    location:
      node: send_confirmation
      key: booking_id
      path: [START, check_availability, send_confirmation]
    writers_on_other_paths: [book_flight]
""",
        after="""expected:
  result: fail
  failure:
    property_condition: "read-key-never-written-on-path"
    location:
      kind: state-key
      node: send_confirmation
      key: booking_id
      path: [START, check_availability, send_confirmation]
    severity: fatal
    claim_class: defensible-a
    writers_on_other_paths: [book_flight]
""",
    ),
    Revision(
        fixture="dataflow-completeness/negative-02-writer-downstream-of-reader.yaml",
        items=_p04_items("neg02"),
        before="""expected:
  result: fail
  failure:
    property_condition: "read-key-never-written-on-path"
    location:
      node: notify_traveler
      key: itinerary_url
      path: [START, compile_itinerary, notify_traveler]
    downstream_writers: [publish_itinerary]
""",
        after="""expected:
  result: fail
  failure:
    property_condition: "read-key-never-written-on-path"
    location:
      kind: state-key
      node: notify_traveler
      key: itinerary_url
      path: [START, compile_itinerary, notify_traveler]
    severity: fatal
    claim_class: defensible-a
    downstream_writers: [publish_itinerary]
""",
    ),
    Revision(
        fixture="dataflow-completeness/negative-03-fan-in-missing-branch-writer.yaml",
        items=_p04_items("neg03"),
        before="""expected:
  result: fail
  failure:
    property_condition: "read-key-never-written-on-path"
    location:
      node: price_quote
      key: loyalty_tier
      path: [START, identify_traveler, create_guest_profile, price_quote]
    writers_on_other_paths: [fetch_loyalty_profile]
""",
        after="""expected:
  result: fail
  failure:
    property_condition: "read-key-never-written-on-path"
    location:
      kind: state-key
      node: price_quote
      key: loyalty_tier
      path: [START, identify_traveler, create_guest_profile, price_quote]
    severity: fatal
    claim_class: defensible-a
    writers_on_other_paths: [fetch_loyalty_profile]
""",
    ),
    Revision(
        fixture="effect-safety/negative-01-billable-in-unguarded-retry.yaml",
        items=_p06_grade_items("neg01", "error"),
        before="""expected:
  result: fail
  failure:
    property_condition: "unprotected-effect-in-retry-region"
    location:
      node: book_flight
      cycle: [book_flight, check_booking]
      effect: [irreversible, billable]
""",
        after="""expected:
  result: fail
  failure:
    property_condition: "unprotected-effect-in-retry-region"
    location:
      kind: node
      node: book_flight
      cycle: [book_flight, check_booking]
      effect: [irreversible, billable]
    severity: error
    claim_class: defensible-a
""",
    ),
    Revision(
        fixture="effect-safety/negative-02-irreversible-in-refinement-cycle.yaml",
        items=(
            *_p06_grade_items("neg02", "error"),
            DriftItem(
                item_id="R-P06-neg02-rotation",
                drift=Drift.CYCLE_ROTATION,
                spec_ref="PROPERTY-CATALOG-SPEC §6.3 [!todo] item 2, §0.3 CycleLocation",
                change=(
                    "location.cycle: [propose_change, submit_change_request, assess_response]"
                    " -> [assess_response, propose_change, submit_change_request]"
                ),
                rationale=(
                    "§6.3 item 2 names this fixture as authored in traversal order and pins "
                    "the §0.3 least-id-first canonical rotation; §6.4's `anchor_cycle` "
                    "returns `canonical_rotation(...)`, so this is the anchor P-06 will emit. "
                    "The rotation preserves the cycle: propose_change -> "
                    "submit_change_request -> assess_response -> (revise) -> propose_change."
                ),
            ),
        ),
        before="""expected:
  result: fail
  failure:
    property_condition: "unprotected-effect-in-cycle"
    location:
      node: submit_change_request
      cycle: [propose_change, submit_change_request, assess_response]
      effect: [irreversible]
""",
        after="""expected:
  result: fail
  failure:
    property_condition: "unprotected-effect-in-cycle"
    location:
      kind: node
      node: submit_change_request
      cycle: [assess_response, propose_change, submit_change_request]
      effect: [irreversible]
    severity: error
    claim_class: defensible-a
""",
    ),
    Revision(
        fixture="effect-safety/negative-03-keyless-idempotent-on-irreversible.yaml",
        items=_p06_grade_items("neg03", "fatal"),
        before="""expected:
  result: fail
  failure:
    property_condition: "irreversible-with-keyless-idempotent"
    location:
      node: charge_deposit
      effect: [irreversible, billable]
      idempotent: keyless
""",
        after="""expected:
  result: fail
  failure:
    property_condition: "irreversible-with-keyless-idempotent"
    location:
      kind: node
      node: charge_deposit
      effect: [irreversible, billable]
      idempotent: keyless
    severity: fatal
    claim_class: defensible-a
""",
    ),
    Revision(
        fixture="effect-safety/positive-01-keyed-idempotent-billable-retry.yaml",
        items=(
            DriftItem(
                item_id="R-P06-pos01-region",
                drift=Drift.REGION_NAMING,
                spec_ref="PROPERTY-CATALOG-SPEC §6.3 [!todo] item 1, §6.4 Phase 3 (DEC-13)",
                change="effects[0].region: cycle -> retry",
                rationale=(
                    "§6.3 item 1 pins it: positive-01 'records region: cycle for a node that "
                    "is structurally in a retry region under §6.4 — normalizes to region: "
                    "retry'. The topology agrees: the SCC is {book_hotel, verify_hold} and "
                    "the conditional label-edge verify_hold -(retry)-> book_hotel puts "
                    "book_hotel in T(S), so §6.4's `retry_region` arm (b) holds. §6.6 records "
                    "the same fact from the other side — positive-01 has 'the same topology "
                    "as negative-01', whose condition is unprotected-effect-in-retry-region."
                ),
            ),
        ),
        before="""expected:
  result: pass
  witness:
    kind: effect-safety
    cycles:
      - [book_hotel, verify_hold]
    effects:
      - node: book_hotel
        effect: [billable]
        region: cycle
        cycle: [book_hotel, verify_hold]
        protection: idempotency_key
        key: hotel_offer_id
""",
        after="""expected:
  result: pass
  witness:
    kind: effect-safety
    cycles:
      - [book_hotel, verify_hold]
    effects:
      - node: book_hotel
        effect: [billable]
        region: retry
        cycle: [book_hotel, verify_hold]
        protection: idempotency_key
        key: hotel_offer_id
""",
    ),
    Revision(
        fixture="effect-safety/positive-02-irreversible-outside-cycle.yaml",
        items=(
            DriftItem(
                item_id="R-P06-pos02-rotation",
                drift=Drift.CYCLE_ROTATION,
                spec_ref="PROPERTY-CATALOG-SPEC §6.3 [!todo] item 2, §0.3 CycleLocation",
                change=(
                    "witness.cycles[0]: [fetch_fare_quote, evaluate_quote] -> "
                    "[evaluate_quote, fetch_fare_quote]"
                ),
                rationale=(
                    "§6.3 item 2 names this fixture; `EffectSafetyWitness.cycles` carries "
                    "'one canonical anchor per non-trivial SCC' and §0.3 fixes canonical as "
                    "least-id-first. The rotation preserves the cycle: fetch_fare_quote -> "
                    "evaluate_quote -> (poll) -> fetch_fare_quote."
                ),
            ),
        ),
        before="""expected:
  result: pass
  witness:
    kind: effect-safety
    cycles:
      - [fetch_fare_quote, evaluate_quote]
    effects:
      - node: charge_card
        effect: [irreversible, billable]
        region: acyclic
        protection: none_required
""",
        after="""expected:
  result: pass
  witness:
    kind: effect-safety
    cycles:
      - [evaluate_quote, fetch_fare_quote]
    effects:
      - node: charge_card
        effect: [irreversible, billable]
        region: acyclic
        protection: none_required
""",
    ),
    Revision(
        fixture="effect-safety/positive-03-compensated-billable-hold-loop.yaml",
        items=(
            DriftItem(
                item_id="R-P06-pos03-rotation",
                drift=Drift.CYCLE_ROTATION,
                spec_ref="PROPERTY-CATALOG-SPEC §6.3 [!todo] item 2, §0.3 CycleLocation",
                change=(
                    "witness.cycles[0] and effects[0].cycle: "
                    "[propose_dates, place_hotel_hold, review_hold, release_hotel_hold] -> "
                    "[place_hotel_hold, review_hold, release_hotel_hold, propose_dates]"
                ),
                rationale=(
                    "§6.3 item 2 names this fixture. Both lists are the same anchor and both "
                    "rotate; §6.4's `anchor_cycle(place_hotel_hold)` returns "
                    "`canonical_rotation((n,) + best[:-1])`, which is this list exactly. The "
                    "rotation preserves the cycle: propose_dates -> place_hotel_hold -> "
                    "review_hold -> (adjust) -> release_hotel_hold -> propose_dates."
                ),
            ),
        ),
        before="""expected:
  result: pass
  witness:
    kind: effect-safety
    cycles:
      - [propose_dates, place_hotel_hold, review_hold, release_hotel_hold]
    effects:
      - node: place_hotel_hold
        effect: [billable]
        region: cycle
        cycle: [propose_dates, place_hotel_hold, review_hold, release_hotel_hold]
        protection: compensation_hook
        hook: release_hotel_hold
""",
        after="""expected:
  result: pass
  witness:
    kind: effect-safety
    cycles:
      - [place_hotel_hold, review_hold, release_hotel_hold, propose_dates]
    effects:
      - node: place_hotel_hold
        effect: [billable]
        region: cycle
        cycle: [place_hotel_hold, review_hold, release_hotel_hold, propose_dates]
        protection: compensation_hook
        hook: release_hotel_hold
""",
    ),
    Revision(
        fixture="determinism-replay/negative-01-seedless-deterministic-llm-classifier.yaml",
        items=(
            DriftItem(
                item_id="R-P08-neg01-kind",
                drift=Drift.LOCATION_DISCRIMINATOR,
                spec_ref=_P08_LOCATION,
                change="location: (flat) -> location.kind: node",
                rationale=(
                    '§8.3 (a): \'Corpus location blocks omit the kind: "node" discriminator '
                    "— the §8.4 constructors pass it explicitly; fixture blocks gain it in "
                    "the single corpus pass'. DeterminismNodeLocation extends the §0.3 node "
                    "anchor."
                ),
            ),
            DriftItem(
                item_id="R-P08-neg01-remediation",
                drift=Drift.REMEDIATION_TEXT,
                spec_ref=_P08_REMEDIATION,
                change="remediation: condensed clause -> Appendix B §B.3 T-1 closing paragraph",
                rationale=(
                    "§8.3 (d): 'Fixture remediation strings are condensed action clauses; "
                    "alignment with the Appendix B closing paragraphs lands in the same "
                    "pass'. §B.3 assigns the closing paragraph to `Failure.remediation`, and "
                    "the paragraph carries no template slots, so the target is the literal "
                    "§B.3 text — quoted here, and asserted equal to what the shipped renderer "
                    "produces. The folded scalar changes from `>` to `>-` because the "
                    "paragraph has no trailing newline."
                ),
            ),
        ),
        before="""expected:
  result: fail
  failure:
    property_condition: "deterministic-llm-seed-unpinned"
    severity: warning
    claim_class: heuristic
    location:
      node: classify_intent
      annotation: deterministic
      form: bare-boolean
      effects: [network, external]
    remediation: >
      Pin the configuration — @gebra.deterministic(seed=N) with
      temperature=0 — or drop the claim; replay divergence must be logged
      either way.
""",
        after="""expected:
  result: fail
  failure:
    property_condition: "deterministic-llm-seed-unpinned"
    severity: warning
    claim_class: heuristic
    location:
      kind: node
      node: classify_intent
      annotation: deterministic
      form: bare-boolean
      effects: [network, external]
    remediation: >-
      The claim is recorded. Pin the configuration —
      @gebra.deterministic(seed=N) with temperature=0 — or drop the claim;
      replay divergence must be logged either way.
""",
    ),
    Revision(
        fixture="determinism-replay/negative-02-seeded-llm-extractor-hot-temperature.yaml",
        items=(
            DriftItem(
                item_id="R-P08-neg02-kind",
                drift=Drift.LOCATION_DISCRIMINATOR,
                spec_ref=_P08_LOCATION,
                change="location: (flat) -> location.kind: node",
                rationale=(
                    "§8.3 (a), the same marker as negative-01: the §8.4 constructors pass the "
                    "discriminator explicitly and the fixture blocks gain it in this pass. "
                    "The evidence fields differ (seed/temperature rather than form/effects) "
                    "but DeterminismNodeLocation extends the same §0.3 node anchor."
                ),
            ),
            DriftItem(
                item_id="R-P08-neg02-remediation",
                drift=Drift.REMEDIATION_TEXT,
                spec_ref=_P08_REMEDIATION,
                change="remediation: condensed clause -> Appendix B §B.3 T-2 closing paragraph",
                rationale=(
                    "§8.3 (d), the same marker as negative-01, resolved against T-2's closing "
                    "paragraph rather than T-1's. §B.3's note that 'when temperature is "
                    "present but nonzero (fixture negative-02)' the wording changes applies to "
                    "the *first* paragraph — the diagnosis, which is D-12's surface — not to "
                    "the closing paragraph this field carries, so the target is constant per "
                    "condition here too."
                ),
            ),
        ),
        before="""expected:
  result: fail
  failure:
    property_condition: "deterministic-llm-temperature-unpinned"
    severity: warning
    claim_class: heuristic
    location:
      node: extract_preferences
      annotation: deterministic
      seed: 7
      temperature: 0.7
    remediation: >
      Pin temperature=0 alongside the seed, or drop the determinism claim;
      keep the annotation only if approximate determinism with logged
      divergence is acceptable.
""",
        after="""expected:
  result: fail
  failure:
    property_condition: "deterministic-llm-temperature-unpinned"
    severity: warning
    claim_class: heuristic
    location:
      kind: node
      node: extract_preferences
      annotation: deterministic
      seed: 7
      temperature: 0.7
    remediation: >-
      The claim is recorded. Replay divergence must be logged, never
      silently accepted. Keep the annotation if you accept approximate
      determinism; remove it if replay reproducibility should not be relied
      on.
""",
    ),
    Revision(
        fixture="mixed/05-evolution-drops-witness-and-state-field.yaml",
        items=(
            DriftItem(
                item_id="R-P04-mixed05-kind",
                drift=Drift.LOCATION_DISCRIMINATOR,
                spec_ref="PROPERTY-CATALOG-SPEC §4.3, §0.3 Location note",
                change="co_failures[2].location: (flat) -> location.kind: state-key",
                rationale=(
                    "The last P-04 record in the corpus still carrying a flat location. Its "
                    "sibling P-02 co-failure in the same block is already normalized "
                    "(kind/severity/claim_class), so leaving this one flat would make the "
                    "pass incomplete inside one fixture. Flagged for R-05 because the host "
                    "fixture's primary is P-12's, a non-wedge shape this pass otherwise "
                    "leaves alone. The `snapshot: ir_after` key is P-12's pair convention and "
                    "is kept untouched — see the open call."
                ),
                needs_r05_call=True,
            ),
            DriftItem(
                item_id="R-P04-mixed05-grades",
                drift=Drift.RECORD_GRADES,
                spec_ref=_P04_GRADES,
                change="co_failures[2]: (no grades) -> severity: fatal, claim_class: defensible-a",
                rationale=(
                    "§0.3: 'Every co-finding record carries its own severity and claim_class, "
                    "so the §0.1 classification guarantee holds for every record in the "
                    "envelope'. Grades read off the §0.4 registry row, as everywhere else."
                ),
                needs_r05_call=True,
            ),
        ),
        before="""      - property: dataflow-completeness
        property_condition: "read-key-never-written-on-path"
        location:
          node: fetch_data
          key: auth_token
          path: [START, fetch_data]
          snapshot: ir_after
""",
        after="""      - property: dataflow-completeness
        property_condition: "read-key-never-written-on-path"
        location:
          kind: state-key
          node: fetch_data
          key: auth_token
          path: [START, fetch_data]
          snapshot: ir_after
        severity: fatal
        claim_class: defensible-a
""",
    ),
)


# ── What the pass verifies instead of editing ────────────────────────────────────────────


def _irs(corpus: Sequence[PropertyFixture]) -> Iterator[WorkflowIR]:
    for fixture in corpus:
        yield from fixture.irs


def _by_id(corpus: Sequence[PropertyFixture], fixture_id: str) -> PropertyFixture:
    for fixture in corpus:
        if fixture.fixture_id == fixture_id:
            return fixture
    raise ReconcileError(f"{fixture_id}: not present in the corpus")


def _check_ir_version(corpus: Sequence[PropertyFixture]) -> tuple[bool, str]:
    versions = {ir.ir_version for ir in _irs(corpus)}
    blocks = sum(1 for _ in _irs(corpus))
    return versions == {"1.0"}, f"{blocks} IR block(s), ir_version in {sorted(versions)}"


def _check_recursion_limit(corpus: Sequence[PropertyFixture]) -> tuple[bool, str]:
    fixture = _by_id(
        corpus, "termination-witness/positive-02-justified-recursion-limit-refinement-loop.yaml"
    )
    ir = fixture.ir
    limit = ir.runtime.recursion_limit if ir is not None and ir.runtime is not None else None
    if limit is None:
        return False, "runtime.recursion_limit absent"
    ok = limit.value > 0 and bool((limit.justification or "").strip())
    return ok, f"runtime.recursion_limit.value={limit.value}, justification non-empty={ok}"


def _check_variant(corpus: Sequence[PropertyFixture]) -> tuple[bool, str]:
    fixture = _by_id(corpus, "termination-witness/positive-03-shrinking-worklist-hotel-quotes.yaml")
    ir = fixture.ir
    if ir is None:
        return False, "no single-snapshot IR"
    variants = {
        node.id: node.annotations.variant
        for node in ir.nodes
        if node.annotations is not None and node.annotations.variant is not None
    }
    ok = bool(variants) and all(
        bool(variant.key) and bool(variant.measure) for variant in variants.values()
    )
    return ok, f"annotations.variant on {sorted(variants)}, key+measure present={ok}"


def _check_compensation(corpus: Sequence[PropertyFixture]) -> tuple[bool, str]:
    fixture = _by_id(corpus, "effect-safety/positive-03-compensated-billable-hold-loop.yaml")
    ir = fixture.ir
    if ir is None:
        return False, "no single-snapshot IR"
    hooks = [
        node.annotations.compensation.hook
        for node in ir.nodes
        if node.annotations is not None and node.annotations.compensation is not None
    ]
    legacy = [
        tag
        for ir_block in _irs(corpus)
        for node in ir_block.nodes
        if node.annotations is not None
        for tag in (node.annotations.effect or ())
        if tag.startswith("compensated_by")
    ]
    return bool(hooks) and not legacy, (
        f"annotations.compensation.hook={hooks}, legacy compensated_by tags in corpus={legacy}"
    )


def _check_mixed04_dec12(corpus: Sequence[PropertyFixture]) -> tuple[bool, str]:
    fixture = _by_id(corpus, "mixed/04-dangling-path-map-target-orphans-downstream-reader.yaml")
    failure = fixture.expected_failure or {}
    conditions = [entry.get("property_condition") for entry in (failure.get("co_failures") or ())]
    ok = "edge-target-undefined" in conditions
    return ok, f"co_failure conditions={conditions}"


def _check_mixed10_p01_witness(corpus: Sequence[PropertyFixture]) -> tuple[bool, str]:
    fixture = _by_id(corpus, "mixed/10-all-properties-pass-healthy-research-pipeline.yaml")
    witness = fixture.expected_witness or {}
    block = (witness.get("properties") or {}).get("graph-well-formed") or {}
    keys = sorted(block)
    expected = sorted(
        (
            "kind",
            "reachable_from_start",
            "terminal_nodes",
            "orphan_nodes",
            "unresolved_targets",
        )
    )
    return keys == expected, f"P-01 witness keys={keys}"


def _check_mixed10_p06_records(corpus: Sequence[PropertyFixture]) -> tuple[bool, str]:
    fixture = _by_id(corpus, "mixed/10-all-properties-pass-healthy-research-pipeline.yaml")
    witness = fixture.expected_witness or {}
    block = (witness.get("properties") or {}).get("effect-safety") or {}
    records = block.get("effects") or []
    regions = [record.get("region") for record in records]
    protections = [record.get("protection") for record in records]
    ok = bool(records) and "protected_effects" not in block and all(regions) and all(protections)
    return ok, f"P06EffectRecord regions={regions}, protections={protections}"


#: The conditions §0.4 holds for P-02, used to find P-02-owned records inside `mixed/`.
_P02_CONDITIONS: Final = frozenset(
    {"cycle-without-termination-witness", "counter-guard-without-exit-edge"}
)

#: The conditions §0.4 holds for P-06, used the same way.
_P06_CONDITIONS: Final = frozenset(
    {
        "unprotected-effect-in-cycle",
        "unprotected-effect-in-retry-region",
        "irreversible-with-keyless-idempotent",
    }
)


def _p02_regions(fixture: PropertyFixture) -> Iterator[tuple[str, Any]]:
    """Every part of ``fixture``'s ``expected:`` block that P-02 owns.

    Scoping matters here: ``evolution-safety/negative-02`` carries a ``witness_before`` block
    spelled in exactly the retired P-02 vocabulary (``witness_type: exit_condition``), but
    that block is **P-12's** diff evidence, and P-12's shapes stay provisional until its
    catalog section is drafted (schema.yaml; :data:`EXCLUSIONS`). Reading it as P-02 drift
    would manufacture work this pass has no authority to do.
    """
    if fixture.directory == "termination-witness":
        yield "expected", dict(fixture.expected)
        return
    witness = fixture.expected_witness or {}
    block = (witness.get("properties") or {}).get("termination-witness")
    if block is not None:
        yield "expected.witness.properties.termination-witness", block
    failure = fixture.expected_failure
    if failure is None:
        return
    if failure.get("property_condition") in _P02_CONDITIONS:
        yield "expected.failure", dict(failure)
    for index, entry in enumerate(failure.get("co_failures") or ()):
        if entry.get("property_condition") in _P02_CONDITIONS:
            yield f"expected.failure.co_failures[{index}]", entry


def _check_p02_shapes(corpus: Sequence[PropertyFixture]) -> tuple[bool, str]:
    retired = ("witness_type", "loop_bound", "exit_condition")
    hits = [
        f"{fixture.fixture_id}:{path}"
        for fixture in corpus
        for path, region in _p02_regions(fixture)
        if any(token in yaml.safe_dump(region) for token in retired)
    ]
    return not hits, f"retired P-02 provisional keys in {hits or 'no P-02-owned record'}"


def _check_gwf_neg03_cascade(corpus: Sequence[PropertyFixture]) -> tuple[bool, str]:
    fixture = _by_id(corpus, "graph-well-formed/negative-03-path-map-typo-dangling-target.yaml")
    failure = fixture.expected_failure or {}
    location = failure.get("location") or {}
    cascade = [entry.get("property_condition") for entry in (failure.get("co_failures") or ())]
    ok = "undefined_target" in location and "node-unreachable-from-start" in cascade
    return ok, f"location keys={sorted(location)}, co_failure conditions={cascade}"


def _check_p04_diagnostics(corpus: Sequence[PropertyFixture]) -> tuple[bool, str]:
    # Four carriers since DEC-24 (2026-08-08): the three DEC-11 negatives plus mixed/08,
    # whose missing `writers_on_other_paths` was the FM-009 deviation until the M13 owner
    # action added it (vault `Gebra-Tech/initial-documents@7be81a9`).
    present = [
        fixture.fixture_id
        for fixture in corpus
        if (fixture.expected_failure or {}).keys()
        & {"writers_on_other_paths", "downstream_writers"}
    ]
    return len(present) == 4, f"P04Failure diagnostics kept on {present}"


def _p06_regions(fixture: PropertyFixture) -> Iterator[tuple[str, Any]]:
    """Every part of ``fixture``'s ``expected:`` block that P-06 owns.

    Same scoping discipline as :func:`_p02_regions`, for the same reason: `retry-coherence`'s
    own ``cycle:`` lists are P-07's shape and stay provisional until §P-07 is drafted, so they
    are not this pass's to rotate.
    """
    if fixture.directory == "effect-safety":
        yield "expected", dict(fixture.expected)
        return
    witness = fixture.expected_witness or {}
    block = (witness.get("properties") or {}).get("effect-safety")
    if block is not None:
        yield "expected.witness.properties.effect-safety", block
    failure = fixture.expected_failure
    if failure is None:
        return
    if failure.get("property_condition") in _P06_CONDITIONS:
        yield "expected.failure", dict(failure)
    for index, entry in enumerate(failure.get("co_failures") or ()):
        if entry.get("property_condition") in _P06_CONDITIONS:
            yield f"expected.failure.co_failures[{index}]", entry


def _check_p06_rotation(corpus: Sequence[PropertyFixture]) -> tuple[bool, str]:
    """Every non-canonical P-06-owned cycle list is one this pass already rotates.

    The companion to :func:`_check_p02_rotation`, and what keeps the rotation half of the plan
    from being *list*-derived: §6.3 item 2 names three fixtures, and this walks every
    P-06-owned cycle list in the corpus to confirm that those three are the only ones. A
    fourth appearing in a later re-vendor fails here rather than passing unseen.
    """
    planned = {
        revision.fixture
        for revision in PLAN
        for item in revision.items
        if item.drift is Drift.CYCLE_ROTATION
    }
    unplanned: list[str] = []
    checked = 0
    for fixture in corpus:
        for region_path, region in _p06_regions(fixture):
            for path, cycle in _cycle_lists(region, region_path):
                checked += 1
                if canonical_rotation(cycle) != cycle and fixture.fixture_id not in planned:
                    unplanned.append(f"{fixture.fixture_id}:{path}")
    return not unplanned, (
        f"{checked} P-06-owned cycle list(s) across the corpus; "
        f"non-canonical and unplanned: {unplanned or 'none'} "
        f"({len(planned)} fixture(s) rotated by the plan)"
    )


def _check_p08_divergence_echo(corpus: Sequence[PropertyFixture]) -> tuple[bool, str]:
    """VAL-D3 / DEC-14 kept ``divergence_handling`` as an echo, so no P-08 witness is edited."""
    seen: list[str] = []
    for fixture in corpus:
        witness = fixture.expected_witness or {}
        blocks = [witness] + list((witness.get("properties") or {}).values())
        for block in blocks:
            if not isinstance(block, Mapping) or block.get("kind") != "determinism":
                continue
            for claim in block.get("claims") or ():
                echo = claim.get("divergence_handling")
                if claim.get("llm_backed") and echo != "logged":
                    return False, f"{fixture.fixture_id}: LLM-backed claim without the echo"
                if not claim.get("llm_backed") and echo is not None:
                    return False, f"{fixture.fixture_id}: non-LLM claim carries the echo"
                if echo == "logged":
                    seen.append(fixture.fixture_id)
    return bool(seen), f"divergence_handling: logged on {seen}, absent from every non-LLM claim"


def _check_no_dangling_hook(corpus: Sequence[PropertyFixture]) -> tuple[bool, str]:
    """VAL-D2 / DEC-13's dangling-hook case is a *gap* fixture (TE-14), not a corpus drift."""
    hooks: list[str] = []
    for fixture in corpus:
        for ir in fixture.irs:
            ids = {node.id for node in ir.nodes}
            for node in ir.nodes:
                compensation = node.annotations.compensation if node.annotations else None
                if compensation is None:
                    continue
                hooks.append(compensation.hook)
                if compensation.hook not in ids:
                    return False, f"{fixture.fixture_id}: hook {compensation.hook!r} names no node"
    return bool(hooks), f"compensation hooks {hooks}, every one resolving to a node in its own IR"


def _check_p02_rotation(corpus: Sequence[PropertyFixture]) -> tuple[bool, str]:
    offenders: list[str] = []
    checked = 0
    for fixture in corpus:
        for region_path, region in _p02_regions(fixture):
            for path, cycle in _cycle_lists(region, region_path):
                checked += 1
                if canonical_rotation(cycle) != cycle:
                    offenders.append(f"{fixture.fixture_id}:{path}")
    return not offenders, (
        f"{checked} P-02-owned cycle list(s); non-canonical: {offenders or 'none'}"
    )


VERIFICATIONS: Final[tuple[Verification, ...]] = (
    Verification(
        "V-01",
        "Every IR block is at ir_version 1.0 (the DEC-09 0.1 -> 1.0 migration is complete).",
        "DEC-09 Consequences ('60-fixture migration'); IR-SPEC §2",
        _check_ir_version,
    ),
    Verification(
        "V-02",
        "The P-02 form-(b) witness rides runtime.recursion_limit {value, justification}.",
        "DEC-09 new-in-1.0 slot 5; PROPERTY-CATALOG-SPEC §2.3, §2.6",
        _check_recursion_limit,
    ),
    Verification(
        "V-03",
        "The P-02 form-(c) witness rides nodes[].annotations.variant {key, measure}.",
        "DEC-09 new-in-1.0 slot 3; PROPERTY-CATALOG-SPEC §2.3, §2.6",
        _check_variant,
    ),
    Verification(
        "V-04",
        "Compensation rides annotations.compensation.hook; no compensated_by effect tag remains.",
        "DEC-09 new-in-1.0 slot 4 + Corpus migration; PROPERTY-CATALOG-SPEC §6.3 item 3",
        _check_compensation,
    ),
    Verification(
        "V-05",
        "mixed/04 carries the DEC-12 edge-target-undefined co-failure (the landed re-vendor).",
        "DEC-12; PD-007 item 5; MANUAL-STEPS M7 ('TE-03 verifies the landed state')",
        _check_mixed04_dec12,
    ),
    Verification(
        "V-06",
        "mixed/10's P-01 witness is the 5-key form, not the 4-key drift.",
        "DEC-11 pin 1; PROPERTY-CATALOG-SPEC §1.3 (Shape normalization), §1.7 open item 2",
        _check_mixed10_p01_witness,
    ),
    Verification(
        "V-07",
        "mixed/10's P-06 block is P06EffectRecord-shaped, not the protected_effects aggregate.",
        "PROPERTY-CATALOG-SPEC §6.3 [!todo] item 4",
        _check_mixed10_p06_records,
    ),
    Verification(
        "V-08",
        "No fixture still carries the retired P-02 provisional keys (witness_type and friends).",
        "PROPERTY-CATALOG-SPEC §2.3 (Corpus reconciliation)",
        _check_p02_shapes,
    ),
    Verification(
        "V-09",
        "graph-well-formed/negative-03 carries undefined_target and the condition-(i) cascade.",
        "PROPERTY-CATALOG-SPEC §1.3 (P01EdgeLocation), §1.7 open item 3",
        _check_gwf_neg03_cascade,
    ),
    Verification(
        "V-10",
        "The DEC-11-kept P-04 diagnostics survive on their four carriers (DEC-24 added mixed/08).",
        "DEC-11 pin 3; DEC-24; PROPERTY-CATALOG-SPEC §4.3 (Optional diagnostic fields)",
        _check_p04_diagnostics,
    ),
    Verification(
        "V-11",
        "Every P-02 cycle list is already in §0.3 canonical rotation.",
        "PROPERTY-CATALOG-SPEC §0.3 CycleLocation; §2.3 fail shapes",
        _check_p02_rotation,
    ),
    Verification(
        "V-12",
        "P-08 witnesses echo divergence_handling on LLM-backed claims only — VAL-D3 kept it.",
        "PD-010 / DEC-14; PROPERTY-CATALOG-SPEC §8.3 marker (b), §8.4",
        _check_p08_divergence_echo,
    ),
    Verification(
        "V-13",
        "Every compensation hook in the corpus names a node of its own IR (no dangling hook).",
        "PD-009 / DEC-13 Q3; DEC-05 D7 side condition; PROPERTY-CATALOG-SPEC §6.3",
        _check_no_dangling_hook,
    ),
    Verification(
        "V-14",
        "The three fixtures §6.3 item 2 names are the only non-canonical P-06 cycle lists.",
        "PROPERTY-CATALOG-SPEC §6.3 [!todo] item 2; §0.3 CycleLocation",
        _check_p06_rotation,
    ),
)


OPEN_CALLS: Final[tuple[OpenCall, ...]] = (
    OpenCall(
        call_id="Q-01",
        fixture="mixed/10-all-properties-pass-healthy-research-pipeline.yaml",
        question=(
            "Its dataflow-completeness sub-block is the pre-contract aggregate "
            "`{unwritten_reads: []}`, not a §4.3 `DataflowWitness{kind: dataflow, coverage}`. "
            "Should this pass normalize it?"
        ),
        spec_ref="PROPERTY-CATALOG-SPEC §4.3; §0.3 scope boundary (run-level wrapper)",
        recommendation=(
            "No — defer. Unlike the P-01/P-02/P-06/P-08 sub-blocks, which were normalized "
            "shape-for-shape, a DataflowWitness needs a derived `coverage` list (one entry "
            "per reachable reader x read key). Deriving it here would mean implementing P-04 "
            "inside a fixture tool, which is improvised semantics (WA-03) rather than a "
            "mechanical rewrite. VAL-09 is the card that computes it; the entry belongs in "
            "TE-02's fidelity matrix until then. mixed/10's `expected:` is a run-level "
            "wrapper §0.3 does not model either way, so nothing downstream is blocked."
        ),
    ),
    OpenCall(
        call_id="Q-02",
        fixture="mixed/03-parallel-reducerless-key-with-unpinned-llm-writers.yaml",
        question=(
            "Its two P-08 advisories carry a bare NodeLocation; §8.3's "
            "`DeterminismNodeLocation` requires `annotation: deterministic`. Add it?"
        ),
        spec_ref="PROPERTY-CATALOG-SPEC §0.3 (Advisory.location), §8.3, §8.6",
        recommendation=(
            "No change. §0.3 types `Advisory.location` as the base `Location` union, and a "
            "bare NodeLocation is a member of it; the block these advisories ride is P-09's "
            "report, whose section is not drafted, so the whole fixture stays non-composing "
            "regardless. Recorded so the §P-09 merge meets the question rather than "
            "discovering it."
        ),
    ),
    OpenCall(
        call_id="Q-03",
        fixture="mixed/05-evolution-drops-witness-and-state-field.yaml",
        question=(
            "Its wedge co-failures carry `snapshot: ir_after`, which no §0.3 location models. "
            "Keep it through this pass?"
        ),
        spec_ref="PROPERTY-CATALOG-SPEC §0.3 (Location union); §4.6 (P-12 pair form)",
        recommendation=(
            "Keep. It is P-12's pair-scoping convention — §4.6 describes this very record as "
            "'P-04 co-failure scoped snapshot: ir_after' — and P-12 is not drafted, so "
            "removing it would delete evidence on a non-wedge authority's shape. It is why "
            "the two revisions in this fixture (R-P04-mixed05-*) are flagged for an explicit "
            "R-05 answer rather than applied as mechanical."
        ),
    ),
    OpenCall(
        call_id="Q-04",
        fixture="tests/fixtures/properties/README.md",
        question=(
            "The corpus README's banner already states the wedge-five shapes are 'PINNED and "
            "normalized'. Should the re-vendor add a line recording this pass and its DEC?"
        ),
        spec_ref="DEC-11 Consequences (DEC-03 addendum); PROVENANCE.md sync rule 2",
        recommendation=(
            "Owner's call, vault-side. The banner is accurate about the shapes pinned at "
            "walkthrough #2 and was written before the §P-nn.3 contracts existed; a one-line "
            "addition naming the ratifying DEC would make the corpus self-describing. This "
            "tool proposes no README bytes — a vendored prose edit is R-05's to author."
        ),
    ),
)


EXCLUSIONS: Final[tuple[Exclusion, ...]] = (
    Exclusion(
        scope=(
            "The eight non-wedge properties' witness and location shapes — signature-soundness "
            "(6), retry-coherence (4), parallel-safety (4), evolution-safety (6), and the "
            "non-wedge records inside mixed/01, /03, /05, /06, /07, /09, /10."
        ),
        reason=(
            "Their shapes are 'provisional until their catalog sections are drafted'; "
            "normalizing them would mean inventing the contract this pass is supposed to "
            "normalize *to*."
        ),
        spec_ref="schema.yaml v2.2 (expected.witness); DEC-11 Consequences (wedge-five scope)",
    ),
    Exclusion(
        scope="P-03's read-key-not-in-state-schema / write-key-not-in-state-schema / "
        "args-schema-type-mismatch, and the four fixtures carrying them.",
        reason=(
            "§0.4 deliberately holds these strings back until §P-03 merges (DEC-05 D6), so no "
            "block naming one can compose whatever its location shape is."
        ),
        spec_ref="PROPERTY-CATALOG-SPEC §0.4 (deliberately unregistered); DEC-05 D6",
    ),
    Exclusion(
        scope="mixed/10's run-level `kind: multi-property` wrapper.",
        reason=(
            "§0.3 specifies the per-property envelope only; the run-level wrapper is "
            "REPORT-FORMAT-SPEC's to own. Not a defect and not this pass's to change."
        ),
        spec_ref="PROPERTY-CATALOG-SPEC §0.3 (Scope boundary)",
    ),
    Exclusion(
        scope="New fixtures — the P-01 orphan negative, the P-04 cycle-entry pair, the P-02 "
        "gap cases, the P-06 retry_policy-only and dangling-hook pair, the P-08 top-up.",
        reason=(
            "Authorized by DEC-16 and authored by TE-14. PD-013's ratification records the "
            "split explicitly: 'The P-01 orphan fixture is delivered via TE-14 under this "
            "authorization, not TE-03 — recorded to prevent double-authoring.'"
        ),
        spec_ref="DEC-16; PD-013 (ratified 2026-07-31) Verification item 5",
    ),
    Exclusion(
        scope="Fixture `notes:`, `description:` and `source_snippet:` prose.",
        reason=(
            "This pass changes contract shapes, not narration. A prose edit inside a vendored "
            "file has no ruling behind it and would widen the re-vendor diff for no gain."
        ),
        spec_ref="WA-11 (byte-copy vendored); PROVENANCE.md sync rule 1",
    ),
)


# ── Canonical rotation (§0.3) ────────────────────────────────────────────────────────────


def canonical_rotation(cycle: Sequence[str]) -> list[str]:
    """``cycle`` rotated so its least node id comes first — §0.3's canonical form.

    "Least" is the ledger §6 comparator (UTF-16 code units, RFC 8785 §3.2.3), which is what
    the canonical serialization orders by; it differs from Python's default code-point order
    only for ids mixing non-BMP characters with U+E000..U+FFFF. Rotation, never sorting: the
    list is a cyclic sequence and its order is the cycle.
    """
    if not cycle:
        return []
    least = min(range(len(cycle)), key=lambda index: cycle[index].encode("utf-16-be"))
    return [*cycle[least:], *cycle[:least]]


def _cycle_lists(node: Any, path: str) -> Iterator[tuple[str, list[str]]]:
    """Every cycle-shaped list of node ids under ``node``, with its dotted path."""
    cycle_keys = {"cycle", "cycles", "representative_cycle"}
    if isinstance(node, Mapping):
        for key, value in node.items():
            yield from _cycle_lists(value, f"{path}.{key}")
    elif isinstance(node, list):
        leaf = path.rsplit(".", 1)[-1].split("[")[0]
        if node and all(isinstance(item, str) for item in node) and leaf in cycle_keys:
            yield path, list(node)
        else:
            for index, value in enumerate(node):
                yield from _cycle_lists(value, f"{path}[{index}]")


# ── Audit ────────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class RevisionStatus:
    """One revision measured against a corpus."""

    revision: Revision
    state: State


@dataclass(frozen=True)
class VerificationStatus:
    """One verification measured against a corpus."""

    verification: Verification
    holds: bool
    detail: str


@dataclass(frozen=True)
class AuditReport:
    """Everything the pass knows about one corpus root."""

    corpus_root: Path
    revisions: tuple[RevisionStatus, ...]
    verifications: tuple[VerificationStatus, ...]
    composing_before: int
    composing_after: int
    fixtures: int

    @property
    def outstanding(self) -> tuple[RevisionStatus, ...]:
        return tuple(status for status in self.revisions if status.state is State.OUTSTANDING)

    @property
    def landed(self) -> tuple[RevisionStatus, ...]:
        return tuple(status for status in self.revisions if status.state is State.APPLIED)

    @property
    def ambiguous(self) -> tuple[RevisionStatus, ...]:
        return tuple(status for status in self.revisions if status.state is State.AMBIGUOUS)

    @property
    def failed_verifications(self) -> tuple[VerificationStatus, ...]:
        return tuple(status for status in self.verifications if not status.holds)

    @property
    def complete(self) -> bool:
        """Whether the pass has fully landed in this corpus."""
        return not self.outstanding and not self.ambiguous and not self.failed_verifications


def _fixture_path(corpus_root: Path, fixture_id: str) -> Path:
    return corpus_root / fixture_id


def _composes(text: str, path: Path) -> bool:
    """Whether the fixture written as ``text`` composes into a §0.3 ``PropertyReport``.

    ``yaml_loader()`` is the loader's own private ``SafeLoader`` subclass — the same parser
    the corpus lint reads its schema through, so a tag another library registers on the shared
    ``yaml.SafeLoader`` cannot change what a candidate fixture means.
    """
    try:
        document = yaml.load(text, Loader=yaml_loader())
        fixture_from_document(document, path).expected_report()
    except (FixtureError, yaml.YAMLError, AttributeError, TypeError):
        return False
    return True


def audit(corpus_root: Path) -> AuditReport:
    """Measure the reconciliation pass against the corpus rooted at ``corpus_root``."""
    corpus = load_corpus(corpus_root)
    revisions: list[RevisionStatus] = []
    for revision in PLAN:
        path = _fixture_path(corpus_root, revision.fixture)
        if not path.is_file():
            raise ReconcileError(f"{revision.fixture}: no such fixture under {corpus_root}")
        revisions.append(RevisionStatus(revision, revision.state_in(path.read_text())))

    verifications: list[VerificationStatus] = []
    for verification in VERIFICATIONS:
        holds, detail = verification.predicate(corpus)
        verifications.append(VerificationStatus(verification, holds, detail))

    before = sum(1 for fixture in corpus if _report_composes(fixture))
    after = before
    for status in revisions:
        path = _fixture_path(corpus_root, status.revision.fixture)
        text = path.read_text()
        if status.state is not State.OUTSTANDING:
            continue
        was = _composes(text, path)
        now = _composes(status.revision.apply_to(text), path)
        after += int(now) - int(was)

    return AuditReport(
        corpus_root=corpus_root,
        revisions=tuple(revisions),
        verifications=tuple(verifications),
        composing_before=before,
        composing_after=after,
        fixtures=len(corpus),
    )


def _report_composes(fixture: PropertyFixture) -> bool:
    try:
        fixture.expected_report()
    except FixtureError:
        return False
    return True


# ── Emitting the candidate corpus ────────────────────────────────────────────────────────


def _refuse_vendored(destination: Path, source: Path) -> None:
    """Refuse any destination that would write inside a vendored corpus (WA-04/WA-11).

    Two comparisons, because path equality is not one question. ``resolve()`` settles symlinks
    and ``..`` segments, which covers the non-existent destinations (``…/properties/new``);
    ``samefile`` settles the rest, and is what makes the guard hold on a case-insensitive
    filesystem, where ``tests/fixtures/PROPERTIES`` resolves to a *different string* for the
    same directory. Ancestors are refused too: emitting into a parent of the corpus would copy
    sixty fixtures alongside the vendored ones.
    """
    resolved = destination.resolve()
    guarded = {source.resolve(), VENDORED_CORPUS.resolve()}
    for root in guarded:
        collides = resolved == root or root in resolved.parents or resolved in root.parents
        for candidate in (resolved, *resolved.parents):
            if collides:
                break
            if candidate.exists() and root.exists() and candidate.samefile(root):
                collides = True
        if collides:
            raise ReconcileError(
                f"refusing to emit into {destination}: {root} is a read-only vendored contract "
                "surface (WA-04/WA-11). A revision routes proposal -> R-05 sign-off recorded "
                "as a vault DEC/addendum -> re-vendor commit citing the new vault hash. Emit "
                "the candidate somewhere else and attach it to the proposal."
            )


def emit(corpus_root: Path, destination: Path) -> tuple[int, int]:
    """Write the reconciled candidate corpus to ``destination``.

    Returns:
        ``(files copied, revisions applied)``.

    Raises:
        ReconcileError: if the destination would touch a vendored corpus, or if any revision
            cannot find its own before/after bytes.
    """
    _refuse_vendored(destination, corpus_root)
    if destination.exists() and any(destination.iterdir()):
        raise ReconcileError(f"{destination} is not empty; emit into a fresh directory")
    shutil.copytree(corpus_root, destination, dirs_exist_ok=True)
    copied = sum(1 for path in destination.rglob("*") if path.is_file())

    applied = 0
    for revision in PLAN:
        path = _fixture_path(destination, revision.fixture)
        text = path.read_text()
        reconciled = revision.apply_to(text)
        if reconciled != text:
            path.write_text(reconciled)
            applied += 1
    return copied, applied


def diff(corpus_root: Path) -> str:
    """A unified diff of every outstanding revision, for review."""
    chunks: list[str] = []
    for revision in PLAN:
        path = _fixture_path(corpus_root, revision.fixture)
        text = path.read_text()
        if revision.state_in(text) is not State.OUTSTANDING:
            continue
        chunks.extend(
            difflib.unified_diff(
                text.splitlines(keepends=True),
                revision.apply_to(text).splitlines(keepends=True),
                fromfile=f"a/{revision.fixture}",
                tofile=f"b/{revision.fixture}",
                n=3,
            )
        )
    return "".join(chunks)


# ── Reporting ────────────────────────────────────────────────────────────────────────────


def format_summary(report: AuditReport) -> str:
    """The one-screen status of the pass against ``report.corpus_root``."""
    verified = len(report.verifications) - len(report.failed_verifications)
    lines = [
        (
            f"corpus reconciliation: {'COMPLETE' if report.complete else 'OUTSTANDING'} — "
            f"{len(report.landed)}/{len(report.revisions)} fixture revision(s) landed, "
            f"{verified}/{len(report.verifications)} verification(s) hold"
        ),
        f"corpus: {report.corpus_root} ({report.fixtures} fixtures)",
        (
            f"envelope: {report.composing_before}/{report.fixtures} `expected:` block(s) "
            f"compose today; {report.composing_after}/{report.fixtures} after the pass"
        ),
    ]
    for status in report.ambiguous:
        lines.append(f"  !! {status.revision.fixture}: {State.AMBIGUOUS.value}")
    for status in report.outstanding:
        items = ", ".join(item.item_id for item in status.revision.items)
        lines.append(f"  -- {status.revision.fixture}: {items}")
    for failed in report.failed_verifications:
        lines.append(
            f"  !! {failed.verification.check_id} does not hold: {failed.verification.claim} "
            f"({failed.detail})"
        )
    if report.outstanding:
        lines.extend(("", _ROUTING))
    return "\n".join(lines)


def format_audit(report: AuditReport) -> str:
    """The full audit report — the artifact the R-05 proposal carries."""
    lines: list[str] = [
        "# TE-03 corpus reconciliation — audit report",
        "",
        (
            "Generated by `python tools/corpus_reconcile.py --audit`. The plan is the frozen "
            "table in that module; every row cites the passage that fixes its target shape."
        ),
        "",
        format_summary(report),
        "",
        "## 1. Fixture revisions",
        "",
        "| Item | Fixture | Drift | Change | State | R-05 call | Spec |",
        "|---|---|---|---|---|---|---|",
    ]
    for status in report.revisions:
        for item in status.revision.items:
            lines.append(
                f"| {item.item_id} | `{status.revision.fixture}` | {item.drift.value} | "
                f"{item.change} | {status.state.value} | "
                f"{'yes' if item.needs_r05_call else 'no'} | {item.spec_ref} |"
            )
    lines.extend(("", "### Rationale, per item", ""))
    for status in report.revisions:
        for item in status.revision.items:
            lines.append(f"- **{item.item_id}** — {item.rationale}")

    lines.extend(("", "## 2. The patch", ""))
    for status in report.revisions:
        lines.extend(
            (
                f"### `{status.revision.fixture}` ({status.state.value})",
                "",
                "```diff",
                _block_diff(status.revision),
                "```",
                "",
            )
        )

    lines.extend(
        (
            "## 3. Verified, not edited",
            "",
            "| Check | Claim | Holds | Observed | Record |",
            "|---|---|---|---|---|",
        )
    )
    for verification_status in report.verifications:
        lines.append(
            f"| {verification_status.verification.check_id} | "
            f"{verification_status.verification.claim} | "
            f"{'yes' if verification_status.holds else 'NO'} | {verification_status.detail} | "
            f"{verification_status.verification.spec_ref} |"
        )

    lines.extend(("", "## 4. Explicit R-05 calls", ""))
    for call in OPEN_CALLS:
        lines.extend(
            (
                f"### {call.call_id} — `{call.fixture}`",
                "",
                f"**Question.** {call.question}",
                "",
                f"**Authority.** {call.spec_ref}",
                "",
                f"**Recommendation.** {call.recommendation}",
                "",
            )
        )

    lines.extend(("## 5. Deliberately out of scope", ""))
    for exclusion in EXCLUSIONS:
        lines.extend(
            (
                f"- **{exclusion.scope}**",
                f"  - *Why:* {exclusion.reason}",
                f"  - *Authority:* {exclusion.spec_ref}",
            )
        )
    lines.extend(("", _ROUTING, ""))
    return "\n".join(lines)


def _block_diff(revision: Revision) -> str:
    return "".join(
        difflib.unified_diff(
            revision.before.splitlines(keepends=True),
            revision.after.splitlines(keepends=True),
            fromfile=f"a/{revision.fixture}",
            tofile=f"b/{revision.fixture}",
            n=2,
        )
    ).rstrip("\n")


_ROUTING: Final = (
    "Routing (WA-04/WA-11): the fixture corpus is a read-only vendored contract surface. This "
    "plan is a proposal — it lands as R-05 sign-off recorded vault-first as a DEC/addendum, "
    "then the new bytes are re-vendored in one commit citing the new vault hash, then this "
    "tool's --check turns green. Never a local edit."
)


# ── CLI ──────────────────────────────────────────────────────────────────────────────────


def build_parser(default_corpus: Path) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="corpus_reconcile.py",
        description=(
            "The DEC-09/DEC-11-mandated corpus reconciliation pass: audit it, emit the "
            "candidate corpus for R-05 review, or check that it has landed."
        ),
    )
    parser.add_argument(
        "--corpus",
        type=Path,
        default=default_corpus,
        help=f"corpus root to measure the pass against (default: {default_corpus})",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--audit", action="store_true", help="print the full audit report (markdown)")
    mode.add_argument("--diff", action="store_true", help="print a unified diff of the pass")
    mode.add_argument(
        "--emit",
        type=Path,
        default=None,
        metavar="DIR",
        help="write the reconciled candidate corpus to DIR (never inside a vendored corpus)",
    )
    mode.add_argument(
        "--check",
        action="store_true",
        help="exit 1 while any revision is outstanding — the post-re-vendor gate",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser(VENDORED_CORPUS).parse_args(argv)
    try:
        if args.emit is not None:
            copied, applied = emit(args.corpus, args.emit)
            print(
                f"corpus reconciliation: emitted {copied} file(s) to {args.emit}, "
                f"{applied} revision(s) applied"
            )
            return 0
        if args.diff:
            sys.stdout.write(diff(args.corpus))
            return 0
        report = audit(args.corpus)
    except (ReconcileError, FixtureError) as exc:
        print(f"corpus reconciliation: {exc}", file=sys.stderr)
        return 1

    rendered = format_audit(report) if args.audit else format_summary(report)
    if args.check and not report.complete:
        print(rendered, file=sys.stderr)
        return 1
    print(rendered)
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
