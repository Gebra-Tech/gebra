"""LCEL fragment extraction — INTROSPECTION-SPEC §5, and this path's WA-07 tripwire.

The suite is organised the way the spec is: one section per §5 rule, then §2's degenerate,
error and termination postures, then the envelope, then the tripwire.

Two things are checked *per shape* rather than by counting tests. ``FRAGMENT_CASES`` in
``tests/sample_workflows/sentinel_lcel.py`` declares each shape's whole expected IR — node
ids, entry/finish, fragment-internal edges and the ``unsupported-construct`` slugs — and
:func:`test_every_case_extracts_to_its_declared_ir` is an equality against it, so a stitching
rule that changed fails the case that declares it. ``KIND_COVERAGE`` is then an equality
against the closed IR-SPEC §5.2 vocabulary, so a kind that lost its cases fails the suite
instead of quietly shrinking the table.

Every callable in every fixture raises if it is called, on every test in this file and not only
inside the guarded subprocess.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any, ClassVar

import pytest
from langchain_core.runnables import Runnable, RunnableLambda

import gebra
from gebra.annotations.contract import NodeContract
from gebra.annotations.slots import SlotGrade
from gebra.extraction import (
    ExtractionEnvelope,
    ExtractionError,
    ExtractionErrorReason,
    ExtractionWarningCode,
    ObjectFamily,
    extract_lcel_fragment,
    extractor_for,
)
from gebra.extraction.digests import NodeDigests
from gebra.extraction.lcel import (
    FRAGMENT_CLASSES,
    FragmentKind,
    FragmentReading,
    _annotations,
    _captured_runnables,
    _closure_candidates,
    _closure_source,
    _deps,
    _deps_hazard,
    _map_children,
    _read_body,
    _wrapped_callable,
    kind_of,
    stitch_fragment,
)
from gebra.extraction.stock import STOCK_BINDING_SUBCLASSES
from gebra.ir.canonical import canonical_bytes
from gebra.ir.identity import SYNTHETIC_KINDS, parse_node_id
from gebra.ir.models import WorkflowIR
from gebra.ir.serialization import dump_json, load_json
from tests.sample_workflows import sentinel_lcel as sl
from tests.sample_workflows.sentinel_graph import SentinelExecutedError

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def _clear_tripped() -> Any:
    """No fixture may record an armed read during a test in this file.

    ``PROBED`` is cleared too but not asserted empty: it is the record-and-return log, and a
    read that *is* licensed lands in it. The tests that care assert it explicitly.
    """
    sl.TRIPPED.clear()
    sl.PROBED.clear()
    yield
    assert sl.TRIPPED == [], sl.TRIPPED


def constructs(envelope: ExtractionEnvelope) -> tuple[str, ...]:
    """The ``unsupported-construct`` slugs an extraction produced, in emission order."""
    return tuple(
        str(warning.detail["construct"])
        for warning in envelope.warnings_of(ExtractionWarningCode.UNSUPPORTED_CONSTRUCT)
    )


def edges_of(envelope: ExtractionEnvelope) -> tuple[tuple[str, str], ...]:
    """The IR's edges as ``(from, to)`` pairs."""
    return tuple((edge.from_, str(getattr(edge, "to", ""))) for edge in envelope.ir.edges)


# ── §5 rule 3 — synthetic tokens, and the closed vocabulary ───────────────────────────────


@pytest.mark.parametrize("name", sorted(sl.FRAGMENT_CASES))
def test_every_case_extracts_to_its_declared_ir(name: str) -> None:
    """Each §5 shape produces exactly the IR its case declares.

    The expectation lives with the fixture rather than in the test, so the table is a
    specification of this path's output rather than a list of things that happen to hold: a
    changed selector, a lost edge or a warning that stopped firing fails the case that declares
    it, and adding a shape means declaring what it means.
    """
    case = sl.FRAGMENT_CASES[name]

    envelope = gebra.extract(case.build())

    assert tuple(node.id for node in envelope.ir.nodes) == case.nodes
    assert envelope.ir.entry == case.entry
    assert envelope.ir.finish == case.finish
    assert edges_of(envelope) == case.edges
    assert constructs(envelope) == case.constructs


def test_the_case_table_covers_every_kind_in_the_closed_vocabulary() -> None:
    """All seven §5.2 tokens have a case — an equality, so the table cannot shrink quietly.

    IR-SPEC §5.2 fixes the vocabulary for 1.0 and IR-SPEC §8 makes adding a token a
    minor-version change, so "the tokens this build emits" and "the tokens the spec defines"
    are the same set by construction, and this is where that is checked.
    """
    covered = {kind for kind, cases in sl.KIND_COVERAGE.items() if cases}

    assert covered == SYNTHETIC_KINDS
    assert {kind.value for kind in FragmentKind} == SYNTHETIC_KINDS
    assert {kind.value for kind, _ in FRAGMENT_CLASSES} == SYNTHETIC_KINDS


@pytest.mark.parametrize("kind", sorted(SYNTHETIC_KINDS))
def test_each_kind_emits_its_own_token_with_stable_ids(kind: str) -> None:
    """Each kind's cases emit that token, and re-extracting yields byte-identical ids.

    §5.3's stability statement made a test: "``node_id`` is a deterministic pure function of
    the workflow structure … re-extracting unchanged source yields byte-identical ids". Both
    halves are checked — the same object twice *and* a freshly built one — because a cached
    answer would pass the first and not the second.
    """
    for name in sl.KIND_COVERAGE[kind]:
        case = sl.FRAGMENT_CASES[name]
        runnable = case.build()

        first = gebra.extract(runnable)
        again = gebra.extract(runnable)
        rebuilt = gebra.extract(case.build())

        emitted = {
            segment.synthetic_kind
            for node in first.ir.nodes
            for segment in parse_node_id(node.id).segments
        }
        assert kind in emitted, name
        ids = tuple(node.id for node in first.ir.nodes)
        assert (
            ids
            == tuple(node.id for node in again.ir.nodes)
            == tuple(node.id for node in rebuilt.ir.nodes)
        ), name
        assert first.graph_version() == again.graph_version() == rebuilt.graph_version(), name


def test_every_emitted_segment_is_a_synthetic_token_of_the_closed_set() -> None:
    """No fragment id carries a user segment, and none carries a uuid (§5 rule 2).

    §5 rule 2 is the one rule an implementation can violate invisibly: "LCEL fragment node ids
    are fresh ``uuid4().hex`` per ``get_graph()`` call — **never persist raw LCEL ids**". This
    path never draws at all, so the check is the stronger structural one: every segment of
    every emitted id parses as a *synthetic* token, which no uuid does.
    """
    for name, case in sl.FRAGMENT_CASES.items():
        for node in gebra.extract(case.build()).ir.nodes:
            for segment in parse_node_id(node.id).segments:
                assert segment.synthetic_kind in SYNTHETIC_KINDS, (name, node.id)


