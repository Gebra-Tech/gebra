"""P-08 ``determinism-replay`` against the vendored corpus (PROPERTY-CATALOG-SPEC §8).

The first vertical slice: envelope (VAL-01) → condition/property registries (VAL-02) →
validator, asserted as **model equality** against the fixtures' own ``expected:`` blocks
rather than as string or dict comparison (A6 PC-6). The golden harness owns this comparison
for every property now that it has landed (:mod:`gebra.testing.harness`, run over the whole
corpus by ``tests/testing/test_golden_harness.py``); the loading rule §0.3 states
(``{"property": fixture["property"], **fixture["expected"]}``) stays spelled out here, and
deliberately so — this module reaches the four fixtures through PyYAML and the models
directly, so it is an *independent* second path to the same assertion rather than a caller of
the harness that would pass whenever the harness agreed with itself.

**No corpus deviation remains.** This module used to carry a two-entry deviation ledger for
the two things §8.3's walkthrough-#2 markers declared pending — marker (a), the negatives'
missing ``kind: "node"`` discriminator, and marker (d), their ``remediation`` strings being
"condensed action clauses" rather than Appendix B §B.3's closing paragraphs. Both landed with
the single corpus-reconciliation pass (TE-03; ruled in DEC-17, re-vendored from vault
``b2056e9``), so the ledger is gone and **all four fixtures are compared against the raw
``expected:`` block, with nothing normalized on either side**.

What the ledger used to assert in both directions is now asserted the other way round: the
corpus's own ``location.kind`` is checked against §8.3's discriminator, and its ``remediation``
against the shipped §B.3 transcription (:func:`render_remediation`), so a one-sided regression
in either the corpus or the renderer still fails here rather than passing silently. The corpus
bytes themselves are held by the provenance guard, which is what closes the loop: a *matching*
edit to both sides is not something a comparison between them could catch.

WA-07: nothing here executes a workflow, a node, or a network call. Fixtures are read with
PyYAML's safe loader; the ``ir:`` block is validated into the frozen IR models and read as
data; ``source_snippet`` is never touched.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from gebra.ir import Annotations, Node, WorkflowIR, canonical_bytes
from gebra.verify import (
    WEDGE_SLUGS,
    AnyLocation,
    CoFailure,
    DeterminismClaim,
    DeterminismNodeLocation,
    DeterminismWitness,
    Failure,
    NotImplementedMarker,
    PropertyReport,
    is_implemented,
    run_property,
    to_data,
    validate_report,
    validate_witness,
)
from gebra.verify.properties.determinism_replay import (
    CAVEAT,
    LLM_EVIDENCE_TAGS,
    SEED_UNPINNED,
    TEMPERATURE_UNPINNED,
    WARNING_HEADER,
    check_determinism_replay,
    render_remediation,
    render_warning,
)
from tests.conftest import FIXTURES_DIR

#: The six P-08 property fixtures (§8.6's four + the DEC-16 3+3 top-up, TE-14), by path.
FIXTURES: tuple[str, ...] = (
    "determinism-replay/positive-01-pinned-seed-zero-temp-classifier.yaml",
    "determinism-replay/positive-02-pure-fare-normalizer.yaml",
    "determinism-replay/positive-03-vacuous-pass-no-deterministic-annotation.yaml",
    "determinism-replay/negative-01-seedless-deterministic-llm-classifier.yaml",
    "determinism-replay/negative-02-seeded-llm-extractor-hot-temperature.yaml",
    "determinism-replay/negative-03-seeded-llm-temperature-field-absent.yaml",
)

POSITIVES: tuple[str, ...] = FIXTURES[:3]
NEGATIVES: tuple[str, ...] = FIXTURES[3:]


# ── Fixture loading (§0.3's rule, spelled out — the second, independent path) ────────────


def _load(relative: str) -> dict[str, Any]:
    document = yaml.safe_load((FIXTURES_DIR / relative).read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    return document


def _ir_of(relative: str, key: str = "ir") -> WorkflowIR:
    """The fixture's IR block, validated into the frozen models (JSON mode, §2.5 note 4)."""
    return WorkflowIR.model_validate_json(json.dumps(_load(relative)[key]))


