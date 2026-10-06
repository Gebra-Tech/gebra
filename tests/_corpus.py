"""The corpus census every pin is held to, derived from the provenance manifest.

The fixture corpus is vendored (WA-04/WA-11), and ``tools/provenance-manifest.json`` is the
record of exactly which files it holds — the provenance guard already holds every one of them
to its recorded bytes. Pinning the corpus size as a literal in each test module made every
sanctioned re-vendor an edit across the suite; deriving the census from that record makes a
re-vendor move one file (the manifest, in the re-vendor commit) and the pins follow.

Nothing is weakened by the move. :func:`read_corpus` compares the manifest's fixture entries
with the files on disk as a **set equality** and refuses either direction of drift — a fixture
file with no entry (*unlisted*) and an entry with no file (*missing*) — so the census can only
be read off a corpus the record accounts for exactly. The counts beyond the fixture set are
then read from the fixtures' own YAML with PyYAML's safe loader, never computed by
:mod:`gebra.testing.harness` or the fixture loader (only the loader's spelling constants are
borrowed): a pin that compared the harness with the harness's own arithmetic would be no pin
at all.

Reading only: nothing here writes, imports or executes anything a fixture names (WA-07).
"""

from __future__ import annotations

import functools
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import yaml

from gebra.testing.fixtures import FIXTURE_SUFFIX, IR_KEYS, SCHEMA_FILENAME
from gebra.verify import UnregisteredConditionError, property_for_condition
from tools.provenance_guard import load_manifest

REPO_ROOT: Final = Path(__file__).resolve().parents[1]

#: Where the corpus and its record sit, relative to a repository root — the real one, or a
#: copy assembled under ``tmp_path`` by a mutation test.
CORPUS_RELATIVE: Final = "tests/fixtures/properties"
MANIFEST_RELATIVE: Final = "tools/provenance-manifest.json"

#: A passing cross-property fixture's run-level witness (the PR-4 shape).
_MULTI_PROPERTY: Final = "multi-property"


class CorpusDriftError(AssertionError):
    """The fixture files on disk and the manifest's fixture entries are not the same set.

    An ``AssertionError`` so that a pin which reaches a drifted corpus fails as a test rather
    than erroring as one.
    """

    def __init__(self, unlisted: Sequence[str], missing: Sequence[str]) -> None:
        self.unlisted = tuple(unlisted)
        self.missing = tuple(missing)
        lines = ["the fixture corpus and tools/provenance-manifest.json disagree:"]
        lines += [f"  unlisted (a fixture file with no manifest entry): {p}" for p in unlisted]
        lines += [f"  missing (a manifest entry with no fixture file): {p}" for p in missing]
        super().__init__("\n".join(lines))


@dataclass(frozen=True)
class CorpusCensus:
    """What the vendored corpus is, as the manifest records it and the YAML spells it.

    Attributes:
        fixture_ids: Every fixture's ``"<directory>/<file>.yaml"`` id, sorted — the spelling
            :attr:`gebra.testing.PropertyFixture.fixture_id` uses.
        ir_blocks: How many IR payloads the fixtures carry (``ir``, or ``ir_before`` +
            ``ir_after``).
        pairs: How many fixtures carry the two-snapshot ``ir_before``/``ir_after`` shape.
        obligations: How many single-property obligations the fixtures' ``expected:`` blocks
            carry, by the golden harness's planning rule read independently of it (see
            :func:`obligations_in`).
    """

    fixture_ids: tuple[str, ...]
    ir_blocks: int
    pairs: int
    obligations: int

    @property
    def fixtures(self) -> int:
        """The corpus size."""
        return len(self.fixture_ids)

    @property
    def single_snapshot(self) -> int:
        """Fixtures carrying one ``ir`` block."""
        return self.fixtures - self.pairs


def is_fixture_path(relative: str) -> bool:
    """Whether a corpus-relative POSIX path names a fixture (the loader's rule, restated)."""
    name = relative.rsplit("/", 1)[-1]
    return name.endswith(FIXTURE_SUFFIX) and name != SCHEMA_FILENAME