def test_a_parallel_key_becomes_the_selector_and_is_escaped() -> None:
    """§5 rule 3's "source key when one exists", including the two characters §5.1 escapes."""
    envelope = gebra.extract(sl.build_escaped_map_key())

    (node,) = envelope.ir.nodes
    (segment,) = parse_node_id(node.id).segments
    assert node.id == "%map[a%2Fb%25c]"
    assert segment.selector == "a/b%c"


def test_keys_that_cannot_carry_the_selector_send_the_whole_frame_to_indices() -> None:
    """Rule 3 *prefers* the source key; a key that collides under NFC cannot be preferred.

    IR-SPEC §5.1 normalizes a selector before escaping, so two keys differing only below NFC
    would become one segment and one of the two branches would vanish from the IR. The frame
    falls back to structural indices — all of it, so a frame's selectors stay one kind of thing
    — and says so; the two branches are of different kinds, so the *order* the indices follow
    is identifiable from the children's own tokens.
    """
    envelope = gebra.extract(sl.build_colliding_map_keys())

    assert [node.id for node in envelope.ir.nodes] == [
        "%map[0]",
        "%map[0]/%map[only]",
        "%map[1]",
        "%map[1]/%bind[0]",
    ]
    assert constructs(envelope) == ("lcel-map-key-not-carried",)


# ── §5 rule 3 — the canonical child ordering, which is digest-critical ────────────────────


@pytest.mark.parametrize(
    ("case", "expected"),
    [
        ("ordered-sequence", ("%seq[0]/%map[only]", "%seq[1]/%branch[0]", "%seq[2]/%bind[0]")),
        (
            "ordered-fallbacks",
            ("%fallback[0]/%map[only]", "%fallback[1]/%branch[0]", "%fallback[2]/%bind[0]"),
        ),
        (
            "ordered-branch",
            ("%branch[0]/%map[only]", "%branch[1]/%bind[0]", "%branch[2]/%retry[0]"),
        ),
        ("lambda-deps-ordered", ("%lambda[0]/%seq[0]", "%lambda[1]/%map[only]")),
    ],
)
def test_child_ordering_follows_the_rule_3_order(case: str, expected: tuple[str, ...]) -> None:
    """§5 rule 3's canonical child order, checked where the order is *identifiable*.

    An index alone cannot show which child sits at it, so each of these fixtures gives its
    children different kinds: the child's own token then says which one index *i* holds, and
    the assertion is that the sequence's steps, the fallback chain's alternatives, the branch's
    branches-then-default and the lambda's captured runnables are all in the order rule 3
    fixes. This is the ordering the rule calls "normative — digest-relevant", and
    :func:`test_each_kind_emits_its_own_token_with_stable_ids` is the other half: the same
    order twice.
    """
    ids = frozenset(node.id for node in gebra.extract(sl.FRAGMENT_CASES[case].build()).ir.nodes)

    assert frozenset(expected) <= ids


def test_a_sequences_edges_chain_its_children_in_order() -> None:
    """§5 rule 1's "an edge from each step's last node to the next step's first node".

    Rule 4 forbids re-pointing anything at a fragment's heads or tails, so the edge is between
    the child *nodes* — which is what makes a multi-head child (the parallel here) need no
    edge-inheritance rule of its own.
    """
    envelope = gebra.extract(sl.build_nested())

    assert edges_of(envelope) == (("%seq[0]", "%seq[1]"), ("%seq[1]", "%seq[2]"))
    assert {"%seq[1]/%map[docs]", "%seq[1]/%map[meta]"} <= {node.id for node in envelope.ir.nodes}


@pytest.mark.parametrize(
    "name", ["parallel", "branch", "fallbacks", "retry", "binding", "ordered-branch"]
)
def test_only_a_sequence_frame_emits_edges(name: str) -> None:
    """Siblings of every other frame are alternatives or concurrent, so no edge orders them.

    A drawing renders them through schema placeholder nodes that §5 rule 1 trims, and after
    trimming there is nothing between them. Reading fan-in/fan-out edges back in would invent
    an ordering the composition does not have.
    """
    envelope = gebra.extract(sl.FRAGMENT_CASES[name].build())

    assert envelope.ir.edges == ()


def test_the_ids_are_identical_across_processes_with_different_hash_seeds() -> None:
    """The digest-critical claim, checked where it can actually fail.

    ``RunnableLambda.deps`` resolves its candidates through ``inspect.getclosurevars``, whose
    global-name loop iterates a **set** — so at CPython 3.13 the substrate answers ``deps`` in a
    different order in different processes, and an extractor that read the member would put a
    process-dependent ``%lambda[i]`` index inside ``graph_version``. IR-SPEC §5.3 ("stable
    within ``graph_version``") and §1.2 conformance both forbid that, so this path derives the
    order from the code object instead. Two child interpreters with different
    ``PYTHONHASHSEED`` values must agree on every id and every digest in the table.

    The child's ``PYTHONPATH`` **prepends** the repo root rather than replacing the parent's:
    the seed is the only variable this test means to change, and a reproduction that reaches
    its substrate through ``PYTHONPATH`` — which is how the VERSION-COMPAT §3 matrix cells
    are run locally — would otherwise lose its packages to a line that only meant to make
    ``tests`` importable (EX-17 / PD-038, "how this was run").
    """
    inherited = os.environ.get("PYTHONPATH")
    search_path = os.pathsep.join([str(REPO_ROOT), *([inherited] if inherited else [])])
    outputs = {
        seed: subprocess.run(
            [sys.executable, "-c", _DIGEST_REPORT],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
            env={**os.environ, "PYTHONHASHSEED": seed, "PYTHONPATH": search_path},
        ).stdout
        for seed in ("0", "1", "12345", "99999")
    }

    assert len(set(outputs.values())) == 1, outputs
    assert "%lambda[1]" in next(iter(outputs.values()))