def _anchor(location: AnyLocation) -> DeterminismNodeLocation:
    """Every P-08 record anchors on the §8.3 node subtype — asserted, then read."""
    assert isinstance(location, DeterminismNodeLocation)
    return location


def _raw_expected(relative: str, slug: str = "determinism-replay") -> dict[str, Any]:
    document = _load(relative)
    return {"property": slug, **document["expected"]}


def _expected_report(relative: str) -> PropertyReport:
    """The fixture's ``expected:`` block as a report — the raw block, since DEC-17 landed."""
    return validate_report(_raw_expected(relative))


# ── Acceptance box 1: all four fixtures, as model equality ───────────────────────────────


@pytest.mark.parametrize("relative", FIXTURES)
def test_the_validator_reproduces_the_fixture_report(relative: str) -> None:
    """The whole chain on one line: IR in, and the report *is* the fixture's expected model.

    Since DEC-17 this is a raw equality on all four fixtures — the corpus block goes into the
    model untouched. Nothing here is circular any more: the ``remediation`` the validator
    renders and the one the corpus carries are compared as two independently-sourced values
    (the renderer transcribes §B.3; the corpus was reconciled to §B.3), and
    ``test_the_reconciled_negatives_carry_the_shapes_dec17_landed`` asserts that from the
    corpus side on its own.
    """
    assert check_determinism_replay(_ir_of(relative)) == _expected_report(relative)


@pytest.mark.parametrize("relative", FIXTURES)
def test_the_report_is_spec_shaped_and_round_trips(relative: str) -> None:
    """Spec-shaped means it survives the PC-4 serialization profile and loads back equal."""
    report = check_determinism_replay(_ir_of(relative))
    assert report.property == "determinism-replay"
    assert report.result == ("pass" if _load(relative)["polarity"] == "positive" else "fail")
    assert validate_report(to_data(report)) == report


@pytest.mark.parametrize("relative", NEGATIVES)
def test_the_negatives_match_the_validator_field_for_field(relative: str) -> None:
    """Nothing is exempt any more — every field of the emitted failure equals the vendored one."""
    emitted = to_data(check_determinism_replay(_ir_of(relative)))["failure"]
    vendored = dict(_load(relative)["expected"]["failure"])
    assert emitted == vendored


@pytest.mark.parametrize("relative", NEGATIVES)
def test_the_reconciled_negatives_carry_the_shapes_dec17_landed(relative: str) -> None:
    """The corpus side alone, checked against the frozen sources rather than the validator.

    This is what the old deviation ledger becomes once the deviation is gone: the two fields
    §8.3's markers (a) and (d) sent to the reconciliation pass are pinned from the corpus,
    against §8.3's discriminator and Appendix B §B.3's closing paragraph — so a re-vendor that
    dropped either would fail here even if the validator were changed to agree with it.
    """
    vendored = dict(_load(relative)["expected"]["failure"])
    assert vendored["location"]["kind"] == "node"
    assert vendored["remediation"] == render_remediation(vendored["property_condition"])
    assert not vendored["remediation"].endswith("\n"), "the folded scalar must strip (`>-`)"
    assert vendored["remediation"].startswith("The claim is recorded.")


def test_the_corpus_holds_exactly_six_determinism_fixtures() -> None:
    """§8.6's 2+2 plus the DEC-16 top-up (TE-14, vault ``e6ea366``): 3 positive + 3 negative.

    The top-up PR-08 tracked has landed — the ≥3+≥3 house minimum is met. A further change
    lands here as a diff.
    """
    found = sorted(
        path.relative_to(FIXTURES_DIR).as_posix()
        for path in (FIXTURES_DIR / "determinism-replay").glob("*.yaml")
    )
    assert found == sorted(FIXTURES)


# ── Acceptance box 2: the mandatory provider caveat, both ways ───────────────────────────


