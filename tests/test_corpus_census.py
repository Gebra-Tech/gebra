"""The corpus census (``tests/_corpus.py``): what every corpus pin is held to, held itself.

Every test module that pins the fixture corpus — its size, its IR-block count, the obligations
the golden harness plans over it — reads the census rather than a literal, and the census is
derived from ``tools/provenance-manifest.json``, the record a sanctioned re-vendor moves in the
same commit as the bytes. Three things are held here so that the move cannot have weakened a
pin:

* **drift in either direction still fails.** On a copy of the corpus and its manifest under
  ``tmp_path``, a fixture file with no manifest entry and a manifest entry with no file are
  each refused by name, and a re-vendor that moves both together is followed rather than
  refused;
* **no literal count came back.** A token scan of every test module finds none of the three
  former literals (fixtures, IR blocks, obligations) outside a ``#`` comment;
* **the obligation count is not the harness's own.** The census module imports nothing from
  ``gebra.testing.harness``, and its count agrees with the harness's plan fixture by fixture,
  so the pins compare two derivations rather than one with itself.

Nothing here writes to the vendored corpus (WA-04/WA-11): every mutation is applied to a copy.
Nothing here executes a node, calls a model or opens a socket (WA-07): fixtures are read as
YAML data and test modules as tokens.
"""

from __future__ import annotations

import ast
import dataclasses
import hashlib
import io
import re
import shutil
import tokenize
from pathlib import Path

import pytest
import yaml

from gebra.testing import iter_fixture_paths, load_fixture
from gebra.testing.harness import plan_fixture
from tests._corpus import (
    CORPUS_RELATIVE,
    MANIFEST_RELATIVE,
    REPO_ROOT,
    CorpusDriftError,
    census,
    listed_fixture_ids,
    obligations_in,
    read_corpus,
)
from tests.conftest import FIXTURES_DIR
from tools.provenance_guard import Entry, load_manifest, write_manifest

TESTS_DIR = REPO_ROOT / "tests"
CENSUS_MODULE = TESTS_DIR / "_corpus.py"

#: A listed fixture the removal seed deletes from the copy.
REMOVED = "graph-well-formed/positive-01-linear-document-pipeline.yaml"

#: The corpus counts that used to be literals across the suite: fixtures, IR blocks and
#: harness obligations at the DEC-16 extension. Spelled as a pattern so this module does not
#: itself carry the literals it scans for.
_CORPUS_COUNT = re.compile(r"(?<![\w.])(?:7[18]|8[9])(?![\w.])")


def _copied_repository(tmp_path: Path) -> Path:
    """A throwaway repository root holding a copy of the corpus and of its manifest."""
    root = tmp_path / "repo"
    shutil.copytree(FIXTURES_DIR, root / CORPUS_RELATIVE)
    (root / MANIFEST_RELATIVE).parent.mkdir(parents=True)
    shutil.copy2(REPO_ROOT / MANIFEST_RELATIVE, root / MANIFEST_RELATIVE)
    return root


def _add_fixture(root: Path, fixture_id: str) -> Path:
    """Write a new fixture into the copied corpus, cloned from an existing one."""
    target = root / CORPUS_RELATIVE / fixture_id
    target.write_bytes((root / CORPUS_RELATIVE / REMOVED).read_bytes())
    return target


# ── The census on the repository as it stands ────────────────────────────────────────────


def test_the_vendored_census_reads_cleanly_and_is_the_manifest_set() -> None:
    expected = census()
    assert expected.fixtures > 0
    assert expected.fixture_ids == listed_fixture_ids()
    assert expected.ir_blocks == expected.single_snapshot + 2 * expected.pairs
    assert expected.obligations >= expected.fixtures


def test_the_census_names_exactly_what_the_loader_enumerates() -> None:
    loaded = {
        path.relative_to(FIXTURES_DIR).as_posix() for path in iter_fixture_paths(FIXTURES_DIR)
    }
    assert loaded == set(census().fixture_ids)


# ── Mutation: drift in either direction fails, a re-vendor is followed ───────────────────


def test_an_unlisted_extra_fixture_fails(tmp_path: Path) -> None:
    """A fixture file with no manifest entry: the census refuses the corpus, naming it."""
    root = _copied_repository(tmp_path)
    added = "graph-well-formed/positive-04-hand-added-not-vendored.yaml"
    _add_fixture(root, added)

    with pytest.raises(CorpusDriftError) as caught:
        read_corpus(root)
    assert caught.value.unlisted == (added,)
    assert caught.value.missing == ()
    assert f"unlisted (a fixture file with no manifest entry): {added}" in str(caught.value)


def test_a_listed_fixture_removed_fails(tmp_path: Path) -> None:
    """A manifest entry with no file: the census refuses the corpus, naming the entry."""
    root = _copied_repository(tmp_path)
    (root / CORPUS_RELATIVE / REMOVED).unlink()

    with pytest.raises(CorpusDriftError) as caught:
        read_corpus(root)
    assert caught.value.missing == (REMOVED,)
    assert caught.value.unlisted == ()
    assert f"missing (a manifest entry with no fixture file): {REMOVED}" in str(caught.value)