def test_the_captured_runnables_are_the_substrates_own_set() -> None:
    """Membership is the substrate's; only the *order* is this build's.

    The claim the test above rests on is that re-deriving the dependency list changes nothing
    but its order, so this asserts set-equality against ``RunnableLambda.deps`` itself — by
    object identity, since two structurally equal chains are still two dependencies.
    """
    checked = 0
    for factory in (
        sl.build_lambda_with_deps,
        sl.build_lambda_with_two_deps,
        sl.build_closure_dep,
        sl.build_stock_module_dep,
        sl.build_wrapped_dep,
        sl.build_missing_member_dep,
        sl.build_sentinel_lambda,
    ):
        lambda_ = factory()
        assert isinstance(lambda_, RunnableLambda)
        function = _closure_source(_wrapped_callable(lambda_))
        body = _read_body(function)
        assert body is not None

        derived = _captured_runnables(body, _closure_candidates(function))

        assert {id(item) for item in derived} == {id(item) for item in lambda_.deps}, factory
        checked += 1

    assert checked == 7


# ── §5 rule 4 — containment, not replacement ─────────────────────────────────────────────


def test_a_fragment_mounts_under_the_carrier_path() -> None:
    """Rule 4's own example: "fragment node ids become ``n/%seq[0]``".

    The carrier is the enclosing node ``n``. The composite itself contributes no segment — it
    *is* the frame — so a two-step chain mounted at ``n`` gives ``n/%seq[0]`` and ``n/%seq[1]``,
    exactly as the rule writes it, and the escaping of a carrier name is the ledger §5 rule the
    ids already follow.
    """
    reading = stitch_fragment(sl.build_sentinel_sequence(), carrier=("plan step",))

    assert tuple(reading.nodes) == ("plan step/%seq[0]", "plan step/%seq[1]")
    assert reading.entry == ("plan step/%seq[0]",)
    assert reading.finish == ("plan step/%seq[1]",)


def test_containment_is_the_path_prefix_and_never_an_edge() -> None:
    """Rule 4: "parent↔fragment linkage is structural path containment".

    So a nested frame's children are reachable from their parent's id by prefix and by nothing
    else — no edge runs between a fragment node and a node under it. That is the (H3) clause of
    IR-SPEC §7, which the same section notes is *inhabited* by LCEL nesting even though ir 1.0
    leaves it vacuous over subgraphs.
    """
    envelope = gebra.extract(sl.build_nested())
    ids = {node.id for node in envelope.ir.nodes}

    assert {"%seq[1]/%map[docs]", "%seq[1]/%map[meta]"} <= ids
    for source, target in edges_of(envelope):
        assert not target.startswith(f"{source}/")
        assert not source.startswith(f"{target}/")


def test_a_composite_child_is_a_node_and_a_path_prefix_at_once() -> None:
    """Rule 4: the fragment's parent "itself persists in ``nodes[]``" — one level in, too."""
    ids = [node.id for node in gebra.extract(sl.build_nested()).ir.nodes]

    assert "%seq[1]" in ids
    assert [node for node in ids if node.startswith("%seq[1]/")] == [
        "%seq[1]/%map[docs]",
        "%seq[1]/%map[meta]",
    ]


def test_the_root_of_a_whole_object_extraction_contributes_no_segment() -> None:
    """IR-SPEC §5.1: "The root graph contributes no segment".

    On the §2 family-3 path the fragment *is* the whole object, so the root composite is the
    frame and its children are top-level ids — which is what makes ``%seq[0]`` and
    ``%map[docs]``, the spec's own examples, the ids of a bare two-step chain and a bare
    parallel rather than something nested under a root token.
    """
    assert [node.id for node in gebra.extract(sl.build_sentinel_sequence()).ir.nodes] == [
        "%seq[0]",
        "%seq[1]",
    ]
    assert [node.id for node in gebra.extract(sl.build_parallel()).ir.nodes] == [
        "%map[docs]",
        "%map[meta]",
    ]


def test_a_declared_contract_on_a_frame_root_is_reported_as_uncarried() -> None:
    """Rule 4 gives the carrier role to ``n``, and a whole-object extraction has no ``n``.

    A contract declared on the root of a fragment that *is* a frame therefore lands nowhere.
    It is warned rather than dropped quietly — and the same fragment mounted under a carrier
    has an ``n`` to carry it, which is the pair that shows the warning is about the missing
    carrier and not about the contract.
    """

    uncarried = gebra.extract(sl.build_declared_frame_root())
    assert constructs(uncarried) == ("fragment-root-contract-not-carried",)
    assert [node.id for node in uncarried.ir.nodes] == ["%lambda[0]", "%lambda[0]/%map[only]"]

    # The same fragment mounted under a carrier has an `n`, and `n` is where the contract goes
    # — so nothing is uncarried and nothing is warned.
    carried = stitch_fragment(sl.build_declared_frame_root(), carrier=("plan",))
    assert tuple(carried.nodes) == ("plan/%lambda[0]", "plan/%lambda[0]/%map[only]")
    assert constructs_of(carried.warnings) == ()

    # And a root that declares nothing says nothing: the D-011 default every node would take
    # is not a declaration, so an undecorated frame root is silent.
    assert constructs(gebra.extract(sl.build_lambda_with_deps())) == ()


# ── §2 — the degenerate case, the boundary, and the termination rule ─────────────────────


def test_the_degenerate_one_fragment_case_is_one_node() -> None:
    """§2's family-3 row: "the whole object as a degenerate one-fragment topology".

    With nothing composed there is no frame to name the object, so it stands as the sole member
    of its own kind's frame at the zero-based index rule 3 gives an unkeyed sibling. One node,
    which is both the entry and the finish — and it satisfies IR-SPEC §2.1's ``minItems 1``,
    which is the reason the case needs an answer at all.
    """
    envelope = gebra.extract(sl.build_sentinel_lambda())

    assert [node.id for node in envelope.ir.nodes] == ["%lambda[0]"]
    assert envelope.ir.entry == "%lambda[0]"
    assert envelope.ir.finish == "%lambda[0]"


def test_a_runnable_no_synthetic_kind_names_is_refused_at_the_boundary() -> None:
    """§2: "never a silent partial IR" — and no 1.0 build may invent a token.

    IR-SPEC §5.2's vocabulary is closed and §8 makes adding to it a minor-version change, so a
    stock runnable that composes nothing and that no token names has no node id at all. That is
    §2's own boundary posture for an object with no extractable content, and the refusal names
    the type as §2 requires.
    """
    with pytest.raises(ExtractionError) as caught:
        gebra.extract(sl.build_unnameable())

    assert caught.value.reason is ExtractionErrorReason.CONSTRUCT_NOT_CARRIED
    assert caught.value.family is ObjectFamily.LCEL
    assert caught.value.object_type == "langchain_core:RunnablePassthrough"


