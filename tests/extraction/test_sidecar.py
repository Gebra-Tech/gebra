"""The sidecar as extraction sees it — ANNOTATION-API-SPEC §2, wired into ``extract()``.

:mod:`tests.annotations.test_sidecar` holds the loader to §2. This module holds the *seam*:
that the file the entry point picked is the one recorded in ``extracted_from``, that its
findings arrive as the taxonomy's warnings and nothing else, that a stale key produces
``annotation-unknown-node`` and a matched one does not, and — the acceptance line that ties
the card together — that a malformed sidecar changes the warnings and leaves the IR and its
``graph_version`` exactly as they were.

The last section is the CWD-reproducibility mechanism §2's SHOULD asks for. §2: "CWD-dependent
discovery makes the digest sensitive to the invocation directory — reproducible/CI extraction
SHOULD pass ``sidecar=`` explicitly, and the envelope's ``extracted_from`` … MUST record the
absolute sidecar path used". So the mechanism is: ``extracted_from.sidecar`` is the surface a
CI job asserts on, the hazard is demonstrated rather than described, and this repository's own
tree is held to carrying nothing discoverable, which is what makes the suite's own extractions
CWD-independent.

Nothing here executes a node: every graph is the armed sentinel builder.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from gebra.annotations import discover_sidecar, read_sidecar
from gebra.extraction import ExtractionEnvelope, ExtractionWarningCode, extract
from tests.sample_workflows import sentinel_graph as sg
from tests.sample_workflows import sentinel_sidecars as ss

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def checkout(tmp_path: Path) -> Path:
    """A bounded tree: a ``.git`` marker so the discovery walk cannot leave ``tmp_path``."""
    (tmp_path / ".git").mkdir()
    return tmp_path


def codes(envelope: ExtractionEnvelope) -> list[str]:
    """The warning codes on an envelope, in emission order."""
    return [warning.code.value for warning in envelope.warnings]


def sidecar_codes(envelope: ExtractionEnvelope) -> list[str]:
    """The same, minus the per-node contract records every extraction now carries.

    Since EX-11 wired ANNOTATION §3's chain in, an undeclared node resolves to the decision
    D-011 default and says so — so a claim about *the sidecar's* findings is quantified over
    the codes §2 owns, and stays exactly as strong as it was.
    """
    owned = {
        ExtractionWarningCode.ANNOTATION_INVALID.value,
        ExtractionWarningCode.ANNOTATION_UNKNOWN_NODE.value,
    }
    return [code for code in codes(envelope) if code in owned]


# ── §2: the absolute path, recorded or recorded absent ───────────────────────────────────


def test_the_absolute_path_of_an_explicit_sidecar_is_recorded(checkout: Path) -> None:
    """§2: the envelope "MUST record the **absolute** sidecar path used"."""
    sidecar = ss.write_sidecar(checkout / "config", ss.SIDECAR_FIXTURES["nine_slots"].text)

    envelope = extract(sg.build_sentinel_graph(), sidecar=sidecar)

    recorded = envelope.extracted_from.sidecar
    assert recorded == str(sidecar.resolve())
    assert Path(recorded).is_absolute()


def test_a_relative_argument_is_recorded_as_the_absolute_path_it_named(
    checkout: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The argument may be relative; what is recorded is not.

    "so digest divergence is diagnosable" (§2) is the whole reason the field exists, and a
    relative path is diagnosable only against a CWD nobody recorded.
    """
    ss.write_sidecar(checkout, ss.SIDECAR_FIXTURES["nine_slots"].text)
    monkeypatch.chdir(checkout)

    envelope = extract(sg.build_sentinel_graph(), sidecar="gebra.toml")

    assert envelope.extracted_from.sidecar == str((checkout / "gebra.toml").resolve())


