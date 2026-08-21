"""What an export and a freshness check answer with, and how they refuse.

Three value types and one error, all frozen dataclasses of plain data — the same posture
:mod:`gebra.lineage` and :mod:`gebra.snapshot` take, and for the same reason: two equal
answers are one value with one rendering, and nothing here reads a clock or a directory.

The audit export deliberately has **no model of its own for the document**. That document is
``REPORT-FORMAT-SPEC`` §1's :class:`~gebra.verify.RunReport` in the §6 snapshot profile —
ratified at CLI-01, superseding SD-07's provisional schema — so :class:`ExportOutcome` carries
the report rather than a shape wrapping it, and there is no second version line anywhere in
this package.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

from gebra.versioning.models import Component

if TYPE_CHECKING:
    from gebra.diff.workflow import WorkflowDiff
    from gebra.verify import RunReport

__all__ = [
    "AuditError",
    "AuditErrorReason",
    "ExportOutcome",
    "Freshness",
    "FreshnessOutcome",
]


class AuditErrorReason(str, Enum):
    """Why an export was refused — a stable code to branch on, never message text.

    Like :class:`~gebra.store.store.StoreErrorReason` and
    :class:`~gebra.lineage.engine.LineageErrorReason` these are artifact-integrity codes, not
    condition IDs: the PROPERTY-CATALOG-SPEC §0.4 registry neither contains nor needs them,
    and no verification envelope reports one. An export that cannot be written is a fault in
    the store or in this build, never a finding about the workflow.
    """

    REPORT_MISSING = "report-missing"
    """No export has been written for that version yet."""

    REPORT_UNREADABLE = "report-unreadable"
    """The file is there and is not a run report — unparseable, or carrying an unknown member."""

    SNAPSHOT_MISSING = "snapshot-missing"
    """An export names a version the store's index does not hold — nothing to validate against."""

    SUBJECT_MISSING = "subject-missing"
    """The report carries no ``subject``, so it cannot name the version it is about (§6.2)."""

    NO_VERDICT = "no-verdict"
    """The run reached no verdict (exit 2), so there is nothing about the version to audit.

    §2.4: "Exit ``2`` means no verdict was reached … Partial outcomes are deliberately not
    carried: exit 2 is 'no verdict', and a half-populated list invites reading one anyway." A
    file at the audit path is read as *the* audit record of a stored version, so writing an
    outcome-less one there is that same failure one level up — indistinguishable, to anything
    that lists ``reports/``, from a version that was audited.
    """

    INPUT_MODE = "input-mode"
    """``subject.input_mode`` is not ``"snapshot"`` — the profile's first obligation (§6.2)."""

    VERSION_MISMATCH = "version-mismatch"
    """``subject.version`` is not the V.S.F.E label the file is named for (§6.2 obligation 1)."""

    DIGEST_MISMATCH = "digest-mismatch"
    """``subject.graph_version`` is not the stored snapshot's (§6.2 obligation 2).

    §6.2 says what that means, in terms: "a report whose digest disagrees with its snapshot is
    a corrupt store, not a stale report".
    """


class AuditError(ValueError):
    """An export could not be produced, written or read back.

    Attributes:
        reason: The :class:`AuditErrorReason` — what to branch on.
        path: The file the fault is about.
    """

    def __init__(self, message: str, *, reason: AuditErrorReason, path: Path) -> None:
        super().__init__(message)
        self.reason = reason
        self.path = path


@dataclass(frozen=True)
class ExportOutcome:
    """One stored version, exported: the document and the file it went to.

    Attributes:
        version: The V.S.F.E label the export is about — the snapshot's own, which is also its
            file base name (PD-012).
        path: ``.gebra/reports/<version>.report.json``, as
            :meth:`~gebra.store.store.SnapshotStore.report_path` computes it.
        report: The document that was written, in memory. It is the
            :class:`~gebra.verify.RunReport` of REPORT-FORMAT-SPEC §1 and nothing wrapping it,
            so a caller that wants the gate, the thirteen outcomes or the SARIF projection has
            them without re-reading the file.
    """

    version: str
    path: Path
    report: RunReport


class Freshness(str, Enum):
    """What a freshness check found — three states, because the third is not the second.

    An empty store is *not* a stale one: nothing changed, nothing was ever recorded, and the
    two want different words and different remedies. Collapsing them would tell a first-time
    user their definition had drifted.
    """

    FRESH = "fresh"
    """The store's current snapshot has the working definition's ``graph_version``."""

    STALE = "stale"
    """The store holds a snapshot and it is of different content — the case the CI check exists for."""

    UNSNAPSHOTTED = "unsnapshotted"
    """The store holds nothing, so there is no snapshot for the definition to agree with."""