def test_the_caveat_is_present_when_a_claim_is_llm_backed() -> None:
    """Appendix B C-4 on the fixture that pins it (``positive-01``)."""
    report = check_determinism_replay(_ir_of(POSITIVES[0]))
    witness = report.witness
    assert isinstance(witness, DeterminismWitness)
    assert witness.caveat == CAVEAT
    assert [claim.llm_backed for claim in witness.claims] == [True]


def test_the_caveat_is_absent_when_no_claim_is_llm_backed() -> None:
    """``positive-02``: a claim on pure local computation carries no provider caveat."""
    report = check_determinism_replay(_ir_of(POSITIVES[1]))
    witness = report.witness
    assert isinstance(witness, DeterminismWitness)
    assert witness.caveat is None
    assert [claim.llm_backed for claim in witness.claims] == [False]


def test_the_caveat_follows_the_claim_not_the_node() -> None:
    """§8.3 words the rule over *claims*: an LLM node with no annotation makes no claim.

    Worth pinning because the loose reading ("any node is llm_backed") would put a provider
    caveat on a report that records no provider-dependent claim at all.
    """
    report = check_determinism_replay(
        _ir(
            _node("plain_llm_call", effect=("network", "external")),
            _node("local", deterministic=True),
        )
    )
    witness = report.witness
    assert isinstance(witness, DeterminismWitness)
    assert [claim.node for claim in witness.claims] == ["local"]
    assert witness.caveat is None


def test_the_caveat_is_present_once_for_several_llm_backed_claims() -> None:
    report = check_determinism_replay(
        _ir(
            _node("alpha", deterministic={"seed": 1, "temperature": 0}, effect=("external",)),
            _node("beta", deterministic={"seed": 2, "temperature": 0}, effect=("network",)),
            _node("gamma", deterministic=True),
        )
    )
    witness = report.witness
    assert isinstance(witness, DeterminismWitness)
    assert witness.caveat == CAVEAT
    assert [claim.llm_backed for claim in witness.claims] == [True, True, False]


def test_a_witness_cannot_be_built_with_the_caveat_on_the_wrong_side() -> None:
    """The iff is the model's invariant (VAL-01), not this validator's convention."""
    llm_backed = DeterminismClaim(node="a", llm_backed=True, seed=1, temperature=0)
    local = DeterminismClaim(node="a", llm_backed=False, basis="pure-local-computation")
    with pytest.raises(ValidationError, match="caveat"):
        DeterminismWitness(kind="determinism", claims=(llm_backed,), claim_class="heuristic")
    with pytest.raises(ValidationError, match="caveat"):
        DeterminismWitness(
            kind="determinism", claims=(local,), caveat=CAVEAT, claim_class="heuristic"
        )
    with pytest.raises(ValidationError, match="caveat"):
        DeterminismWitness(kind="determinism", claims=(), caveat=CAVEAT, claim_class="heuristic")


# ── The nine §8.7 edge cases ─────────────────────────────────────────────────────────────


def _node(
    node_id: str,
    *,
    deterministic: bool | dict[str, Any] | None = None,
    effect: tuple[str, ...] | None = None,
    pure: bool | None = None,
) -> dict[str, Any]:
    annotations = {
        key: value
        for key, value in (
            ("deterministic", deterministic),
            ("effect", list(effect) if effect is not None else None),
            ("pure", pure),
        )
        if value is not None
    }
    return {"id": node_id, "annotations": annotations} if annotations else {"id": node_id}


def _ir(*nodes: dict[str, Any], edges: list[dict[str, str]] | None = None) -> WorkflowIR:
    """A minimal IR carrying ``nodes`` — P-08 reads nothing else (§8.3)."""
    ids = [node["id"] for node in nodes]
    return WorkflowIR.model_validate_json(
        json.dumps(
            {
                "ir_version": "1.0",
                "entry": ids[0],
                "finish": ids[-1],
                "nodes": list(nodes),
                "edges": edges if edges is not None else [],
            }
        )
    )


