"""The ``gebra.toml`` sidecar loader — ANNOTATION-API-SPEC §2.

Three claims, each with its own section below:

* **Discovery is ordered, bounded and singular.** §2's file discovery rule, tested as three
  separate properties rather than one: an explicit argument wins, the walk finds the *nearest*
  file and ends at the repository root, and exactly one file is ever read.
* **Validation is warning-grade, all of it.** Every fixture in
  :data:`~tests.sample_workflows.sentinel_sidecars.SIDECAR_FIXTURES` is loaded and its exact
  outcome asserted — which rules fire, in which order, and which entries survive. §2 says the
  sidecar surface has no errors, so the parametrized test that asserts "nothing raised" runs
  over every fixture rather than a chosen few.
* **Keying is the escaped node id, byte-for-byte.** Multi-segment quoted keys, ``%2F``/``%25``
  escapes, and the NFC/NFD pair.

Plus the WA-07 tripwire for this path, and the value-identity test that holds the sidecar and
the decorator to producing the *same* carrier — the property §3's "identical values are not a
conflict" rule is decided by.

Nothing here imports langgraph or opens a socket; the loader reads exactly one file per call.
"""

from __future__ import annotations

import subprocess
import sys
import unicodedata
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

import gebra
from gebra.annotations import (
    SIDECAR_FILENAME,
    SIDECAR_SCHEMA,
    SLOT_KEYWORDS,
    NodeContract,
    SidecarReading,
    SidecarRule,
    SidecarSource,
    discover_sidecar,
    read_sidecar,
    repository_root,
)
from gebra.ir.models import Compensation, DeterministicSpec, IdempotentKey, Variant
from tests.sample_workflows import sentinel_sidecars as ss

if TYPE_CHECKING:
    from gebra.annotations.sidecar import SidecarIssue

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def checkout(tmp_path: Path) -> Path:
    """A directory that looks like a repository root, with a nested working directory.

    Every discovery test needs a bounded walk: without a ``.git`` marker the walk would leave
    ``tmp_path`` and climb into the real filesystem, where what it finds is not the test's to
    decide. The marker makes each of these tests a statement about a tree the test built.
    """
    (tmp_path / ".git").mkdir()
    nested = tmp_path / "services" / "booking"
    nested.mkdir(parents=True)
    return tmp_path


def rules(reading: SidecarReading) -> tuple[str, ...]:
    """The rule of every issue on ``reading``, in order — what the fixtures declare."""
    return tuple(issue.rule.value for issue in reading.issues)


# ── §2 discovery rule 1: an explicit argument wins ───────────────────────────────────────


def test_an_explicit_path_wins_over_a_discoverable_one(checkout: Path) -> None:
    """§2 rule 1: "an explicit ``gebra.extract(workflow, sidecar=<path>)`` argument wins"."""
    ss.write_sidecar(checkout, ss.SIDECAR_FIXTURES["nine_slots"].text)
    explicit = ss.write_sidecar(
        checkout, ss.SIDECAR_FIXTURES["multi_segment_key"].text, name="elsewhere.toml"
    )

    reading = read_sidecar(explicit, start=checkout)

    assert reading.source is SidecarSource.EXPLICIT
    assert reading.path == explicit.resolve()
    assert list(reading.entries) == ["research/tools/web_search"]


def test_an_unreadable_explicit_path_does_not_fall_back_to_the_walk(checkout: Path) -> None:
    """Rule 1 wins even when it loses: the walk is not a second chance.

    Falling back would silently substitute a *different* file for the one the caller named,
    and sidecar-filled annotations sit inside the ``graph_version`` hash scope (§2) — so the
    fallback would move a digest without anything saying it had. The reading comes back
    sidecar-less with the file named, which is §2's own repair for a file it will not load.
    """
    ss.write_sidecar(checkout, ss.SIDECAR_FIXTURES["nine_slots"].text)

    reading = read_sidecar(checkout / "typo.toml", start=checkout)

    assert reading.path is None
    assert reading.entries == {}
    assert rules(reading) == (SidecarRule.FILE_UNREADABLE.value,)
    assert reading.issues[0].detail["file"] == str((checkout / "typo.toml").resolve())


def test_a_directory_named_as_the_explicit_path_is_a_warning_not_a_crash(checkout: Path) -> None:
    """A path that exists but is not a file takes the same warning-grade route (§2)."""
    reading = read_sidecar(checkout / "services", start=checkout)

    assert reading.path is None
    assert rules(reading) == (SidecarRule.FILE_UNREADABLE.value,)


# ── §2 discovery rule 2: the nearest file, walking to the repository root ─────────────────


def test_the_walk_finds_the_nearest_file(checkout: Path) -> None:
    """ "the nearest ``gebra.toml`` found walking up … first found governs" (§2)."""
    ss.write_sidecar(checkout, ss.SIDECAR_FIXTURES["nine_slots"].text)
    nearest = ss.write_sidecar(checkout / "services", ss.SIDECAR_FIXTURES["multi_segment_key"].text)

    assert discover_sidecar(checkout / "services" / "booking") == nearest.resolve()


def test_exactly_one_file_is_read_and_nothing_is_merged(checkout: Path) -> None:
    """§2: "exactly **one** sidecar file per extraction, never merged across directories".

    Both files declare an entry, and only the nearer one's entry is present — a merge would
    show up as two. The far file's entry is the one a merge would be *most* tempting for,
    since it names a node the near file says nothing about.
    """
    ss.write_sidecar(checkout, ss.SIDECAR_FIXTURES["nine_slots"].text)
    ss.write_sidecar(checkout / "services", ss.SIDECAR_FIXTURES["multi_segment_key"].text)

    reading = read_sidecar(start=checkout / "services" / "booking")

    assert list(reading.entries) == ["research/tools/web_search"]
    assert "plan_step" not in reading.entries


