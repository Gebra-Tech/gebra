"""The extractor-conformance suite — IR-SPEC §1.2/§1.3 layer 2, SOW §2 criterion 3 (EX-14).

For every workflow in :data:`tests.sample_workflows.conformance.CASES`, extraction followed
by canonical serialization must be **byte-identical** to the committed golden and the
``graph_version`` **string-equal** to the committed digest
(``tests/extraction/golden/conformance/``, WA-05 lifecycle — see the README there). §1.2:
"There is no partial conformance in either class: a single differing byte in canonical form
is non-conformance." That sentence is *executed* here rather than quoted: the tamper tests
run the suite's own comparison against a one-byte substitution at every byte position of
every golden and against a JSON-semantically-equal byte-different variant, so a comparison
loose enough to tolerate either would fail this file, not pass it quietly.

Three tiers, by what they need:

* **Extraction comparisons** — the conformance operation itself, gated where a case's
  golden is substrate-gated (exactly one is; the gate and its named reason are themselves
  under test).
* **Committed-pair checks** — self-consistency and tamper sensitivity of the golden files
  alone, no extraction, so they hold on every matrix cell unconditionally.
* **Coverage checks** — the EX-14 acceptance floor (three object families, all four edge
  kinds, both ``ir_version`` values, every annotation-resolution tier, the digest slots,
  the runtime block, the three Σ value forms), asserted against the committed documents so
  the set cannot quietly narrow.

WA-07: no workflow node, router, tool or model is ever invoked — every fixture body is
armed and the autouse fixture asserts the ledger stayed empty. This card adds no new
extraction path, so no new tripwire is owed here: every path this suite reaches already
carries its own (``tests/test_never_invokes.py`` is the index), and the arming below is a
redundant guard on top of those, not their replacement.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from gebra.extraction import extract
from gebra.ir.canonical import canonical_bytes
from tests import substrate
from tests.sample_workflows import conformance as cf

if TYPE_CHECKING:
    from gebra.extraction import ExtractionEnvelope

GOLDEN_DIR = Path(__file__).parent / "golden" / "conformance"

#: Every case, in one stable order — the registry is the quantifier everywhere below.
CASE_NAMES = sorted(cf.CASES)

#: The OCI digest grammar (IR-SPEC §6.1 step 8).
DIGEST_GRAMMAR = re.compile(r"sha256:[a-f0-9]{64}")


def _extraction_params() -> list[Any]:
    """One param per case, wearing its substrate gate as a *named* skip (EX-17 discipline)."""
    params: list[Any] = []
    for name in CASE_NAMES:
        gate = cf.CASES[name].gate
        if gate is not None and not gate.available:
            params.append(pytest.param(name, marks=pytest.mark.skip(reason=gate.reason)))
        else:
            params.append(pytest.param(name))
    return params


EXTRACTION_PARAMS = _extraction_params()


@pytest.fixture(autouse=True)
def _nothing_was_executed() -> Any:
    """Every test in this file asserts the armed fixtures were read, never run."""
    del cf.TRIPPED[:]
    yield
    assert cf.TRIPPED == []


def extracted(name: str, tmp_path: Path) -> ExtractionEnvelope:
    """Extract one conformance case, writing its sidecar (if any) to an explicit path."""
    case = cf.CASES[name]
    workflow = case.build()
    if case.sidecar is None:
        return extract(workflow)
    sidecar = tmp_path / "gebra.toml"
    sidecar.write_text(case.sidecar, encoding="utf-8")
    return extract(workflow, sidecar=sidecar)


def committed_canonical(name: str) -> bytes:
    """The committed canonical serialization, byte for byte."""
    return (GOLDEN_DIR / f"{name}.canonical.json").read_bytes()


def committed_digest(name: str) -> str:
    """The committed ``graph_version``."""
    return (GOLDEN_DIR / f"{name}.digest").read_text(encoding="utf-8").strip()


def document(name: str) -> dict[str, Any]:
    """The committed canonical document, parsed — for the coverage checks only."""
    loaded = json.loads(committed_canonical(name))
    assert isinstance(loaded, dict)
    return loaded


# ── The conformance operation (IR-SPEC §1.2: extract, canonicalize, hash, compare) ───────


@pytest.mark.parametrize("name", EXTRACTION_PARAMS)
def test_extraction_reproduces_the_committed_canonical_bytes(name: str, tmp_path: Path) -> None:
    """Byte-identical canonical serialization — the §1.2 extractor-conformance clause.

    ``bytes`` equality against the committed file, never a parsed-JSON comparison: surface
    facts a parse would forgive (member order, whitespace, number spelling) are exactly what
    canonical form pins.
    """
    envelope = extracted(name, tmp_path)

    assert canonical_bytes(envelope.ir) == committed_canonical(name)


@pytest.mark.parametrize("name", EXTRACTION_PARAMS)
def test_extraction_reproduces_the_committed_digest(name: str, tmp_path: Path) -> None:
    """String-equal ``graph_version`` — §6.1 step 9's recompute-and-string-compare."""
    envelope = extracted(name, tmp_path)

    assert envelope.graph_version() == committed_digest(name)