def test_such_a_runnable_is_still_extractable_as_a_fragment_child() -> None:
    """The refusal above is about the *root*: inside a frame, the frame does the naming.

    Which is the structural reason the closed vocabulary is not a coverage limit on what an
    LCEL fragment may contain — a chat model, a tool or a passthrough is named by the composite
    it sits in, whatever it is.
    """
    envelope = gebra.extract(sl.build_ordered_sequence())

    assert "%seq[1]/%branch[1]" in {node.id for node in envelope.ir.nodes}


def test_a_self_referential_composition_is_kept_opaque_and_warned() -> None:
    """§2's termination rule, in its own words.

    "An object already on the current walk path is never re-expanded — it is kept as a single
    opaque node and ``unsupported-construct`` (self-referential composition) is emitted." The
    fixture is a chain one of whose steps closes over the chain itself, so the walk really does
    meet it again.
    """
    envelope = gebra.extract(sl.build_self_referential())

    assert [node.id for node in envelope.ir.nodes] == [
        "%seq[0]",
        "%seq[0]/%lambda[0]",
        "%seq[1]",
    ]
    (warning,) = envelope.warnings_of(ExtractionWarningCode.UNSUPPORTED_CONSTRUCT)
    assert warning.detail["construct"] == "self-referential-composition"
    assert warning.node == "%seq[0]/%lambda[0]"


def test_a_composition_deeper_than_the_bound_stops_and_says_so() -> None:
    """The walk terminates on a finite object graph, and on a very deep one it says where.

    A bound rather than a policy: the alternative to a recorded stop is a ``RecursionError``
    out of ``gebra.extract()``, which tells a caller nothing about the workflow.
    """
    envelope = gebra.extract(sl.build_deep_composition())

    assert len(envelope.ir.nodes) < sl.DEEP_LEVELS
    assert constructs(envelope) == ("lcel-fragment-too-deep",)


# ── §5 rule 5 — the stitched-lambda contract, and the §8 co-emission ─────────────────────


def test_a_stitched_lambda_with_no_contract_takes_the_default_and_is_warned() -> None:
    """§5 rule 5: the D-011 conservative default, plus ``opaque-lambda``.

    "A stitched lambda node MUST carry a decorator or sidecar contract, or extraction applies
    the D-011 conservative default (writes-state → ``effect: [write]`` …) and emits
    ``opaque-lambda``. Defaults never upgrade to ``idempotent`` or ``deterministic``."
    """
    envelope = gebra.extract(sl.build_sentinel_sequence())
    (node,) = (node for node in envelope.ir.nodes if node.id == "%seq[0]")

    assert node.annotations is not None
    assert node.annotations.effect == ("write",)
    assert node.annotations.pure is None
    assert node.annotations.idempotent is None
    assert node.annotations.deterministic is None
    assert {
        warning.node for warning in envelope.warnings_of(ExtractionWarningCode.OPAQUE_LAMBDA)
    } == {
        "%seq[0]",
        "%seq[1]",
    }


def test_the_defaulted_slots_stay_heuristic_grade_under_the_annotation_lookup() -> None:
    """The one place this build emits two codes where §8 words it as one, and why.

    §8's ``contract-defaulted`` row says that for stitched lambdas ``opaque-lambda`` "is emitted
    instead and carries the default". Taken literally the defaulted slots would be named by
    ``opaque-lambda`` alone — and ANNOTATION §5's grade lookup is an **iff** over
    ``contract-inferred``/``contract-defaulted``, so those slots would read back as
    *declared*-grade and unlock the ``pure`` ⟹ idempotent implication §4's NEVER-SILENT-UPGRADE
    corollary forbids. This build emits both: rule 5 is satisfied in terms, and the grade lookup
    keeps its footing. **Ratified — DEC-20, 2026-08-03**: §8's row now reads "in addition"
    and gives this test's reason as its own — both codes name the (node, slot) pair.
    """
    envelope = gebra.extract(sl.build_sentinel_sequence())

    assert envelope.slot_grade("%seq[0]", "effect") is SlotGrade.DEFAULTED
    assert {warning.code for warning in envelope.warnings_for("%seq[0]")} == {
        ExtractionWarningCode.CONTRACT_DEFAULTED,
        ExtractionWarningCode.OPAQUE_LAMBDA,
    }


def test_a_declared_contract_replaces_the_default_and_the_warning() -> None:
    """The rule's first branch: a stitched lambda that *does* carry a contract.

    Both halves matter — the declared value wins, and no ``opaque-lambda`` is emitted, because
    §8's row fires when the node "lacks a decorator/sidecar contract". A node whose contract was
    declared is declared-grade under §5's lookup, which is what a validator reads before
    trusting it.
    """

    @gebra.contract(effects=["network"], reads=["question"], writes=["answer"])
    def declared(value: Any) -> Any:
        raise AssertionError("a declared step was invoked")

    envelope = gebra.extract(RunnableLambda(declared) | RunnableLambda(sl.format_fragment))
    (node,) = (node for node in envelope.ir.nodes if node.id == "%seq[0]")

    assert node.annotations is not None
    assert node.annotations.effect == ("network",)
    assert envelope.slot_grade("%seq[0]", "effect") is SlotGrade.DECLARED
    assert {
        warning.node for warning in envelope.warnings_of(ExtractionWarningCode.OPAQUE_LAMBDA)
    } == {"%seq[1]"}


def test_a_sidecar_entry_keyed_by_a_synthetic_token_reaches_its_node(tmp_path: Path) -> None:
    """ANNOTATION §2's entries are keyed by node id, and on this path that is a §5.2 token.

    Which is the whole reason the ids have to be stable: a sidecar written against ``%seq[0]``
    is config pinned to a structural position, and §5.3 makes a re-keyed sibling a *new
    identity* rather than the same node moved.
    """
    sidecar = tmp_path / "gebra.toml"
    sidecar.write_text(
        'schema = "gebra-sidecar-v1"\n\n[nodes."%seq[1]"]\neffects = ["billable"]\n',
        encoding="utf-8",
    )

    envelope = gebra.extract(sl.build_sentinel_sequence(), sidecar=sidecar)
    annotations = {node.id: node.annotations for node in envelope.ir.nodes}

    assert annotations["%seq[1]"] is not None
    assert annotations["%seq[1]"].effect == ("billable",)
    assert envelope.slot_grade("%seq[1]", "effect") is SlotGrade.DECLARED
    assert envelope.warnings_of(ExtractionWarningCode.ANNOTATION_UNKNOWN_NODE) == ()


def test_a_stale_sidecar_key_is_reported_against_the_fragment_ids() -> None:
    """§2's stale-key rule reaches this family too, and the ids it compares against are §5's."""
    reading = stitch_fragment(sl.build_sentinel_sequence())

    assert set(reading.nodes) == {"%seq[0]", "%seq[1]"}


