"""The ``gebra.toml`` sidecar — ANNOTATION-API-SPEC §2.

The second declaration surface, "for nodes whose source cannot be decorated — third-party
tools, vendored callables". It carries "the same slot vocabulary (the §1 closed
annotatable-slot set, byte-for-byte)", keyed by **IR node id in its escaped form** (ledger
§5), and it is *config*: everything it can get wrong degrades to a warning.

Three rules carry the whole module, and each is enforced rather than described.

**Discovery is ordered, bounded, and singular** (§2 "File discovery rule"). An explicit
``gebra.extract(workflow, sidecar=…)`` argument wins outright. Otherwise the walk starts at
the current working directory and goes up, ending at the repository root — "the nearest
ancestor directory containing a ``.git`` entry; when no repository root exists, the walk ends
at the filesystem root" — and the first ``gebra.toml`` found governs. There is **exactly one
sidecar file per extraction, never merged across directories**: :func:`discover_sidecar`
returns at the first hit and nothing in this module ever reads a second file.

**Keying is byte equality of the escaped form.** §2: "the table key is the node id
byte-for-byte in its escaped form (``%2F``/``%25`` per ledger §5). TOML quoting is orthogonal
to percent-escaping — quote, never double-escape. Matching is exact byte equality of the
escaped form, case-sensitive." So a multi-segment id is written ``[nodes."research/tools/web_search"]``
— quoted because ``/`` is not a TOML bare-key character — and a *literal* ``/`` in a source
name arrives already escaped, as ``[nodes."summarize%2Fmerge"]``. This module does no
escaping and no unescaping: it validates the key against the §5 grammar and then compares it
verbatim.

**Nothing here is an error.** §2 puts every validation outcome at warning grade — "the
sidecar is config and extraction stays total, per the §3 rationale; import-time errors live
on the decorator surface only". :func:`read_sidecar` therefore has no failure mode: a missing
file, a TOML syntax error, a wrong ``schema``, an unknown key, a rejected effect tag and a
contradictory entry all come back as :class:`SidecarIssue` records on the reading, which the
extraction side turns into ``annotation-invalid`` warnings. The one thing the loader will not
do is guess: a slot it cannot read is left **unset**, so the lower precedence tiers of §3 fill
it, rather than filled with something nobody declared.

**What this module does not do.** It does not resolve anything into an IR. §3's per-slot
precedence chain (Decorator > Tool-carried > Sidecar > Inference), its conflict warnings, and
the resolved-contract validation are a later card; this module's output is a parsed, validated
:class:`NodeContract` per entry key and nothing more. Until that card lands, a sidecar reaches
the provenance envelope and its warnings, and no sidecar value reaches the IR or
``graph_version``.

Nothing here imports langgraph, opens a socket, or executes anything (WA-07). It reads exactly
one file — the sidecar — and parses it as TOML data; no value in the file is ever called, and
the discovery walk only asks the filesystem whether paths exist. Two residuals, stated rather
than implied, in the voice :mod:`gebra.annotations.contract` uses for its own:

* the ``sidecar=`` argument is typed ``os.PathLike``, and turning one into a :class:`Path`
  runs the caller's own ``__fspath__``. That is the caller's object in the caller's own call,
  not a node being invoked, and there is no way to accept the declared type without it.
* every value the file itself yields comes out of the TOML parser, whose value universe is
  ``str``/``int``/``float``/``bool``/``list``/``dict`` and the date-time family — all builtin
  or stdlib. So a rendered ``{key!r}`` here cannot reach a foreign ``__repr__`` the way the
  same expression on the decorator surface could. That is a property of the parser, not of
  this module's care, which is why the values that *do* get rendered are still narrowed by
  :func:`_reportable` rather than trusted.
"""

from __future__ import annotations

import math
import sys
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final