@pytest.mark.parametrize("name", EXTRACTION_PARAMS)
def test_extraction_is_the_same_document_twice(name: str, tmp_path: Path) -> None:
    """Two extractions of one unchanged source program agree byte for byte.

    The committed golden pins this run against the repository; this pins the run against
    itself, so a nondeterministic serialization cannot hide behind a lucky first match.
    """
    first = canonical_bytes(extracted(name, tmp_path).ir)
    second = canonical_bytes(extracted(name, tmp_path).ir)

    assert first == second


# ── One-byte tamper: the comparison rejects every single-byte variant ────────────────────


@pytest.mark.parametrize("name", EXTRACTION_PARAMS)
def test_a_substitution_at_every_byte_position_fails_the_byte_comparison(
    name: str, tmp_path: Path
) -> None:
    """A single differing byte is non-conformance — a substitution at every byte position.

    The comparison under test is the one the green test runs (``bytes`` equality between
    the extracted canonical serialization and the golden), applied to a golden variant
    differing in exactly one byte, at each position in turn. Not sampled: the loop covers
    every position, so there is no byte position of any committed golden whose corruption
    this suite would tolerate.
    """
    produced = canonical_bytes(extracted(name, tmp_path).ir)
    committed = committed_canonical(name)
    assert produced == committed

    for index in range(len(committed)):
        tampered = bytearray(committed)
        tampered[index] ^= 0x01
        assert produced != bytes(tampered)


@pytest.mark.parametrize("name", EXTRACTION_PARAMS)
def test_a_json_equal_but_byte_different_golden_fails_the_comparison(
    name: str, tmp_path: Path
) -> None:
    """The comparison is byte-level, not structural — §1.2's "byte-identical" taken at its word.

    A trailing newline leaves a JSON document semantically identical, and RFC 8785 §3.2.4
    is precisely the rule that canonical bytes contain no such freedom. A suite that parsed
    both sides before comparing would pass this variant; this one must not.
    """
    produced = canonical_bytes(extracted(name, tmp_path).ir)
    committed = committed_canonical(name)
    padded = committed + b"\n"

    assert json.loads(padded) == json.loads(committed)
    assert produced != padded


@pytest.mark.parametrize("name", EXTRACTION_PARAMS)
def test_a_substitution_at_every_digest_position_fails_the_string_compare(
    name: str, tmp_path: Path
) -> None:
    """The digest comparison is a full string compare — every position load-bearing.

    One character substituted per position, each position in turn, prefix included.
    """
    produced = extracted(name, tmp_path).graph_version()
    committed = committed_digest(name)
    assert produced == committed

    for index, original in enumerate(committed):
        substitute = "0" if original != "0" else "1"
        tampered = committed[:index] + substitute + committed[index + 1 :]
        assert produced != tampered


@pytest.mark.parametrize("name", CASE_NAMES)
def test_the_committed_pair_is_self_consistent_and_tamper_evident(name: str) -> None:
    """The pair guards itself, with no extraction — so this holds on every matrix cell.

    The digest file must be the SHA-256 of the canonical file (§6.1 steps 7-8), rendered in
    the OCI grammar; and for a one-byte substitution at each position of the canonical
    bytes the recomputed digest must stop matching. Tampering either file alone is
    therefore caught by the pair itself, even on a cell where the gated extraction
    comparison is skipped.
    """
    committed = committed_canonical(name)
    digest = committed_digest(name)

    assert DIGEST_GRAMMAR.fullmatch(digest)
    assert f"sha256:{hashlib.sha256(committed).hexdigest()}" == digest

    for index in range(len(committed)):
        tampered = bytearray(committed)
        tampered[index] ^= 0x01
        assert f"sha256:{hashlib.sha256(bytes(tampered)).hexdigest()}" != digest


