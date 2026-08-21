"""The version-history query surface — listing a store, and comparing two of its versions.

Brief D-11 In-Scope 3 makes this team's deliverable "the library APIs these commands call …
a stable Python API contract"; W10 names the engine ("version-history listing with per-version
diff summaries"). Two functions are that surface:

* :func:`lineage` — the listing. Every version the store holds, in the store's own order, with
  its digest, when it landed, and the V.S.F.E step from the version before it.
* :func:`compare` — the content answer for one pair: the two snapshots read out of the store
  and run through :func:`~gebra.diff.workflow_diff`.

**:func:`lineage` reads exactly one file.** It opens ``meta.yaml`` and nothing else — never a
snapshot. That is deliberate and is held by a test that deletes every snapshot file and still
gets a complete listing. Three things follow, and all three are the point:

* a listing over a hundred versions is one read, not a hundred;
* what a listing reports is what the *index* records, which is the honest scope of a listing.
  Whether each snapshot file still hashes to the digest beside it is a different question with
  its own answer — :meth:`~gebra.store.store.SnapshotStore.check` — and a listing that
  silently did that work would be reporting on data it had also just re-derived;
* the expensive answer is opt-in and named: :func:`compare`.

**Ordering and pagination** are this card's second decision, and they are stated in
:class:`~gebra.lineage.models.Lineage`: one order (the store's, oldest first, not
configurable), inclusive ``since``/``until`` anchors that must name versions the history
holds, and a ``limit`` that drops the **oldest** rows first — ``git log -n`` semantics, the
only truncation direction that makes sense for a log that grows at one end. Whatever the
window, ``total``, ``omitted_before``, ``omitted_after`` and every absolute ``index`` ride
along, so a page never reads as the whole store.

**Nothing here grades a change.** A step says which counters moved; :func:`compare` returns a
:class:`~gebra.diff.workflow.WorkflowDiff`, which carries the property registry's own
deferred-P-12 marker in the slot where a safe/breaking classification would sit (SOW §8;
PD-006 R4). Neither says whether an evolution is safe, because Phase 0 ships no classifier
that could.

**What this package is not.** It is not a CLI verb. D-12's OQ-12-04 — whether the verb is
``gebra trace`` or ``gebra history``, and whether its output is a table, a timeline, or
inline diff summaries — is open, routed to card CLI-D4, and the naming half of it exists
because "trace" already means runtime traces in a future hosted surface. So this
package is named for what it computes rather than for a verb that has not been named, and it
chooses no display shape: it returns data, and :mod:`gebra.lineage.document` projects that
data to stable JSON.

Nothing in this module imports langgraph, opens a socket, or executes anything (WA-07). Its
inputs are a store directory and IR models; there is no user object in reach to invoke.
"""

from __future__ import annotations

from enum import Enum

from gebra.diff.workflow import WorkflowDiff, workflow_diff
from gebra.lineage.models import Lineage, LineageEntry, LineageStep
from gebra.store.models import SnapshotRecord
from gebra.store.store import SnapshotStore
from gebra.versioning.models import Component, Version, VersionFormatError

__all__ = [
    "LineageError",
    "LineageErrorReason",
    "compare",
    "lineage",
]


class LineageErrorReason(str, Enum):
    """Why a lineage query was refused — a stable code to branch on, never message text.

    Like :class:`~gebra.store.store.StoreErrorReason` these are query-integrity codes, not
    condition IDs: the PROPERTY-CATALOG-SPEC §0.4 registry neither contains nor needs them,
    and no verification envelope reports one.
    """

    UNKNOWN_VERSION = "unknown-version"
    """A ``since`` or ``until`` anchor naming a version the history does not hold."""

    INVALID_WINDOW = "invalid-window"
    """``since`` sits after ``until`` in the history — a window that cannot contain a row."""

    NEGATIVE_LIMIT = "negative-limit"
    """A ``limit`` below zero. ``0`` is a legal, empty window; ``-1`` is a mistake."""


class LineageError(ValueError):
    """A lineage query that names something the store does not hold, or cannot be answered.

    A :class:`ValueError` for the same reason :class:`~gebra.store.store.StoreError` is one.
    It is deliberately *not* a ``StoreError``: nothing is wrong with the store — the query is
    what is wrong — and a caller distinguishing "this store is damaged" from "I asked for a
    version that is not there" should not have to read a message to do it.

    Attributes:
        reason: The :class:`LineageErrorReason` code — match on this, not on text.
        value: What was refused: the unknown label, the offending window, or the limit.
    """

    def __init__(self, message: str, *, reason: LineageErrorReason, value: str) -> None:
        super().__init__(message)
        self.reason = reason
        self.value = value


