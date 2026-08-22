"""The `.gebra/` store documents — the IR-SPEC §4.1 envelope and the store index.

Normative authority: IR-SPEC §4.1 fixes the envelope's three field names (``version``,
``extracted_from``, ``graph_version``) and states that their *semantics* are owned by brief
D-11. PD-012 (ratified 2026-07-31, owner-signed, with the ``sidecar_path`` amendment) is
where that ownership was exercised: it fixes the field-level shape of both documents, and
this module is that shape as code.

Two documents live here:

* :class:`Snapshot` — one version of one workflow, ``.gebra/snapshots/<version>.yaml``. The
  core IR sits **nested** under ``ir`` rather than merged into the envelope's key space
  (PD-012 Option B rejected): ``WorkflowIR`` is ``extra="forbid"`` and IR-SPEC §8 permits new
  top-level core-IR slots in 1.x, so a flat merge would put a future core-IR field one name
  collision away from an envelope field with nothing structural to catch it.
* :class:`StoreMeta` — ``.gebra/meta.yaml``, the store-wide pointer and append-only history
  D-11 In-Scope 1 asks for ("current version pointer, version history, timestamps"). Each
  :class:`SnapshotRecord` carries enough to answer "what versions exist and what do they hash
  to" without opening every snapshot file.

**The envelope is outside the hash scope by construction, not by rule.** IR-SPEC §6.4
excludes ``version``, ``extracted_from`` and ``graph_version`` from the digest — ``version``
is *derived from* diffs of the digested content so including it would be circular,
``extracted_from`` is provenance, and ``graph_version`` cannot contain itself. Here that
exclusion needs no enforcing: :func:`~gebra.ir.canonical.graph_version` takes a
:class:`~gebra.ir.models.WorkflowIR`, and the only ``WorkflowIR`` in a snapshot is the ``ir``
member. There is no path by which an envelope field could reach a digest.

**What this module validates, and what it deliberately does not.** ``version`` is checked
against a *path-safety floor* — it becomes a file name, and a label carrying a separator
would write outside the store. That floor is not the V.S.F.E grammar, which is SD-02's card;
any grammar SD-02 fixes has to be a subset of what is admitted here, and ``"1.0.0.0"`` is.
``graph_version`` is checked against the rendered §6.1 step-8 form. Whether a snapshot's
digest actually *matches* its IR is a different question — a recompute, not a shape check —
and it belongs to :class:`~gebra.store.store.SnapshotStore`, which runs it on every write and
every read; :meth:`Snapshot.digest_matches` is the same check available directly.

Nothing in this module imports langgraph, opens a socket, or executes anything (WA-07).
"""

from __future__ import annotations

import datetime as _datetime
import re
from typing import Annotated, Final, Literal, TypeAlias

from pydantic import AfterValidator, StringConstraints, model_validator

from gebra.ir.canonical import graph_version as compute_graph_version
from gebra.ir.canonical import verify_graph_version
from gebra.ir.models import WorkflowIR
from gebra.store.base import StoreModel

__all__ = [
    "MAX_VERSION_LENGTH",
    "TIMESTAMP_FORMAT",
    "Digest",
    "ExtractedFrom",
    "Snapshot",
    "SnapshotRecord",
    "StoreMeta",
    "Timestamp",
    "VersionLabel",
    "format_timestamp",
    "parse_timestamp",
]

#: The longest version label the store will use as a file base name. Set far above any
#: V.S.F.E string and far below every filesystem's own limit, so the refusal a caller meets
#: is this one — with the label in it — rather than an ``OSError`` from the write.
MAX_VERSION_LENGTH: Final = 64

#: The one spelling of an instant in the store: ISO-8601, UTC, second precision, ``Z``.
#: A single spelling is the point — two renderings of one instant would be two different
#: documents, and the store's whole determinism claim is that identical content emits
#: identical bytes.
TIMESTAMP_FORMAT: Final = "%Y-%m-%dT%H:%M:%SZ"