from gebra.annotations.contract import (
    SLOT_KEYWORDS,
    NodeContract,
    normalize_declared_value,
    normalize_effect_members,
)
from gebra.annotations.errors import ContractErrorReason, GebraContractError
from gebra.annotations.slots import EFFECT_TAGS, AnnotationSlot
from gebra.ir.identity import NodeIdError, validate_node_id
from gebra.naming import type_identity

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - exercised on the 3.10 matrix cells
    import tomli as tomllib

if TYPE_CHECKING:
    import os

__all__ = [
    "SIDECAR_FILENAME",
    "SIDECAR_SCHEMA",
    "SidecarIssue",
    "SidecarReading",
    "SidecarRule",
    "SidecarSource",
    "discover_sidecar",
    "read_sidecar",
    "repository_root",
]

#: The file name the §2 discovery walk looks for, at every level of the walk.
SIDECAR_FILENAME: Final = "gebra.toml"

#: The only accepted value of the file's ``schema`` key (§2's own example). Any other value —
#: and a missing key — means the file is not loaded at all.
SIDECAR_SCHEMA: Final = "gebra-sidecar-v1"

#: The directory entry that marks a repository root (§2: "the nearest ancestor directory
#: containing a ``.git`` entry"). An *entry*, not a directory: a linked worktree and a
#: submodule both carry a ``.git`` **file**, and both are repository roots for this purpose.
_GIT_ENTRY: Final = ".git"

#: The top-level keys the file format has. ``nodes`` is optional — a sidecar that declares
#: only its schema is a well-formed empty sidecar, not a defect.
_FILE_KEYS: Final[frozenset[str]] = frozenset({"schema", "nodes"})


class SidecarSource(str, Enum):
    """How the sidecar path for one extraction was arrived at (§2's two discovery rules).

    Recorded because the two differ in exactly the way §2 warns about: an explicit path is a
    property of the call, while a discovered one is a property of the *current working
    directory*, and "CWD-dependent discovery makes the digest sensitive to the invocation
    directory".
    """

    EXPLICIT = "explicit"
    """§2 rule 1 — an explicit ``sidecar=`` argument, which "wins"."""

    DISCOVERED = "discovered"
    """§2 rule 2 — the nearest ``gebra.toml`` on the walk from the CWD to the repo root."""

    ABSENT = "absent"
    """No explicit argument and nothing found on the walk."""


class SidecarRule(str, Enum):
    """The §2 rule a :class:`SidecarIssue` reports as violated — a stable code to branch on.

    §2's validation list has five bullets and each has its own code here, so "every §2 rule
    degrades to a warning" is checkable per rule rather than by message text. The remaining
    codes cover the ways a *file* can fail to be readable at all, which §2 does not enumerate
    but whose grade its own sentence fixes: the sidecar surface produces warnings, never
    errors.

    Attributes:
        FILE_UNREADABLE: The path does not exist, is not a file, could not be opened, or is
            not one the operating system can express. Reached from an explicit argument
            naming a file that is not there; the discovery walk only yields paths it has just
            seen.
        FILE_UNPARSABLE: The bytes are not a UTF-8 TOML document. TOML *is* UTF-8 by
            definition, so a file saved in another encoding is this rather than a separate
            outcome.
        SCHEMA_MISSING: §2 bullet 1, absent half — no ``schema`` key.
        SCHEMA_UNKNOWN: §2 bullet 1, wrong-value half — a ``schema`` other than
            :data:`SIDECAR_SCHEMA`.
        FILE_KEY_UNKNOWN: A top-level key that is neither ``schema`` nor ``nodes``.
        NODES_TABLE_INVALID: ``nodes`` is present but is not a table.
        ENTRY_KEY_NOT_A_NODE_ID: A ``[nodes.…]`` key that the IR-SPEC §5 grammar does not
            admit, so it is not the escaped node id §2 requires it to be and can match
            nothing.
        ENTRY_NOT_A_TABLE: A ``nodes`` member that is not a table of slots.
        SLOT_KEY_UNKNOWN: §2 bullet 2 — "an entry key outside the §1 closed
            annotatable-slot set (typos included)".
        SLOT_VALUE_INVALID: A value whose slot shape does not admit it. Not one of §2's five
            bullets: §2 enumerates the *semantic* rules and is silent on shape, and the
            §3 repair rule ("the contribution is discarded … an ``annotation-invalid``
            warning names … the violated invariant") is the form the silence is filled in
            with. Raising instead would contradict §2's own posture.
        EFFECT_TAG_UNKNOWN: §2 bullet 3 — a tag outside the closed D-011 vocabulary.
        PURE_EFFECT_EXCLUSIVE: §2 bullet 4 — ``pure = true`` with non-empty ``effects``;
            **both** slots are rejected, "the loader has no basis to prefer one".
        DETERMINISTIC_SEED_REQUIRED: §2 bullet 5 — a ``deterministic`` object without
            ``seed``.
    """

    FILE_UNREADABLE = "file-unreadable"
    FILE_UNPARSABLE = "file-unparsable"
    SCHEMA_MISSING = "schema-missing"
    SCHEMA_UNKNOWN = "schema-unknown"
    FILE_KEY_UNKNOWN = "file-key-unknown"
    NODES_TABLE_INVALID = "nodes-table-invalid"
    ENTRY_KEY_NOT_A_NODE_ID = "entry-key-not-a-node-id"
    ENTRY_NOT_A_TABLE = "entry-not-a-table"
    SLOT_KEY_UNKNOWN = "slot-key-unknown"
    SLOT_VALUE_INVALID = "slot-value-invalid"
    EFFECT_TAG_UNKNOWN = "effect-tag-unknown"
    PURE_EFFECT_EXCLUSIVE = "pure-effect-exclusive"
    DETERMINISTIC_SEED_REQUIRED = "deterministic-seed-required"