# ── the never-invokes surfaces this path declines ────────────────────────────────────────


def test_a_lambda_whose_dependencies_hide_behind_a_user_property_is_not_read() -> None:
    """The gate, on the shape it exists for.

    Resolving a dotted captured name means walking ``getattr`` from the module value it roots
    at, and the fixture's root is a user object whose property raises. The read is declined —
    the lambda stays a leaf, the decline is recorded, and the property is never reached, which
    the fixture's own record (``TRIPPED``, written *before* it raises) is what proves.
    """
    envelope = gebra.extract(sl.build_deps_hazard())

    assert [node.id for node in envelope.ir.nodes] == ["%lambda[0]"]
    (warning,) = envelope.warnings_of(ExtractionWarningCode.UNSUPPORTED_CONSTRUCT)
    assert warning.detail["construct"] == "lcel-deps-not-read"
    assert "HOLDER.chain" in str(warning.detail["why"])
    assert sl.TRIPPED == []


def test_the_hazard_fixture_is_armed() -> None:
    """A gate nobody trips proves nothing: the property really does raise, and records first."""
    with pytest.raises(SentinelExecutedError):
        _ = sl.HOLDER.chain

    assert sl.TRIPPED == ["Holder.chain"]
    sl.TRIPPED.clear()


def test_a_composite_subclass_is_kept_opaque_rather_than_asked_for_children() -> None:
    """Exact-type matching, and exactly what it buys.

    A subclass can answer a **composition** member with code of its own, and §1 rule 3's closed
    operation list admits no such call — so ``deps`` is never read, the object is named by the
    kind it derives from (it *is* a lambda), and its unread composition is reported (§8). The
    fixture's ``deps`` raises, so this is checked rather than described.
    """
    envelope = gebra.extract(sl.build_not_stock())

    assert [node.id for node in envelope.ir.nodes] == ["%lambda[0]"]
    (warning,) = envelope.warnings_of(ExtractionWarningCode.UNSUPPORTED_CONSTRUCT)
    assert warning.detail["construct"] == "lcel-composition-not-stock"
    assert sl.TRIPPED == []


def test_the_wrapper_walk_still_reads_a_foreign_nodes_contract_members() -> None:
    """The other half of the same sentence, stated rather than implied.

    Exact-type matching governs the **composition** members — the ones that decide the node set
    and the ids. It does not, and must not, govern ANNOTATION §6's wrapper walk: §6 *requires*
    extraction to follow ``__wrapped__``/``func``/``afunc``/``coroutine``/``bound`` inward to
    find a contract, and it does that on every node including a foreign one. So a
    ``RunnableLambda`` subclass whose ``func`` is a property really does have it read — this
    fixture records and answers rather than raising, because a fixture that only raised could
    show that extraction stopped and never that the read happened.

    It is read **once** per node: :func:`~gebra.extraction.contracts.resolve_node` carries the
    opacity flag out rather than making the caller walk the chain a second time to ask.
    """
    envelope = gebra.extract(sl.build_probed_subclass())

    assert [node.id for node in envelope.ir.nodes] == ["%lambda[0]"]
    assert sl.PROBED == ["ProbedLambdaSubclass.func"]
    assert sl.TRIPPED == []
    sl.PROBED.clear()


def test_a_member_is_selected_by_presence_and_never_by_truthiness() -> None:
    """``func or afunc`` would evaluate ``bool(func)``, which is the caller's code.

    A ``RunnableLambda`` accepts any callable, a class instance included, so the truthiness of
    its ``func`` is user code — not on §1 rule 3's list, and able to raise straight out of
    ``extract()``. The fixture's ``__bool__`` is armed, so a build that reintroduced the ``or``
    fails here.
    """
    envelope = gebra.extract(sl.build_sourceless_lambda())

    assert [node.id for node in envelope.ir.nodes] == ["%lambda[0]"]
    assert sl.TRIPPED == []


def test_the_truthiness_fixture_is_armed() -> None:
    """And the control: that ``__bool__`` really does raise, and records before it does."""
    with pytest.raises(SentinelExecutedError):
        bool(sl.CallableStep())

    assert sl.TRIPPED == ["CallableStep.__bool__"]
    sl.TRIPPED.clear()


def test_the_subclass_fixture_is_armed() -> None:
    """The other control: the override really is user code that raises, and records first."""
    with pytest.raises(SentinelExecutedError):
        _ = sl.ArmedLambdaSubclass(sl.summarize_fragment).deps

    assert sl.TRIPPED == ["ArmedLambdaSubclass.deps"]
    sl.TRIPPED.clear()


def test_a_branch_condition_is_never_a_child_and_never_read() -> None:
    """§6: "Guards are opaque references … guards are never evaluated".

    A ``RunnableBranch`` coerces each condition into a ``RunnableLambda``, so a walk that took
    ``branches`` at face value would stitch the guards as children — twice the nodes, half of
    them naming code the IR has no carrier for. The children are the branch *bodies* only.
    """
    envelope = gebra.extract(sl.build_branch())

    assert [node.id for node in envelope.ir.nodes] == [
        "%branch[0]",
        "%branch[1]",
        "%branch[2]",
    ]
    assert sl.TRIPPED == []


def test_the_condition_fixture_is_armed() -> None:
    """And the condition really would raise if anything called it."""
    with pytest.raises(SentinelExecutedError):
        sl.armed_condition("anything")

    assert sl.TRIPPED == ["armed_condition"]
    sl.TRIPPED.clear()


# ── the envelope this family returns ─────────────────────────────────────────────────────


def test_the_envelope_records_the_family_and_leaves_the_other_levels_absent() -> None:
    """§0's never-guess discipline, applied to what an LCEL object simply does not have.

    A fragment declares no state schema, has no compile-time surfaces and no builder to read a
    ``runtime`` block from — so all three are absent rather than defaulted, exactly as §4.3
    rule 4 leaves ``state`` absent on the other path that cannot know it.
    """
    envelope = gebra.extract(sl.build_sentinel_sequence())

    assert envelope.extracted_from.family is ObjectFamily.LCEL
    assert envelope.extracted_from.source == "langchain_core:RunnableSequence"
    assert envelope.extracted_from.compiled is None
    assert envelope.extracted_from.managed_state_keys == ()
    assert envelope.ir.state is None
    assert envelope.ir.runtime is None


def test_the_lcel_family_is_wired_at_import() -> None:
    """``gebra.extract`` reaches this path without a test having to register it."""
    assert extractor_for(ObjectFamily.LCEL) is extract_lcel_fragment