def test_a_drifted_corpus_fails_as_a_test_rather_than_erroring() -> None:
    """A pin reaching a drifted corpus reports a failure, not a collection or setup error."""
    assert issubclass(CorpusDriftError, AssertionError)


def test_a_re_vendor_that_moves_file_and_entry_together_is_followed(tmp_path: Path) -> None:
    """The point of the derivation: a sanctioned re-vendor needs no edit to the pins."""
    root = _copied_repository(tmp_path)
    added = "graph-well-formed/positive-04-re-vendored-arrival.yaml"
    target = _add_fixture(root, added)
    manifest_path = root / MANIFEST_RELATIVE
    manifest = load_manifest(manifest_path)
    entry = Entry(
        path=f"{CORPUS_RELATIVE}/{added}",
        sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
        vault_source=f"09-RnD-Docs/fixtures/properties/{added}",
        vault_commit="0000000",
    )
    write_manifest(dataclasses.replace(manifest, entries=(*manifest.entries, entry)), manifest_path)

    moved = read_corpus(root)
    before = census()
    assert set(moved.fixture_ids) == {*before.fixture_ids, added}
    assert moved.ir_blocks == before.ir_blocks + 1
    assert moved.obligations == before.obligations + 1
    assert moved.pairs == before.pairs


def test_the_mutations_left_the_vendored_corpus_alone() -> None:
    """Every seed above wrote to a copy: the real corpus still reads as its manifest."""
    assert read_corpus(REPO_ROOT) == census()


# ── No literal count came back ───────────────────────────────────────────────────────────


def _literal_counts(source: str) -> list[tuple[int, str]]:
    """Every corpus-count literal in a module's code or strings, as ``(line, token)``.

    Comments are the one exemption. Strings include docstrings and, on Python 3.12+, the
    literal parts of an f-string (``FSTRING_MIDDLE``); before 3.12 an f-string is one
    ``STRING`` token, so the same text is scanned either way.
    """
    string_kinds = {tokenize.STRING}
    fstring_middle = getattr(tokenize, "FSTRING_MIDDLE", None)
    if fstring_middle is not None:
        string_kinds.add(fstring_middle)
    hits: list[tuple[int, str]] = []
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type == tokenize.NUMBER:
            if _CORPUS_COUNT.fullmatch(token.string.replace("_", "")):
                hits.append((token.start[0], token.string))
        elif token.type in string_kinds and _CORPUS_COUNT.search(token.string):
            hits.append((token.start[0], token.string[:60]))
    return hits


def test_no_literal_corpus_count_remains_in_the_test_suite() -> None:
    """The corpus size, IR-block count and obligation count come from the census only.

    A ``#`` comment may still cite a historical figure (a ruling's arithmetic, say); code,
    strings and docstrings may not, because a docstring that states the size goes stale on
    the first re-vendor exactly as a literal assertion would fail on it.
    """
    modules = sorted(
        path
        for path in TESTS_DIR.rglob("*.py")
        if "__pycache__" not in path.parts and not path.is_relative_to(FIXTURES_DIR)
    )
    assert CENSUS_MODULE in modules
    hits = [
        f"{path.relative_to(REPO_ROOT).as_posix()}:{line}: {text}"
        for path in modules
        for line, text in _literal_counts(path.read_text(encoding="utf-8"))
    ]
    assert hits == [], "derive corpus counts from tests/_corpus.py:\n" + "\n".join(hits)


def test_the_scan_sees_a_literal_in_code_and_in_a_string_but_not_in_a_comment() -> None:
    """The scan is armed: code, a docstring and an f-string are reported; a comment and a
    version-shaped string are not."""
    count = "7" + "1"
    source = (
        f"# {count} fixtures at the DEC-16 extension\n"
        f"assert len(corpus) == {count}\n"
        f'"""All {count} fixtures load."""\n'
        f'message = f"{{n}} of {count} loaded"\n'
        '"12.34.56.78"\n'
    )
    assert [line for line, _ in _literal_counts(source)] == [2, 3, 4]


# ── The obligation count is not the harness's own ────────────────────────────────────────


def test_the_census_module_does_not_import_the_harness() -> None:
    """Statically: ``tests/_corpus.py`` reads no part of ``gebra.testing.harness``."""
    tree = ast.parse(CENSUS_MODULE.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.add(node.module)
            imported.update(f"{node.module}.{alias.name}" for alias in node.names)
    assert not [name for name in imported if "harness" in name], sorted(imported)


@pytest.mark.parametrize("fixture_id", listed_fixture_ids())
def test_the_independent_count_agrees_with_the_harness_plan(fixture_id: str) -> None:
    """Two derivations, fixture by fixture: the raw-YAML rule and ``plan_fixture``."""
    path = FIXTURES_DIR / fixture_id
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert obligations_in(document) == len(plan_fixture(load_fixture(path)))