@dataclass(frozen=True)
class SidecarIssue:
    """One warning-grade §2 validation finding, in the shape the warning registry asks for.

    A neutral record rather than an
    :class:`~gebra.extraction.warnings.ExtractionWarning` because this package must not import
    :mod:`gebra.extraction` — that package reads the substrate's classes, and the dependency
    between the two runs one way only. :mod:`gebra.extraction.annotations` is what turns these
    into ``annotation-invalid`` records; the fields here are already the fields §2 names, so
    that conversion adds a code and nothing else.

    Attributes:
        rule: The violated §2 rule.
        message: A one-line human summary. Display-only, like every other warning message in
            this build: the facts are the fields.
        node: The entry's node id, for a node-scoped finding; ``None`` for a file-scoped one.
            Always a string the §5 grammar admits, since an entry with any other key is
            rejected before its contents are read.
        slots: The IR slot names the finding concerns, empty for a file-scoped one.
        detail: The rest of §2's "carries" list as JSON data — scope, surface, the file, the
            rule, and the value(s) involved.
    """

    rule: SidecarRule
    message: str
    node: str | None = None
    slots: tuple[AnnotationSlot, ...] = ()
    detail: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SidecarReading:
    """What one extraction's sidecar lookup found — the whole result, never an exception.

    Attributes:
        source: Which §2 discovery rule produced :attr:`path`, or
            :attr:`SidecarSource.ABSENT`.
        path: The **absolute** path of the file that was loaded, or ``None``. Absolute
            because §2 makes it so: the envelope "MUST record the absolute sidecar path used
            (or its absence) so digest divergence is diagnosable". ``None`` covers both "no
            sidecar" and "a file that was found but not loaded" — §2's own wording for the
            latter is that "extraction proceeds sidecar-less", so recording the path as
            *used* would be the one lie this field exists to prevent. The file is still named,
            in the issue.
        entries: One :class:`~gebra.annotations.contract.NodeContract` per well-keyed entry,
            keyed by the node id exactly as the file spells it. An entry every one of whose
            slots was rejected is still present, carrying an empty contract: the key is what
            §2's unmatched-key rule is about, and dropping it would hide a stale key behind an
            invalid value.
        issues: Every §2 finding, in file order.
    """

    source: SidecarSource = SidecarSource.ABSENT
    path: Path | None = None
    entries: Mapping[str, NodeContract] = field(default_factory=dict)
    issues: tuple[SidecarIssue, ...] = ()

    @property
    def loaded(self) -> bool:
        """Whether a file was read and accepted — i.e. whether :attr:`path` is set."""
        return self.path is not None

    def unmatched_keys(self, node_ids: frozenset[str]) -> tuple[str, ...]:
        """The entry keys that match no extracted node id, in file order (§2).

        §2: "A sidecar entry whose key matches no extracted node id emits an
        ``annotation-unknown-node`` warning — deliberate, because a rename is a *new identity*
        (ledger §5 stability statement) and stale sidecar keys are exactly the config drift §3
        guards against."

        Matching is exact byte equality of the escaped form, case-sensitive (§2), which is a
        plain ``in`` against the extracted id set — no normalization on either side, because
        both were normalized once, where they were built.
        """
        return tuple(key for key in self.entries if key not in node_ids)


