"""What a snapshot call answers with, and how it refuses.

Brief D-11 In-Scope 3 asks this track for "the library APIs these commands call … a stable
Python API contract for them", and ``docs/specs/CLI-SPEC.md`` §4.2 says what ``gebra
snapshot`` has to be able to print from one: "the version label recorded, the file it was
written to, and which of S/F/E moved relative to the previous current version", and — when
the policy records nothing — "a statement that nothing moved, never a fabricated new label".
:class:`SnapshotOutcome` is that sentence as a value.

**Two actions, never a third.** A call either recorded a new version or found the store
already holding this exact content under its current label. There is no "failed" action: a
call that could not do either raises, because a caller that ignored a returned failure would
go on to read a version the store does not hold.

**Which of S/F/E moved is derived, not stored.** :attr:`SnapshotOutcome.bump_class` reads the
diff the label came from, so the reported movement and the label can never disagree — the
same reason :class:`~gebra.diff.workflow.WorkflowDiff` derives its own bump class from its
deltas rather than carrying one.

Nothing in this module imports langgraph, opens a socket, or executes anything (WA-07).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from gebra.diff.workflow import WorkflowDiff
from gebra.versioning.models import Component

__all__ = [
    "SnapshotAction",
    "SnapshotError",
    "SnapshotErrorReason",
    "SnapshotOutcome",
]


class SnapshotAction(str, Enum):
    """What a snapshot call did."""

    RECORDED = "recorded"
    """A new version was written to the store."""

    UNCHANGED = "unchanged"
    """Nothing was written: the store's current version already holds this content."""


class SnapshotErrorReason(str, Enum):
    """Why a snapshot call refused — a stable code to branch on, never message text.

    Like :class:`~gebra.store.store.StoreErrorReason` these are engine codes, not condition
    IDs: the PROPERTY-CATALOG-SPEC §0.4 registry neither contains nor needs them, and no
    verification envelope reports one.
    """

    NOT_SNAPSHOT_ELIGIBLE = "not-snapshot-eligible"
    """The run report handed in says a FATAL finding forbids recording (§0.2)."""

    ELIGIBILITY_MISMATCH = "eligibility-mismatch"
    """The run report handed in verified some other IR, so it says nothing about this one."""

    UNVERSIONABLE_CURRENT = "unversionable-current"
    """The store's current label is outside the V.S.F.E grammar, so nothing can bump it."""

    NO_VERSION_MOVEMENT = "no-version-movement"
    """The content moved but the derived bump class was empty — see :func:`.engine.record`."""


class SnapshotError(ValueError):
    """A snapshot call that could not be completed.

    Subclassing :class:`ValueError` mirrors :class:`~gebra.store.store.StoreError` and
    :class:`~gebra.ir.canonical.CanonicalizationError`. Store-side faults are **not**
    re-wrapped in this type: :class:`~gebra.store.store.StoreError` is already a coded
    refusal naming its own file, and translating it here would give one fault two vocabularies.

    Attributes:
        reason: The :class:`SnapshotErrorReason` code — match on this, not on text.
    """

    def __init__(self, message: str, *, reason: SnapshotErrorReason) -> None:
        super().__init__(message)
        self.reason = reason


@dataclass(frozen=True)
class SnapshotOutcome:
    """What one snapshot call did, and to what.

    Attributes:
        action: Whether a version was recorded or the store already held this content.
        version: The label the store now holds this content under. For
            :attr:`SnapshotAction.UNCHANGED` that is the label it already held — the card's
            "same version", never a fabricated new one.
        graph_version: The IR-SPEC §6 content digest of the IR this call was about.
        path: The snapshot file. Written by this call when :attr:`recorded`; the file that
            was already there when not.
        previous: The store's current label before the call, or ``None`` if the store held
            nothing — in which case this was its first snapshot.
        diff: The delta from the previous current version to this content, or ``None`` when
            there was no previous version to compare against. It is the *whole* diff rather
            than a summary because the label was derived from it, and because SD-07's audit
            export needs "the classified diff against the previous version".

    Four invariants are enforced here rather than left to the engine, so a hand-built outcome
    cannot say something the engine would never say: an unchanged call names the version it
    found and carries an identical diff; a recorded call against a previous version carries a
    diff that has changes; and a first snapshot has no previous version and no diff.
    """

    action: SnapshotAction
    version: str
    graph_version: str
    path: Path
    previous: str | None = None
    diff: WorkflowDiff | None = None

    def __post_init__(self) -> None:
        if self.action is SnapshotAction.UNCHANGED:
            if self.previous != self.version:
                raise ValueError(
                    f"an unchanged call found {self.version!r} and reports "
                    f"{self.previous!r} as the previous version; they are one version"
                )
            if self.diff is None or not self.diff.identical:
                raise ValueError(
                    "an unchanged call compared the working content against the store's "
                    "current version and found them identical; the diff saying so is what "
                    "makes the claim checkable"
                )
            return
        if self.previous is None:
            if self.diff is not None:
                raise ValueError(
                    "a first snapshot has no previous version, so there is nothing it "
                    "could have been diffed against"
                )
            return
        if self.diff is None or not self.diff.has_changes:
            raise ValueError(
                f"recording {self.version!r} over {self.previous!r} means the content "
                "moved, and the diff it moved by is what the label was derived from"
            )

    @property
    def recorded(self) -> bool:
        """Whether this call wrote a snapshot. ``False`` is the no-op, never a failure."""
        return self.action is SnapshotAction.RECORDED

    @property
    def first(self) -> bool:
        """Whether this was the store's first snapshot — the one label nothing derived."""
        return self.previous is None

    @property
    def bump_class(self) -> frozenset[Component]:
        """Which of S, F and E moved relative to :attr:`previous`.

        Empty for an unchanged call and for a first snapshot: nothing moved in the first
        case, and in the second there is nothing for it to have moved relative to.
        """
        return frozenset() if self.diff is None else self.diff.bump_class