def test_case_1_no_determinism_annotation_anywhere_is_a_vacuous_pass() -> None:
    report = check_determinism_replay(_ir(_node("a", effect=("external",)), _node("b")))
    assert report == PropertyReport.passing(
        "determinism-replay",
        DeterminismWitness(kind="determinism", claims=(), claim_class="heuristic"),
    )


def test_case_1_a_single_node_graph_is_subsumed_by_the_vacuous_pass() -> None:
    report = check_determinism_replay(_ir(_node("only")))
    witness = report.witness
    assert isinstance(witness, DeterminismWitness)
    assert witness.claims == ()


def test_case_2_deterministic_false_is_an_explicit_disclaimer_not_a_claim() -> None:
    """A disclaimer is skipped, not recorded — and never a finding, even on an LLM node."""
    report = check_determinism_replay(
        _ir(_node("llm", deterministic=False, effect=("external", "network")))
    )
    witness = report.witness
    assert isinstance(witness, DeterminismWitness)
    assert witness.claims == ()
    assert witness.caveat is None


def test_case_3_a_bare_claim_on_a_non_llm_node_is_trivially_coherent() -> None:
    report = check_determinism_replay(_ir(_node("local", deterministic=True, pure=True)))
    witness = report.witness
    assert isinstance(witness, DeterminismWitness)
    assert witness.claims == (
        DeterminismClaim(
            node="local", llm_backed=False, basis="pure-local-computation", pinning_required=False
        ),
    )


@pytest.mark.parametrize("tag", sorted(LLM_EVIDENCE_TAGS))
def test_case_4_a_bare_claim_on_an_llm_backed_node_is_seed_unpinned(tag: str) -> None:
    """Either D-011 evidence tag alone is enough (C-1) — the fixtures carry both."""
    report = check_determinism_replay(_ir(_node("llm", deterministic=True, effect=(tag,))))
    assert report.result == "fail"
    assert report.failure is not None
    assert report.failure.property_condition == SEED_UNPINNED
    assert report.failure.location == DeterminismNodeLocation(
        kind="node", node="llm", annotation="deterministic", form="bare-boolean", effects=(tag,)
    )


def test_a_non_evidence_effect_tag_creates_no_pinning_obligation() -> None:
    """``billable``/``audit`` are P-06's business; C-1's proxy set is exactly two tags."""
    report = check_determinism_replay(
        _ir(_node("charges", deterministic=True, effect=("billable", "irreversible", "audit")))
    )
    witness = report.witness
    assert isinstance(witness, DeterminismWitness)
    assert [claim.llm_backed for claim in witness.claims] == [False]


@pytest.mark.parametrize("temperature", [None, 0.7, 1, 0.0001, -0.5])
def test_case_5_absent_or_nonzero_temperature_is_temperature_unpinned(
    temperature: float | None,
) -> None:
    annotation: dict[str, Any] = {"seed": 7}
    if temperature is not None:
        annotation["temperature"] = temperature
    report = check_determinism_replay(
        _ir(_node("llm", deterministic=annotation, effect=("external",)))
    )
    assert report.result == "fail"
    assert report.failure is not None
    assert report.failure.property_condition == TEMPERATURE_UNPINNED
    assert report.failure.location == DeterminismNodeLocation(
        kind="node", node="llm", annotation="deterministic", seed=7, temperature=temperature
    )


@pytest.mark.parametrize("temperature", [0, 0.0, -0.0])
def test_case_6_a_fully_pinned_claim_passes_with_numeric_zero_comparison(
    temperature: float,
) -> None:
    """§8.4's ``numeric(det.temperature) != 0`` — ``0 == 0.0``, and the spelling is free."""
    report = check_determinism_replay(
        _ir(
            _node(
                "llm", deterministic={"seed": 42, "temperature": temperature}, effect=("network",)
            )
        )
    )
    witness = report.witness
    assert isinstance(witness, DeterminismWitness)
    assert witness.caveat == CAVEAT
    assert witness.claims == (
        DeterminismClaim(
            node="llm", llm_backed=True, seed=42, temperature=0, divergence_handling="logged"
        ),
    )