@pytest.mark.parametrize("name", sorted(sl.FRAGMENT_CASES))
def test_every_case_round_trips_and_canonicalizes(name: str) -> None:
    """A block ``extract()`` emits is one the IR models load and canonicalization accepts.

    "Spec-shaped" asserted rather than asserted-about: an IR that cannot be re-loaded, or that
    canonicalization refuses, is one this path must not emit — and the digest is where a value
    that reached out on ``__str__`` would surface.
    """
    envelope = gebra.extract(sl.FRAGMENT_CASES[name].build())

    assert load_json(WorkflowIR, dump_json(envelope.ir)) == envelope.ir
    assert canonical_bytes(envelope.ir)
    assert envelope.graph_version().startswith("sha256:")


def test_two_different_fragments_do_not_share_a_digest() -> None:
    """The digest is a faithful function of the IR, in both directions, over the whole table.

    Equal IRs digest equally and distinct IRs digest distinctly — which is IR-SPEC §1.2's
    recompute-and-compare conformance operation, quantified over every shape this path emits.
    Some cases *do* share an IR and must: a bare lambda and a lambda whose dependency read was
    declined are the same document, which is the honest outcome of a decline. What would make
    every assertion above vacuous is the converse, and that is what the second line rules out.
    """
    by_ir: dict[str, set[str]] = {}
    for case in sl.FRAGMENT_CASES.values():
        envelope = gebra.extract(case.build())
        by_ir.setdefault(dump_json(envelope.ir), set()).add(envelope.graph_version())

    assert all(len(digests) == 1 for digests in by_ir.values())
    assert len({digest for digests in by_ir.values() for digest in digests}) == len(by_ir)


def test_kind_of_matches_the_stock_classes_only() -> None:
    """The lookup underneath all of it: exact type, and the seven classes §5.2 names.

    Plus the one named widening: the stock ``RunnableBinding`` subclasses INTROSPECTION §7.4 (a)
    as amended by DEC-21 enumerates answer the ``bind`` token too (EX-16). Everything outside
    the seven classes and that enumeration still answers ``None`` — ``build_not_stock`` is a
    ``RunnableLambda`` subclass and stays declined, which is DEC-20's stockness discipline.
    ``tests/extraction/test_stock.py`` is where the enumeration itself is held to the substrate.
    """
    for kind, stock in FRAGMENT_CLASSES:
        assert kind_of(sl.FRAGMENT_CASES[_case_for(kind)].build()) is kind
        assert issubclass(stock, Runnable)
    assert kind_of(sl.build_unnameable()) is None
    assert kind_of(sl.build_not_stock()) is None
    for admitted in STOCK_BINDING_SUBCLASSES:
        assert kind_of(object.__new__(admitted)) is FragmentKind.BIND


def test_the_substrates_own_bind_result_is_expanded_whatever_class_it_is() -> None:
    """The §5 half of EX-16, on the authored shape rather than on a declared class.

    ``Runnable.bind()`` answers with the stock ``RunnableBinding``; ``BaseChatModel.bind()``
    answers with ``_ChatModelBinding`` from langchain-core 1.4.0 on. §7.4 (a) as amended admits
    both by exact type, so the *authored* shape ``x | y.bind(...)`` stitches to the same three
    nodes on every cell of the frozen VERSION-COMPAT §3 matrix — the node-set difference
    EX-17 recorded and handed to this card. The bound object is the ``%bind[0]`` child and the
    wrapper is the node that holds it, which is PD-028 D1's carrier reading, unchanged.
    """
    from langchain_core.prompts import ChatPromptTemplate

    from tests.sample_workflows import sentinel_digests as sd

    lambda_bound = gebra.extract(
        RunnableLambda(sl.summarize_fragment) | RunnableLambda(sl.render_fragment).bind(stop=["e"])
    )
    model_bound = gebra.extract(
        ChatPromptTemplate.from_messages([("system", "s")]) | sd.ArmedChatModel().bind(stop=["e"])
    )

    for envelope in (lambda_bound, model_bound):
        assert [node.id for node in envelope.ir.nodes] == [
            "%seq[0]",
            "%seq[1]",
            "%seq[1]/%bind[0]",
        ]
        assert envelope.warnings_of(ExtractionWarningCode.UNSUPPORTED_CONSTRUCT) == ()
    assert sl.TRIPPED == [] and sd.TRIPPED == []


def _case_for(kind: FragmentKind) -> str:
    """The first table case whose root is ``kind`` — used to keep the lookup test honest."""
    return sl.KIND_COVERAGE[kind.value][0]


# ── the guards that keep the walk honest ─────────────────────────────────────────────────


def test_two_children_may_never_occupy_one_node_id() -> None:
    """Merging two fragment children would delete one from the IR, so it is a refusal.

    Unreachable through the public path today — a frame's selectors are unique and its
    children's paths differ by construction — which is exactly why the invariant is asserted
    here rather than left to hold by accident: IR-SPEC §4.2 takes (m5) uniqueness *after*
    normalization, and a future selector rule that broke it would be caught by a refusal
    rather than by a silently shorter ``nodes[]``.
    """
    reading = FragmentReading(workflow=object())
    reading.add("%seq[0]", sl.build_sentinel_lambda())

    with pytest.raises(ExtractionError) as caught:
        reading.add("%seq[0]", sl.build_sentinel_lambda())

    assert caught.value.reason is ExtractionErrorReason.CONSTRUCT_NOT_CARRIED


def test_a_contract_that_declares_nothing_leaves_annotations_absent() -> None:
    """IR-SPEC §6.3: absence round-trips as absence, so an empty contract is no object at all.

    Not reachable from a real extraction — §4's D-011 defaults always fill something — but the
    two are different values in the model, and an empty ``annotations`` object would serialize
    differently from an absent one before omit-normalization ever ran.
    """
    assert _annotations(None, None) is None
    assert _annotations(NodeContract(), None) is None
    assert _annotations(None, NodeDigests()) is None


def test_a_parallel_whose_branch_map_is_not_readable_yields_no_children() -> None:
    """The frame reader asks for a mapping and takes no answer that is not one.

    A stock ``RunnableParallel`` always holds a ``dict`` there; this is the guard that keeps the
    reader from iterating whatever a non-stock object put in its place, which is the same
    posture exact-type matching takes one level up.
    """

    class NotAMapping:
        steps__ = "not a mapping"

    class NonStringKeys:
        steps__: ClassVar[dict[object, object]] = {1: sl.build_sentinel_lambda()}

    reading = FragmentReading(workflow=object())
    assert _map_children(NotAMapping(), (), reading) == ()
    assert reading.warnings == []

    keyed = _map_children(NonStringKeys(), (), reading)
    assert [selector for selector, _ in keyed] == [0]
    assert constructs_of(reading.warnings) == ("lcel-map-key-not-carried",)