def test_the_conformance_fixtures_are_armed() -> None:
    """Every invokable body in the registry records itself and raises — proven by firing it.

    A tripwire nobody trips proves nothing (the standard the per-path suites state and this
    file inherits): without this control, a future edit that de-armed one body — say a
    plausible return replacing ``_trip`` during a golden retake — would leave the autouse
    ledger check green while the guard it claims was silently dead. Every builder-held
    callable is reached by walking the built graphs (nodes and branch routers, the compiled
    case through its ``.builder``); the callables no builder holds are fired by name. Both
    halves of the design are asserted: the raise, and the ledger entry recorded *before*
    it — the property that keeps a swallowed raise visible.
    """
    fired = 0

    def fire(function: Any, *arguments: Any) -> None:
        nonlocal fired
        before = len(cf.TRIPPED)
        with pytest.raises(cf.ConformanceSentinelError):
            function(*arguments)
        assert len(cf.TRIPPED) == before + 1
        fired += 1

    for case in cf.CASES.values():
        if case.family == "lcel":
            continue
        built = case.build()
        builder = built if case.family == "builder" else built.builder
        callables: list[Any] = [spec.runnable for spec in builder.nodes.values()]
        callables += [
            spec.path for branches in builder.branches.values() for spec in branches.values()
        ]
        for runnable in callables:
            function = runnable
            while hasattr(function, "func"):
                function = function.func
            fire(function, {})

    # The callables no builder holds: the LCEL bodies, the captured dep, the branch
    # condition, the tool implementation, and every armed member of the chat model.
    fire(cf._digest_topic, {})
    fire(cf._wants_prose, {})
    # `CAPTURED_FORMATTER` is declared `Runnable[Any, Any]`; the concrete `RunnableLambda`
    # holds the wrapped callable in `.func`, which the declared type does not carry.
    fire(getattr(cf.CAPTURED_FORMATTER, "func"), {})  # noqa: B009
    fire(cf._lookup_impl, "key")
    model = cf.ConformanceChatModel()
    fire(model._generate, [])
    fire(model._stream)
    for accessor in ("_llm_type", "_identifying_params", "lc_attributes", "lc_secrets"):
        fire(getattr, model, accessor)

    assert fired >= 25
    del cf.TRIPPED[:]


# ── The golden directory and the gate stay honest ────────────────────────────────────────


def test_the_golden_directory_is_exactly_the_registry_set() -> None:
    """No stale golden, no missing golden, and the WA-05 README is present.

    Set equality in both directions: a case renamed in the registry cannot leave its old
    pair behind as an unread file, and a case added cannot land without its pair.
    """
    expected = (
        {f"{name}.canonical.json" for name in cf.CASES}
        | {f"{name}.digest" for name in cf.CASES}
        | {"README.md"}
    )
    # Hidden entries (`.DS_Store` and kin) are OS droppings, not goldens — tolerated so a
    # file browser visit cannot redden the suite; nothing hidden is ever a golden.
    present = {
        path.name
        for path in GOLDEN_DIR.iterdir()
        if path.name != "__pycache__" and not path.name.startswith(".")
    }

    assert present == expected


def test_the_one_substrate_gate_is_stated_and_names_its_boundary() -> None:
    """Exactly one case is gated, the gate is derived from the shared substrate table, and
    its reason names the mechanism, the exact pin, and what is actually installed — EX-17's
    "a skip must say what it skips and why".

    The set equality is the composition claim from the golden README: every *other* golden
    holds on every cell of the frozen matrix, so a second gate appearing here is a
    composition change that must be argued, not slipped in. The gate is exact-pin equality,
    not a floor, because ``config_digest`` embeds ``metadata.lc_versions`` — the installed
    core's own version string — so the committed bytes cannot hold at any other release.
    """
    gated = {name: case.gate for name, case in cf.CASES.items() if case.gate is not None}

    assert set(gated) == {"lcel-tool-bound"}
    gate = gated["lcel-tool-bound"]
    assert gate is not None
    assert gate.available is (substrate.LANGCHAIN_CORE_VERSION == cf.TOOL_BOUND_CORE_PIN)
    assert "lc_versions" in gate.reason
    assert (
        ".".join(map(str, cf.TOOL_BOUND_CORE_PIN)) in gate.reason
    )  # the pin itself, not a hardcoded string (PD-049 alignment)
    assert ".".join(map(str, substrate.LANGCHAIN_CORE_VERSION)) in gate.reason


# ── Coverage: the acceptance floor, asserted against the committed documents ─────────────


def test_coverage_spans_the_three_object_families() -> None:
    """INTROSPECTION-SPEC §2's families, all present and correctly claimed.

    The family labels are load-bearing (the coverage claim quantifies over them), so each
    is also cross-checked against its committed document: a compiled case must carry the
    ``runtime`` block only the §4 path emits, and an LCEL case must use the §5.2 synthetic
    id grammar.
    """
    assert {case.family for case in cf.CASES.values()} == {"builder", "compiled", "lcel"}

    for name, case in cf.CASES.items():
        payload = document(name)
        if case.family == "compiled":
            assert "runtime" in payload
        elif case.family == "lcel":
            assert all(node["id"].startswith("%") for node in payload["nodes"])
        else:
            assert "runtime" not in payload


