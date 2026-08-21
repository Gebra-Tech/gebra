"""Drift tests 1-6 — VERSION-COMPAT §3, executed row by row (GOV-05).

Each §3-named test carries the row's three parts, in order:

* **Hard ⊇ surface preconditions** — asserted directly against the live substrate object
  (the builder, its specs, ``Send``, ``RetryPolicy``, the drawn graph). A miss here is
  drift in the substrate's shape and fails the test, which blocks the frozen matrix cell.
* **Hard golden compare** — the fixture is driven through ``gebra.extract()`` and the core
  IR is compared against the committed golden: canonical bytes **byte-identical**,
  ``graph_version`` **string-equal** (the DEC-10 equivalence; the same §1.2 operation the
  conformance suite runs). Any inequality is drift by definition (§3: tolerated additive
  churn never reaches the closed core IR).
* **Paired soft assertion** — an exact-set compare of the same surface against the
  recorded inventory (:mod:`tests.version_drift.inventory`). A soft-only divergence never
  fails the test: it is collected and emitted as a CI annotation by the package
  ``conftest.py`` (§3: the cell stays green; warnings never live only in logs).

On the twelve frozen matrix cells these tests run through the ordinary blocking ``pytest``
gate; on the single ``--pre`` cell the job-level ``continue-on-error`` (GOV-04) is the
``xfail(strict=False)`` semantics — the tests themselves are identical everywhere.

The suite-integrity tests at the bottom keep the evidence honest: the committed golden
pairs are self-consistent and tamper-evident without extraction, the golden directory is
exactly the registry set, the registry names exactly the six §3 tests, and every armed
fixture body is proven live by firing it.

WA-07: no workflow node, router, or subgraph is ever invoked — every fixture body is armed
and the autouse ledger check runs per test. ``compile()`` (test 4's fixture factories) is
graph construction, not execution; ``get_graph(xray=True)`` is the row-4 substrate call
under test, performed under the same armed ledger.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from collections.abc import Set as AbstractSet
from pathlib import Path
from typing import Any

import pytest
from langgraph.graph import END
from langgraph.pregel import Pregel
from langgraph.types import RetryPolicy, Send

from gebra.extraction import ExtractionEnvelope, extract
from gebra.ir.canonical import canonical_bytes
from tests.version_drift import drawable, inventory, workflows

GOLDEN_DIR = Path(__file__).parent / "golden"

#: Every case, in one stable order — the registry is the quantifier everywhere below.
CASE_NAMES = sorted(workflows.CASES)

#: The OCI digest grammar (IR-SPEC §6.1 step 8).
DIGEST_GRAMMAR = re.compile(r"sha256:[a-f0-9]{64}")

#: The §3 rows this card owns, by their spec-fixed test names (tests 7-12 are GOV-06).
SECTION_3_TESTS = frozenset(
    {
        "test_drift_builder_nodes_spec_shape",
        "test_drift_builder_branches_shape",
        "test_drift_builder_edges_waiting_edges",
        "test_drift_get_graph_drawable_fidelity",
        "test_drift_send_signature",
        "test_drift_retry_policy_fields",
    }
)


def extracted(name: str) -> ExtractionEnvelope:
    """One drift case, built live and driven through extraction."""
    return extract(workflows.CASES[name].build())


def committed_canonical(name: str) -> bytes:
    """The committed canonical core-IR serialization, byte for byte."""
    return (GOLDEN_DIR / f"{name}.canonical.json").read_bytes()


def committed_digest(name: str) -> str:
    """The committed ``graph_version``."""
    return (GOLDEN_DIR / f"{name}.digest").read_text(encoding="utf-8").strip()


def committed_drawable() -> dict[str, Any]:
    """The committed drawable golden for test 4 (counts + per-edge conditional flags)."""
    loaded = json.loads(
        (GOLDEN_DIR / "drawable-fidelity.drawable.json").read_text(encoding="utf-8")
    )
    assert isinstance(loaded, dict)
    return loaded


def assert_matches_golden(name: str, envelope: ExtractionEnvelope) -> None:
    """The §3 golden-equality contract: byte-identical canonical form, string-equal digest.

    ``bytes`` equality, never a parsed-JSON comparison — surface facts a parse would
    forgive (member order, whitespace, number spelling) are exactly what canonical form
    pins; the digest compare is the same fact through DEC-10's recompute-and-string-compare.
    """
    assert canonical_bytes(envelope.ir) == committed_canonical(name)
    assert envelope.graph_version() == committed_digest(name)


def innermost(wrapped: Any) -> Any:
    """The callable inside the substrate's wrapper chain, by the ``.func`` convention.

    ``BranchSpec.path`` and ``StateNodeSpec.runnable`` both arrive wrapped (a
    ``RunnableCallable`` at the pinned substrate) with the author's callable at ``.func``
    — the same convention the extractor's ANNOTATION §6 wrapper walk reads. A substrate
    that holds the bare callable unwraps in zero steps.
    """
    while hasattr(wrapped, "func"):
        wrapped = wrapped.func
    return wrapped


# ── The six §3 rows ──────────────────────────────────────────────────────────────────────


def test_drift_builder_nodes_spec_shape() -> None:
    """§3 test 1 — ``StateGraph.nodes: str → StateNodeSpec`` and the spec's field floor.

    Hard: the mapping shape; the spec type's name; the field set ⊇ {runnable,
    input_schema, retry_policy, cache_policy, metadata, ends}; extracted core IR == golden
    (which is also the closed-IR fact: the metadata value and any additive substrate field
    never reach the document). Soft: exact field set == the recorded line inventory.
    """
    builder = workflows.build_nodes_spec()
    nodes = builder.nodes
    assert isinstance(nodes, Mapping)
    assert set(nodes) == {"summarize"}
    assert all(isinstance(name, str) for name in nodes)
    spec = nodes["summarize"]
    assert type(spec).__name__ == "StateNodeSpec"
    observed = inventory.member_names(spec)
    assert observed >= {
        "runnable",
        "input_schema",
        "retry_policy",
        "cache_policy",
        "metadata",
        "ends",
    }

    assert_matches_golden("nodes-spec", extracted("nodes-spec"))

    inventory.soft_exact_set(
        "test_drift_builder_nodes_spec_shape", "state-node-spec-fields", observed
    )


def test_drift_builder_branches_shape() -> None:
    """§3 test 2 — ``.branches: dict[node, dict[name, BranchSpec]]``, path + resolvable ends.

    Hard: the two-level mapping shape; the spec type's name; the **path callable** — the
    fixture's own router exposed at ``path``, reached through the substrate's standard
    ``.func`` wrapper chain (the member itself is a ``RunnableCallable`` at the pinned
    substrate, which is how the extractor's §6 wrapper walk reads it too); ``ends``
    mapping resolvable against declared nodes ∪ {END}; conditional-edge IR == golden
    (the P-01/P-02 input surface). Soft: exact ``BranchSpec`` field set == recorded.
    """
    builder = workflows.build_branches()
    branches = builder.branches
    assert isinstance(branches, Mapping)
    assert set(branches) == {"classify"}
    named = branches["classify"]
    assert isinstance(named, Mapping)
    assert set(named) == {"route_ticket"}
    spec = named["route_ticket"]
    assert type(spec).__name__ == "BranchSpec"
    assert innermost(spec.path) is workflows.route_ticket
    ends = spec.ends
    assert isinstance(ends, Mapping)
    assert ends == {"hot": "escalate", "cold": "resolve"}
    assert set(ends.values()) <= set(builder.nodes) | {END}

    assert_matches_golden("branches", extracted("branches"))

    inventory.soft_exact_set(
        "test_drift_builder_branches_shape", "branch-spec-fields", inventory.member_names(spec)
    )


def test_drift_builder_edges_waiting_edges() -> None:
    """§3 test 3 — ``.edges`` as (start, end) pairs; the join in ``.waiting_edges`` only.

    Hard: ``.edges`` is a set of string 2-tuples; the multi-source join group sits in
    ``.waiting_edges`` and contributes no plain pair to ``.edges``; join IR == golden
    (both sources land in ``finish``, per INTROSPECTION-SPEC §3's ``.waiting_edges``
    row — one incidence per source, END routed to ``finish``).
    Soft: exact public instance-attribute set of the builder == recorded — the wiring
    store itself is the surface a new topology member would appear on.
    """
    builder = workflows.build_waiting_edges()
    edges = builder.edges
    assert isinstance(edges, AbstractSet)
    for pair in edges:
        assert isinstance(pair, tuple)
        assert len(pair) == 2
        assert all(isinstance(endpoint, str) for endpoint in pair)
    waiting = builder.waiting_edges
    assert isinstance(waiting, AbstractSet)
    assert (("check_stock", "check_price"), END) in waiting
    assert ("check_stock", END) not in edges
    assert ("check_price", END) not in edges

    assert_matches_golden("waiting-edges", extracted("waiting-edges"))

    inventory.soft_exact_set(
        "test_drift_builder_edges_waiting_edges",
        "state-graph-instance-attrs",
        inventory.public_instance_attrs(builder),
    )


def test_drift_get_graph_drawable_fidelity() -> None:
    """§3 test 4 — the drawable graph against its golden and against the builder truth.

    Hard, in row order: the drawn surface shape (``.nodes`` mapping, ``.edges`` with
    ``source``/``target``/``conditional``); node/edge counts + per-edge conditional
    booleans == the committed drawable golden, every endpoint keyed by the ledger-§5 path
    id (never a raw drawing id); the drawing equals the builder-derived IR after stripping
    the per-level ``__start__``/``__end__`` pseudo-nodes and folding the xray'd subgraph
    expansion back to the parent granularity (DEC-19); and the builder-derived core IR
    itself == golden. Soft: exact drawable ``Node``/``Edge`` member sets == recorded
    (langchain-core's surface — the hottest-churn distribution on the matrix).

    The drawing is called on a fixture composed so that no route a drawing can take
    reaches user code (the DEC-19 hazard routes) — and that closure is *asserted* before
    the call, not merely described: no checkpointer and no per-node ``cache_policy``, so a
    later fixture edit cannot quietly hand the drawing an unarmed invokable. Every body
    and router the fixture does carry is armed under the package ledger.
    """
    compiled = workflows.build_drawable_compiled()
    assert getattr(compiled, "checkpointer", None) is None
    for spec in workflows.build_drawable().nodes.values():
        assert getattr(spec, "cache_policy", None) is None
    drawn = compiled.get_graph(xray=True)
    nodes = getattr(drawn, "nodes", None)
    assert isinstance(nodes, Mapping)
    assert all(isinstance(identifier, str) for identifier in nodes)
    triples = drawable.drawn_edges(drawn)
    assert triples

    assert drawable.drawable_payload(drawn) == committed_drawable()

    envelope = extracted("drawable-fidelity")
    document = json.loads(canonical_bytes(envelope.ir))
    assert drawable.folded_topology(drawn) == drawable.ir_topology(document)

    assert_matches_golden("drawable-fidelity", envelope)

    sample_node = next(iter(nodes.values()))
    sample_edge = next(iter(drawn.edges))
    inventory.soft_exact_set(
        "test_drift_get_graph_drawable_fidelity",
        "drawable-node-fields",
        inventory.member_names(sample_node),
    )
    inventory.soft_exact_set(
        "test_drift_get_graph_drawable_fidelity",
        "drawable-edge-fields",
        inventory.member_names(sample_edge),
    )


def test_drift_send_signature() -> None:
    """§3 test 5 — ``Send(node, arg)`` constructs; ``.node``/``.arg``; extras tolerated.

    Hard: the two-argument construction; both members readable back; the ⊇ member floor
    (which is what "extra fields tolerated" means — ``.timeout`` and any later additive
    member never fail this half); dynamic-dispatch edge set == golden (the P-09
    send-template input surface). Soft: exact ``Send`` member set == recorded.
    """
    probe = Send("book_leg", {"leg": "outbound"})
    assert probe.node == "book_leg"
    assert probe.arg == {"leg": "outbound"}
    observed = inventory.member_names(probe)
    assert observed >= {"node", "arg"}

    assert_matches_golden("send-signature", extracted("send-signature"))

    inventory.soft_exact_set("test_drift_send_signature", "send-members", observed)


def test_drift_retry_policy_fields() -> None:
    """§3 test 6 — the ``RetryPolicy`` field floor and the accepted policy sequence.

    Hard: field set ⊇ the six A2/A1 fields; ``add_node`` accepted a *sequence* of policies
    (held intact on the spec — a single policy is itself a ``Sequence`` because the class
    is a ``NamedTuple``, so the shape is pinned by exclusion and length); retry IR block ==
    golden (the decision D-012 input surface: first-policy projection per DEC-18, with the
    flattening recorded in the envelope, outside hash scope). Soft: exact field set ==
    recorded.
    """
    observed = inventory.member_names(RetryPolicy())
    assert observed >= {
        "initial_interval",
        "backoff_factor",
        "max_interval",
        "max_attempts",
        "jitter",
        "retry_on",
    }
    builder = workflows.build_retry_policy()
    declared = builder.nodes["fetch_with_backoff"].retry_policy
    assert isinstance(declared, Sequence)
    assert not isinstance(declared, RetryPolicy)
    assert len(declared) == 2
    assert all(isinstance(policy, RetryPolicy) for policy in declared)

    assert_matches_golden("retry-policy", extracted("retry-policy"))

    inventory.soft_exact_set("test_drift_retry_policy_fields", "retry-policy-fields", observed)


# ── Suite integrity: the committed evidence guards itself ────────────────────────────────


@pytest.mark.parametrize("name", CASE_NAMES)
def test_the_committed_pair_is_self_consistent_and_tamper_evident(name: str) -> None:
    """The pair guards itself, with no extraction — so this holds on every matrix cell.

    The digest file must be the SHA-256 of the canonical file (IR-SPEC §6.1 steps 7-8) in
    the OCI grammar, and a one-byte substitution at each canonical byte position must stop
    the recomputed digest matching — tampering either file alone is caught by the pair.
    """
    committed = committed_canonical(name)
    digest = committed_digest(name)

    assert DIGEST_GRAMMAR.fullmatch(digest)
    assert f"sha256:{hashlib.sha256(committed).hexdigest()}" == digest

    for index in range(len(committed)):
        tampered = bytearray(committed)
        tampered[index] ^= 0x01
        assert f"sha256:{hashlib.sha256(bytes(tampered)).hexdigest()}" != digest


def test_the_golden_directory_is_exactly_the_registry_set() -> None:
    """No stale golden, no missing golden; the drawable golden and WA-05 README present."""
    expected = (
        {f"{name}.canonical.json" for name in workflows.CASES}
        | {f"{name}.digest" for name in workflows.CASES}
        | {"drawable-fidelity.drawable.json", "README.md"}
    )
    present = {
        path.name
        for path in GOLDEN_DIR.iterdir()
        if path.name != "__pycache__" and not path.name.startswith(".")
    }

    assert present == expected


def test_the_registry_names_exactly_the_six_section3_tests() -> None:
    """The registry ↔ §3 naming contract: six cases, six spec-fixed test names, all here."""
    named = {case.test for case in workflows.CASES.values()}

    assert named == SECTION_3_TESTS
    for test_name in named:
        assert callable(globals()[test_name])


def test_the_drift_fixtures_are_armed() -> None:
    """Every invokable body in the registry records itself and raises — proven by firing it.

    A tripwire nobody trips proves nothing: without this control, an edit de-arming one
    body (a plausible return replacing ``_trip`` during a golden retake) would leave the
    autouse ledger check green while the guard it claims was dead. Every builder-held
    callable is reached by walking the built graphs — nodes and branch routers, the
    subgraph through its own child builder — and both halves of the design are asserted:
    the raise, and the ledger entry recorded *before* it. The one runnable no unwrap
    reaches is the ``finalize`` subgraph node, which is a graph rather than a body; the
    walk asserts it is exactly that one, so the exemption cannot quietly widen.
    """
    fired = 0

    def fire(function: Any) -> None:
        nonlocal fired
        before = len(workflows.TRIPPED)
        with pytest.raises(workflows.DriftSentinelError):
            function({})
        assert len(workflows.TRIPPED) == before + 1
        fired += 1

    graphs = [case.build() for case in workflows.CASES.values()]
    graphs.append(workflows.build_editorial_child())
    subgraph_nodes: list[str] = []
    for builder in graphs:
        for name, spec in builder.nodes.items():
            function = innermost(spec.runnable)
            if isinstance(function, Pregel):
                subgraph_nodes.append(name)
                continue
            fire(function)
        for branches in builder.branches.values():
            for branch in branches.values():
                fire(innermost(branch.path))

    assert subgraph_nodes == ["finalize"]
    # 14 node bodies + 3 routers across the six cases and the child builder; a composition
    # change moves this constant in the same commit as its fixture.
    assert fired == 17
    del workflows.TRIPPED[:]