#: The path-safety floor on a version label, **not** the V.S.F.E grammar (SD-02 owns that).
#: An allowlist rather than a list of forbidden characters: it admits alphanumerics and
#: ``. _ + -`` between alphanumeric ends, which excludes every path separator, every
#: character Windows refuses in a file name, the empty label, ``.``/``..``, and the leading
#: or trailing dot and space a Windows filesystem silently strips.
_VERSION_PATTERN: Final = r"^[0-9A-Za-z](?:[0-9A-Za-z._+-]*[0-9A-Za-z])?$"

#: Names a Windows filesystem cannot give a file, with or without an extension. Unreachable
#: through a V.S.F.E label, and cheap to refuse: the alternative is a store that writes fine
#: on POSIX and cannot be opened on Windows.
_RESERVED_FILE_NAMES: Final = frozenset(
    {"con", "prn", "aux", "nul"}
    | {f"com{digit}" for digit in "123456789"}
    | {f"lpt{digit}" for digit in "123456789"}
)

#: The rendered digest grammar of IR-SPEC §6.1 step 8 — ``"sha256:" + lowercase hex``, the
#: OCI form :func:`~gebra.ir.canonical.render_digest` produces. ``sha256`` is spelled out
#: rather than left open: §6.1 step 8 keeps ``sha512:``/``blake3:`` agility available *as a
#: versioned change*, and ir 1.0 has exactly one algorithm.
_DIGEST_PATTERN: Final = r"^sha256:[0-9a-f]{64}$"

_TIMESTAMP_PATTERN: Final = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$"


def _refuse_reserved_name(label: str) -> str:
    """Refuse a label a Windows filesystem reserves, comparing as Windows does."""
    if label.split(".")[0].lower() in _RESERVED_FILE_NAMES:
        raise ValueError(
            f"{label!r} is a reserved device name on Windows, so no file could carry it; "
            "a version label is used verbatim as a file base name (PD-012)"
        )
    return label


def _refuse_impossible_instant(text: str) -> str:
    """Refuse a well-shaped timestamp naming no instant — month 13, 31 February."""
    try:
        _datetime.datetime.strptime(text, TIMESTAMP_FORMAT)  # noqa: DTZ007 — Z is in the format
    except ValueError as exc:
        raise ValueError(f"{text!r} is not an instant ({exc})") from exc
    return text


#: A store version label: the V.S.F.E string SD-02 produces, used verbatim as the base name
#: of ``snapshots/<version>.yaml`` and ``reports/<version>.report.json`` (PD-012).
VersionLabel: TypeAlias = Annotated[
    str,
    StringConstraints(pattern=_VERSION_PATTERN, max_length=MAX_VERSION_LENGTH),
    AfterValidator(_refuse_reserved_name),
]

#: A rendered content digest (IR-SPEC §6.1 step 8).
Digest: TypeAlias = Annotated[str, StringConstraints(pattern=_DIGEST_PATTERN)]

#: An instant in :data:`TIMESTAMP_FORMAT`.
Timestamp: TypeAlias = Annotated[
    str,
    StringConstraints(pattern=_TIMESTAMP_PATTERN),
    AfterValidator(_refuse_impossible_instant),
]

#: A provenance string that has to say something — absence is spelled ``None``, never ``""``.
_NonEmpty: TypeAlias = Annotated[str, StringConstraints(min_length=1)]


def format_timestamp(moment: _datetime.datetime) -> str:
    """Render ``moment`` in the store's one timestamp spelling.

    An aware datetime is converted to UTC; a naive one is *taken* as UTC rather than guessed
    at, because the alternative — reading the host's local zone — makes the same instant
    render differently on two machines. Sub-second precision is dropped: the store's
    timestamps are provenance, and a second is the resolution its one spelling carries.

    This function reads no clock. Nothing in :mod:`gebra.store` does — a store write is a
    function of its arguments, which is what makes "identical content emits identical bytes"
    a property a test can hold the store to (PD-012 finding 6).
    """
    if moment.tzinfo is not None:
        moment = moment.astimezone(_datetime.timezone.utc)
    return moment.replace(tzinfo=None, microsecond=0).strftime(TIMESTAMP_FORMAT)