def listed_fixture_ids(repo_root: Path = REPO_ROOT) -> tuple[str, ...]:
    """The fixture entries of ``tools/provenance-manifest.json``, as corpus-relative ids."""
    prefix = f"{CORPUS_RELATIVE}/"
    manifest = load_manifest(repo_root / MANIFEST_RELATIVE)
    return tuple(
        sorted(
            entry.path.removeprefix(prefix)
            for entry in manifest.entries
            if entry.path.startswith(prefix) and is_fixture_path(entry.path.removeprefix(prefix))
        )
    )


def fixture_ids_on_disk(repo_root: Path = REPO_ROOT) -> tuple[str, ...]:
    """Every fixture file under the corpus directory, as corpus-relative ids."""
    corpus = repo_root / CORPUS_RELATIVE
    return tuple(
        sorted(
            relative
            for path in corpus.rglob(f"*{FIXTURE_SUFFIX}")
            if path.is_file() and is_fixture_path(relative := path.relative_to(corpus).as_posix())
        )
    )


def read_corpus(repo_root: Path = REPO_ROOT) -> CorpusCensus:
    """The census of the corpus under ``repo_root``, refused unless the manifest accounts for it.

    Raises:
        CorpusDriftError: if a fixture file has no manifest entry or an entry has no file.
    """
    listed = listed_fixture_ids(repo_root)
    on_disk = fixture_ids_on_disk(repo_root)
    if set(listed) != set(on_disk):
        raise CorpusDriftError(
            unlisted=sorted(set(on_disk) - set(listed)),
            missing=sorted(set(listed) - set(on_disk)),
        )
    corpus = repo_root / CORPUS_RELATIVE
    documents = [_document(corpus / fixture_id) for fixture_id in listed]
    return CorpusCensus(
        fixture_ids=listed,
        ir_blocks=sum(1 for document in documents for key in IR_KEYS if key in document),
        pairs=sum(1 for document in documents if "ir_before" in document),
        obligations=sum(obligations_in(document) for document in documents),
    )


@functools.cache
def census() -> CorpusCensus:
    """The vendored corpus's census, read once per session."""
    return read_corpus(REPO_ROOT)


def obligations_in(document: Mapping[str, Any]) -> int:
    """How many single-property obligations one fixture's ``expected:`` block carries.

    The golden harness's planning rule (``gebra.testing.harness.plan_fixture``), restated over
    the raw document so that the harness's count is compared with something it did not
    compute: a single-property fixture carries one; a passing cross-property fixture with a
    run-level ``multi-property`` witness carries one per declared property (PR-4); a failing
    one whose primary condition the PROPERTY-CATALOG-SPEC §0.4 registry assigns to a declared
    property carries that owner's plus one per further declared property its
    ``co_failures``/``advisories`` records name (PR-1..PR-3); one whose owner cannot be
    derived carries one per declared property.
    """
    declared = _declared(document.get("property"))
    if len(declared) < 2:
        return 1
    expected = document.get("expected")
    expected = expected if isinstance(expected, Mapping) else {}
    witness = expected.get("witness")
    if isinstance(witness, Mapping) and witness.get("kind") == _MULTI_PROPERTY:
        return len(declared)
    failure = expected.get("failure")
    failure = failure if isinstance(failure, Mapping) else {}
    condition = failure.get("property_condition")
    try:
        owner = property_for_condition(condition) if isinstance(condition, str) else None
    except UnregisteredConditionError:
        owner = None
    if owner is None or owner not in declared:
        return len(declared)
    further = 0
    for key in ("co_failures", "advisories"):
        records = failure.get(key)
        named = {
            record.get("property")
            for record in (records if isinstance(records, list) else [])
            if isinstance(record, Mapping)
        }
        further += len({slug for slug in named if slug in declared and slug != owner})
    return 1 + further


def _declared(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,)
    if isinstance(value, list):
        return tuple(slug for slug in value if isinstance(slug, str))
    return ()


def _document(path: Path) -> Mapping[str, Any]:
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(document, Mapping), f"{path}: a fixture's top level is a mapping"
    return document