def repository_root(start: str | os.PathLike[str]) -> Path | None:
    """The repository root governing ``start``, per §2's definition, or ``None``.

    "the nearest ancestor directory containing a ``.git`` entry". ``start`` itself counts as
    its own nearest ancestor — running in the top directory of a checkout is the ordinary
    case, and it is where a ``gebra.toml`` most often sits.
    """
    directory = Path(start).resolve()
    for candidate in (directory, *directory.parents):
        if _is_repository_root(candidate):
            return candidate
    return None


def discover_sidecar(start: str | os.PathLike[str] | None = None) -> Path | None:
    """The §2 rule-2 walk: the nearest ``gebra.toml`` from ``start`` up to the repo root.

    Args:
        start: Where the walk begins. ``None`` means the current working directory, which is
            what §2 fixes for an extraction; the argument exists so that a caller can ask the
            question about a directory other than the one it is standing in — which is how a
            CI job pins what an extraction *would* discover.

    Returns:
        The absolute path of the first ``gebra.toml`` found, or ``None``. "First found
        governs" and "exactly one sidecar file per extraction, never merged across
        directories" are the same statement read twice: this returns at the first hit, and no
        caller in this package looks again.

    The walk's end is the repository root **inclusive** — the root is searched, and then the
    walk stops, so a sidecar above a checkout never governs an extraction inside it. With no
    repository root anywhere above ``start``, the walk ends at the filesystem root (§2).

    Total, like everything else on this surface: a starting point the filesystem will not
    answer for — a deleted working directory, a symlink loop — is "nothing discoverable"
    rather than an exception, since a walk that cannot start has found nothing.
    """
    try:
        directory = (Path.cwd() if start is None else Path(start)).resolve()
    except (OSError, RuntimeError, ValueError):
        # `RuntimeError` is not a slip: on the declared 3.10 floor, non-strict
        # `Path.resolve()` raises it — not `OSError` — for a symlink loop.
        return None
    for candidate in (directory, *directory.parents):
        sidecar = candidate / SIDECAR_FILENAME
        if sidecar.is_file():
            return sidecar
        if _is_repository_root(candidate):
            return None
    return None


def read_sidecar(
    explicit: str | os.PathLike[str] | None = None,
    *,
    start: str | os.PathLike[str] | None = None,
) -> SidecarReading:
    """Resolve, read and validate the sidecar for one extraction (§2). Never raises.

    The §2 discovery rule in order: ``explicit`` wins if given; otherwise
    :func:`discover_sidecar` walks. An explicit path that cannot be read does **not** fall
    back to the walk — substituting a different file for the one the caller named would move
    the digest silently, which is the failure mode §2's provenance requirement exists to make
    visible. It comes back as a :attr:`SidecarRule.FILE_UNREADABLE` issue instead, and the
    extraction proceeds sidecar-less.

    Args:
        explicit: The ``sidecar=`` argument of ``gebra.extract()``, if any.
        start: Where the discovery walk begins; ``None`` means the current working directory.

    Returns:
        The :class:`SidecarReading`. Total: every way a sidecar can be wrong is an issue on
        the reading, because "the sidecar is config and extraction stays total" (§2).
    """
    if explicit is not None:
        return _read_file(Path(explicit), source=SidecarSource.EXPLICIT)
    discovered = discover_sidecar(start)
    if discovered is None:
        return SidecarReading()
    return _read_file(discovered, source=SidecarSource.DISCOVERED)