def parse_timestamp(text: str) -> _datetime.datetime:
    """The UTC-aware datetime ``text`` names, the inverse of :func:`format_timestamp`.

    Raises:
        ValueError: if ``text`` is not in :data:`TIMESTAMP_FORMAT`, or names no instant.
    """
    if re.fullmatch(_TIMESTAMP_PATTERN, text) is None:
        raise ValueError(
            f"{text!r} is not a store timestamp; the one spelling is "
            f"{TIMESTAMP_FORMAT!r}, e.g. '2026-07-31T00:00:00Z'"
        )
    naive = _datetime.datetime.strptime(text, TIMESTAMP_FORMAT)  # noqa: DTZ007 — Z is in the format
    return naive.replace(tzinfo=_datetime.timezone.utc)


class ExtractedFrom(StoreModel):
    """Provenance — IR-SPEC §4.1's ``extracted_from``, field-by-field per PD-012.

    §4.1 gives this field one line of prose ("source reference, extractor version, extraction
    timestamp") and its shape to brief D-11; PD-012 fixed these four members, the fourth
    added at ratification because frozen ANNOTATION-API-SPEC §2 requires the envelope's
    ``extracted_from`` to record the sidecar used or its absence.

    Distinct from :class:`gebra.extraction.envelope.ExtractedFrom`, which is what one
    extraction knows about itself — an object family, warning-bearing surfaces, no clock
    reading. This one is what the *store* records about a snapshot, and it is the §4.1
    envelope field proper. Filling it is the snapshot engine's —
    :func:`gebra.snapshot.engine.record` bridges an extraction envelope over, and
    :func:`gebra.snapshot.engine.record_document` (CLI-05) states what a document recording
    knows — and that engine is also where the clock the ``extracted_at`` member needs is
    read; nothing in this package imports the extractor.

    Attributes:
        source: Where the IR came from, in whatever form the producer's provenance takes —
            an object reference for an extraction, a file path for a hand-built fixture or
            a recorded IR document. Free text on purpose: §4.1 says "source reference" and
            the producer owns what a reference means.
        extractor_version: The version of the producer that made the IR as stored. For an
            extraction that is the extracting build, carried verbatim; for a recorded IR
            document — whose authoring producer the document does not name — it is the
            build that read, validated and re-emitted it
            (:func:`gebra.snapshot.engine.record_document` states the reading in full).
        extracted_at: When it was made, in :data:`TIMESTAMP_FORMAT`.
        sidecar_path: The absolute path of the ``gebra.toml`` sidecar the extraction
            consulted, or ``None`` when none was — ANNOTATION-API-SPEC §2, "so digest
            divergence is diagnosable". Absoluteness is the sidecar loader's to resolve and
            is deliberately not re-checked here: a path is absolute *on a platform*, and a
            store written on POSIX has to stay readable on Windows. What is refused is the
            empty string, which is neither a path nor an honest absence.
    """

    source: _NonEmpty
    extractor_version: _NonEmpty
    extracted_at: Timestamp
    sidecar_path: _NonEmpty | None = None


class Snapshot(StoreModel):
    """One stored version of one workflow — the §4.1 envelope around a core IR.

    Field order is declaration order and is the on-disk key order (PD-012 emitter rules): the
    envelope reads first and the IR last, so the head of a snapshot file is the part a person
    scanning a ``git diff`` wants.

    Attributes:
        version: The V.S.F.E label (SD-02's grammar), used verbatim as the file base name.
        extracted_from: Provenance.
        graph_version: The IR-SPEC §6 content digest of :attr:`ir`. Stored rather than
            computed on read, because that is what §4.1 makes it — an envelope *field* — and
            because a stored digest is what lets a reader detect that the IR beside it
            changed. :meth:`digest_matches` is the §6.1 step-9 recompute-and-compare that
            turns it back into a check.
        ir: The core IR — the whole hash scope, nested rather than flattened.
    """

    version: VersionLabel
    extracted_from: ExtractedFrom
    graph_version: Digest
    ir: WorkflowIR

    @classmethod
    def of(cls, ir: WorkflowIR, *, version: str, extracted_from: ExtractedFrom) -> Snapshot:
        """Build a snapshot of ``ir``, computing :attr:`graph_version` from it.

        The ordinary way to make one: the digest is derived here rather than passed in, so a
        snapshot built this way cannot disagree with itself.

        Raises:
            CanonicalizationError: if ``ir`` carries a value the canonical form refuses.
            pydantic.ValidationError: if ``version`` is not usable as a file base name.
        """
        return cls(
            version=version,
            extracted_from=extracted_from,
            graph_version=compute_graph_version(ir),
            ir=ir,
        )

    def digest_matches(self) -> bool:
        """Whether :attr:`graph_version` is the digest of :attr:`ir` (IR-SPEC §6.1 step 9).

        Recompute-and-string-compare, the §1.2 conformance operation. A ``False`` here is the
        store's one detectable content corruption: the two halves of a snapshot file stopped
        agreeing, whether by a hand edit, a partial write, or an IR that was substituted
        under a digest that no longer describes it.

        Raises:
            CanonicalizationError: if :attr:`ir` carries a value the canonical form refuses.
        """
        return verify_graph_version(self.ir, self.graph_version)