def test_the_walk_ends_at_the_repository_root(tmp_path: Path) -> None:
    """The repo root is searched and then the walk stops — a sidecar above it never governs.

    §2 defines the root as "the nearest ancestor directory containing a ``.git`` entry" and
    ends the walk there. A checkout that sat inside another project would otherwise inherit
    that project's contract declarations, silently, on a digest-affecting surface.
    """
    outer = tmp_path / "outer"
    inner = outer / "checkout"
    inner.mkdir(parents=True)
    (inner / ".git").mkdir()
    ss.write_sidecar(outer, ss.SIDECAR_FIXTURES["nine_slots"].text)

    assert discover_sidecar(inner) is None


def test_the_repository_root_is_searched_before_the_walk_stops(tmp_path: Path) -> None:
    """ "to the repository root" is inclusive — the root is where a sidecar usually lives."""
    (tmp_path / ".git").mkdir()
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)
    root_sidecar = ss.write_sidecar(tmp_path, ss.SIDECAR_FIXTURES["nine_slots"].text)

    assert discover_sidecar(nested) == root_sidecar.resolve()


def test_with_no_repository_root_the_walk_runs_to_the_filesystem_root(tmp_path: Path) -> None:
    """ "when no repository root exists, the walk ends at the filesystem root" (§2).

    Asserted the way it can be: with no ``.git`` anywhere below ``tmp_path``, a sidecar four
    levels up is still found — so nothing shorter than the filesystem root ends the walk.
    """
    deep = tmp_path / "a" / "b" / "c" / "d"
    deep.mkdir(parents=True)
    far = ss.write_sidecar(tmp_path, ss.SIDECAR_FIXTURES["nine_slots"].text)

    assert discover_sidecar(deep) == far.resolve()


def test_nothing_found_is_an_empty_reading_and_not_an_issue(checkout: Path) -> None:
    """No sidecar is the ordinary case: absence is recorded, never warned about."""
    reading = read_sidecar(start=checkout / "services" / "booking")

    assert reading == SidecarReading()
    assert reading.source is SidecarSource.ABSENT
    assert reading.path is None
    assert reading.issues == ()