def test_a_body_with_no_code_object_resolves_no_captured_names() -> None:
    """The candidate reader is total over what a ``RunnableLambda`` can actually hold.

    A callable object has no ``__code__`` and a code object with no ``__globals__`` beside it
    resolves nothing — both are answered with an empty mapping rather than an ``AttributeError``
    from inside ``extract()``.
    """

    class NoGlobals:
        __code__ = sl.calls_captured_chain.__code__

    assert _closure_candidates(sl.CallableStep()) == {}
    assert _closure_candidates(NoGlobals()) == {}


def test_the_deps_reader_is_narrow_about_what_it_will_read() -> None:
    """Only a stock ``RunnableLambda`` has a ``deps`` surface to derive, and only it is asked.

    The three narrowings are one posture: this path reads composition off objects whose class
    it recognises, and answers "nothing" for everything else rather than duck-typing its way
    into somebody's ``__getattr__``.
    """
    reading = FragmentReading(workflow=object())

    assert _deps(object(), (), reading) == ()
    assert _wrapped_callable(object()) is None
    assert _read_body(None) is None
    assert reading.warnings == []


def test_the_capture_reader_refuses_a_foreign_subject_on_its_own() -> None:
    """The stock check is a property of the reader, not of the order two functions ran in.

    The gate would decline this body, and does — but the reader refuses it independently, so a
    future caller that reached it without the gate still reads no attribute of a user object.
    The fixture records before it raises, so a read that happened and was swallowed would show
    up here rather than nowhere.
    """
    body = _read_body(sl.reads_a_user_property)
    assert body is not None
    candidates = _closure_candidates(sl.reads_a_user_property)

    assert _deps_hazard(body, candidates) is not None
    assert _captured_runnables(body, candidates) == ()
    assert sl.TRIPPED == []


def test_a_body_with_no_readable_definition_reports_no_dependencies() -> None:
    """No definition to read is a miss, never an extraction failure.

    A callable object has no ``__code__``, so the engine's source reader answers "not a Python
    function" and this path answers "no dependencies" — which is what the substrate's own helper
    answers for the same shape, by a route that reaches user code and this one does not.
    """
    assert _read_body(sl.CallableStep()) is None
    assert _read_body(None) is None


def constructs_of(warnings: Any) -> tuple[str, ...]:
    """The ``unsupported-construct`` slugs in a raw warning list."""
    return tuple(
        str(warning.detail["construct"])
        for warning in warnings
        if warning.code is ExtractionWarningCode.UNSUPPORTED_CONSTRUCT
    )


# ── WA-07 — the tripwire for the path this card lands ────────────────────────────────────

#: Re-extracts the whole table and reports the ids and digests. Used by the cross-process
#: stability test above, where the point is that two interpreters agree.
_DIGEST_REPORT = """
import gebra
from tests.sample_workflows import sentinel_lcel as sl
from tests.sample_workflows.sentinel_graph import SentinelExecutedError

for name, case in sorted(sl.FRAGMENT_CASES.items()):
    envelope = gebra.extract(case.build())
    print(name, tuple(n.id for n in envelope.ir.nodes), envelope.graph_version())

assert sl.TRIPPED == [], sl.TRIPPED
"""

#: The guarded child. Network primitives raise from the first line and socket *construction* is
#: only counted until the imports are done — the same bounded-import phase ``test_dispatch``
#: explains, for the same reason. Then four things this path must never do are taken away at
#: once: every ``Runnable`` execution entry point, ``get_graph()`` on every class in play,
#: ``uuid4`` (which is what a drawing would call for its node ids, §5 rule 2), and
#: ``StateGraph.compile``. Unlike the §4 path, this one can arm ``Runnable.invoke`` outright:
#: it never draws, so LangGraph's own ``ChannelWrite.invoke`` is never reached either.
_TRIPWIRE = """
import socket, sys, uuid

attempts = []
built = []


def _record(name):
    def _seen(*a, **k):
        attempts.append(name); print("WA07-TRIP", file=sys.stderr)
        raise AssertionError(name + " was reached")
    return _seen


class _CountSocket(socket.socket):
    def __new__(cls, *a, **k):
        built.append(a)
        return super().__new__(cls, *a, **k)


class _TripSocket(socket.socket):
    def __new__(cls, *a, **k):
        attempts.append("socket"); print("WA07-TRIP", file=sys.stderr)
        raise AssertionError("a socket was created on the LCEL extraction path")


socket.socket = _CountSocket
socket.getaddrinfo = _record("getaddrinfo")
socket.gethostbyname = _record("gethostbyname")
socket.create_connection = _record("create_connection")

import gebra
from gebra.extraction import ExtractionError
from langchain_core.runnables import graph as lc_graph
from langgraph.graph.state import StateGraph
from tests.sample_workflows import sentinel_lcel as sl
from tests.sample_workflows.sentinel_graph import SentinelExecutedError

# Build every shape while the substrate is still whole — building a composition never runs it.
cases = {name: case.build() for name, case in sl.FRAGMENT_CASES.items()}
refused = {name: factory() for name, factory in sl.REFUSED_FRAGMENTS.items()}

assert attempts == [], attempts
socket.socket = _TripSocket
StateGraph.compile = _record("StateGraph.compile")

# `langchain_core.runnables.graph` binds `uuid4` at import (`from uuid import ... uuid4`) and
# `Graph.next_id()` mints drawing ids through *that* binding, so rebinding `uuid.uuid4` alone
# would arm a name nothing calls — langgraph imports the module long before this line runs.
# Both are taken, and the control below probes `Graph().next_id()` rather than `uuid.uuid4()`.
uuid.uuid4 = _record("uuid4")
lc_graph.uuid4 = _record("langchain_core.runnables.graph.uuid4")

# Every class the fixtures actually instantiate, and every class each of those inherits from —
# `RunnableBinding` defines none of these itself (they live on `RunnableBindingBase`), and
# `RunnablePassthrough` is in three fixtures, so an arm list built from FRAGMENT_CLASSES alone
# would leave live implementations of `invoke` and `get_graph` untouched.
armed = []
for runnable in (*cases.values(), *refused.values()):
    for cls in type(runnable).__mro__:
        for method in ("invoke", "ainvoke", "stream", "astream", "batch", "abatch", "get_graph"):
            if method in vars(cls) and not getattr(vars(cls)[method], "_wa07", False):
                raiser = _record(cls.__name__ + "." + method)
                raiser._wa07 = True
                setattr(cls, method, raiser)
                armed.append(cls.__name__ + "." + method)
assert "Runnable.get_graph" in armed, armed
assert "RunnableBindingBase.invoke" in armed, armed
assert "RunnablePassthrough.invoke" in armed, armed

extracted = 0
for name, runnable in cases.items():
    envelope = gebra.extract(runnable)
    assert envelope.ir.nodes, name
    envelope.graph_version()          # canonicalize and digest, still under the guard
    extracted += 1

boundary = 0
for name, runnable in refused.items():
    try:
        gebra.extract(runnable)
    except ExtractionError:
        boundary += 1

assert (extracted, boundary) == (%d, %d), (extracted, boundary)
assert sl.TRIPPED == [], sl.TRIPPED
assert sl.PROBED == ["ProbedLambdaSubclass.func"], sl.PROBED
"""

