"""The card's second acceptance criterion: output stable and suitable for golden-testing.

Two goldens hold it. ``golden/lineage-evolved.json`` is the five-version store's whole
history — the ordinary shape, every member populated. ``golden/lineage-awkward.json`` is the
store the engine must stay total over, and it is the one that pins *absence*: a row with no
step, a step with no component-wise bump class, and a step whose two digests agree.

**"Stable" is three separate claims, and each has its own test**: the same listing dumps to
identical text twice; two independently built listings of the same store dump to one text; and
four child interpreters under four ``PYTHONHASHSEED`` values print one digest of it — which is
where "across runs" is observable at all, since dict iteration order is what would otherwise
reach a document assembled from mappings.

**The projection and its text describe one shape.** RFC 8785 as IR-SPEC §3.6 applies it drops
``null``-valued members, so a mapping carrying nulls would serialize to a document shaped
differently from the mapping itself. :func:`~gebra.lineage.document.lineage_document` therefore
omits those members itself, and the consequence — ``json.loads(dump_lineage(x)) ==
lineage_document(x)``, exactly — is asserted here rather than left as a comment.

**Regenerating a golden (WA-05).** These files are the engine's own output; the command that
writes them is in :func:`_regenerate`, and a diff in one is a change in the projection, which
belongs in a commit that says which change and why.

Everything is hand-built IR models (WA-07): no extractor, no substrate, nothing to invoke.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from gebra.ir.canonical import canonical_foreign_bytes
from gebra.lineage import (
    LINEAGE_DOCUMENT_VERSION,
    Lineage,
    dump_lineage,
    lineage,
    lineage_document,
)
from gebra.store import SnapshotStore
from tests.lineage.stores import awkward_store, evolved_labels, evolved_store

REPO_ROOT = Path(__file__).resolve().parents[2]
GOLDEN = Path(__file__).parent / "golden"

#: Each golden file, and the store whose whole history it holds.
BUILDERS = {
    "lineage-evolved.json": evolved_store,
    "lineage-awkward.json": awkward_store,
}


def _regenerate(tmp_path: Path) -> None:  # pragma: no cover — WA-05: run by hand, with a why
    """Rewrite every golden from the engine's current output.

    From the repository root, so that ``tests.lineage`` imports::

        .venv/bin/python -c "import tempfile, pathlib
        from tests.lineage.test_document import _regenerate
        _regenerate(pathlib.Path(tempfile.mkdtemp()))"

    Written as bytes, not text: ``write_text`` would translate the line ending on a platform
    whose default is not LF, committing a golden whose bytes differ from the engine's output.
    """
    for index, (name, build) in enumerate(BUILDERS.items()):
        store = build(tmp_path / str(index))
        (GOLDEN / name).write_bytes(dump_lineage(lineage(store)).encode("utf-8"))


@pytest.fixture
def evolved(tmp_path: Path) -> SnapshotStore:
    return evolved_store(tmp_path)


@pytest.fixture
def awkward(tmp_path: Path) -> SnapshotStore:
    return awkward_store(tmp_path)


def _nulls(value: Any, path: str = "") -> list[str]:
    """Every path in ``value`` holding ``None`` — empty for a document built by this package."""
    if value is None:
        return [path or "<root>"]
    if isinstance(value, dict):
        return [found for key, item in value.items() for found in _nulls(item, f"{path}.{key}")]
    if isinstance(value, list):
        return [
            found for index, item in enumerate(value) for found in _nulls(item, f"{path}[{index}]")
        ]
    return []


# ── The goldens ──────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("name", list(BUILDERS))
def test_a_whole_history_dumps_to_its_golden_file(name: str, tmp_path: Path) -> None:
    """Byte-for-byte, trailing newline included — the file *is* the output, not a rendering
    of it.

    Compared as bytes rather than as text: ``read_text`` applies universal-newline
    translation, so a CRLF-ified golden would read equal to an LF one and a line-ending
    change could land unseen (the IR track's ``test_canonical.py`` compares its goldens the
    same way, for the same reason)."""
    store = BUILDERS[name](tmp_path)

    assert dump_lineage(lineage(store)).encode("utf-8") == (GOLDEN / name).read_bytes()


def test_the_evolved_golden_holds_the_history_the_engine_lists(evolved: SnapshotStore) -> None:
    """What the golden is *of*, asserted rather than left to a reader of the JSON."""
    document = json.loads((GOLDEN / "lineage-evolved.json").read_bytes())

    assert document["lineage_version"] == LINEAGE_DOCUMENT_VERSION
    assert document["total"] == 5
    assert document["current"] == evolved_labels()[-1]
    assert [entry["version"] for entry in document["entries"]] == list(evolved_labels())
    assert [entry["step"]["bump_class"] for entry in document["entries"][1:]] == [
        ["S", "F"],
        ["F"],
        ["E"],
        ["S"],
    ]
    assert (document["omitted_before"], document["omitted_after"]) == (0, 0)


def test_the_awkward_golden_is_where_absence_is_pinned(awkward: SnapshotStore) -> None:
    """The "not applicable" statements the projection makes by omission — and the one case
    that must *not* be an omission.

    An empty ``bump_class`` (the labels record no rise) and an absent one (the two labels
    carry no component-wise step at all) are different answers, so the empty array is emitted
    rather than omitted. That is where this projection parts from IR-SPEC §6.3, which drops
    empty optional arrays on the IR; only §6.1 step 3's null rule is borrowed."""
    entries = json.loads((GOLDEN / "lineage-awkward.json").read_bytes())["entries"]

    assert "step" not in entries[0]  # nothing precedes the oldest version
    assert entries[1]["step"]["bump_class"] == [] and entries[1]["step"]["decreased"] == ["S"]
    assert "bump_class" not in entries[2]["step"]  # 'draft' is not a V.S.F.E label
    assert "decreased" not in entries[2]["step"]
    assert entries[2]["step"]["content_changed"] is False  # two versions, one content
    assert entries[4]["step"]["bump_class"] == ["V"]  # the component no content diff reports
    assert lineage(awkward).versions == tuple(entry["version"] for entry in entries)