class SnapshotRecord(StoreModel):
    """One row of :attr:`StoreMeta.history` — a version, its digest, and when it landed.

    Attributes:
        version: The V.S.F.E label, matching a ``snapshots/<version>.yaml``.
        graph_version: That snapshot's content digest, repeated here so that "what versions
            exist and what do they hash to" is answerable from one file.
        created_at: When the snapshot was written to the store, as its writer reports it.
            :meth:`~gebra.store.store.SnapshotStore.write` defaults it to the snapshot's own
            ``extracted_from.extracted_at``, and :func:`gebra.snapshot.engine.record` takes
            that default rather than reading a second clock — a snapshot is written as soon as
            it is made there, and one instant is what keeps a store write a function of its
            arguments. A writer that stores an IR made earlier passes the landing instant.
    """

    version: VersionLabel
    graph_version: Digest
    created_at: Timestamp


class StoreMeta(StoreModel):
    """``.gebra/meta.yaml`` — the store-wide pointer and append-only history (PD-012).

    Attributes:
        store_version: The layout version of ``meta.yaml`` itself, independent of
            ``ir_version`` so the store format can evolve without an IR-format bump and an
            IR-format bump does not restate the layout.
        current: The version the store's newest snapshot carries, or ``None`` for an empty
            store.
        history: Every version the store holds, oldest first. Append-only (D-11's
            "append-only stores"): :meth:`~gebra.store.store.SnapshotStore.write` adds rows
            and never rewrites one.

    Two invariants are enforced here rather than left to the writer, so a hand-edited
    ``meta.yaml`` is refused at the boundary: no version appears twice, and ``current`` names
    a version the history holds (and is ``None`` exactly when the history is empty).
    ``current`` is *not* required to be the last row — this store's writer always makes it
    so, but pinning that in the model would make a reader's legitimate move (pointing at an
    earlier version) a validation error.
    """

    store_version: Literal["1.0"] = "1.0"
    current: VersionLabel | None = None
    history: tuple[SnapshotRecord, ...] = ()

    @model_validator(mode="after")
    def _check_history(self) -> StoreMeta:
        versions = [record.version for record in self.history]
        duplicates = sorted({version for version in versions if versions.count(version) > 1})
        if duplicates:
            raise ValueError(
                f"history holds more than one row for {', '.join(duplicates)}; a version is "
                "written once and the history is append-only (PD-012)"
            )
        if self.current is None:
            if versions:
                raise ValueError(
                    f"history holds {len(versions)} version(s) but `current` is absent; an "
                    "empty pointer names an empty store"
                )
        elif self.current not in versions:
            raise ValueError(
                f"`current` is {self.current!r}, which the history does not hold "
                f"({', '.join(versions) if versions else 'the history is empty'})"
            )
        return self

    def record_for(self, version: str) -> SnapshotRecord | None:
        """The history row for ``version``, or ``None`` if the store holds no such version."""
        for record in self.history:
            if record.version == version:
                return record
        return None

    def appended(self, record: SnapshotRecord) -> StoreMeta:
        """This meta with ``record`` appended and :attr:`current` moved to it.

        Returns a new value — every store model is frozen — and revalidates, so appending a
        version the history already holds is refused here rather than on the way to disk.

        Raises:
            pydantic.ValidationError: if ``record``'s version is already in the history.
        """
        return StoreMeta(
            store_version=self.store_version,
            current=record.version,
            history=(*self.history, record),
        )