def test_case_7_the_object_form_on_a_non_llm_node_needs_no_temperature() -> None:
    """``mixed/10``'s ``compose_digest``: object form, no LLM evidence, no obligation."""
    report = check_determinism_replay(_ir(_node("compose", deterministic={"seed": 42})))
    witness = report.witness
    assert isinstance(witness, DeterminismWitness)
    assert witness.claims == (
        DeterminismClaim(
            node="compose",
            llm_backed=False,
            basis="pure-local-computation",
            pinning_required=False,
        ),
    )


def test_case_8_a_seedless_object_is_refused_upstream_and_never_reaches_p08() -> None:
    """§8.4: "a seedless object is an IR-validation error upstream of P-08 … never a verdict"."""
    with pytest.raises(ValidationError):
        _ir(_node("llm", deterministic={"temperature": 0}, effect=("external",)))


def test_case_9_multiple_findings_ride_as_same_property_co_failures() -> None:
    """§0.3 packaging: canonical order fixes the primary, the rest are ``co_failures``."""
    report = check_determinism_replay(
        _ir(
            _node("zulu", deterministic=True, effect=("external",)),
            _node("alpha", deterministic={"seed": 3}, effect=("network",)),
            _node("mike", deterministic=True, effect=("network", "external")),
        )
    )
    assert report.failure is not None
    assert report.failure.property_condition == TEMPERATURE_UNPINNED
    assert _anchor(report.failure.location).node == "alpha"
    assert report.failure.advisories is None
    assert report.failure.co_failures is not None
    assert [
        (co.property, co.property_condition, _anchor(co.location).node)
        for co in report.failure.co_failures
    ] == [
        ("determinism-replay", SEED_UNPINNED, "mike"),
        ("determinism-replay", SEED_UNPINNED, "zulu"),
    ]
    assert all(
        (co.severity, co.claim_class) == ("warning", "heuristic")
        for co in report.failure.co_failures
    )


def test_a_single_finding_carries_no_empty_co_failures_member() -> None:
    """``or absent`` in §8.4: an empty tuple would serialize as a member the corpus omits."""
    report = check_determinism_replay(_ir_of(NEGATIVES[0]))
    assert report.failure is not None
    assert report.failure.co_failures is None
    assert "co_failures" not in to_data(report)["failure"]


# ── The mixed corpus (§8.6) ──────────────────────────────────────────────────────────────


def test_mixed_10_the_healthy_pipeline_produces_the_fixtures_p08_witness() -> None:
    """The over-flagging guard: a cycle, a fan-out and a billable effect, and P-08 passes."""
    relative = "mixed/10-all-properties-pass-healthy-research-pipeline.yaml"
    expected = validate_witness(
        _load(relative)["expected"]["witness"]["properties"]["determinism-replay"]
    )
    assert check_determinism_replay(_ir_of(relative)).witness == expected


def test_mixed_03_run_standalone_finds_both_unpinned_writers() -> None:
    """``mixed/03`` is P-09's report — its P-08 findings ride as cross-property advisories.

    Run alone, P-08 owns the report instead, so the same two findings pack the §0.3
    *same-property* way (primary + ``co_failures``) and carry the full §8.3 evidence the
    advisory form leaves out. The fixture's own ``expected:`` block belongs to P-09 and is
    asserted by neither this card nor this test.
    """
    relative = "mixed/03-parallel-reducerless-key-with-unpinned-llm-writers.yaml"
    report = check_determinism_replay(_ir_of(relative))
    assert report.failure is not None
    assert report.failure.property_condition == SEED_UNPINNED
    assert _anchor(report.failure.location).node == "market_analysis"
    assert report.failure.co_failures is not None
    assert [_anchor(co.location).node for co in report.failure.co_failures] == ["risk_analysis"]

    advisories = _load(relative)["expected"]["failure"]["advisories"]
    assert [entry["property_condition"] for entry in advisories] == [SEED_UNPINNED] * 2
    assert [entry["location"]["node"] for entry in advisories] == [
        "market_analysis",
        "risk_analysis",
    ]