# ── Discovery ────────────────────────────────────────────────────────────────────────────


def _is_repository_root(directory: Path) -> bool:
    """Whether ``directory`` carries a ``.git`` entry (§2's repository-root definition).

    ``is_symlink`` is asked alongside ``exists`` so that a dangling ``.git`` symlink still
    ends the walk: the entry is there, which is what §2's test is about, and treating it as
    absent would walk out of the checkout it marks.
    """
    entry = directory / _GIT_ENTRY
    return entry.exists() or entry.is_symlink()


# ── Reading ──────────────────────────────────────────────────────────────────────────────


def _read_file(path: Path, *, source: SidecarSource) -> SidecarReading:
    """Read one sidecar file end to end, collecting §2 issues rather than raising.

    Every way the bytes can fail to become a document is caught, because §2's grade for this
    surface is a warning and a single uncaught exception here would make "extraction stays
    total" false for a file the author can fix in a second. Three of them are easy to miss:
    ``Path.resolve`` refuses a path the operating system cannot express; ``tomllib`` decodes
    the bytes as UTF-8 *before* parsing, so a file saved in another encoding raises
    :class:`UnicodeDecodeError` rather than ``TOMLDecodeError``; and the parse itself can
    exhaust the interpreter's stack on a pathologically nested document.
    """
    try:
        absolute = _absolute(path)
    except (OSError, RuntimeError, ValueError) as error:
        # Three, because `Path.resolve()` picks a different one per failure and per version:
        # `ValueError` for a path the OS cannot express (an embedded NUL), `OSError` or —
        # on the declared 3.10 floor — `RuntimeError` for a symlink loop.
        return _not_loaded(
            source,
            path,
            SidecarRule.FILE_UNREADABLE,
            f"the sidecar path {path} is not one this system can resolve "
            f"({type_identity(error)}); extraction proceeds without it",
            {"error": type_identity(error)},
        )
    if not absolute.is_file():
        # Asked before opening, so that the explicit-argument route is gated the same way the
        # walk's own hit already is. It is not only tidiness: `open()` on a FIFO blocks until
        # something writes to it, and on a character device it reads without end — a sidecar
        # is a regular file, and a path that is not one is named rather than followed.
        return _not_loaded(
            source,
            absolute,
            SidecarRule.FILE_UNREADABLE,
            f"the sidecar {absolute} is not a readable file; extraction proceeds without it",
            {"error": "not a regular file"},
        )
    try:
        with absolute.open("rb") as handle:
            document = tomllib.load(handle)
    except OSError as error:
        return _not_loaded(
            source,
            absolute,
            SidecarRule.FILE_UNREADABLE,
            f"the sidecar {absolute} could not be read ({error.strerror or error}); "
            "extraction proceeds without it",
            {"error": error.strerror or type_identity(error)},
        )
    except (tomllib.TOMLDecodeError, UnicodeDecodeError, RecursionError) as error:
        return _not_loaded(
            source,
            absolute,
            SidecarRule.FILE_UNPARSABLE,
            f"the sidecar {absolute} is not a UTF-8 TOML document ({error}); extraction "
            "proceeds without it",
            {"error": str(error)},
        )

    schema = document.get("schema")
    if schema is None:
        return _not_loaded(
            source,
            absolute,
            SidecarRule.SCHEMA_MISSING,
            f'the sidecar {absolute} declares no "schema"; a sidecar is loaded only when it '
            f'declares schema = "{SIDECAR_SCHEMA}" (ANNOTATION-API-SPEC §2)',
            {"schema": None},
        )
    if schema != SIDECAR_SCHEMA:
        return _not_loaded(
            source,
            absolute,
            SidecarRule.SCHEMA_UNKNOWN,
            f"the sidecar {absolute} declares an unknown schema; this build loads "
            f'"{SIDECAR_SCHEMA}" only (ANNOTATION-API-SPEC §2)',
            {"schema": _reportable(schema)},
        )

    issues: list[SidecarIssue] = []
    for key in document:
        if key not in _FILE_KEYS:
            issues.append(
                _file_issue(
                    absolute,
                    SidecarRule.FILE_KEY_UNKNOWN,
                    f"the sidecar {absolute} has the top-level key {key!r}, which the format "
                    f"does not carry; it is ignored (the file's keys are "
                    f"{', '.join(sorted(_FILE_KEYS))})",
                    {"key": key},
                )
            )
    entries = _read_nodes(document.get("nodes"), absolute, issues)
    return SidecarReading(
        source=source,
        path=absolute,
        entries=MappingProxyType(entries),
        issues=tuple(issues),
    )