def test_an_empty_store_dumps_to_an_empty_history(tmp_path: Path) -> None:
    document = lineage_document(lineage(SnapshotStore.for_project(tmp_path)))

    assert document == {
        "lineage_version": "1.0",
        "total": 0,
        "omitted_before": 0,
        "omitted_after": 0,
        "entries": [],
    }
    assert "current" not in document  # an empty store has no pointer, and says so by omission


def test_a_window_projects_the_rows_it_shows_and_the_counts_it_does_not(
    evolved: SnapshotStore,
) -> None:
    labels = evolved_labels()

    document = json.loads(dump_lineage(lineage(evolved, limit=2)))

    assert (document["total"], document["omitted_before"], document["omitted_after"]) == (5, 3, 0)
    assert document["current"] == labels[-1]
    assert [entry["index"] for entry in document["entries"]] == [3, 4]  # absolute, not 0 and 1
    # A page's first row still steps from the store's row before it, not from nothing.
    assert document["entries"][0]["step"]["previous"] == labels[2]


# ── The document's shape is locked to its version ────────────────────────────────────────

#: Every member name the projection may emit, by level. The list is exhaustive on purpose: it
#: is what ties a change in the document's shape to a bump of ``LINEAGE_DOCUMENT_VERSION``,
#: which nothing else derives.
VOCABULARY = {
    "": {"lineage_version", "current", "total", "omitted_before", "omitted_after", "entries"},
    "entries[]": {"index", "version", "graph_version", "created_at", "is_current", "step"},
    "entries[].step": {"previous", "content_changed", "bump_class", "decreased"},
}


def test_the_documents_member_vocabulary_is_locked_to_its_version(
    evolved: SnapshotStore, awkward: SnapshotStore, tmp_path: Path
) -> None:
    """Adding, renaming or dropping a member is a shape change, and a shape change bumps
    ``LINEAGE_DOCUMENT_VERSION``.

    Without this the constant would be decorative: a projection could grow a member, the two
    goldens would be regenerated, and the document would still call itself ``1.0``. Absence is
    meaningful in this document, so the check is subset-per-level rather than equality — what
    it forbids is a name outside the vocabulary."""
    assert LINEAGE_DOCUMENT_VERSION == "1.0"

    for history in (
        lineage(evolved),
        lineage(awkward),
        lineage(evolved, limit=2),
        lineage(SnapshotStore.for_project(tmp_path / "empty")),
    ):
        document = json.loads(dump_lineage(history))
        assert set(document) <= VOCABULARY[""]
        for entry in document["entries"]:
            assert set(entry) <= VOCABULARY["entries[]"]
            assert set(entry.get("step", {})) <= VOCABULARY["entries[].step"]

    # …and every name is reachable, so the vocabulary cannot rot into a superset of the truth.
    seen = set(json.loads(dump_lineage(lineage(evolved)))) | {
        name
        for store in (evolved, awkward)
        for entry in json.loads(dump_lineage(lineage(store)))["entries"]
        for name in (*entry, *entry.get("step", ()))
    }
    assert seen == VOCABULARY[""] | VOCABULARY["entries[]"] | VOCABULARY["entries[].step"]