# ── §8.5: annotation-only, topology never read ───────────────────────────────────────────


@pytest.mark.parametrize("relative", FIXTURES)
def test_the_verdict_is_invariant_under_every_field_p08_does_not_read(relative: str) -> None:
    """§8.3/§8.7 state the negative: no ``edges[]``, no ``state``, no ``runtime``.

    Stripping the topology entirely cannot move a P-08 verdict — if it did, the property
    would have coupled to the graph and §8.5's "no |E| term" bound would be false.
    """
    document = _load(relative)
    stripped = {**document["ir"], "edges": []}
    stripped.pop("state", None)
    stripped.pop("runtime", None)
    assert check_determinism_replay(
        WorkflowIR.model_validate_json(json.dumps(stripped))
    ) == check_determinism_replay(_ir_of(relative))


def test_the_module_cites_no_graph_library() -> None:
    """§8.7's spec-conformance claim — "networkx primitives: **None**" — read off the source.

    A conformance check, not the hermeticity one: WA-07 is enforced by the tripwire below,
    which runs in a fresh interpreter and cannot be evaded by an import spelling.
    """
    source = (
        Path(check_determinism_replay.__globals__["__file__"]).read_text(encoding="utf-8").lower()
    )
    for graph_library in ("networkx", "igraph", "graph_tool", "scipy.sparse.csgraph"):
        assert graph_library not in source


def test_running_p08_creates_no_socket_and_resolves_no_name() -> None:
    """WA-07 on the P-08 path, import **and** call, to the VAL-13 tripwire standard.

    A fresh interpreter, because another test in this session may have imported anything.
    Three claims, separately enforced: no execution-substrate or HTTP/LLM-client package
    enters the import closure; no socket is created and no name resolved, either while
    importing the validator or while *running* it over a real corpus fixture; and a
    swallowed exception still fails the run, because every attempt is recorded before the
    raise and also announced on stderr. The call leg is the part import-time tripwires
    cannot give: a client imported lazily inside the checker would pass an import-only
    probe. Stdlib module presence is deliberately not asserted — VAL-13 traced that to
    version-dependent stdlib internals with no network involved.
    """
    fixture = FIXTURES_DIR / NEGATIVES[0]
    forbidden = (
        "{'langgraph', 'langchain', 'langchain_core', 'networkx', 'openai', 'anthropic', "
        "'httpx', 'requests', 'aiohttp', 'urllib3'}"
    )
    script = (
        "import json, socket, sys\n"
        "attempts = []\n"
        "class _TripSocket(socket.socket):\n"
        "    def __new__(cls, *a, **k):\n"
        "        attempts.append('socket'); print('WA07-TRIP', file=sys.stderr)\n"
        "        raise AssertionError('socket created on the P-08 path')\n"
        "def _trip_dns(*a, **k):\n"
        "    attempts.append('getaddrinfo'); print('WA07-TRIP', file=sys.stderr)\n"
        "    raise AssertionError('name resolved on the P-08 path')\n"
        "socket.socket = _TripSocket\n"
        "socket.getaddrinfo = _trip_dns\n"
        "import yaml\n"
        "from gebra.ir import WorkflowIR\n"
        "from gebra.verify.properties.determinism_replay import check_determinism_replay\n"
        f"with open({str(fixture)!r}, encoding='utf-8') as handle:\n"
        "    document = yaml.safe_load(handle)\n"
        "ir = WorkflowIR.model_validate_json(json.dumps(document['ir']))\n"
        "assert check_determinism_replay(ir).result == 'fail'\n"
        f"print([m for m in sys.modules if m.split('.')[0] in {forbidden}] + attempts)\n"
    )
    completed = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, check=True
    )
    assert completed.stdout.strip() == "[]", completed.stdout
    assert "WA07-TRIP" not in completed.stderr, completed.stderr


