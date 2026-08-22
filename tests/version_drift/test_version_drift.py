"""Drift tests 1-12 — VERSION-COMPAT §3, executed row by row (1-6 GOV-05; 7-12 GOV-06).

Each §3-named test carries the row's three parts, in order:

* **Hard ⊇ surface preconditions** — asserted directly against the live substrate object
  (the builder, its specs, ``Send``, ``RetryPolicy``, the drawn graph, the getters, the
  channels, the compiled attributes). A miss here is drift in the substrate's shape and
  fails the test, which blocks the frozen matrix cell.
* **Hard golden compare** — the fixture is driven through ``gebra.extract()`` and the core
  IR is compared against the committed golden: canonical bytes **byte-identical**,
  ``graph_version`` **string-equal** (the DEC-10 equivalence; the same §1.2 operation the
  conformance suite runs). Any inequality is drift by definition (§3: tolerated additive
  churn never reaches the closed core IR). Rows 4, 7 and 11 add a committed **document
  golden** beside the core IR (drawable payload, named-key schema projection, LCEL
  name-keyed topology).
* **Paired soft assertion** — an exact-set compare of the same surface against the
  recorded inventory (:mod:`tests.version_drift.inventory`). A soft-only divergence never
  fails the test: it is collected and emitted as a CI annotation by the package
  ``conftest.py`` (§3: the cell stays green; warnings never live only in logs).

Three rows carry **special semantics**, implemented here and dry-run-proven in
``test_review.py``:

* **Row 4, block-and-propose** — a drawable divergence *while the builder-derived IR is
  still golden* records the ``get-graph-demotion`` review proposal
  (:mod:`tests.version_drift.review`) before the blocking assertion fails; both failure
  branches still block the cell.
* **Row 8, 2.0-ceiling review** — a ``config_schema=`` construction that raises
  ``TypeError`` is the documented 2.0 removal observed: the ``major-version-review``
  proposal is recorded, then the cell blocks. A construction that works without the
  deprecation warning is ordinary hard drift (marker vanished) — blocked, no proposal.
* **Row 9, beta xfail** — the DeltaChannel variant runs ``xfail(strict=False)`` even on
  frozen cells: absent module (pre-1.2 lines) or moved behavior never blocks anything.

On the twelve frozen matrix cells these tests run through the ordinary blocking ``pytest``
gate; on the single ``--pre`` cell the job-level ``continue-on-error`` (GOV-04) is the
``xfail(strict=False)`` semantics — the tests themselves are identical everywhere.

The suite-integrity tests at the bottom keep the evidence honest: the committed golden
pairs are self-consistent and tamper-evident without extraction, the golden directory is
exactly the registry set, the registry names exactly the twelve §3 tests, the beta case
carries its non-strict xfail marker structurally, and every armed fixture body is proven
live by firing it.

WA-07: no workflow node, router, reducer or subgraph is ever invoked — every fixture body
is armed and the autouse ledger check runs per test. ``compile()`` (fixture factories and
the tests that read compiled surfaces) is graph construction, not execution;
``get_graph(xray=True)`` is the row-4 substrate call under test and the jsonschema getters
are row 7's, each performed under the same armed ledger.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import operator
import re
import typing
from collections.abc import Mapping, Sequence
from collections.abc import Set as AbstractSet
from pathlib import Path
from typing import Any

import pytest
from langgraph.channels.base import BaseChannel
from langgraph.graph import END, StateGraph
from langgraph.pregel import Pregel
from langgraph.types import RetryPolicy, Send

from gebra.extraction import ExtractionEnvelope, extract
from gebra.ir.canonical import canonical_bytes
from tests import substrate
from tests.version_drift import documents, drawable, inventory, review, workflows

GOLDEN_DIR = Path(__file__).parent / "golden"

#: Every case, in one stable order — the registry is the quantifier everywhere below.
CASE_NAMES = sorted(workflows.CASES)

#: The OCI digest grammar (IR-SPEC §6.1 step 8).
DIGEST_GRAMMAR = re.compile(r"sha256:[a-f0-9]{64}")

#: The twelve §3 rows, by their spec-fixed test names (1-6 GOV-05; 7-12 GOV-06).
SECTION_3_TESTS = frozenset(
    {
        "test_drift_builder_nodes_spec_shape",
        "test_drift_builder_branches_shape",
        "test_drift_builder_edges_waiting_edges",
        "test_drift_get_graph_drawable_fidelity",
        "test_drift_send_signature",
        "test_drift_retry_policy_fields",
        "test_drift_schema_getters_jsonschema",
        "test_drift_context_schema_surface",
        "test_drift_channel_reducer_repr",
        "test_drift_node_metadata_additive",
        "test_drift_lcel_fragment_identity",
        "test_drift_compiled_interrupt_checkpointer",
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
    return committed_document("drawable-fidelity.drawable.json")


def committed_document(filename: str) -> dict[str, Any]:
    """One committed document golden (tests 4, 7 and 11), parsed."""
    loaded = json.loads((GOLDEN_DIR / filename).read_text(encoding="utf-8"))
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

    **Block-and-propose (the row's on-failure column, GOV-06):** the extraction runs
    before the drawable compare so that, when the drawable payload diverges, the builder
    path's own verdict already exists — if the builder-derived core IR is still golden,
    the ``get-graph-demotion`` review proposal is recorded (routed via §5 R-06 governance
    by :mod:`tests.version_drift.review`) *before* the assertion fails. Both divergence
    branches still fail the test and block the cell; the version-gap issue on the red cell
    is GOV-07's machinery.

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

    envelope = extracted("drawable-fidelity")
    drawn_payload = drawable.drawable_payload(drawn)
    committed = committed_drawable()
    if drawn_payload != committed:
        builder_still_golden = canonical_bytes(envelope.ir) == committed_canonical(
            "drawable-fidelity"
        ) and envelope.graph_version() == committed_digest("drawable-fidelity")
        if builder_still_golden:
            review.propose(review.get_graph_demotion_proposal(committed, drawn_payload))
    assert drawn_payload == committed

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


def test_drift_schema_getters_jsonschema() -> None:
    """§3 test 7 — the jsonschema getters' named keys against the committed document.

    Hard: both getters return dicts; the named-key projection — ``title``, ``type``, and
    the ``properties`` key set with each key's ``type``, input and output each — == the
    committed schema document; extracted core IR == golden. Soft: **full-dict** equality
    against the recorded rendering, as flatten atoms — §3 designates the full dict soft
    because JSON Schema rendering churns with the pydantic version, which the matrix pins
    only transitively (recorded per cell in ``gebra[compat-test]``; no independent axis).
    The getters build a pydantic model from the state schema and render it — §1 rule 3's
    permitted model/JSON-schema introspection, no node is invoked — under the armed ledger.
    """
    builder = workflows.build_schema_getters()
    compiled = builder.compile()
    input_schema = compiled.get_input_jsonschema()
    output_schema = compiled.get_output_jsonschema()
    assert isinstance(input_schema, dict)
    assert isinstance(output_schema, dict)

    assert documents.schema_payload(input_schema, output_schema) == committed_document(
        "schema-getters.schemas.json"
    )

    assert_matches_golden("schema-getters", extracted("schema-getters"))

    inventory.soft_documents_exact(
        "test_drift_schema_getters_jsonschema",
        "input-output-jsonschema",
        {"input": input_schema, "output": output_schema},
    )


def test_drift_context_schema_surface() -> None:
    """§3 test 8 — ``context_schema`` on builder + compiled; the legacy ctor still
    warns-and-works.

    Hard: the modern construction carries the context schema on the builder and the
    compiled object (identity, not just presence); the legacy ``config_schema=``
    construction classifies as deprecated-but-working — a ``DeprecationWarning`` (the
    substrate's own subclass) was emitted and the graph built, auto-routed to
    ``context_schema``; both constructions extract to the **same** committed golden (the
    auto-route pinned at IR granularity).

    **2.0-ceiling review (the row's on-failure column, GOV-06):** a ``TypeError`` from the
    legacy construction is the documented 2.0 removal observed — the
    ``major-version-review`` proposal (freeze range + §5 R-06 routing) is recorded before
    the blocking assertion fails. A silent success (no deprecation warning) is ordinary
    hard drift: blocked, no proposal — the classification is
    :func:`tests.version_drift.review.classify_config_schema_probe`'s, dry-run-proven in
    ``test_review.py``. Soft: the exact warning-class set == recorded.
    """
    builder = workflows.build_context_schema()
    assert builder.context_schema is workflows.ReviewContext
    compiled = builder.compile()
    assert compiled.context_schema is workflows.ReviewContext

    probe = review.classify_config_schema_probe(workflows.build_context_schema_legacy)
    if probe.outcome is review.ConfigSchemaOutcome.REMOVED:
        review.propose(review.major_version_review_proposal(probe.error or "TypeError"))
    assert probe.outcome is review.ConfigSchemaOutcome.DEPRECATED_WORKS
    legacy = probe.built
    assert isinstance(legacy, StateGraph)
    assert legacy.context_schema is workflows.ReviewContext

    assert_matches_golden("context-schema", extracted("context-schema"))
    legacy_envelope = extract(legacy)
    assert canonical_bytes(legacy_envelope.ir) == committed_canonical("context-schema")
    assert legacy_envelope.graph_version() == committed_digest("context-schema")

    inventory.soft_exact_set(
        "test_drift_context_schema_surface",
        "config-schema-warning-classes",
        probe.warning_class_names,
    )


def test_drift_channel_reducer_repr() -> None:
    """§3 test 9 (main case) — per-key channels carry what the Σ read consumes.

    Hard: the compiled ``.channels`` mapping exposes each declared state key as a channel
    object; the channel **class** identifies the reducer semantics (the reducer key is a
    ``BinaryOperatorAggregate``, the plain key a ``LastValue`` — the two classes whose
    semantics ir 1.0 carries); each exposes the ``ValueType``/``UpdateType`` the extractor
    reads, carrying the declared annotation (the reducer riding in the ``Annotated``
    metadata); extracted ``state`` block (keys, types, reducer strings — the V.S.F.E diff
    inputs) == golden. Soft: both channel classes' exact declared member sets == recorded.
    """
    builder = workflows.build_channel_reducer()
    compiled = builder.compile()
    channels = compiled.channels
    assert isinstance(channels, Mapping)
    assert {"log", "latest"} <= set(channels)
    log = channels["log"]
    latest = channels["latest"]
    assert isinstance(log, BaseChannel) and isinstance(latest, BaseChannel)
    assert type(log).__name__ == "BinaryOperatorAggregate"
    assert type(latest).__name__ == "LastValue"
    assert typing.get_args(log.ValueType) == (list[str], operator.add)
    assert log.UpdateType == log.ValueType
    assert latest.ValueType is str
    assert latest.UpdateType is str

    assert_matches_golden("channel-reducer", extracted("channel-reducer"))

    inventory.soft_exact_set(
        "test_drift_channel_reducer_repr",
        "binop-channel-members",
        inventory.member_names(log),
    )
    inventory.soft_exact_set(
        "test_drift_channel_reducer_repr",
        "last-value-channel-members",
        inventory.member_names(latest),
    )


@pytest.mark.xfail(
    strict=False,
    reason="DeltaChannel is beta (VERSION-COMPAT §3 row 9; A2 §4) and never blocks a "
    "cell: the module is absent on pre-1.2 lines, and moved beta behavior anywhere is "
    "an xfail, not a blocker",
)
def test_drift_channel_reducer_repr_delta_beta() -> None:
    """§3 test 9's separate DeltaChannel variant — beta, ``xfail(strict=False)`` always.

    On the pre-1.2 lines the factory's ``langgraph.channels.delta`` import raises — that
    is this xfail firing as designed, not a defect. Where the module exists, the variant
    pins today's best-effort contract (§4: beta features extract best-effort with
    ``unsupported-construct`` scoped to the beta surface, exempt from the conformance
    promises — hence no committed golden): the key binds to a ``DeltaChannel``; extraction keeps the
    key with the ``type:unrepresentable`` marker, no reducer, and emits the
    ``state-channel-not-carried`` warning naming the channel class; the plain key beside
    it is unaffected.
    """
    builder = workflows.build_channel_reducer_delta()
    compiled = builder.compile()
    assert type(compiled.channels["log"]).__name__ == "DeltaChannel"

    envelope = extract(builder)
    state = envelope.ir.state
    assert state is not None
    field = state["log"]
    assert not isinstance(field, str)
    assert field.type == "type:unrepresentable"
    assert field.reducer is None
    plain = state["latest"]
    assert plain == "str" or (not isinstance(plain, str) and plain.type == "str")
    assert any(
        warning.code.value == "unsupported-construct"
        and "state-channel-not-carried" in warning.message
        and "DeltaChannel" in warning.message
        for warning in envelope.warnings
    )


def test_drift_node_metadata_additive() -> None:
    """§3 test 10 — the 1.2-era additive kwargs round-trip; pre-1.2 fields undisturbed.

    The golden carrier is the **plain twin** (the pre-1.2 declaration only), so the golden
    holds byte-identically on every cell — the additive kwargs never reach the closed core
    IR, and the synthesized handler node exists only where the substrate synthesizes it.
    Where the substrate has the kwargs (:data:`tests.substrate.HAS_NODE_TIMEOUT` /
    :data:`~tests.substrate.HAS_NODE_ERROR_HANDLER` — presence gates, never try/except:
    the 1.0/1.1 ``add_node`` *swallows* both through ``**kwargs``), the enriched twin
    round-trips them: ``timeout=`` lands as the spec's ``TimeoutPolicy``,
    ``error_handler=`` synthesizes the handler node (``is_error_handler`` set) and the
    compiled ``node_error_handler_map`` names it — and the pre-1.2 fields on the enriched
    spec equal the plain twin's, which is the row's "without disturbing" claim at spec
    granularity. On the pre-1.2 lines the additive members are asserted absent instead.
    Soft: the exact ``add_node`` signature parameter set == recorded (the surface the
    kwargs landed on).
    """
    builder = workflows.build_node_metadata()
    plain_spec = builder.nodes["ingest"]
    plain_members = inventory.member_names(plain_spec)

    if substrate.HAS_NODE_TIMEOUT and substrate.HAS_NODE_ERROR_HANDLER:
        enriched = workflows.build_node_metadata_enriched()
        spec = enriched.nodes["ingest"]
        timeout_policy = substrate.node_spec_timeout(spec)
        assert timeout_policy is not None
        assert type(timeout_policy).__name__ == "TimeoutPolicy"
        assert timeout_policy.run_timeout == 30.5
        handler_name = substrate.node_spec_error_handler_node(spec)
        assert isinstance(handler_name, str) and handler_name
        assert substrate.node_spec_is_error_handler(spec) is False
        handler_spec = enriched.nodes[handler_name]
        assert substrate.node_spec_is_error_handler(handler_spec) is True
        assert innermost(handler_spec.runnable) is workflows.recover_ingest
        assert spec.metadata == plain_spec.metadata == workflows.INGEST_METADATA
        assert spec.retry_policy == plain_spec.retry_policy
        declared = spec.retry_policy
        assert declared is not None
        policy = declared if isinstance(declared, RetryPolicy) else declared[0]
        assert policy.max_attempts == 4
        assert spec.cache_policy is None and plain_spec.cache_policy is None
        assert spec.defer is False and spec.ends == plain_spec.ends
        compiled = enriched.compile()
        assert substrate.compiled_node_error_handler_map(compiled) == {"ingest": handler_name}
    else:
        assert not (plain_members & {"timeout", "error_handler_node", "is_error_handler"})

    assert_matches_golden("node-metadata-additive", extracted("node-metadata-additive"))

    inventory.soft_exact_set(
        "test_drift_node_metadata_additive",
        "add-node-params",
        frozenset(inspect.signature(StateGraph.add_node).parameters),
    )


def test_drift_lcel_fragment_identity() -> None:
    """§3 test 11 — LCEL names+topology golden; uuid-fresh raw ids; synthetic extracted ids.

    Hard, in row order: ``get_graph()`` names + topology == the committed document and
    stable across two successive draws; the raw drawn ids differ per call (``uuid4``,
    A1 §7) and none appears in any extracted id; the extracted node ids are exactly the
    ledger-§5 synthetic-segment grammar for this composition (``%seq[0]``, ``%seq[1]``,
    ``%seq[1]/%map[docs]``, ``%seq[1]/%map[meta]``, ``%seq[2]`` — name + structural
    position, never a drawing id); and the core IR is byte-identical across two
    extractions (the drawn chain and a fresh build) and == golden. Soft: the sequence's
    public composition members == recorded (langchain-core — the hottest-churn
    distribution on the matrix, A2 §1).
    """
    chain = workflows.build_lcel_fragment()
    first_draw = chain.get_graph()
    second_draw = chain.get_graph()
    first_payload = documents.lcel_payload(first_draw)

    assert first_payload == committed_document("lcel-fragment.drawable.json")
    assert documents.lcel_payload(second_draw) == first_payload

    first_ids = set(documents.drawn_names(first_draw))
    second_ids = set(documents.drawn_names(second_draw))
    assert first_ids and second_ids
    assert first_ids.isdisjoint(second_ids)

    envelope = extracted("lcel-fragment")
    same_chain_envelope = extract(chain)
    assert canonical_bytes(envelope.ir) == canonical_bytes(same_chain_envelope.ir)
    extracted_ids = {node.id for node in envelope.ir.nodes}
    assert extracted_ids == {
        "%seq[0]",
        "%seq[1]",
        "%seq[1]/%map[docs]",
        "%seq[1]/%map[meta]",
        "%seq[2]",
    }
    for raw_id in first_ids | second_ids:
        assert all(raw_id not in node_id for node_id in extracted_ids)

    assert_matches_golden("lcel-fragment", envelope)

    inventory.soft_exact_set(
        "test_drift_lcel_fragment_identity",
        "runnable-sequence-instance-attrs",
        inventory.public_instance_attrs(chain),
    )


def test_drift_compiled_interrupt_checkpointer() -> None:
    """§3 test 12 — the compiled P-13 carriers: interrupt gate lists + checkpointer.

    Hard: the compiled object exposes both interrupt-gate node lists with exactly the
    compiled gate names and a present checkpointer (A1 §3 — the conventionally-stable
    compiled attrs); extracted ``runtime.interrupts``/``runtime.checkpointer`` == golden
    (ledger-§1 P-13 carriers, ratified DEC-09). The registry fixture **is** the compiled
    object — the carriers exist only at the compiled level, so this is the one case whose
    ``extract()`` target is compiled (an already-tripwired EX path). Soft: the compiled
    Pregel's public instance-attribute set == recorded.
    """
    compiled = workflows.CASES["interrupt-checkpointer"].build()
    assert list(compiled.interrupt_before_nodes) == ["publish"]
    assert list(compiled.interrupt_after_nodes) == ["draft"]
    checkpointer = compiled.checkpointer
    assert checkpointer is not None and checkpointer is not False
    assert type(checkpointer).__name__ == "InMemorySaver"

    envelope = extract(compiled)
    runtime = envelope.ir.runtime
    assert runtime is not None
    assert runtime.interrupts is not None
    assert runtime.interrupts.before == ("publish",)
    assert runtime.interrupts.after == ("draft",)
    assert runtime.checkpointer is not None
    assert runtime.checkpointer.present is True

    assert_matches_golden("interrupt-checkpointer", envelope)

    inventory.soft_exact_set(
        "test_drift_compiled_interrupt_checkpointer",
        "compiled-pregel-instance-attrs",
        inventory.public_instance_attrs(compiled),
    )


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
    """No stale golden, no missing golden; the document goldens and WA-05 README present."""
    expected = (
        {f"{name}.canonical.json" for name in workflows.CASES}
        | {f"{name}.digest" for name in workflows.CASES}
        | {
            "drawable-fidelity.drawable.json",
            "schema-getters.schemas.json",
            "lcel-fragment.drawable.json",
            "README.md",
        }
    )
    present = {
        path.name
        for path in GOLDEN_DIR.iterdir()
        if path.name != "__pycache__" and not path.name.startswith(".")
    }

    assert present == expected


def test_the_registry_names_exactly_the_twelve_section3_tests() -> None:
    """The registry ↔ §3 naming contract: twelve cases, twelve spec-fixed names, all here."""
    named = {case.test for case in workflows.CASES.values()}

    assert named == SECTION_3_TESTS
    for test_name in named:
        assert callable(globals()[test_name])


def test_the_beta_case_is_marked_xfail_non_strict() -> None:
    """The §3 row-9 semantics held structurally: the DeltaChannel variant never blocks.

    ``xfail(strict=False)`` read off the test function's own marks, so a mark edit (or a
    deletion) fails here rather than surfacing as a blocking beta case on some cell.
    """
    marks = [
        mark
        for mark in getattr(test_drift_channel_reducer_repr_delta_beta, "pytestmark", [])
        if mark.name == "xfail"
    ]

    assert len(marks) == 1
    assert marks[0].kwargs.get("strict") is False
    assert "beta" in str(marks[0].kwargs.get("reason", ""))


def test_the_drift_fixtures_are_armed() -> None:
    """Every invokable body in the fixture set records itself and raises — proven by firing.

    A tripwire nobody trips proves nothing: without this control, an edit de-arming one
    body (a plausible return replacing ``_trip`` during a golden retake) would leave the
    autouse ledger check green while the guard it claims was dead. Every held callable is
    reached by walking the built graphs — nodes and branch routers, the subgraph through
    its own child builder, the row-12 case through its exposed builder factory (its
    registry entry is the compiled object), the LCEL chain through its sequence steps and
    parallel branches — and both halves of the design are asserted: the raise, and the
    ledger entry recorded *before* it. The line-gated bodies (the enriched twin's async
    body and handler, the delta pair) are fired directly off the module on **every** cell,
    and their graphs are additionally walked where the substrate builds them; the async
    body is driven to its immediate raise with a single ``send(None)``. The one runnable
    no unwrap reaches is the ``finalize`` subgraph node, which is a graph rather than a
    body; the walk asserts it is exactly that one, so the exemption cannot quietly widen.
    """
    fired = 0

    def fire(function: Any, *call_arguments: Any) -> None:
        nonlocal fired
        arguments = call_arguments if call_arguments else ({},)
        before = len(workflows.TRIPPED)
        with pytest.raises(workflows.DriftSentinelError):
            if inspect.iscoroutinefunction(function):
                function(*arguments).send(None)
            else:
                function(*arguments)
        assert len(workflows.TRIPPED) == before + 1
        fired += 1

    def held(runnable: Any) -> Any:
        """The callable a node spec holds: the ``.func`` chain, else the async ``.afunc``."""
        seen = runnable
        while getattr(seen, "func", None) is not None:
            seen = seen.func
        afunc = getattr(seen, "afunc", None)
        if getattr(seen, "func", "absent") is None and afunc is not None:
            return afunc
        return seen

    def walk(builder: Any) -> list[str]:
        skipped: list[str] = []
        for name, spec in builder.nodes.items():
            function = held(spec.runnable)
            if isinstance(function, Pregel):
                skipped.append(name)
                continue
            fire(function)
        for branches in builder.branches.values():
            for branch in branches.values():
                fire(innermost(branch.path))
        return skipped

    builders = [
        workflows.build_nodes_spec(),
        workflows.build_branches(),
        workflows.build_waiting_edges(),
        workflows.build_drawable(),
        workflows.build_editorial_child(),
        workflows.build_send_signature(),
        workflows.build_retry_policy(),
        workflows.build_schema_getters(),
        workflows.build_context_schema(),
        workflows.build_channel_reducer(),
        workflows.build_node_metadata(),
        workflows.build_interrupt_checkpointer(),
    ]
    subgraph_nodes: list[str] = []
    for builder in builders:
        subgraph_nodes.extend(walk(builder))

    for step in workflows.build_lcel_fragment().steps:
        parallel_branches = getattr(step, "steps__", None)
        if isinstance(parallel_branches, dict):
            for branch in parallel_branches.values():
                fire(innermost(branch))
            continue
        fire(innermost(step))

    fire(workflows.ingest_enriched)
    fire(workflows.recover_ingest)
    fire(workflows.merge_delta, [], ())
    fire(workflows.track_delta)

    if substrate.HAS_NODE_TIMEOUT and substrate.HAS_NODE_ERROR_HANDLER:
        subgraph_nodes.extend(walk(workflows.build_node_metadata_enriched()))
    if substrate.HAS_DELTA_CHANNEL:
        subgraph_nodes.extend(walk(workflows.build_channel_reducer_delta()))

    assert subgraph_nodes == ["finalize"]
    # 20 node bodies + 3 routers across the walked builders, the LCEL chain's 4, the 4
    # direct fires of the line-gated bodies, plus the line-gated graph walks where the
    # substrate builds them; a composition change moves these terms in the same commit as
    # its fixture.
    expected = (
        23  # nodes + routers across the twelve walked builders (child included)
        + 4  # the LCEL chain: sequence head, two parallel branches, the inline lambda
        + 4  # direct fires: enriched async body + handler, delta reducer + delta body
        + (2 if substrate.HAS_NODE_ERROR_HANDLER else 0)  # enriched-twin walk (1.2 line)
        + (1 if substrate.HAS_DELTA_CHANNEL else 0)  # delta-graph walk (1.2 line)
    )
    assert fired == expected
    del workflows.TRIPPED[:]