def lineage(
    store: SnapshotStore,
    *,
    since: str | None = None,
    until: str | None = None,
    limit: int | None = None,
) -> Lineage:
    """The store's version history, oldest first, with digests and per-pair bump classes.

    Reads ``meta.yaml`` and no snapshot file (see the module docstring). A store that does not
    exist, or exists and holds nothing, lists as an empty lineage.

    Args:
        store: The ``.gebra/`` store to list.
        since: Inclusive oldest version to show. Must be a version the history holds.
        until: Inclusive newest version to show. Must be a version the history holds.
        limit: At most this many rows, dropping the **oldest** first — so ``limit=10`` is the
            ten most recent versions of the selected range. ``0`` is a legal empty window.

    Returns:
        The window. Rows are oldest first; ``total``, ``omitted_before`` and ``omitted_after``
        describe the whole history whatever the window shows, and every row's ``index`` and
        ``step`` are relative to the store rather than to the page.

    Raises:
        LineageError: ``unknown-version`` if ``since`` or ``until`` names a version the
            history does not hold; ``invalid-window`` if ``since`` sits after ``until``;
            ``negative-limit`` for a ``limit`` below zero.
        StoreError: ``meta-unreadable`` if the index is there and is not a store index. A
            damaged index is the store's fault, not the query's, and keeps the store's own
            error type.
    """
    meta = store.read_meta()
    rows = meta.history
    total = len(rows)
    positions = {record.version: index for index, record in enumerate(rows)}

    start = 0 if since is None else _position(since, positions, "since")
    stop = total if until is None else _position(until, positions, "until") + 1
    if start > stop:
        raise LineageError(
            f"the window is empty by construction: since={since!r} is row {start} of the "
            f"history and until={until!r} is row {stop - 1}, so nothing can lie between them",
            reason=LineageErrorReason.INVALID_WINDOW,
            value=f"{since}..{until}",
        )
    if limit is not None:
        if limit < 0:
            raise LineageError(
                f"a limit counts rows, so it cannot be {limit}; pass 0 for an empty window "
                "or leave it out for the whole history",
                reason=LineageErrorReason.NEGATIVE_LIMIT,
                value=str(limit),
            )
        start = max(start, stop - limit)

    return Lineage(
        entries=tuple(_entry(rows, index, current=meta.current) for index in range(start, stop)),
        total=total,
        current=meta.current,
        omitted_before=start,
        omitted_after=total - stop,
    )


def compare(store: SnapshotStore, before: str, after: str) -> WorkflowDiff:
    """The structural diff between two stored versions — what the *content* says changed.

    The content answer to the question :attr:`~gebra.lineage.models.LineageStep.bump_class`
    answers from the labels. Both snapshots are read with the store's digest check on, so the
    diff's own refusal of a snapshot that disagrees with itself (IR-SPEC §6.1 step 9) is
    unreachable through this path — the store raises first, naming the file.

    Args:
        store: The store holding both versions.
        before: The version compared from.
        after: The version compared to.

    Returns:
        The diff, anchored on both sides' recomputed digests and carrying both V.S.F.E labels.
        Its ``bump_class`` is derived from the two IRs and ranges over
        :meth:`Component.derived() <gebra.versioning.models.Component.derived>` — S, F and E.
        Compared with the step the labels record, **over those three components only**, a
        difference means the store's labels and its content disagree, and neither is quietly
        preferred. A ``V`` in the label step is not such a difference: the frozen package says
        nothing about what V counts, so no content diff can ever report one
        (:mod:`gebra.lineage.models` states the domain split in full).

    Raises:
        StoreError: ``unsafe-version``, ``snapshot-missing``, ``snapshot-unreadable``,
            ``version-mismatch`` or ``digest-mismatch`` for either side.
        CanonicalizationError: if a stored IR has no canonical form.
    """
    return workflow_diff(store.read(before), store.read(after))


def _position(version: str, positions: dict[str, int], anchor: str) -> int:
    """Where ``version`` sits in the history, or a coded refusal naming the anchor."""
    try:
        return positions[version]
    except KeyError:
        held = list(positions)
        raise LineageError(
            f"{anchor}={version!r} is not a version this store holds ("
            + (
                "the store is empty"
                if not held
                else f"it holds {len(held)} version(s), {held[0]!r} … {held[-1]!r}"
            )
            + ")",
            reason=LineageErrorReason.UNKNOWN_VERSION,
            value=version,
        ) from None


def _entry(rows: tuple[SnapshotRecord, ...], index: int, *, current: str | None) -> LineageEntry:
    """One history row, placed in the whole history and stepped from its predecessor."""
    record = rows[index]
    return LineageEntry(
        index=index,
        version=record.version,
        graph_version=record.graph_version,
        created_at=record.created_at,
        is_current=record.version == current,
        step=None if index == 0 else _step(rows[index - 1], record),
    )


def _step(before: SnapshotRecord, after: SnapshotRecord) -> LineageStep:
    """The step between two neighbouring history rows — labels compared, digests compared."""
    bump_class, decreased = _label_delta(before.version, after.version)
    return LineageStep(
        previous=before.version,
        content_changed=before.graph_version != after.graph_version,
        bump_class=bump_class,
        decreased=decreased,
    )


def _label_delta(
    before: str, after: str
) -> tuple[tuple[Component, ...], tuple[Component, ...]] | tuple[None, None]:
    """Which components count higher in ``after`` than in ``before``, and which lower.

    Both tuples come out in label order (V, S, F, E), because that is the order
    :class:`~gebra.versioning.models.Component` and
    :attr:`~gebra.versioning.models.Version.counts` are both written in — sorted by
    construction rather than by a sort, which is one fewer thing to keep stable.

    ``(None, None)`` when either label is outside SD-02's grammar: the store's floor on a
    label is path-safety, not V.S.F.E (see :mod:`gebra.lineage.models`), so a listing has to
    stay total over labels the store accepts and this engine cannot parse.
    """
    try:
        counts = (Version.parse(before).counts, Version.parse(after).counts)
    except VersionFormatError:
        return None, None
    paired = tuple(zip(Component, *counts, strict=True))
    return (
        tuple(component for component, old, new in paired if new > old),
        tuple(component for component, old, new in paired if new < old),
    )