def test_the_walk_starts_at_the_current_working_directory(
    checkout: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§2 fixes the walk's start at the CWD, which is what makes discovery CWD-sensitive."""
    ss.write_sidecar(checkout / "services", ss.SIDECAR_FIXTURES["nine_slots"].text)

    monkeypatch.chdir(checkout / "services" / "booking")
    assert discover_sidecar() == (checkout / "services" / "gebra.toml").resolve()

    monkeypatch.chdir(checkout)
    assert discover_sidecar() is None


@pytest.mark.parametrize("marker", ["directory", "file"], ids=["worktree", "linked-worktree"])
def test_a_git_entry_of_either_kind_marks_the_root(tmp_path: Path, marker: str) -> None:
    """§2 says "a ``.git`` **entry**" — a linked worktree and a submodule carry a file."""
    root = tmp_path / "checkout"
    root.mkdir()
    if marker == "directory":
        (root / ".git").mkdir()
    else:
        (root / ".git").write_text("gitdir: ../.git/worktrees/checkout\n", encoding="utf-8")

    assert repository_root(root) == root.resolve()


def test_a_dangling_git_symlink_still_ends_the_walk(tmp_path: Path) -> None:
    """The entry is there, which is what §2's test asks — following it is not the question.

    Treating a broken link as absent would walk *out* of the checkout it marks, which is the
    direction that silently widens a digest-affecting lookup.
    """
    root = tmp_path / "checkout"
    root.mkdir()
    (root / ".git").symlink_to(tmp_path / "nowhere")

    assert repository_root(root) == root.resolve()
    assert discover_sidecar(root) is None


def test_repository_root_is_none_outside_any_checkout(tmp_path: Path) -> None:
    """No ``.git`` above ``tmp_path`` — the honest answer is ``None``, not the filesystem root."""
    assert repository_root(tmp_path) is None


def test_the_walk_stops_when_it_runs_out_of_directories(tmp_path: Path) -> None:
    """The other end of "the walk ends at the filesystem root": it *ends*, and returns ``None``.

    The precondition is asserted rather than assumed — on a machine that really did keep a
    ``gebra.toml`` or a repository at ``/``, the walk would (correctly) find it, and this test
    would be making a claim about that machine rather than about the code.
    """
    root = Path(tmp_path.anchor)
    if (root / SIDECAR_FILENAME).exists() or (root / ".git").exists():
        pytest.skip("this machine carries a sidecar or a repository at the filesystem root")

    assert discover_sidecar(root) is None


# ── §2 keying: the escaped node id, byte-for-byte ────────────────────────────────────────


@pytest.mark.parametrize(
    ("fixture", "key"),
    [
        ("multi_segment_key", "research/tools/web_search"),
        ("escaped_separator_key", "summarize%2Fmerge"),
        ("escaped_marker_key", "100%25_certain"),
        ("nfc_key", ss.NFC_KEY),
        ("expression_shaped_key", "__import__('os').system('echo tripped')"),
    ],
)
def test_an_entry_key_is_carried_verbatim(tmp_path: Path, fixture: str, key: str) -> None:
    """§2: "the table key is the node id **byte-for-byte in its escaped form**".

    Nothing is escaped or unescaped on the way in — "TOML quoting is orthogonal to
    percent-escaping — quote, never double-escape". A loader that unescaped ``%2F`` here
    would produce a key that could never equal an extracted node id, since extraction escapes
    on the way out (IR-SPEC §5.1); one that escaped again would turn ``%2F`` into ``%252F``.
    """
    path = ss.write_sidecar(tmp_path, ss.SIDECAR_FIXTURES[fixture].text)

    reading = read_sidecar(path)

    assert list(reading.entries) == [key]


def test_a_multi_segment_key_resolves_against_a_matching_node_id(tmp_path: Path) -> None:
    """The keying rule's whole purpose: an id built by §5.1 finds its entry, and only it."""
    from gebra.ir.identity import node_id_from_names

    path = ss.write_sidecar(tmp_path, ss.SIDECAR_FIXTURES["multi_segment_key"].text)
    reading = read_sidecar(path)
    built = node_id_from_names(["research", "tools", "web_search"])

    assert built in reading.entries
    assert reading.unmatched_keys(frozenset({built})) == ()
    assert reading.unmatched_keys(frozenset({"research"})) == (built,)


def test_a_literal_slash_in_a_source_name_matches_its_escaped_key(tmp_path: Path) -> None:
    """§2's third example: "a literal ``/`` in a source name arrives already percent-escaped"."""
    from gebra.ir.identity import node_id_from_names

    path = ss.write_sidecar(tmp_path, ss.SIDECAR_FIXTURES["escaped_separator_key"].text)
    reading = read_sidecar(path)

    assert node_id_from_names(["summarize/merge"]) == "summarize%2Fmerge"
    assert reading.unmatched_keys(frozenset({"summarize%2Fmerge"})) == ()


def test_the_nfd_spelling_of_a_key_is_refused_rather_than_normalized(tmp_path: Path) -> None:
    """Keys are compared as bytes, so normalizing one here would hide the mismatch.

    §5.1 puts NFC *before* escaping and makes byte equality the sound comparison that follows
    from it. A loader that quietly normalized an NFD key would make the file's bytes and the
    matched node's bytes differ while the match succeeded — and the author would never learn
    that the file says something other than what it appears to.
    """
    assert not unicodedata.is_normalized("NFC", ss.NFD_KEY)
    path = ss.write_sidecar(tmp_path, ss.SIDECAR_FIXTURES["nfd_key"].text)

    reading = read_sidecar(path)

    assert reading.entries == {}
    assert rules(reading) == (SidecarRule.ENTRY_KEY_NOT_A_NODE_ID.value,)
    assert reading.issues[0].detail["reason"] == "not-nfc"


def test_matching_is_case_sensitive(tmp_path: Path) -> None:
    """§2: "Matching is exact byte equality of the escaped form, case-sensitive"."""
    path = ss.write_sidecar(tmp_path, f"{ss.SCHEMA_LINE}\n[nodes.Plan_Step]\npure = true\n")

    reading = read_sidecar(path)

    assert reading.unmatched_keys(frozenset({"plan_step"})) == ("Plan_Step",)
    assert reading.unmatched_keys(frozenset({"Plan_Step"})) == ()


# ── §2 validation: every rule, at warning grade ──────────────────────────────────────────


@pytest.mark.parametrize("name", sorted(ss.SIDECAR_FIXTURES))
def test_every_fixture_reads_to_its_declared_outcome(tmp_path: Path, name: str) -> None:
    """The whole §2 validation table, one fixture at a time, asserted exactly.

    "Exactly" matters more than it usually would: §2's repair for a violated rule is that the
    slot (or the key, or the file) is *dropped*, and a test that only checked "some warning
    appeared" would pass on a loader that dropped more than the rule asks it to. So the
    fixtures declare their rules **in order** and their surviving entry keys, and both are
    compared as sequences.
    """
    fixture = ss.SIDECAR_FIXTURES[name]
    path = ss.write_sidecar(tmp_path, fixture.text)

    reading = read_sidecar(path)

    assert reading.loaded is fixture.loaded
    assert reading.path == (path.resolve() if fixture.loaded else None)
    assert rules(reading) == fixture.rules
    assert tuple(reading.entries) == fixture.entries


@pytest.mark.parametrize("name", sorted(ss.SIDECAR_FIXTURES))
def test_no_fixture_raises(tmp_path: Path, name: str) -> None:
    """§2: the sidecar surface has no errors — "import-time errors live on the decorator
    surface only". The claim is only worth as much as the set it is quantified over, so it is
    quantified over all of them, malformed files included."""
    path = ss.write_sidecar(tmp_path, ss.SIDECAR_FIXTURES[name].text)

    assert read_sidecar(path) is not None


@pytest.mark.parametrize("name", sorted(ss.SIDECAR_FIXTURES))
def test_every_issue_carries_the_fields_its_registry_row_names(tmp_path: Path, name: str) -> None:
    """§2: ``annotation-invalid`` "carries scope (file / node id), slot(s), value(s), and the
    violated rule — structured fields, never a bare string"; §4's registry adds the surface.

    Checked on every issue of every fixture, because the conversion into an
    ``ExtractionWarning`` copies these fields rather than deriving them: a missing one would
    surface as a warning that says nothing, not as a failure.
    """
    path = ss.write_sidecar(tmp_path, ss.SIDECAR_FIXTURES[name].text)

    for issue in read_sidecar(path).issues:
        assert issue.message.strip()
        assert issue.detail["surface"] == "sidecar"
        assert issue.detail["rule"] == issue.rule.value
        assert issue.detail["file"] == str(path.resolve())
        if issue.detail["scope"] == "node":
            assert issue.node is not None
        else:
            assert issue.detail["scope"] == "file"
            assert issue.node is None


def test_a_file_in_the_wrong_encoding_is_a_warning_not_a_crash(tmp_path: Path) -> None:
    """TOML is UTF-8 by definition, and the parser decodes *before* it parses.

    Worth its own test because the failure arrives as a ``UnicodeDecodeError`` rather than
    the ``TOMLDecodeError`` a reader expects — a loader that caught only the latter would let
    a file saved as latin-1 propagate an exception out of ``extract()``, which is exactly the
    totality §2 promises. The fixture is a real one: ``café`` in latin-1 is not valid UTF-8.
    """
    path = tmp_path / "gebra.toml"
    path.write_bytes('schema = "gebra-sidecar-v1"\n# café\n'.encode("latin-1"))

    reading = read_sidecar(path)

    assert reading.path is None
    assert rules(reading) == (SidecarRule.FILE_UNPARSABLE.value,)


def test_a_pathologically_nested_document_is_a_warning_not_a_crash(tmp_path: Path) -> None:
    """The third pre-parse failure: the TOML parser recurses, so nesting can exhaust the stack.

    A sidecar is a file someone else may have written — a generated one, a merged one, a
    hostile one — and "extraction stays total" has to hold for all of them. ``RecursionError``
    inherits from ``RuntimeError``, not ``ValueError``, so it sits outside both parse-failure
    branches a reader would write.
    """
    nesting = 2000
    path = ss.write_sidecar(
        tmp_path,
        f"{ss.SCHEMA_LINE}\n[nodes.plan_step]\nargs_schema = {{ x = "
        + "[" * nesting
        + "]" * nesting
        + " }\n",
    )

    reading = read_sidecar(path)

    assert reading.path is None
    assert rules(reading) == (SidecarRule.FILE_UNPARSABLE.value,)


def test_a_file_that_cannot_be_opened_is_a_warning_not_a_crash(tmp_path: Path) -> None:
    """A regular file the process may not read: the last way ``open`` itself can fail.

    The ``is_file()`` gate ahead of it turns away the shapes that would *block* rather than
    fail, so what reaches the ``open`` is a real file — and a real file can still be
    unreadable. §2's grade covers this the same way it covers the rest.
    """
    path = ss.write_sidecar(tmp_path, ss.SIDECAR_FIXTURES["nine_slots"].text)
    path.chmod(0o000)
    try:
        if path.is_file() and _is_readable(path):
            pytest.skip("this process can read a mode-000 file (running as root?)")

        reading = read_sidecar(path)
    finally:
        path.chmod(0o600)

    assert reading.path is None
    assert rules(reading) == (SidecarRule.FILE_UNREADABLE.value,)


def _is_readable(path: Path) -> bool:
    """Whether this process can open ``path`` — asked so the test above can skip honestly."""
    try:
        with path.open("rb"):
            return True
    except OSError:
        return False


def test_a_walk_that_cannot_start_finds_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§2's walk begins at the CWD, and a CWD can stop existing while a process runs.

    "Nothing discoverable" is the only honest answer — a walk that cannot start has found
    nothing — and it is the answer that keeps the surface total. An exception here would come
    out of ``extract()`` with no mention of a sidecar at all.
    """
    gone = tmp_path / "gone"
    gone.mkdir()
    monkeypatch.chdir(gone)
    gone.rmdir()
    try:
        Path.cwd()
    except OSError:
        pass
    else:  # pragma: no cover - platform-dependent; some keep a deleted CWD usable
        pytest.skip("this platform still answers for a deleted working directory")

    assert discover_sidecar() is None


def test_a_path_the_system_cannot_express_is_a_warning_not_a_crash() -> None:
    """The other pre-parse failure: a path with an embedded NUL cannot even be resolved.

    ``Path.resolve()`` raises ``ValueError`` for it rather than ``OSError``, so it sits
    outside the branch a reader would write first — and an uncaught one would come out of
    ``extract()`` as a bare ``ValueError`` with no mention of the sidecar at all.
    """
    reading = read_sidecar("gebra\x00.toml")

    assert reading.path is None
    assert rules(reading) == (SidecarRule.FILE_UNREADABLE.value,)


def test_the_schema_issue_names_the_file_and_the_value_found(tmp_path: Path) -> None:
    """§2 bullet 1: "an ``annotation-invalid`` warning naming the file and the schema value
    found" — both, because "no schema" and "the wrong schema" are different mistakes."""
    wrong = ss.write_sidecar(tmp_path, ss.SIDECAR_FIXTURES["wrong_schema"].text)
    missing = ss.write_sidecar(tmp_path / "sub", ss.SIDECAR_FIXTURES["no_schema"].text)

    (found,) = read_sidecar(wrong).issues
    (absent,) = read_sidecar(missing).issues

    assert found.detail == {
        "scope": "file",
        "surface": "sidecar",
        "file": str(wrong.resolve()),
        "rule": "schema-unknown",
        "schema": "gebra-sidecar-v2",
    }
    assert absent.detail["schema"] is None
    assert SIDECAR_SCHEMA in found.message


def test_a_rejected_effect_tag_drops_the_tag_and_keeps_the_entry(tmp_path: Path) -> None:
    """§2 bullet 3 rejects **the tag**, not the slot and not the entry."""
    path = ss.write_sidecar(tmp_path, ss.SIDECAR_FIXTURES["unknown_effect_tag"].text)

    reading = read_sidecar(path)
    (issue,) = reading.issues

    assert reading.entries["plan_step"].effect == ("network",)
    assert issue.slots == ("effect",)
    assert issue.detail["rejected"] == ("teleport",)
    assert issue.detail["kept"] == ("network",)


def test_when_every_tag_is_rejected_the_slot_is_left_unset(tmp_path: Path) -> None:
    """The judgement §2 leaves open, pinned: no surviving tag means **no declaration**.

    Under §3 "Set means not-``None``", an ``effect: []`` is a declaration — "this node has no
    effects" — which would both assert something the author never wrote and block the lower
    precedence tiers from filling the slot. A literally-authored ``effects = []`` is a
    different thing, and the next test is the pair to this one.
    """
    path = ss.write_sidecar(tmp_path, ss.SIDECAR_FIXTURES["every_effect_tag_unknown"].text)

    reading = read_sidecar(path)

    assert reading.entries["plan_step"].effect is None
    assert reading.entries["plan_step"].declared_slots() == ()
    assert reading.issues[0].detail["slot_declared"] is False


def test_an_authored_empty_effect_list_is_a_declaration(tmp_path: Path) -> None:
    """The pair to the test above: ``effects = []`` is what the author wrote, so it stands."""
    path = ss.write_sidecar(tmp_path, ss.SIDECAR_FIXTURES["empty_effects_is_a_declaration"].text)

    contract = read_sidecar(path).entries["act_step"]

    assert contract.effect == ()
    assert contract.declared_slots() == ("effect",)


def test_pure_with_effects_rejects_both_slots(tmp_path: Path) -> None:
    """§2 bullet 4: "**both** slots rejected (the loader has no basis to prefer one)"."""
    path = ss.write_sidecar(tmp_path, ss.SIDECAR_FIXTURES["pure_with_effects"].text)

    reading = read_sidecar(path)
    (issue,) = reading.issues

    assert reading.entries["plan_step"].declared_slots() == ()
    assert sorted(issue.slots) == ["effect", "pure"]
    assert issue.detail["effect"] == ("network",)


def test_pure_with_an_empty_effect_list_is_not_a_conflict(tmp_path: Path) -> None:
    """D-011 exclusivity is against a **non-empty** ``effects`` (§2), and both slots survive."""
    path = ss.write_sidecar(
        tmp_path, f"{ss.SCHEMA_LINE}\n[nodes.plan_step]\npure = true\neffects = []\n"
    )

    contract = read_sidecar(path).entries["plan_step"]

    assert contract.pure is True
    assert contract.effect == ()


def test_a_deterministic_object_without_seed_rejects_the_slot(tmp_path: Path) -> None:
    """§2 bullet 5, with its own rule code so "each rule degrades" is checkable per rule."""
    path = ss.write_sidecar(tmp_path, ss.SIDECAR_FIXTURES["deterministic_without_seed"].text)

    reading = read_sidecar(path)
    (issue,) = reading.issues

    assert reading.entries["plan_step"].deterministic is None
    assert issue.rule is SidecarRule.DETERMINISTIC_SEED_REQUIRED
    assert issue.detail["reason"] == "deterministic-seed-required"


def test_a_rejected_slot_leaves_the_others_standing(tmp_path: Path) -> None:
    """Rejection is per slot: §2's repair is that the slot is unset, not that the entry is."""
    path = ss.write_sidecar(
        tmp_path,
        f'{ss.SCHEMA_LINE}\n[nodes.plan_step]\nreads = "budget"\nwrites = ["plan"]\n',
    )

    reading = read_sidecar(path)

    assert reading.entries["plan_step"].input is None
    assert reading.entries["plan_step"].output == ("plan",)
    assert rules(reading) == (SidecarRule.SLOT_VALUE_INVALID.value,)


def test_an_unknown_slot_key_names_the_nine(tmp_path: Path) -> None:
    """§2 bullet 2, "typos included" — and the message says what the nine are."""
    path = ss.write_sidecar(tmp_path, ss.SIDECAR_FIXTURES["unknown_slot_key"].text)

    (issue,) = read_sidecar(path).issues

    assert issue.node == "plan_step"
    assert issue.detail["key"] == "retry_policy"
    assert issue.detail["slot_keywords"] == tuple(SLOT_KEYWORDS)
    assert len(SLOT_KEYWORDS) == 9


def test_the_ir_spelling_of_a_slot_is_not_an_accepted_key(tmp_path: Path) -> None:
    """§2 writes ``reads``/``writes``/``effects`` in its own example, and §1 shares the set
    "byte-for-byte" — so a slot has one spelling on both declaration surfaces, and ``input``
    is refused here exactly as ``@gebra.contract(input=…)`` is refused there."""
    path = ss.write_sidecar(tmp_path, ss.SIDECAR_FIXTURES["ir_spelled_slot_key"].text)

    reading = read_sidecar(path)

    assert reading.entries["plan_step"].input is None
    assert rules(reading) == (SidecarRule.SLOT_KEY_UNKNOWN.value,)


def test_a_toml_only_value_kind_is_named_by_type_never_rendered_as_data(tmp_path: Path) -> None:
    """TOML has dates; JSON does not — so the warning names the type instead of the value.

    A warning is reported (INTROSPECTION §8), and a ``detail`` holding a ``datetime.date``
    could not be. Naming the type is also the only reading that does not run anything: a
    ``str()`` of a foreign value is exactly the hazard the never-invokes tripwires exist for.
    """
    path = ss.write_sidecar(tmp_path, ss.SIDECAR_FIXTURES["date_valued_unknown_key"].text)

    (issue,) = read_sidecar(path).issues

    assert issue.detail["key"] == "released_on"
    assert all(
        isinstance(value, (str, int, float, bool, tuple, type(None)))
        for value in issue.detail.values()
    )


def test_a_non_finite_temperature_is_refused_on_both_surfaces(tmp_path: Path) -> None:
    """TOML has a literal ``nan``; JSON has no form for one, and the slot is digested.

    Left through, it would surface as a ``CanonicalizationError`` at ``graph_version()``
    time — extraction total in name only. The decorator surface raises on the same value and
    the sidecar warns, which is the one difference §2 draws between the two.
    """
    path = ss.write_sidecar(tmp_path, ss.SIDECAR_FIXTURES["non_finite_temperature"].text)

    reading = read_sidecar(path)

    assert reading.entries["plan_step"].deterministic is None
    assert rules(reading) == (SidecarRule.SLOT_VALUE_INVALID.value,)
    with pytest.raises(gebra.GebraContractError):
        gebra.deterministic(seed=1, temperature=float("inf"))


def test_an_out_of_range_integer_is_refused_on_both_surfaces(tmp_path: Path) -> None:
    """The twin of the non-finite float, and refused for the same §6.3 reason.

    TOML integers are 64-bit, so a ``seed`` past ±(2**53−1) is an ordinary thing to write and
    an impossible thing to digest: IR-SPEC §6.3 bounds the canonical form at the I-JSON exact
    range, and a value outside it can never be valid IR. Carried through, it would reach the
    §3 resolution and then raise a ``CanonicalizationError`` at ``graph_version()`` time —
    which is the one shape ANNOTATION §2's totality promise cannot survive, since the
    extraction would look total and the digest would be unobtainable. The largest exact seed
    is kept, so the bound is tested from both sides rather than assumed.
    """
    rejected = ss.write_sidecar(tmp_path, ss.SIDECAR_FIXTURES["out_of_range_seed"].text)
    accepted = ss.write_sidecar(tmp_path / "ok", ss.SIDECAR_FIXTURES["largest_exact_seed"].text)

    assert read_sidecar(rejected).entries["act_step"].deterministic is None
    assert rules(read_sidecar(rejected)) == (SidecarRule.SLOT_VALUE_INVALID.value,)
    assert read_sidecar(accepted).entries["act_step"] == NodeContract(
        deterministic=DeterministicSpec(seed=9007199254740991)
    )
    with pytest.raises(gebra.GebraContractError):
        gebra.deterministic(seed=2**53)
    with pytest.raises(gebra.GebraContractError):
        gebra.contract(args_schema={"maximum": 2**53})


# ── The values themselves ────────────────────────────────────────────────────────────────


def test_the_nine_slots_load_into_the_carrier_the_decorator_builds(tmp_path: Path) -> None:
    """§3's value identity is byte-equality of canonicalizations — so the carriers must match.

    This is the test EX-08's pre-review asked for by name: a TOML ``temperature = 0`` and a
    decorator ``temperature=0.0`` have to become one value, or §3's "identical values are not
    a conflict" rule would report a conflict between two spellings of the same declaration.
    Asserting the whole :class:`NodeContract` rather than that one slot is what keeps the
    other eight from drifting apart later — there is one normalization path
    (``normalize_declared_value``), and this is what says so.
    """
    path = ss.write_sidecar(tmp_path, ss.SIDECAR_FIXTURES["nine_slots"].text)

    @gebra.contract(
        reads=["query", "budget"],
        writes=["plan"],
        effects=["network", "billable"],
        pure=False,
        idempotent={"key": "plan"},
        deterministic={"seed": 7, "temperature": 0.0},
        args_schema={
            "type": "object",
            "required": ["query"],
            "properties": {"query": {"type": "string"}},
        },
    )
    @gebra.variant(key="remaining", measure="len")
    @gebra.compensation(hook="act_step")
    def plan_step(state: dict[str, object]) -> dict[str, object]:
        raise AssertionError("never called")

    from gebra.annotations import read_contract

    declared = read_contract(plan_step)
    loaded = read_sidecar(path).entries["plan_step"]

    assert loaded == declared
    assert loaded.declared_slots() == tuple(SLOT_KEYWORDS.values())


@pytest.mark.parametrize(
    ("keyword", "authored", "carried"),
    [
        ("reads", ["query", "budget"], ("query", "budget")),
        ("writes", ["plan"], ("plan",)),
        ("effects", ["network", "billable"], ("network", "billable")),
        ("pure", True, True),
        ("idempotent", {"key": "plan"}, IdempotentKey(key="plan")),
        (
            "deterministic",
            {"seed": 7, "temperature": 0},
            DeterministicSpec(seed=7, temperature=0.0),
        ),
        ("args_schema", {"type": "object"}, {"type": "object"}),
        ("variant", {"key": "n", "measure": "len"}, Variant(key="n", measure="len")),
        ("compensation", {"hook": "act_step"}, Compensation(hook="act_step")),
    ],
)
def test_the_normalization_seam_is_total_over_the_nine(
    keyword: str, authored: object, carried: object
) -> None:
    """One normalization path, exercised directly over every slot it is meant to be total on.

    ``normalize_declared_value`` is what makes "the decorator (§1) and sidecar (§2) share the
    set byte-for-byte" true of the *values* and not only of the names, so it is worth a test
    of its own rather than only being reached through one of the two surfaces — otherwise a
    keyword no caller happens to route through it could rot unnoticed. The ``temperature``
    row is the one EX-08's pre-review named: an authored ``0`` and an authored ``0.0`` have to
    become the same value, or §3's "identical values are not a conflict" rule reports a
    conflict between two spellings of one declaration.
    """
    from gebra.annotations.contract import normalize_declared_value

    assert normalize_declared_value(keyword, authored) == carried
    assert set(SLOT_KEYWORDS) == {
        "reads",
        "writes",
        "effects",
        "pure",
        "idempotent",
        "deterministic",
        "args_schema",
        "variant",
        "compensation",
    }


def test_each_slot_lands_in_its_ir_shape(tmp_path: Path) -> None:
    """The carrier speaks IR slot names and IR sub-models, as §3's chain and §5's lookup do."""
    path = ss.write_sidecar(tmp_path, ss.SIDECAR_FIXTURES["nine_slots"].text)

    contract = read_sidecar(path).entries["plan_step"]

    assert contract.input == ("query", "budget")
    assert contract.output == ("plan",)
    assert contract.effect == ("network", "billable")
    assert contract.pure is False
    assert contract.idempotent == IdempotentKey(key="plan")
    assert contract.deterministic == DeterministicSpec(seed=7, temperature=0.0)
    assert contract.variant == Variant(key="remaining", measure="len")
    assert contract.compensation == Compensation(hook="act_step")
    assert contract.args_schema == {
        "type": "object",
        "required": ("query",),
        "properties": {"query": {"type": "string"}},
    }


def test_an_explicit_false_occupies_its_slot(tmp_path: Path) -> None:
    """§3's "Set means not-``None``": ``pure = false`` is a declaration, not an absence."""
    path = ss.write_sidecar(tmp_path, f"{ss.SCHEMA_LINE}\n[nodes.plan_step]\npure = false\n")

    contract = read_sidecar(path).entries["plan_step"]

    assert contract.pure is False
    assert contract.declared_slots() == ("pure",)


def test_an_entry_whose_every_slot_was_rejected_keeps_its_key(tmp_path: Path) -> None:
    """The key is what §2's unmatched-key rule is about, so a bad value must not hide a
    stale key behind it — the author would fix the value and then meet the rename."""
    path = ss.write_sidecar(tmp_path, ss.SIDECAR_FIXTURES["non_boolean_pure"].text)

    reading = read_sidecar(path)

    assert list(reading.entries) == ["plan_step"]
    assert reading.entries["plan_step"] == NodeContract()


def test_the_loader_reads_the_file_once_and_the_reading_is_a_value(tmp_path: Path) -> None:
    """Two readings of one unchanged file compare equal — no wall-clock, no identity."""
    path = ss.write_sidecar(tmp_path, ss.SIDECAR_FIXTURES["nine_slots"].text)

    assert read_sidecar(path) == read_sidecar(path)


def test_the_accepted_schema_value_is_the_one_the_spec_writes() -> None:
    """Pinned against the spec's own literal rather than against the code that reads it."""
    assert SIDECAR_SCHEMA == "gebra-sidecar-v1"
    assert SIDECAR_FILENAME == "gebra.toml"


# ── WA-07 — the tripwire for the path this card lands ────────────────────────────────────

#: The guarded child, in two phases, because the two halves of this path can honestly claim
#: different strengths.
#:
#: **Phase A — the loader.** Every raiser is armed from the first line, socket *construction*
#: included: :mod:`gebra.annotations` reaches no substrate, so unlike the extraction tripwires
#: there is no bounded import phase to exclude and none is granted. Every fixture is written
#: and read under that guard.
#:
#: **Phase B — extraction with each fixture as its sidecar.** Importing langgraph builds a
#: socket, so construction is counted rather than refused while the substrate imports — the
#: same bounded phase ``test_dispatch`` and ``test_builder`` explain — and refused again
#: before the first extraction. Name resolution and connection raise throughout, in both
#: phases.
_TRIPWIRE = """
import builtins, socket, sys, tempfile, pathlib

attempts = []


def _record(name):
    def _seen(*a, **k):
        attempts.append(name); print("WA07-TRIP", file=sys.stderr)
        raise AssertionError(name + " was reached")
    return _seen


class _PermissiveSocket(socket.socket):
    # The import phase's socket: constructed sockets are allowed through while langgraph and
    # langchain-core import, because they build one. Nothing is *done* with it — the three
    # network verbs below raise from the child's first line to the last, in both phases.
    pass


class _TripSocket(socket.socket):
    def __new__(cls, *a, **k):
        attempts.append("socket"); print("WA07-TRIP", file=sys.stderr)
        raise AssertionError("a socket was created on the sidecar path")


socket.socket = _TripSocket
socket.getaddrinfo = _record("getaddrinfo")
socket.gethostbyname = _record("gethostbyname")
socket.create_connection = _record("create_connection")

# ── Phase A: the loader, with no import phase excused ──
from gebra.annotations import discover_sidecar, read_sidecar
from tests.sample_workflows import sentinel_sidecars as ss

assert "langgraph" not in sys.modules, sorted(sys.modules)
assert "langchain_core" not in sys.modules, sorted(sys.modules)
assert "gebra.extraction" not in sys.modules

# Armed only now, and only around the loader: `dataclasses` and pydantic build classes with
# `exec` at *import* time, so arming these before the imports above would trip on gebra's own
# construction rather than on anything a sidecar caused. Everything below this line is reading
# a file, and reading a file compiles nothing.
_evaluators = {name: getattr(builtins, name) for name in ("eval", "exec", "compile")}
for _name in _evaluators:
    setattr(builtins, _name, _record(_name))

read = 0
with tempfile.TemporaryDirectory() as home:
    root = pathlib.Path(home)
    (root / ".git").mkdir()
    for name, fixture in ss.SIDECAR_FIXTURES.items():
        path = ss.write_sidecar(root, fixture.text, name=name + ".toml")
        reading = read_sidecar(path)
        assert reading.loaded is fixture.loaded, name
        read += 1
    # The discovery walk under the same guard: a hit at the start, and the bounded miss.
    ss.write_sidecar(root / "nested", ss.SIDECAR_FIXTURES["nine_slots"].text)
    assert discover_sidecar(root / "nested") is not None
    assert discover_sidecar(root) is None
    assert read_sidecar(start=root / "nested").loaded is True

for _name, _original in _evaluators.items():
    setattr(builtins, _name, _original)

# ── Phase B: the whole extraction path over an armed graph, each fixture as its sidecar ──
socket.socket = _PermissiveSocket
import gebra
from tests.sample_workflows import sentinel_graph as sg

assert attempts == [], attempts
socket.socket = _TripSocket

extracted = 0
with tempfile.TemporaryDirectory() as home:
    root = pathlib.Path(home)
    (root / ".git").mkdir()
    for name, fixture in ss.SIDECAR_FIXTURES.items():
        path = ss.write_sidecar(root, fixture.text, name=name + ".toml")
        envelope = gebra.extract(sg.build_sentinel_graph(), sidecar=path)
        envelope.graph_version()
        extracted += 1

assert (read, extracted) == (%d, %d), (read, extracted)
"""

#: Probes for the three evaluators, which are only armed inside Phase A — so each control has
#: to re-arm the one it is testing rather than run after the child, the way the network probes
#: do. Kept beside the tripwire so the two cannot drift apart.
_EVALUATOR_PROBE = "setattr(builtins, {name!r}, _record({name!r}))\nbuiltins.{name}({call})\n"

_REPORT = "print(attempts)\n"


def _run_guarded(probe: str = "") -> subprocess.CompletedProcess[str]:
    body = _TRIPWIRE % (len(ss.SIDECAR_FIXTURES), len(ss.SIDECAR_FIXTURES))
    return subprocess.run(
        [sys.executable, "-c", body + probe + _REPORT],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_the_sidecar_path_invokes_nothing_and_reaches_no_substrate() -> None:
    """The WA-07 claim for the §2 path, in a fresh interpreter.

    Five things at once. The loader is exercised over every fixture — including the one whose
    table key is spelled ``__import__('os').system(...)`` — and nothing is called, resolved or
    connected to. That fixture's point is *armed* rather than argued: ``eval``, ``exec`` and
    ``compile`` all raise for the whole of Phase A, so "a sidecar is data, and the only
    operation it licenses is parsing" fails the run if it stops being true, including
    silently. The discovery walk runs under the same guard, both its hit and its bounded miss.
    Importing the loader reaches neither langgraph nor ``gebra.extraction``, asserted in the
    child rather than reviewed, which is what keeps the annotation surface usable without the
    substrate. Then the full extraction runs with each fixture as its sidecar over a graph
    whose every node and router raises if called, and each result is canonicalized and
    digested under the same guard. The child asserts its own counts from the fixture table, so
    a pass that stopped reaching the fixtures would fail here rather than prove nothing.
    """
    result = _run_guarded()

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "[]", result.stdout
    assert "WA07-TRIP" not in result.stderr, result.stderr


@pytest.mark.parametrize(
    ("probe", "expected"),
    [
        ("socket.socket()\n", "a socket was created"),
        ("socket.getaddrinfo('example.invalid', 80)\n", "getaddrinfo was reached"),
        ("socket.gethostbyname('example.invalid')\n", "gethostbyname was reached"),
        ("socket.create_connection(('example.invalid', 80))\n", "create_connection was reached"),
    ],
    ids=["socket", "getaddrinfo", "gethostbyname", "create_connection"],
)
def test_each_raiser_is_armed(probe: str, expected: str) -> None:
    """A tripwire nobody trips proves nothing, so every raiser gets its own control.

    The controls run *after* the child's own assertions, so each one shows the raiser was
    live at the end of the very run that made the claim.
    """
    result = _run_guarded(probe)

    assert result.returncode != 0
    assert expected in result.stderr


@pytest.mark.parametrize(
    ("name", "call"),
    [("eval", "'1'"), ("exec", "'pass'"), ("compile", "'1', '<probe>', 'eval'")],
)
def test_each_evaluator_raiser_is_armed(name: str, call: str) -> None:
    """The same control for the three evaluators, whose arming window is Phase A only.

    They cannot simply run after the child the way the network probes do — Phase A restores
    them before Phase B imports langgraph, which would otherwise fail on gebra's own class
    construction rather than on anything a sidecar did. So each probe re-arms the one it is
    testing and then calls it, which is enough to show the raiser itself is a real one and
    that the child's prologue installs the same object.
    """
    result = _run_guarded(_EVALUATOR_PROBE.format(name=name, call=call))

    assert result.returncode != 0
    assert f"{name} was reached" in result.stderr


def test_the_tripwire_covers_the_shapes_this_path_handles() -> None:
    """The claim above is only as wide as the table it quantifies over, so the table has a
    floor — and both halves of §2's file-level split are represented in it."""
    assert len(ss.SIDECAR_FIXTURES) >= 30
    assert len(ss.LOADED_SIDECARS) >= 10
    assert len(ss.NOT_LOADED_SIDECARS) >= 4
    assert set(ss.LOADED_SIDECARS) | set(ss.NOT_LOADED_SIDECARS) == set(ss.SIDECAR_FIXTURES)


def test_every_rule_the_loader_can_report_has_a_fixture() -> None:
    """A rule with no fixture is a §2 branch nothing runs. Every code is covered by name.

    ``file-unreadable`` is the one rule no *file* fixture can carry — it is about a path that
    is not there — so it is covered by its own tests above and listed here as the exception,
    rather than left to be noticed missing.
    """
    covered = {rule for fixture in ss.SIDECAR_FIXTURES.values() for rule in fixture.rules}

    assert covered == {rule.value for rule in SidecarRule} - {SidecarRule.FILE_UNREADABLE.value}


def test_the_issue_record_is_what_the_extraction_side_converts() -> None:
    """A structural check on the seam: an issue carries what a warning needs, and no more."""
    issue: SidecarIssue = read_sidecar(REPO_ROOT / "does-not-exist.toml").issues[0]

    assert (issue.rule, issue.node, issue.slots) == (SidecarRule.FILE_UNREADABLE, None, ())
