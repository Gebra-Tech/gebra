"""What a version history is, as data — the shapes :func:`~gebra.lineage.engine.lineage` returns.

Brief D-11 In-Scope 3 owes brief D-12 "the library APIs these commands call … a stable Python
API contract for them", and W10 names this engine: "version-history listing with per-version
diff summaries". The card leaves the query API shape to the implementer; these three frozen
dataclasses are that decision.

**One row per stored version, and one step between neighbours.** A :class:`LineageEntry` is a
``meta.yaml`` history row — the version, its digest, when it landed — plus its position and
whether the store's pointer names it. A :class:`LineageStep` is the pair-wise part the card
asks for: which V.S.F.E counters moved from the previous version to this one, and whether the
content moved with them. The first version of a store has no step, and that is the only thing
``step is None`` means.

**The bump class here is read off the labels, not off the content.** The store records no bump
class — it records a version, a digest and a timestamp (PD-012) — so a lineage has to derive
one, and there are two different questions it could be answering:

* *what the labels record* — which of V, S, F and E is higher on this row than on the one
  before it. One arithmetic comparison per pair, over data the index already holds.
* *what the content says* — what :func:`~gebra.diff.workflow_diff` finds between the two
  stored IRs. Two file reads and a graph diff per pair.

:attr:`LineageStep.bump_class` is the first. :func:`~gebra.lineage.engine.compare` is the
second, and it is a separate call precisely because the two can disagree over S, F and E: a
label is assigned by whoever wrote the snapshot, and nothing in the store makes it describe
what changed. Where they disagree is a fact about that store, and neither answer is the
"real" one to quietly prefer.

**Two things about that comparison have to be said out loud, because the same words name two
different domains.** :attr:`WorkflowDiff.bump_class <gebra.diff.workflow.WorkflowDiff>` ranges
over :meth:`Component.derived() <gebra.versioning.models.Component.derived>` — S, F and E —
because the frozen package defines those three and says nothing about what V counts (SD-02
ruling 4: V is never derived). The step here ranges over **all four**, since a caller is free
to assign ``2.0.0.0`` after ``1.3.0.0`` and a listing that dropped the V would be hiding a
version change from a version history. So: a V in a step is not a disagreement with the diff
engine and never can be — it is outside the domain the diff engine reports on at all. The two
are comparable over ``Component.derived()`` and nowhere else, which is how the tests compare
them.

**A step reports what went *down* as well as what went up.**
:meth:`~gebra.store.store.SnapshotStore.write` refuses a duplicate version; it does not
require the history to be label-monotonic, and a store assembled by hand or re-pointed by a
reader can hold a step that counts backwards. Reporting only the counters that rose would show
such a step as an empty bump class — indistinguishable from no version change at all.

**A label that is not a V.S.F.E label still lists.** PD-012 fixes that the label is used
verbatim as the snapshot's file base name; SD-01's recorded ruling on its
``decisions_to_implementer`` then makes the store's check on it a *path-safety floor* and
"explicitly **not** the V.S.F.E grammar", with any grammar SD-02 fixes required to be a subset
of it (it is). So a history can hold ``"draft"``, and a listing engine that raised on one could
not list a store the store itself accepts. Such a step reports
:attr:`~LineageStep.bump_class` and :attr:`~LineageStep.decreased` as ``None`` together — no
component-wise step exists between those two labels — which is a different statement from
``step is None`` (no predecessor at all).

*Naming note.* IR-SPEC §5.3 uses "lineage" for a different thing: tracking a node across a
rename, which it assigns to "the V.S.F.E diff layer (``gebra diff``, P-12)". That layer
shipped, and its ratified position is that no such tracking exists — a renamed node is a new
node, one removal plus one addition, with no similarity matching anywhere
(:mod:`gebra.diff`); the P-12 half of §5.3's sentence is separately out of Phase-0 scope
(SOW §8). "Lineage" here is the card's own word for the version history of a store, and it is
not that question under another name.

Nothing in this module imports langgraph, opens a socket, or executes anything (WA-07).
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

from gebra.versioning.models import Component

__all__ = [
    "Lineage",
    "LineageEntry",
    "LineageStep",
]


@dataclass(frozen=True, slots=True)
class LineageStep:
    """The step from the previous stored version to this one, read off the two index rows.

    Attributes:
        previous: The version this step comes from — the preceding row of the store's
            history, **not** of a window (see :class:`Lineage`). A paginated page's first
            entry therefore still reports its true predecessor.
        content_changed: Whether the two rows' **index-recorded** ``graph_version``s differ.
            Canonicalization is deterministic, so differing digests mean differing canonical
            bytes and the content did move; ``False`` says the index records one digest for
            both rows — a revert, or a version bumped without a content change. (The stronger
            reading, that one digest implies one content, is a collision-resistance
            assumption IR-SPEC §1.2 does not make, and this field does not need it.) Read
            together with :attr:`bump_class`, it is the pair of facts a lineage can state
            from the index alone: an empty bump class beside a changed digest says the labels
            did not record what moved.
        bump_class: Which of V, S, F and E count higher here than on :attr:`previous`, in
            label order. All four, not just the derived three — see the module docstring on
            why a V here is not a disagreement with the diff engine. ``None`` when at least
            one of the two labels is not a V.S.F.E label; ``None`` and ``()`` are different
            answers.
        decreased: Which count *lower*, in label order. ``()`` in any store written by this
            package's own engines; ``None`` exactly when :attr:`bump_class` is.
    """

    previous: str
    content_changed: bool
    bump_class: tuple[Component, ...] | None = None
    decreased: tuple[Component, ...] | None = None

    @property
    def comparable(self) -> bool:
        """Whether both labels parse as V.S.F.E, so a component-wise step exists at all."""
        return self.bump_class is not None

    @property
    def forward(self) -> bool | None:
        """Whether this step moves strictly forward in the version order.

        ``True`` iff no component counts down — since the store forbids a duplicate version,
        the two labels differ, so "nothing decreased" means "something increased and nothing
        decreased", which is exactly the :class:`~gebra.versioning.models.Version` order's
        strictly-greater. ``None`` when the step is not :attr:`comparable`.
        """
        return None if self.decreased is None else not self.decreased


@dataclass(frozen=True, slots=True)
class LineageEntry:
    """One stored version — a ``meta.yaml`` history row, placed and stepped.

    Attributes:
        index: Position in the **whole** history, oldest first, zero-based — absolute, so a
            windowed listing's rows keep their real place in the store.
        version: The V.S.F.E label, which is also the snapshot's file base name (PD-012).
        graph_version: The IR-SPEC §6 content digest the index records for it. What the
            *index* records: whether the snapshot file beside it still hashes to this is
            :meth:`~gebra.store.store.SnapshotStore.check`'s question, not a listing's.
        created_at: When the version landed, in the store's one timestamp spelling.
        is_current: Whether the store's ``current`` pointer names this version. Named apart
            from :attr:`Lineage.current`, which is a *label*: one name carrying a string at
            one level and a boolean at another is a trap for a schema-derived reader, and
            SD-07 and the CLI are both named consumers of this projection.
        step: The step from the preceding version, or ``None`` for the oldest version in the
            store — which is the only thing ``None`` means here.
    """

    index: int
    version: str
    graph_version: str
    created_at: str
    is_current: bool = False
    step: LineageStep | None = None


@dataclass(frozen=True, slots=True)
class Lineage:
    """A version history, or a window onto one — what :func:`~gebra.lineage.engine.lineage`
    returns.

    **One order, and it is the store's own**: oldest first, the order ``meta.yaml`` appends
    in. It is not configurable. A newest-first display is ``reversed(lineage)`` at the
    presentation layer, where D-11 puts display decisions (In-Scope 3: "the terminal UX,
    flags, and rendering belong to D-12"); an ordering *option* here would mean two golden
    files for one store and two shapes for D-12 to render.

    **A window never lies about the whole.** :attr:`total` is the full history length,
    :attr:`omitted_before` and :attr:`omitted_after` count what the window dropped on each
    side, and every :attr:`~LineageEntry.index` is absolute. Those three plus the entry count
    are checked to add up at construction, so a window cannot be built that under-reports the
    store.

    Attributes:
        entries: The rows in the window, oldest first.
        total: How many versions the store holds, whatever the window shows.
        current: The version the store's pointer names, or ``None`` for an empty store. It
            may sit outside the window — :attr:`current_entry` is ``None`` when it does.
        omitted_before: How many rows the window dropped from the old end.
        omitted_after: How many it dropped from the new end.
    """

    entries: tuple[LineageEntry, ...] = ()
    total: int = 0
    current: str | None = None
    omitted_before: int = 0
    omitted_after: int = 0

    def __post_init__(self) -> None:
        counted = self.omitted_before + len(self.entries) + self.omitted_after
        if counted != self.total:
            raise ValueError(
                f"a window has to account for the whole history: {self.omitted_before} "
                f"omitted before + {len(self.entries)} shown + {self.omitted_after} omitted "
                f"after is {counted}, and the store holds {self.total}"
            )
        for offset, entry in enumerate(self.entries):
            if entry.index != self.omitted_before + offset:
                raise ValueError(
                    f"entry {entry.version!r} carries index {entry.index}, but it is row "
                    f"{offset} of a window starting at {self.omitted_before}; an index is "
                    "the row's absolute place in the store's history"
                )

    def __len__(self) -> int:
        """How many rows this window shows — not :attr:`total`."""
        return len(self.entries)

    def __iter__(self) -> Iterator[LineageEntry]:
        """The rows, oldest first."""
        return iter(self.entries)

    @property
    def versions(self) -> tuple[str, ...]:
        """The window's version labels, oldest first."""
        return tuple(entry.version for entry in self.entries)

    @property
    def truncated(self) -> bool:
        """Whether the window drops anything the store holds."""
        return bool(self.omitted_before or self.omitted_after)

    @property
    def oldest(self) -> LineageEntry | None:
        """The window's first row, or ``None`` if it is empty."""
        return self.entries[0] if self.entries else None

    @property
    def newest(self) -> LineageEntry | None:
        """The window's last row, or ``None`` if it is empty."""
        return self.entries[-1] if self.entries else None

    @property
    def current_entry(self) -> LineageEntry | None:
        """The row :attr:`current` names, or ``None`` if the window does not show it."""
        return None if self.current is None else self.entry_for(self.current)

    def entry_for(self, version: str) -> LineageEntry | None:
        """The row for ``version``, or ``None`` if the window does not show it."""
        for entry in self.entries:
            if entry.version == version:
                return entry
        return None