# ── One shape, no nulls ──────────────────────────────────────────────────────────────────


def test_the_projection_and_its_text_describe_one_shape(
    evolved: SnapshotStore, awkward: SnapshotStore, tmp_path: Path
) -> None:
    """The §6.1 step-3 null rule §3.6 keeps in force for foreign objects drops null members on
    the way through the emitter — RFC 8785 itself serializes them — so this equality holds
    only because the projection emits none for it to drop."""
    for history in (
        lineage(evolved),
        lineage(awkward),
        lineage(evolved, limit=2),
        lineage(evolved, limit=0),
        lineage(SnapshotStore.for_project(tmp_path / "empty")),
    ):
        assert json.loads(dump_lineage(history)) == lineage_document(history)


def test_no_document_carries_a_null_anywhere(
    evolved: SnapshotStore, awkward: SnapshotStore
) -> None:
    for history in (lineage(evolved), lineage(awkward), lineage(evolved, limit=1)):
        assert _nulls(lineage_document(history)) == []


def test_dumping_is_a_fixed_point_through_json(evolved: SnapshotStore) -> None:
    """Re-serializing the parsed document reproduces the text — nothing is lost or reordered on
    the way through, which is what lets a consumer read a golden and write it back."""
    text = dump_lineage(lineage(evolved))

    assert canonical_foreign_bytes(json.loads(text)).decode("utf-8") + "\n" == text


def test_the_text_ends_in_exactly_one_newline(evolved: SnapshotStore) -> None:
    """PD-012's emitter rule for every file the store writes, kept by the thing written beside
    them: LF, one of them, and no blank line before it."""
    text = dump_lineage(lineage(evolved))

    assert text.endswith("\n") and not text.endswith("\n\n")
    assert "\r" not in text
    assert text.count("\n") == 1


# ── Stability ────────────────────────────────────────────────────────────────────────────


def test_the_same_history_dumps_to_the_same_text_twice(evolved: SnapshotStore) -> None:
    assert dump_lineage(lineage(evolved)) == dump_lineage(lineage(evolved))
    assert lineage(evolved) == lineage(evolved)
    assert repr(lineage(evolved)) == repr(lineage(evolved))


def test_two_stores_built_the_same_way_list_the_same(tmp_path: Path) -> None:
    """Equal input, equal output — the claim a golden file rests on. Nothing in the path reads
    a clock or a store's own mtimes; the timestamps are the ones the writer was given."""
    one = dump_lineage(lineage(evolved_store(tmp_path / "one")))
    two = dump_lineage(lineage(evolved_store(tmp_path / "two")))

    assert one == two


_ACROSS_RUNS = """\
import hashlib
import tempfile
from pathlib import Path

from gebra.lineage import dump_lineage, lineage
from tests.lineage.stores import awkward_store, evolved_store

text = "".join(
    dump_lineage(lineage(build(Path(tempfile.mkdtemp())), **window))
    for build in (evolved_store, awkward_store)
    for window in ({}, {"limit": 2}, {"limit": 0})
)
print(hashlib.sha256(text.encode("utf-8")).hexdigest())
"""


def test_lineage_text_is_one_document_across_interpreter_runs() -> None:
    """Four child interpreters under four ``PYTHONHASHSEED`` values list both stores in three
    windows each and must print one digest. A document assembled from mappings is exactly
    where dict iteration order could reach the output, so this is where "stable" is observable
    across runs rather than within one."""
    runs = {
        seed: subprocess.run(
            [sys.executable, "-c", _ACROSS_RUNS],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
            env={**os.environ, "PYTHONHASHSEED": seed},
        )
        for seed in ("0", "1", "777", "12345")
    }

    for seed, run in runs.items():
        assert run.returncode == 0, (seed, run.stderr)
    printed = {run.stdout.strip() for run in runs.values()}
    assert len(printed) == 1, runs
    assert len(next(iter(printed))) == len(hashlib.sha256().hexdigest())


# ── The projection's own version ─────────────────────────────────────────────────────────


def test_the_document_version_is_this_projections_and_no_other() -> None:
    """Three layouts, three version fields: ``ir_version`` for the IR format, ``store_version``
    for ``meta.yaml``, and this one for the projection — so none has to move when another
    does."""
    document = lineage_document(Lineage())

    assert document["lineage_version"] == LINEAGE_DOCUMENT_VERSION == "1.0"
    assert "ir_version" not in document and "store_version" not in document