def test_a_discovered_sidecar_is_recorded_the_same_way(
    checkout: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Discovery rule 2 records exactly what rule 1 does — the field is about the file."""
    sidecar = ss.write_sidecar(checkout, ss.SIDECAR_FIXTURES["nine_slots"].text)
    nested = checkout / "services" / "booking"
    nested.mkdir(parents=True)
    monkeypatch.chdir(nested)

    envelope = extract(sg.build_sentinel_graph())

    assert envelope.extracted_from.sidecar == str(sidecar.resolve())


def test_absence_is_recorded_as_absence(checkout: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """§2: "(or its absence)". No sidecar is the ordinary case and warns about nothing."""
    monkeypatch.chdir(checkout)

    envelope = extract(sg.build_sentinel_graph())

    assert envelope.extracted_from.sidecar is None
    assert ExtractionWarningCode.ANNOTATION_INVALID.value not in codes(envelope)


def test_a_file_that_was_not_loaded_is_not_recorded_as_used(checkout: Path) -> None:
    """§2's own words for a rejected schema are that "extraction proceeds sidecar-less".

    So the provenance says no sidecar was used, and the warning names the file. Recording the
    path here would be the one lie the field exists to prevent: a reader comparing two
    digests would see a sidecar on both sides and conclude it could not be the cause.
    """
    sidecar = ss.write_sidecar(checkout, ss.SIDECAR_FIXTURES["wrong_schema"].text)

    envelope = extract(sg.build_sentinel_graph(), sidecar=sidecar)

    assert envelope.extracted_from.sidecar is None
    (invalid,) = envelope.warnings_of(ExtractionWarningCode.ANNOTATION_INVALID)
    assert invalid.detail["file"] == str(sidecar.resolve())
    assert invalid.detail["rule"] == "schema-unknown"


# ── §2: malformed degrades to warnings, and extraction stays total ───────────────────────


@pytest.mark.parametrize("name", sorted(ss.SIDECAR_FIXTURES))
def test_no_sidecar_can_make_extraction_fail_or_move_anything_but_a_contract(
    checkout: Path, name: str
) -> None:
    """The card's second acceptance line, over every fixture rather than a chosen few.

    EX-09 wrote this as "the IR is byte-identical to the sidecar-less one", true then because
    no entry was resolved. EX-11 landed ANNOTATION §3's chain, so a matched entry now *does*
    reach the IR — which is what §2's own digest-sensitivity warning is about. What is
    invariant is everything else, and it is worth more than the equality it replaces:
    extraction does not raise, the IR still has a digest, no sidecar can move the topology or
    Σ by a byte, and a node the file never keyed resolves exactly as it did without the file.
    A loader that leaked an entry onto the wrong node, or a chain that let one node's
    declaration reach another, fails here.
    """
    sidecar = ss.write_sidecar(checkout, ss.SIDECAR_FIXTURES[name].text)
    baseline = extract(sg.build_sentinel_graph(), sidecar=checkout / "nothing-here.toml")

    envelope = extract(sg.build_sentinel_graph(), sidecar=sidecar)

    assert envelope.graph_version().startswith("sha256:")
    for member in ("ir_version", "entry", "finish", "state", "edges", "runtime"):
        assert getattr(envelope.ir, member) == getattr(baseline.ir, member), member

    keyed = frozenset(read_sidecar(sidecar).entries)
    for node, unannotated in zip(envelope.ir.nodes, baseline.ir.nodes, strict=True):
        assert node.id == unannotated.id
        if node.id not in keyed:
            assert node.annotations == unannotated.annotations, node.id


@pytest.mark.parametrize("name", sorted(ss.SIDECAR_FIXTURES))
def test_every_sidecar_finding_arrives_as_a_taxonomy_warning(checkout: Path, name: str) -> None:
    """§2's findings are ``annotation-invalid`` records of the one closed taxonomy (§4).

    Constructing the record is itself the check: ``ExtractionWarning`` refuses a ``detail``
    that is not JSON data and refuses a code whose registry row names fields the record lacks,
    so a loader that put a ``datetime`` or a NaN in a warning would fail here rather than at
    the moment someone tried to report it.

    Scoped to the findings the *loader* produced. ``annotation-invalid`` is also §3's own
    repair code, and since EX-11 the resolved-contract pass can add one on top of a §2
    finding — the ``nine_slots`` fixture declares ``idempotent = {key = "plan"}`` beside
    ``reads = ["query", "budget"]``, and §1 requires the key to appear in the resolved
    ``input``. A §3 record carries ``surfaces`` (the tiers the violation spans), never the
    single ``surface`` a §2 record names, so the two halves of one code separate on the field
    each registry row actually carries.
    """
    fixture = ss.SIDECAR_FIXTURES[name]
    sidecar = ss.write_sidecar(checkout, fixture.text)

    envelope = extract(sg.build_sentinel_graph(), sidecar=sidecar)
    invalid = [
        warning
        for warning in envelope.warnings_of(ExtractionWarningCode.ANNOTATION_INVALID)
        if warning.detail.get("surface") == "sidecar"
    ]

    assert [warning.detail["rule"] for warning in invalid] == list(fixture.rules)


def test_the_sidecar_findings_come_before_the_graphs_own(checkout: Path) -> None:
    """Warnings are ordered by source: the file is read first, so its findings are first.

    The unmatched-key findings are last, and deliberately so — they are the one sidecar fact
    that cannot be known until the node set exists.
    """
    sidecar = ss.write_sidecar(
        checkout, f"{ss.SCHEMA_LINE}\nnodez = {{ }}\n[nodes.renamed_step]\npure = true\n"
    )

    envelope = extract(sg.build_unwired_graph(), sidecar=sidecar)

    assert codes(envelope)[0] == "annotation-invalid"
    assert codes(envelope)[-1] == "annotation-unknown-node"
    assert "unsupported-construct" in codes(envelope)


# ── §2: the unmatched-key rule ───────────────────────────────────────────────────────────


def test_a_stale_key_emits_annotation_unknown_node(checkout: Path) -> None:
    """§2: "A sidecar entry whose key matches no extracted node id emits an
    ``annotation-unknown-node`` warning" — because "a rename is a *new identity*"."""
    sidecar = ss.write_sidecar(checkout, f"{ss.SCHEMA_LINE}\n[nodes.plan_step_v2]\npure = true\n")

    envelope = extract(sg.build_sentinel_graph(), sidecar=sidecar)

    (unknown,) = envelope.warnings_of(ExtractionWarningCode.ANNOTATION_UNKNOWN_NODE)
    assert unknown.detail["key"] == "plan_step_v2"
    assert unknown.detail["file"] == str(sidecar.resolve())


def test_the_unmatched_key_warning_names_no_node(checkout: Path) -> None:
    """§4's row carries "sidecar path; the unmatched entry key" — not a node id.

    Putting the key in ``node`` would enter a name that annotates nothing into §5's
    (node id, slot) grade lookup, where every reader takes a node id to be an extracted node.
    """
    sidecar = ss.write_sidecar(checkout, f"{ss.SCHEMA_LINE}\n[nodes.plan_step_v2]\npure = true\n")

    envelope = extract(sg.build_sentinel_graph(), sidecar=sidecar)

    (unknown,) = envelope.warnings_of(ExtractionWarningCode.ANNOTATION_UNKNOWN_NODE)
    assert unknown.node is None
    assert unknown.targets() == ()


def test_a_matching_key_emits_nothing(checkout: Path) -> None:
    """The complement, without which the test above would pass on a loader that warns always."""
    sidecar = ss.write_sidecar(
        checkout,
        f"{ss.SCHEMA_LINE}\n"
        + "".join(f"[nodes.{node}]\npure = true\n" for node in ss.SENTINEL_NODE_IDS),
    )

    envelope = extract(sg.build_sentinel_graph(), sidecar=sidecar)

    assert envelope.warnings_of(ExtractionWarningCode.ANNOTATION_UNKNOWN_NODE) == ()


def test_a_multi_segment_quoted_key_is_matched_by_byte_equality(checkout: Path) -> None:
    """The card's third acceptance line: a quoted multi-segment key resolves, or does not,
    on exactly the bytes it carries (§2, IR-SPEC §5.1).

    The sentinel graph has no nested node, so the id cannot match — which is the honest thing
    to assert here, and it is asserted *both ways*: the same file matched against a node set
    that does contain the id produces no warning at all. Between them they say the comparison
    is the id, not the shape of the key.
    """
    sidecar = ss.write_sidecar(checkout, ss.SIDECAR_FIXTURES["multi_segment_key"].text)

    envelope = extract(sg.build_sentinel_graph(), sidecar=sidecar)
    reading = read_sidecar(sidecar)

    (unknown,) = envelope.warnings_of(ExtractionWarningCode.ANNOTATION_UNKNOWN_NODE)
    assert unknown.detail["key"] == "research/tools/web_search"
    assert reading.unmatched_keys(frozenset({"research/tools/web_search"})) == ()


def test_an_entry_whose_slots_were_all_rejected_still_reports_its_stale_key(
    checkout: Path,
) -> None:
    """Two independent §2 findings on one entry, both surfaced — neither hides the other."""
    sidecar = ss.write_sidecar(checkout, f'{ss.SCHEMA_LINE}\n[nodes.plan_step_v2]\npure = "yes"\n')

    envelope = extract(sg.build_sentinel_graph(), sidecar=sidecar)

    assert sidecar_codes(envelope) == ["annotation-invalid", "annotation-unknown-node"]


# ── The CWD-reproducibility mechanism (§2's SHOULD) ──────────────────────────────────────


def test_discovery_is_cwd_sensitive_and_the_explicit_argument_removes_it(
    checkout: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The hazard §2 names, demonstrated, and the remedy §2 recommends, demonstrated with it.

    Two directories in one checkout, each with its own ``gebra.toml``: the same call on the
    same object picks a different file from each. That is what "CWD-dependent discovery makes
    the digest sensitive to the invocation directory" means concretely — and it is why §2
    makes the recorded path a MUST.

    Both surfaces are pinned, and the second one only became assertable with EX-11. EX-09
    could show the *provenance* diverging — two directories, two recorded paths — but not the
    digest, because no sidecar value reached the IR yet. Now one does, so the sentence §2
    actually writes ("sidecar-filled annotations sit inside the ``graph_version`` hash scope,
    so CWD-dependent discovery makes the digest sensitive to the invocation directory") is
    demonstrated as a digest divergence, and the remedy §2 recommends is demonstrated as the
    digest coming back together.
    """
    ss.write_sidecar(checkout, ss.SIDECAR_FIXTURES["nine_slots"].text)
    ss.write_sidecar(checkout / "services", ss.SIDECAR_FIXTURES["multi_segment_key"].text)
    pinned = checkout / "gebra.toml"

    monkeypatch.chdir(checkout)
    from_root = extract(sg.build_sentinel_graph())
    pinned_from_root = extract(sg.build_sentinel_graph(), sidecar=pinned)

    monkeypatch.chdir(checkout / "services")
    from_services = extract(sg.build_sentinel_graph())
    pinned_from_services = extract(sg.build_sentinel_graph(), sidecar=pinned)

    assert from_root.extracted_from.sidecar != from_services.extracted_from.sidecar
    assert from_root.graph_version() != from_services.graph_version()
    assert (
        pinned_from_root.extracted_from.sidecar
        == pinned_from_services.extracted_from.sidecar
        == str(pinned.resolve())
    )
    assert pinned_from_root.graph_version() == pinned_from_services.graph_version()


def test_this_repository_carries_no_discoverable_sidecar() -> None:
    """The suite's own extractions must not depend on where pytest was started.

    Every ``extract()`` call in this repository that passes no ``sidecar=`` runs §2's walk
    from the CWD. A ``gebra.toml`` anywhere between a test's working directory and this
    repository root would therefore join every one of those extractions — silently, and
    differently depending on which directory the developer ran ``pytest`` from. This is the
    guard that keeps the reproducibility claim structural rather than incidental; a card that
    genuinely needs a checked-in sidecar has to change this test, and say why.
    """
    assert discover_sidecar(REPO_ROOT) is None
    assert discover_sidecar(REPO_ROOT / "tests" / "extraction") is None
    assert discover_sidecar(REPO_ROOT / "src" / "gebra" / "annotations") is None


def test_an_extraction_from_two_directories_agrees_when_the_sidecar_is_pinned(
    checkout: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The whole envelope, not only the recorded path: pinning makes the result a value.

    ``ExtractionEnvelope`` carries no wall-clock and no identity (EX-01's ruling), so two
    extractions of one unchanged object with one pinned sidecar are *equal* — which is what
    lets a CI job compare an extraction against a stored one at all.
    """
    sidecar = ss.write_sidecar(checkout / "config", ss.SIDECAR_FIXTURES["nine_slots"].text)
    ss.write_sidecar(checkout, ss.SIDECAR_FIXTURES["multi_segment_key"].text)
    (checkout / "services").mkdir()

    monkeypatch.chdir(checkout)
    here = extract(sg.build_sentinel_graph(), sidecar=sidecar)
    monkeypatch.chdir(checkout / "services")
    there = extract(sg.build_sentinel_graph(), sidecar=sidecar)

    assert here == there
