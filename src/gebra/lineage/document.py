"""The lineage as stable JSON — the golden-testable projection of a listing.

The card's second acceptance criterion is that the output be "stable and suitable for
golden-testing". A frozen dataclass of sorted tuples is stable *as a value*; a golden file
needs a byte-stable *text*, and this module is that text.

**The emitter is the one the digest goes through.**
:func:`~gebra.ir.canonical.canonical_foreign_bytes` is RFC 8785 (JCS) — member names sorted as
UTF-16 code units, no whitespace, ES number formatting, UTF-8 out — already proven byte-stable
across interpreter runs by the IR track's own suite. Reusing it means there is no second
serializer in the package to keep honest, and it is why :func:`lineage_document` is written to
produce exactly what that emitter accepts.

**Absent means not applicable.** RFC 8785 serializes ``null`` like any other value; what drops
it is IR-SPEC §6.1 step 3's null rule, which §3.6 keeps in force for foreign objects ("drop
nulls, serialize the object as-is per RFC 8785 JCS") and which
:func:`~gebra.ir.canonical.canonical_foreign_bytes` therefore applies. A projection carrying
nulls would consequently serialize to a document shaped differently from the mapping it came
from, so :func:`lineage_document` omits those members itself rather than emitting nulls for
the emitter to drop. The consequence is what makes the pair usable together:
``json.loads(dump_lineage(x)) == lineage_document(x)``, exactly, pinned by test. A missing
``step`` means the oldest version in the store, a missing ``bump_class`` means the two labels
are not both V.S.F.E, and a missing ``current`` means an empty store — the same three
statements the dataclasses make with ``None``.

**Only the null half of that convention is borrowed, and the divergence is deliberate.**
IR-SPEC §6.3 also omits members equal to a declared default and *empty optional arrays*, which
together make absent, ``null`` and empty interchangeable on the IR. Here they are not: an empty
``bump_class`` (the labels record no rise) and an absent one (the labels carry no
component-wise step at all) are different answers, and both are pinned in
``tests/lineage/golden/lineage-awkward.json``. So an empty array is emitted, never omitted, and
a reader must not carry §6.3's array rule across.

**This is data, not display.** D-11 In-Scope 3 keeps "the terminal UX, flags, and rendering"
with brief D-12, and D-12's OQ-12-04 — table, timeline, or inline diff summaries — is open and
routed to card CLI-D4. Nothing here chooses a display shape; what it offers is a stable
document a golden file can hold, a renderer can read, and SD-07's per-version audit export can
build on without re-deriving the history.

Nothing in this module imports langgraph, opens a socket, or executes anything (WA-07).
"""

from __future__ import annotations

from typing import Final, TypeAlias

from gebra.ir.canonical import canonical_foreign_bytes
from gebra.lineage.models import Lineage, LineageEntry, LineageStep

__all__ = [
    "LINEAGE_DOCUMENT_VERSION",
    "Document",
    "dump_lineage",
    "lineage_document",
]

#: The version of *this projection's* shape — a third compatibility surface beside
#: ``ir_version`` (the IR format) and ``store_version`` (the ``meta.yaml`` layout), carried so
#: that none of the three has to move when another does.
#:
#: The obligation that comes with it: **a change to the document's member vocabulary bumps
#: this constant.** Nothing derives it, so it is held by
#: ``tests/lineage/test_document.py::test_the_documents_member_vocabulary_is_locked_to_its_version``,
#: which pins the exact key set at every level — a shape change fails that test rather than
#: quietly rewriting a golden.
LINEAGE_DOCUMENT_VERSION: Final = "1.0"

#: A JSON document as this module builds it. Null-free by construction — see the module
#: docstring — so the alias states the value domain the emitter is handed.
Document: TypeAlias = "bool | int | float | str | list[Document] | dict[str, Document]"


def lineage_document(lineage: Lineage) -> dict[str, Document]:
    """``lineage`` as a JSON-shaped mapping — the stable data projection.

    Every member is JSON data and none is ``null``: what does not apply is absent (see the
    module docstring). Component tuples become lists of their one-letter names in label order.

    Args:
        lineage: The listing to project.

    Returns:
        A mapping whose members are ``lineage_version``, the store's ``current`` pointer when
        it has one, ``total``, ``omitted_before``, ``omitted_after``, and ``entries``. A row's
        own "is this the one the pointer names" is ``is_current``, spelled apart from the
        root's ``current`` on purpose: one member name carrying a label at one level and a
        boolean at another is a trap for a schema-derived reader.
    """
    document: dict[str, Document] = {"lineage_version": LINEAGE_DOCUMENT_VERSION}
    if lineage.current is not None:
        document["current"] = lineage.current
    document["total"] = lineage.total
    document["omitted_before"] = lineage.omitted_before
    document["omitted_after"] = lineage.omitted_after
    document["entries"] = [_entry_document(entry) for entry in lineage.entries]
    return document


def dump_lineage(lineage: Lineage) -> str:
    """``lineage`` as canonical JSON text — the form a golden file holds.

    RFC 8785 through :func:`~gebra.ir.canonical.canonical_foreign_bytes`, decoded from UTF-8,
    with one trailing newline: PD-012's formatting rule for the store's own files ("UTF-8
    encoding, LF line endings, exactly one trailing newline"), followed here so that a lineage
    dumped beside them reads the same way under ``git diff``. PD-012 states it of the YAML
    emitter it was fixing; adopting it is this module's choice, not that PD's reach.

    Identical listings produce identical text — there is no clock and no set iteration
    anywhere in the path.
    """
    return canonical_foreign_bytes(lineage_document(lineage)).decode("utf-8") + "\n"


def _entry_document(entry: LineageEntry) -> dict[str, Document]:
    """One row: its place, its identity, and the step into it when it has one."""
    document: dict[str, Document] = {
        "index": entry.index,
        "version": entry.version,
        "graph_version": entry.graph_version,
        "created_at": entry.created_at,
        "is_current": entry.is_current,
    }
    if entry.step is not None:
        document["step"] = _step_document(entry.step)
    return document


def _step_document(step: LineageStep) -> dict[str, Document]:
    """One step: where it came from, what the labels counted, whether the content moved."""
    document: dict[str, Document] = {
        "previous": step.previous,
        "content_changed": step.content_changed,
    }
    if step.bump_class is not None:
        document["bump_class"] = [component.value for component in step.bump_class]
    if step.decreased is not None:
        document["decreased"] = [component.value for component in step.decreased]
    return document