def _read_nodes(
    nodes: object,
    path: Path,
    issues: list[SidecarIssue],
) -> dict[str, NodeContract]:
    """``[nodes.<node id>]`` → one contract per well-keyed entry (§2)."""
    entries: dict[str, NodeContract] = {}
    if nodes is None:
        return entries
    if not isinstance(nodes, dict):
        issues.append(
            _file_issue(
                path,
                SidecarRule.NODES_TABLE_INVALID,
                f'the sidecar {path} has a "nodes" key that is not a table of node entries, '
                "so no entry is read",
                {"value": _reportable(nodes)},
            )
        )
        return entries
    for key, table in nodes.items():
        try:
            node_id = validate_node_id(key)
        except NodeIdError as error:
            issues.append(
                _file_issue(
                    path,
                    SidecarRule.ENTRY_KEY_NOT_A_NODE_ID,
                    f"the sidecar entry key {key!r} is not a node id ({error}); §2 keys "
                    "entries by the node id byte-for-byte in its escaped form, so this entry "
                    "can match nothing and is ignored",
                    {"key": key, "reason": error.reason.value},
                )
            )
            continue
        if not isinstance(table, dict):
            issues.append(
                _file_issue(
                    path,
                    SidecarRule.ENTRY_NOT_A_TABLE,
                    f"the sidecar entry for {node_id!r} is not a table of slots, so nothing "
                    "is read from it",
                    {"key": node_id, "value": _reportable(table)},
                )
            )
            continue
        entries[node_id] = _read_entry(node_id, table, path, issues)
    return entries


def _read_entry(
    node_id: str,
    table: dict[str, Any],
    path: Path,
    issues: list[SidecarIssue],
) -> NodeContract:
    """One ``[nodes.<id>]`` table → a contract, with every §2 rejection warned (§2).

    Rejection is per slot, never per file: an entry with one bad value still contributes its
    other slots, because §2's repair for a rejected slot is that the slot is unset — which is
    exactly what leaves §3's lower tiers free to fill it.
    """
    declared: dict[str, object] = {}
    effect: tuple[str, ...] | None = None
    for keyword, value in table.items():
        if keyword not in SLOT_KEYWORDS:
            issues.append(_unknown_slot_key(node_id, keyword, path))
            continue
        slot = SLOT_KEYWORDS[keyword]
        if keyword == "effects":
            effect = _read_effects(node_id, value, path, issues)
            continue
        try:
            declared[slot] = normalize_declared_value(keyword, value)
        except GebraContractError as error:
            issues.append(_slot_value_issue(node_id, slot, keyword, value, path, error))
    if effect is not None:
        _place_effects(node_id, effect, path, declared, issues)
    return NodeContract.model_validate(declared)