# ── Canonical order (ledger §6), the sort the primary depends on ─────────────────────────


def test_claims_and_findings_follow_canonical_node_order_not_authored_order() -> None:
    report = check_determinism_replay(
        _ir(
            _node("charlie", deterministic=True),
            _node("alpha", deterministic=True),
            _node("bravo", deterministic=True),
        )
    )
    witness = report.witness
    assert isinstance(witness, DeterminismWitness)
    assert [claim.node for claim in witness.claims] == ["alpha", "bravo", "charlie"]


def test_the_sort_is_the_ledger_comparator_not_pythons_default() -> None:
    """Ledger §6: ``nodes[]`` by id as **UTF-16 code units** (RFC 8785 §3.2.3).

    Pinned against the IR canonicalizer's own ordering rather than restated: the two differ
    for ids mixing non-BMP characters with U+E000..U+FFFF, where Python's default code-point
    order sorts U+1F600 after U+FFFD and the ledger's sorts it before.
    """
    ids = ("\U0001f600", "�", "a")
    assert sorted(ids) != sorted(ids, key=lambda value: value.encode("utf-16-be"))

    ir = _ir(*(_node(node_id, deterministic=True) for node_id in ids))
    canonical = json.loads(canonical_bytes(ir))
    witness = check_determinism_replay(ir).witness
    assert isinstance(witness, DeterminismWitness)
    assert [claim.node for claim in witness.claims] == [node["id"] for node in canonical["nodes"]]


# ── Appendix B §B.3: the warning grammar ─────────────────────────────────────────────────


def test_the_remediation_is_the_appendix_b_closing_paragraph() -> None:
    for condition in (SEED_UNPINNED, TEMPERATURE_UNPINNED):
        remediation = render_remediation(condition)
        assert remediation.startswith("The claim is recorded.")
        assert remediation in render_warning(
            condition,
            DeterminismNodeLocation(kind="node", node="n", annotation="deterministic", seed=1),
            ("external",),
        )


def test_the_tutorial_conformance_anchor_renders_verbatim() -> None:
    """Appendix B §B.3: T-2 at ``classify_request``/``seed=42``/``external``/no temperature.

    Line wrapping is not part of the comparison — B.3's fenced blocks are hard-wrapped for
    the spec page, and the display width belongs to whatever renders the warning (D-12).
    """
    rendered = render_warning(
        TEMPERATURE_UNPINNED,
        DeterminismNodeLocation(
            kind="node", node="classify_request", annotation="deterministic", seed=42
        ),
        ("network", "external"),
    )
    assert rendered.splitlines()[0] == WARNING_HEADER
    assert rendered.split("\n\n")[1] == (
        "'classify_request' is @gebra.deterministic(seed=42), but its effects include "
        '"external": it calls a remote LLM provider. Determinism depends on the provider '
        "honouring the seed at temperature=0, and most providers do NOT guarantee strict "
        "seed reproducibility. 'temperature' is not pinned in the node's configuration."
    )


def test_a_pinned_nonzero_temperature_changes_the_final_sentence() -> None:
    """B.3's stated variant, on the fixture that exercises it (``negative-02``)."""
    rendered = render_warning(
        TEMPERATURE_UNPINNED,
        DeterminismNodeLocation(
            kind="node",
            node="extract_preferences",
            annotation="deterministic",
            seed=7,
            temperature=0.7,
        ),
        ("network", "external"),
    )
    assert "'temperature' is pinned to 0.7, not 0, in the node's configuration." in rendered
    assert "'temperature' is not pinned" not in rendered


def test_the_seed_unpinned_rendering_names_the_evidence_tag() -> None:
    rendered = render_warning(
        SEED_UNPINNED,
        DeterminismNodeLocation(
            kind="node",
            node="classify_intent",
            annotation="deterministic",
            form="bare-boolean",
            effects=("network",),
        ),
        ("network",),
    )
    assert rendered.split("\n\n")[1] == (
        "'classify_intent' is @gebra.deterministic, but its effects include \"network\": it "
        "calls a remote LLM provider. Determinism depends on the provider honouring a seed "
        "at temperature=0, and no seed is pinned in the node's configuration."
    )