@dataclass(frozen=True)
class FreshnessOutcome:
    """The answer to "has this definition been snapshotted since it last changed?".

    The four members after ``state`` are populated exactly as far as the state supports, and
    that is enforced in :meth:`__post_init__` rather than left as a convention — an outcome
    that reported a stored digest for an empty store, or a diff for a fresh one, would be
    saying something no check could have observed.

    Attributes:
        state: Which of the three :class:`Freshness` cases holds.
        graph_version: The IR-SPEC §6 digest of the **working** definition — what was checked.
        store: The store directory the check was made against.
        version: The V.S.F.E label of the store's current snapshot; ``None`` when there is none.
        snapshot_graph_version: That snapshot's digest; ``None`` when there is none.
        diff: What moved between the stored snapshot and the working definition — present only
            on :attr:`Freshness.STALE`, where the whole point is being able to say which of
            S/F/E moved. Absent when fresh, because equal digests are equal canonical forms and
            the diff engine short-circuits on exactly that comparison rather than building a
            graph to confirm it.
    """

    state: Freshness
    graph_version: str
    store: Path
    version: str | None = None
    snapshot_graph_version: str | None = None
    diff: WorkflowDiff | None = None

    def __post_init__(self) -> None:
        """Refuse an outcome that says more, or less, than its own state supports."""
        has_snapshot = self.state is not Freshness.UNSNAPSHOTTED
        if has_snapshot != (self.version is not None):
            raise ValueError("`version` names the current snapshot iff the store holds one")
        if has_snapshot != (self.snapshot_graph_version is not None):
            raise ValueError("`snapshot_graph_version` is the current snapshot's iff there is one")
        if (self.state is Freshness.STALE) != (self.diff is not None):
            raise ValueError(
                "a diff is carried exactly when the definition and the snapshot differ"
            )
        if self.state is Freshness.FRESH and self.snapshot_graph_version != self.graph_version:
            raise ValueError("a fresh outcome's two digests are one digest")
        if self.state is Freshness.STALE and self.snapshot_graph_version == self.graph_version:
            raise ValueError("a stale outcome's two digests differ")

    @property
    def fresh(self) -> bool:
        """Whether the store already holds this definition — what a CI check gates on."""
        return self.state is Freshness.FRESH

    @property
    def moved(self) -> tuple[Component, ...]:
        """Which V.S.F.E components moved, in label order; empty unless stale.

        Read off the diff's own bump class, so the components a message shows and the counters
        a re-snapshot would bump are one derivation (SD-02, SD-05). In label order rather than
        the frozenset's, which is :class:`~gebra.lineage.models.LineageStep`'s convention and
        the only order a V.S.F.E reader expects.
        """
        if self.diff is None:
            return ()
        return tuple(component for component in Component if component in self.diff.bump_class)

    def summary(self) -> str:
        """The check's answer as text — what a failing CI item prints.

        Says what was compared, what differs, and what to do about it. What it never says is
        whether the change is safe or breaking: P-12 ``evolution-safety`` is deferred out of
        Phase 0 (SOW §8; PD-006 R4), so a freshness check reports that content moved and which
        counters it moved, and stops there.
        """
        working = f"  working definition  {_elide(self.graph_version)}"
        store = f"  store               {self.store}"
        if self.state is Freshness.UNSNAPSHOTTED:
            lines = [
                (
                    "the store holds no snapshot, so the working definition has nothing to be "
                    "fresh against"
                ),
                store,
                working,
                "  record the first one: gebra.snapshot.snapshot(workflow, store=store)",
            ]
            return "\n".join(lines)
        stored = f"  snapshot {self.version:<10} {_elide(str(self.snapshot_graph_version))}"
        if self.state is Freshness.FRESH:
            lines = [
                "the store's current snapshot is the working definition",
                store,
                stored,
                working,
            ]
            return "\n".join(lines)
        # An empty bump class beside two different digests is possible rather than
        # contradictory, and it is worth its own words: it is the shape SD-03's recorder
        # refuses outright (a change with no counter to bump), and a check that printed an
        # empty list there would read as "nothing moved" beside two digests that say otherwise.
        moved = (
            ", ".join(component.value for component in self.moved)
            or "the content, without selecting a V.S.F.E counter — the store cannot record it"
        )
        lines = [
            (
                "the working definition is not the snapshot the store holds — it changed and "
                "was not re-snapshotted"
            ),
            store,
            stored,
            working,
            f"  moved               {moved}",
            "  record it: gebra.snapshot.snapshot(workflow, store=store)",
        ]
        return "\n".join(lines)


def _elide(digest: str, *, keep: int = 16) -> str:
    """``sha256:5db68464…`` — enough hex to tell two digests apart in a message.

    The same elision the pytest plugin applies for the same reason: a message a person reads
    is not a place to compare 64 hex digits, and the full digest is on the outcome.
    """
    algorithm, _, hexdigest = digest.partition(":")
    if not hexdigest or len(hexdigest) <= keep:
        return digest
    return f"{algorithm}:{hexdigest[:keep]}…"