def _read_effects(
    node_id: str,
    value: object,
    path: Path,
    issues: list[SidecarIssue],
) -> tuple[str, ...] | None:
    """``effects`` → the surviving tags, or ``None`` for "no declaration survived".

    §2 bullet 3 rejects **the tag**, not the slot and not the entry. One consequence is worth
    stating, because it is a judgement the spec leaves open: when tags were declared and
    *every* one of them was rejected, the slot is left **unset** rather than set to the empty
    list. Under §3's "Set means not-``None``" an ``effect: []`` is a declaration — "this node
    has no effects" — which is a claim the author never made and which would additionally
    block the lower tiers from filling the slot. A literally-authored ``effects = []`` is a
    different thing and is kept.
    """
    try:
        members = normalize_effect_members(value)
    except GebraContractError as error:
        issues.append(_slot_value_issue(node_id, "effect", "effects", value, path, error))
        return None
    kept = tuple(tag for tag in members if tag in EFFECT_TAGS)
    rejected = tuple(tag for tag in members if tag not in EFFECT_TAGS)
    if rejected:
        issues.append(
            SidecarIssue(
                rule=SidecarRule.EFFECT_TAG_UNKNOWN,
                message=(
                    f"the sidecar entry for {node_id!r} declares the effect tag(s) "
                    f"{', '.join(repr(tag) for tag in rejected)}, which the closed decision "
                    f"D-011 vocabulary does not contain; "
                    + (
                        f"they are dropped and {list(kept)} is kept"
                        if kept
                        else "no tag survives, so the slot is left unset rather than declared empty"
                    )
                ),
                node=node_id,
                slots=("effect",),
                detail={
                    "scope": "node",
                    "surface": "sidecar",
                    "file": str(path),
                    "rule": SidecarRule.EFFECT_TAG_UNKNOWN.value,
                    "rejected": rejected,
                    "kept": kept,
                    "slot_declared": bool(kept or not members),
                    "vocabulary": tuple(sorted(EFFECT_TAGS)),
                },
            )
        )
    return kept if kept or not members else None


def _place_effects(
    node_id: str,
    effect: tuple[str, ...],
    path: Path,
    declared: dict[str, object],
    issues: list[SidecarIssue],
) -> None:
    """Set ``effect``, unless §2 bullet 4 rejects it and ``pure`` together.

    The exclusivity is read over what *survived* the per-slot validation, which is the same
    order §3's resolved-contract validation runs in: a tag set that was entirely rejected
    never became a declaration, so it cannot contradict a ``pure`` that did — and an authored
    ``effects = []`` is empty, which D-011 exclusivity is not about.

    Both slots go when it does fire, and §2 says why in the same breath — "the loader has no
    basis to prefer one". Discarding one would be picking a winner between two things the same
    author wrote in the same table.
    """
    if declared.get("pure") is not True or not effect:
        declared["effect"] = effect
        return
    declared.pop("pure")
    issues.append(
        SidecarIssue(
            rule=SidecarRule.PURE_EFFECT_EXCLUSIVE,
            message=(
                f"the sidecar entry for {node_id!r} declares pure = true together with the "
                f"effects {list(effect)!r}; decision D-011 makes the two mutually exclusive, "
                "and both slots are rejected because the file gives no basis to prefer one"
            ),
            node=node_id,
            slots=("pure", "effect"),
            detail={
                "scope": "node",
                "surface": "sidecar",
                "file": str(path),
                "rule": SidecarRule.PURE_EFFECT_EXCLUSIVE.value,
                "pure": True,
                "effect": effect,
            },
        )
    )


# ── Issue construction ───────────────────────────────────────────────────────────────────


def _not_loaded(
    source: SidecarSource,
    path: Path,
    rule: SidecarRule,
    message: str,
    detail: Mapping[str, Any],
) -> SidecarReading:
    """A reading for a file that was **not** loaded: no path recorded, one issue (§2)."""
    return SidecarReading(
        source=source, path=None, issues=(_file_issue(path, rule, message, detail),)
    )