def test_every_rendering_states_the_severity_and_the_claim_class() -> None:
    """B.1/B.3: a HEURISTIC advisory must never read as a proof-backed finding."""
    assert WARNING_HEADER.endswith("WARNING (HEURISTIC)")
    # honest-claims: allow: B.1's banned phrasings, quoted to assert their absence
    for banned in ("proves determinism", "guaranteed reproducible", "verified agent behavior"):
        for condition in (SEED_UNPINNED, TEMPERATURE_UNPINNED):
            assert banned not in render_remediation(condition).lower()


def test_rendering_refuses_a_node_with_no_llm_evidence() -> None:
    """Both templates open with "its effects include …" — there is no reading without one."""
    with pytest.raises(ValueError, match="LLM-backed"):
        render_warning(
            SEED_UNPINNED,
            DeterminismNodeLocation(kind="node", node="n", annotation="deterministic"),
            ("billable",),
        )


# ── Registry integration: the chain the card is named for ────────────────────────────────


def test_dispatch_runs_p08_through_the_property_registry() -> None:
    """``run_property`` is the registry-driven surface ``verify()`` will aggregate."""
    assert is_implemented("determinism-replay")
    answer = run_property("determinism-replay", _ir_of(NEGATIVES[1]))
    assert isinstance(answer, PropertyReport)
    assert answer == _expected_report(NEGATIVES[1])


def test_every_wedge_slug_is_wired_and_the_eight_stay_deferred() -> None:
    """The wedge is complete (VAL-07 wired P-02, the last of the five); the eight are not.

    Retires ``test_the_wedge_slugs_that_have_not_landed_are_still_honest_about_being_unwired``
    on its own instruction — its unwired set is empty now, and it asked to be deleted
    deliberately rather than left passing vacuously. What remains worth asserting from it:
    the non-wedge absence is still honest, and no wedge slug answers with a marker.
    """
    assert all(is_implemented(slug) for slug in WEDGE_SLUGS)
    marker = run_property("retry-coherence", _ir(_node("a")))
    assert isinstance(marker, NotImplementedMarker)
    assert marker.status == "deferred-to-phase-1"


def test_the_grades_are_read_off_the_registry_never_restated() -> None:
    """§8.3: every P-08 record is ``warning``/``heuristic``, on the primary and on co-findings."""
    report = check_determinism_replay(
        _ir(
            _node("alpha", deterministic=True, effect=("external",)),
            _node("bravo", deterministic={"seed": 1}, effect=("network",)),
        )
    )
    failure = report.failure
    assert isinstance(failure, Failure)
    assert (failure.severity, failure.claim_class) == ("warning", "heuristic")
    assert failure.co_failures is not None
    for record in failure.co_failures:
        assert isinstance(record, CoFailure)
        assert (record.severity, record.claim_class) == ("warning", "heuristic")


def test_the_validator_emits_only_the_two_conditions_section_8_names() -> None:
    """The §0.4 closed set, from P-08's side: no other name can leave this validator."""
    emitted = set()
    for relative in FIXTURES:
        report = check_determinism_replay(_ir_of(relative))
        if report.failure is not None:
            emitted.add(report.failure.property_condition)
            emitted.update(co.property_condition for co in report.failure.co_failures or ())
    assert emitted == {SEED_UNPINNED, TEMPERATURE_UNPINNED}


def test_annotations_built_in_python_take_the_same_path_as_loaded_ones() -> None:
    """The validator reads models, not documents — the construction route is not special."""
    ir = WorkflowIR(
        ir_version="1.0",
        entry="llm",
        finish="llm",
        nodes=(Node(id="llm", annotations=Annotations(deterministic=True, effect=("external",))),),
        edges=(),
    )
    report = check_determinism_replay(ir)
    assert report.failure is not None
    assert report.failure.property_condition == SEED_UNPINNED