_REPORT = "print(attempts)\n"


def _run_guarded(probe: str = "") -> subprocess.CompletedProcess[str]:
    body = _TRIPWIRE % (len(sl.FRAGMENT_CASES), len(sl.REFUSED_FRAGMENTS))
    return subprocess.run(
        [sys.executable, "-c", body + probe + _REPORT],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_lcel_extraction_invokes_nothing_and_draws_nothing() -> None:
    """The WA-07 claim for the §5 path, in a fresh interpreter.

    The fixtures are what make it real rather than asserted: every step, every branch condition
    and both armed composition members raise if they are reached, and they *record before they
    raise*, so a sentinel swallowed by an ``except`` block still fails the run — the child
    asserts the fixture log empty as well as its own exit status.

    Four things are taken away before the first extraction, and each is a claim this path makes:
    every ``Runnable`` execution entry point (§1 rule 1's "MUST NOT call … ``Runnable.invoke``
    /``stream``/``batch``"), ``get_graph()`` on every class in play, ``uuid.uuid4`` — which is
    what a drawing calls for the ids §5 rule 2 forbids persisting, so arming it makes "no
    drawing id is even constructed" checked rather than reviewed — and ``StateGraph.compile``.
    The §4 path could not arm the first two, because a drawing of a stock ``Pregel`` runs
    LangGraph's own ``ChannelWrite.invoke``; this path never draws, so it can.

    The child asserts its own counts from the fixture tables, so a shape added to either table
    joins this claim with it, and an extraction pass that silently stopped reaching the fixtures
    fails here rather than passing with nothing to prove.
    """
    result = _run_guarded()

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "[]", result.stdout
    assert "WA07-TRIP" not in result.stderr, result.stderr


@pytest.mark.parametrize(
    ("probe", "expected"),
    [
        ("sl.build_sentinel_lambda().invoke('x')\n", "RunnableLambda.invoke was reached"),
        ("sl.build_sentinel_sequence().get_graph()\n", "RunnableSequence.get_graph was reached"),
        ("sl.build_unnameable().invoke('x')\n", "RunnablePassthrough.invoke was reached"),
        (
            "from langchain_core.runnables.graph import Graph\nGraph().next_id()\n",
            "langchain_core.runnables.graph.uuid4 was reached",
        ),
        ("StateGraph(dict).compile()\n", "StateGraph.compile was reached"),
        ("socket.socket()\n", "a socket was created"),
        ("socket.getaddrinfo('example.invalid', 80)\n", "getaddrinfo was reached"),
        ("socket.gethostbyname('example.invalid')\n", "gethostbyname was reached"),
        ("socket.create_connection(('example.invalid', 80))\n", "create_connection was reached"),
    ],
    ids=[
        "invoke",
        "get_graph",
        "passthrough-invoke",
        "drawing-id",
        "compile",
        "socket",
        "getaddrinfo",
        "resolve",
        "connect",
    ],
)
def test_each_raiser_is_armed(probe: str, expected: str) -> None:
    """A tripwire nobody trips proves nothing — so every raiser gets its own control.

    All eight, not a sample: this child is an independent copy of the guard prologue, so a
    copy-paste slip that dropped one line would leave that raiser unarmed and the claim it
    carries silently vacuous, with everything still green. The controls run *after* the child's
    own assertions, so each one proves the raiser was live at the end of the very run that made
    the claim.
    """
    result = _run_guarded(probe)

    assert result.returncode != 0
    assert expected in result.stderr


def test_a_swallowed_trip_is_still_visible() -> None:
    """Recording before raising is what makes a ``try: … except: pass`` path visible.

    The assertion that matters is the *record*, not the exit status: a child that swallowed the
    exception exits 0 either way, so checking only the status would pass identically if
    ``attempts.append(…)`` moved below the ``raise`` — which is the one design decision this
    control exists to prove.
    """
    swallow = "\ntry:\n    socket.getaddrinfo('example.invalid', 80)\nexcept Exception:\n    pass\n"

    result = _run_guarded(swallow)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "['getaddrinfo']", result.stdout
    assert "WA07-TRIP" in result.stderr


def test_the_tripwire_covers_the_shapes_this_path_handles() -> None:
    """The claim above is only as wide as the tables it quantifies over.

    The child's counts are derived from these tables, so both sides move together if a fixture
    is dropped — which means the tables themselves need a floor. Without one, the guarded run
    could shrink to a single fragment and every assertion would still pass.
    """
    assert len(sl.FRAGMENT_CASES) >= 20
    assert len(sl.REFUSED_FRAGMENTS) >= 1
    assert set(sl.FRAGMENT_CASES) & set(sl.REFUSED_FRAGMENTS) == set()


def test_the_fragment_fixtures_are_armed() -> None:
    """Every step function in every §5 shape raises when called.

    All of them, not a sample: an unarmed fixture is a hole exactly where the claim above is
    strongest, since that is the fragment whose extraction would then prove nothing.
    """
    checked = 0
    for step in (
        sl.summarize_fragment,
        sl.format_fragment,
        sl.render_fragment,
        sl.pregel_step,
        sl.calls_captured_chain,
        sl.calls_two_captured,
        sl.recursive_step,
        sl.declared_root,
        sl.CallableStep(),
    ):
        with pytest.raises(SentinelExecutedError):
            step("anything")
        checked += 1

    assert checked == 9
    # `recursive_step` is armed *before* it reaches the chain it closes over, which is what
    # lets it be called here at all: invoking the chain itself would recur without bound, and
    # a fixture that can only be checked by hanging the suite is not checked.
