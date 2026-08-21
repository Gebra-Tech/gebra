"""The ``gebra.toml`` sidecar as extraction sees it — ANNOTATION-API-SPEC §2.

:mod:`gebra.annotations.sidecar` owns the file: discovery, parsing, and the §2 validation
rules, all warning-grade and all substrate-free. This module is the seam between that loader
and an extraction — it does the two things the loader cannot:

* turns a :class:`~gebra.annotations.sidecar.SidecarIssue` into the ``annotation-invalid``
  record of the one warnings taxonomy (INTROSPECTION §8 / ANNOTATION §4). The loader cannot
  build one itself: :class:`~gebra.extraction.warnings.ExtractionWarning` lives in this
  package, which imports langgraph to dispatch on its classes, and the dependency between the
  annotation surface and the extractor runs one way only;
* answers §2's unmatched-key rule, which needs something no loader has — the set of node ids
  the extraction actually produced.

The split is why the loader's issues already carry §2's fields (scope, surface, file, slots,
value(s), the violated rule): the conversion below adds a code and copies, and there is no
second place where the taxonomy's "what it carries" column is interpreted.

Nothing here executes anything (WA-07): it reads a parsed reading and builds records.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from gebra.annotations.sidecar import SidecarReading, read_sidecar
from gebra.extraction.warnings import ExtractionWarning, ExtractionWarningCode

if TYPE_CHECKING:
    import os
    from collections.abc import Iterable

__all__ = ["load_sidecar", "sidecar_warnings", "unknown_node_warnings"]


def load_sidecar(explicit: str | os.PathLike[str] | None) -> SidecarReading:
    """The one sidecar lookup an extraction performs (§2: "exactly **one** sidecar file").

    Called from :func:`gebra.extraction.dispatch.extract` rather than from each family path,
    so that "one file per extraction" is a property of the entry point rather than a rule
    every path has to remember.
    """
    return read_sidecar(explicit)


def sidecar_warnings(reading: SidecarReading) -> tuple[ExtractionWarning, ...]:
    """The reading's §2 findings as ``annotation-invalid`` warnings, in file order.

    Every §2 validation outcome is this one code — §2 names it for each of its five bullets
    and §4's registry lists it once, as "this spec (§2, §3)" — so the code is constant here
    and the *rule* lives in ``detail["rule"]``, which is what a consumer branches on.
    """
    return tuple(
        ExtractionWarning(
            code=ExtractionWarningCode.ANNOTATION_INVALID,
            message=issue.message,
            node=issue.node,
            slots=issue.slots,
            detail=dict(issue.detail),
        )
        for issue in reading.issues
    )


def unknown_node_warnings(
    reading: SidecarReading,
    node_ids: Iterable[str],
) -> tuple[ExtractionWarning, ...]:
    """§2's stale-key rule: one ``annotation-unknown-node`` per entry that matches no node.

    §2: "A sidecar entry whose key matches no extracted node id emits an
    ``annotation-unknown-node`` warning — deliberate, because a rename is a *new identity*
    (ledger §5 stability statement) and stale sidecar keys are exactly the config drift §3
    guards against."

    The warning is **file-scoped**, not node-scoped: §4's registry row carries "sidecar path;
    the unmatched entry key", and the entry names no node that exists — putting the key in
    :attr:`~gebra.extraction.warnings.ExtractionWarning.node` would enter it into the §5
    (node id, slot) lookup as if it were an extracted node.
    """
    if reading.path is None:
        # A file that was not loaded has no entries, so the comprehension below would already
        # be empty — but it would also have formatted the path as the string ``"None"`` on the
        # way there, and this warning exists to name the file. Answered here rather than left
        # to be true by accident.
        return ()
    extracted = frozenset(node_ids)
    path = str(reading.path)
    return tuple(
        ExtractionWarning(
            code=ExtractionWarningCode.ANNOTATION_UNKNOWN_NODE,
            message=(
                f"the sidecar entry {key!r} matches no extracted node id; a renamed node is a "
                "new identity (ir-field-ledger §5), so a stale key annotates nothing"
            ),
            detail={
                "scope": "file",
                "surface": "sidecar",
                "file": path,
                "key": key,
            },
        )
        for key in reading.unmatched_keys(extracted)
    )