def test_coverage_spans_all_four_edge_kinds_and_both_ir_versions() -> None:
    """``normal``/``conditional``/``send`` (ir 1.0) and ``dynamic`` (ir 1.1, DEC-28)."""
    kinds = {edge.get("kind", "normal") for name in CASE_NAMES for edge in document(name)["edges"]}
    versions = {document(name)["ir_version"] for name in CASE_NAMES}

    assert kinds == {"normal", "conditional", "send", "dynamic"}
    assert versions == {"1.0", "1.1"}


def test_the_resolution_golden_covers_every_annotation_tier() -> None:
    """One node per ANNOTATION-API-SPEC §3 tier, each pinned by the slot only its tier sets.

    The sidecar-only slots (``compensation``, ``idempotent``) prove the sidecar tier is in
    the golden — a decorator cannot declare them — and the bare defaults on
    ``opaque_step``/``plain_step`` prove the D-011 floors, which are honest-absence records
    rather than claims.
    """
    nodes = {node["id"]: node["annotations"] for node in document("annotations-resolved")["nodes"]}

    assert nodes["declared_step"]["deterministic"] == {"seed": 11}
    assert nodes["declared_step"]["input"] == ["query"]
    assert nodes["filed_step"]["compensation"] == {"hook": "declared_step"}
    assert nodes["filed_step"]["idempotent"] == {"key": "query"}
    assert nodes["filed_step"]["output"] == ["ledger"]
    assert nodes["inferred_step"]["input"] == ["query"]
    assert nodes["inferred_step"]["output"] == ["summary"]
    assert nodes["search_tool"]["args_schema"]["title"] == "LookupArgs"
    assert nodes["opaque_step"] == {"effect": ["write"]}
    assert nodes["plain_step"] == {"pure": True}


def test_the_lcel_goldens_carry_the_digest_slots() -> None:
    """``prompt_digest`` on the prompt leaves; ``config_digest`` on the bound model.

    The tool-bound document is read from its committed golden even where the extraction
    comparison is gated: what the set *covers* is a fact about the committed files.
    """
    composite = {n["id"]: n["annotations"] for n in document("lcel-composite")["nodes"]}
    bound = {n["id"]: n["annotations"] for n in document("lcel-tool-bound")["nodes"]}

    assert DIGEST_GRAMMAR.fullmatch(composite["%seq[0]"]["prompt_digest"])
    assert DIGEST_GRAMMAR.fullmatch(bound["%seq[0]"]["prompt_digest"])
    assert DIGEST_GRAMMAR.fullmatch(bound["%seq[1]/%bind[0]"]["config_digest"])
    assert "config_digest" not in bound["%seq[1]"]


def test_the_composite_golden_spans_six_synthetic_kinds() -> None:
    """The §5.2 grammar coverage the README claims, counted off the committed ids."""
    ids = {node["id"] for node in document("lcel-composite")["nodes"]}
    tokens = {token.split("[", 1)[0] for identifier in ids for token in identifier.split("/")}

    assert tokens == {"%seq", "%map", "%lambda", "%branch", "%retry", "%bind"}


def test_the_compiled_golden_carries_the_runtime_block() -> None:
    """§3.7: interrupt gates and checkpointer presence, exactly as compiled."""
    runtime = document("compiled-runtime")["runtime"]

    assert runtime == {
        "checkpointer": {"present": True},
        "interrupts": {"after": ["triage"], "before": ["execute"]},
    }


def test_the_surface_golden_carries_all_three_state_value_forms() -> None:
    """§6.3's Σ representations: bare type string, reducer object, optional-flag object."""
    state = document("builder-surface")["state"]

    assert state["audit"] == "str"
    assert state["notes"] == {"reducer": "_operator.add", "type": "list[str]"}
    assert state["query"] == {"optional": True, "type": "str"}


def test_the_surface_golden_escapes_the_node_id_grammar() -> None:
    """§5.1: a ``/`` in an authored name is ``%2F`` in the id, everywhere the id appears."""
    payload = document("builder-surface")

    assert any(node["id"] == "review%2Fstep" for node in payload["nodes"])
    conditional = next(e for e in payload["edges"] if e.get("kind") == "conditional")
    assert conditional["path_map"]["deep"] == "review%2Fstep"