def _file_issue(
    path: Path,
    rule: SidecarRule,
    message: str,
    detail: Mapping[str, Any],
) -> SidecarIssue:
    """A file-scoped issue, carrying the §2/§4 fields every ``annotation-invalid`` names."""
    return SidecarIssue(
        rule=rule,
        message=message,
        detail={
            "scope": "file",
            "surface": "sidecar",
            "file": str(path),
            "rule": rule.value,
            **detail,
        },
    )


def _unknown_slot_key(node_id: str, keyword: str, path: Path) -> SidecarIssue:
    """§2 bullet 2 — a key outside the closed nine, "typos included"."""
    return SidecarIssue(
        rule=SidecarRule.SLOT_KEY_UNKNOWN,
        message=(
            f"the sidecar entry for {node_id!r} has the key {keyword!r}, which is not one of "
            f"the nine annotatable slots ({', '.join(SLOT_KEYWORDS)}); the key is ignored "
            f"(ANNOTATION-API-SPEC §1's closed set, shared byte-for-byte with §2)"
        ),
        node=node_id,
        detail={
            "scope": "node",
            "surface": "sidecar",
            "file": str(path),
            "rule": SidecarRule.SLOT_KEY_UNKNOWN.value,
            "key": keyword,
            "slot_keywords": tuple(SLOT_KEYWORDS),
        },
    )


def _slot_value_issue(
    node_id: str,
    slot: AnnotationSlot,
    keyword: str,
    value: object,
    path: Path,
    error: GebraContractError,
) -> SidecarIssue:
    """A rejected slot value, keeping the §1 shape check's own diagnosis.

    The check that produced it is the decorator surface's — one normalization path for both
    surfaces (:func:`~gebra.annotations.contract.normalize_declared_value`), so a value the
    decorator refuses is a value the sidecar refuses, and the two can never drift into
    accepting different things. What differs is only the grade: an error there, this warning
    here, per §2.
    """
    rule = (
        SidecarRule.DETERMINISTIC_SEED_REQUIRED
        if error.reason is ContractErrorReason.DETERMINISTIC_SEED_REQUIRED
        else SidecarRule.SLOT_VALUE_INVALID
    )
    return SidecarIssue(
        rule=rule,
        message=(
            f"the sidecar entry for {node_id!r} declares {keyword!r} in a form the slot does "
            f"not carry: {error}. The slot is left unset"
        ),
        node=node_id,
        slots=(slot,),
        detail={
            "scope": "node",
            "surface": "sidecar",
            "file": str(path),
            "rule": rule.value,
            "key": keyword,
            "value": _reportable(value),
            "reason": error.reason.value,
        },
    )


def _absolute(path: Path) -> Path:
    """``path`` as the absolute path §2 requires the envelope to record.

    ``resolve()`` rather than ``absolute()``: it also normalizes ``..`` segments and follows
    symlinks, so two invocations that named one file by two routes record one path — which is
    what makes "the digest moved and the sidecar did not" a readable statement. It is
    non-strict, so a path that does not exist still resolves and can be named in the issue
    that says so.
    """
    return path.resolve()


def _reportable(value: object) -> Any:
    """A parsed TOML value in a form a warning can carry, without rendering anything foreign.

    Warning ``detail`` is JSON data (INTROSPECTION §8: warnings are reported), and TOML has
    two value kinds JSON does not — the date/time family, and non-finite floats. Neither is
    coerced into something that looks like data it is not: a scalar JSON can carry is kept as
    itself, and anything else is named by its type. Nothing here calls a method on the value:
    every object involved came out of the TOML parser, and naming a type reads two attributes
    of that type (:func:`~gebra.naming.type_identity`).

    Containers are summarized by type rather than copied. What §2 asks a warning to carry is
    "value(s)" for a reader to recognize the declaration by, and a whole nested
    ``args_schema`` is not that.
    """
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else f"a non-finite TOML float ({value})"
    return f"a {type_identity(value)}"
