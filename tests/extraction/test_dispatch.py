"""Object-family dispatch, the boundary errors, and the never-invokes tripwire for both.

Normative authority: INTROSPECTION-SPEC §2 (dispatch table, pseudocode, error posture,
degenerate-input rule) with §4.3 rules 1 and 4 (the builder-authoritative reading and the
compiled-only downgrade), under the §1 never-invokes discipline.
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Any

import pytest
from langgraph.graph.state import StateGraph

import gebra
from gebra.annotations import SidecarReading
from gebra.extraction import (
    Dispatch,
    ExtractedFrom,
    ExtractionEnvelope,
    ExtractionError,
    ExtractionErrorReason,
    Extractor,
    ObjectFamily,
    classify,
    extract,
    extractor_for,
    register_extractor,
    unregister_extractor,
)
from gebra.ir import WorkflowIR
from tests.sample_workflows import sentinel_graph, sentinel_lcel

REPO_ROOT = Path(__file__).resolve().parents[2]


def probe_ir() -> WorkflowIR:
    """The smallest valid IR — enough for a probe extractor to return an envelope."""
    return WorkflowIR.model_validate_json(
        json.dumps(
            {
                "ir_version": "1.0",
                "entry": "plan_step",
                "finish": "plan_step",
                "nodes": [{"id": "plan_step"}],
                "edges": [],
            }
        )
    )


@contextmanager
def extractor_registered(family: ObjectFamily, implementation: Extractor | None) -> Iterator[None]:
    """Swap in (or remove) ``family``'s extraction path for the duration, then restore.

    Written as a swap rather than a register/unregister pair so it keeps working once the
    per-family paths land and register themselves at import: a test that needs "no path for
    this family" gets exactly that, and puts back whatever was there.
    """
    previous = extractor_for(family)
    unregister_extractor(family)
    if implementation is not None:
        register_extractor(family, implementation)
    try:
        yield
    finally:
        unregister_extractor(family)
        if previous is not None:
            register_extractor(family, previous)


class ProbeExtractor:
    """A stand-in extraction path: records what dispatch handed it, returns an envelope."""

    def __init__(self) -> None:
        self.calls: list[tuple[Dispatch, SidecarReading]] = []

    def __call__(self, dispatch: Dispatch, /, *, sidecar: SidecarReading) -> ExtractionEnvelope:
        self.calls.append((dispatch, sidecar))
        return ExtractionEnvelope(
            ir=probe_ir(),
            extracted_from=ExtractedFrom(source="tests:probe", family=dispatch.family),
        )


# ── §2 dispatch, one test per object family ──────────────────────────────────────────────


def test_an_uncompiled_builder_takes_the_builder_family() -> None:
    """§2 row 2: a ``StateGraph`` takes "§3 only; compiled-only surfaces recorded absent"."""
    builder = sentinel_graph.build_sentinel_graph()

    dispatch = classify(builder)

    assert dispatch.family is ObjectFamily.BUILDER
    assert dispatch.workflow is builder
    assert dispatch.builder is builder
    assert dispatch.compiled_only is False


def test_a_compiled_graph_takes_the_compiled_family_through_its_builder() -> None:
    """§2 row 1 with §4.3 rule 1: topology routes through the ``.builder`` backreference.

    The decision carries the *builder*, not the compiled object, precisely because
    "builder-authoritative-when-available" is what §4.3 rule 1 says: when ``.builder`` is
    reachable, §3 rules define topology, state schema and per-node declarations, and the
    compiled object contributes only what the builder cannot.
    """
    builder = sentinel_graph.build_sentinel_graph()
    compiled = builder.compile()

    dispatch = classify(compiled)

    assert dispatch.family is ObjectFamily.COMPILED
    assert dispatch.workflow is compiled
    assert dispatch.builder is builder
    assert dispatch.compiled_only is False


def test_a_builderless_pregel_takes_the_compiled_only_downgrade() -> None:
    """§2 route 3 / §4.3 rule 4: a Pregel with no backreference extracts compiled-only.

    The object is a real ``Pregel`` constructed directly rather than compiled from a builder,
    which is the only honest way to have one: ``compile()`` is what attaches ``.builder``.
    """
    dispatch = classify(sentinel_lcel.SENTINEL_PREGEL)

    assert dispatch.family is ObjectFamily.COMPILED
    assert dispatch.builder is None
    assert dispatch.compiled_only is True


def test_a_compiled_graph_that_lost_its_builder_takes_the_same_downgrade() -> None:
    """The §4.3 rule-4 condition is the *absence of a reachable builder*, not the class.

    A ``CompiledStateGraph`` matches §2's first dispatch row on its type alone, so the
    pseudocode would route it to §4 either way; what decides between rule 1 and rule 4 is
    whether §3 has a builder to run on. With none, the downgrade applies — the branch that
    announces reduced knowability, rather than one that would apply §3 rules to nothing.
    """
    compiled = sentinel_graph.build_sentinel_graph().compile()
    del compiled.builder

    dispatch = classify(compiled)

    assert dispatch.family is ObjectFamily.COMPILED
    assert dispatch.builder is None
    assert dispatch.compiled_only is True


@pytest.mark.parametrize(
    "runnable",
    [sentinel_lcel.SENTINEL_LAMBDA, sentinel_lcel.SENTINEL_SEQUENCE],
    ids=["lambda", "sequence"],
)
def test_any_other_runnable_takes_the_lcel_family(runnable: object) -> None:
    """§2 row 3: any other ``Runnable`` takes §5 fragment extraction of the whole object."""
    dispatch = classify(runnable)

    assert dispatch.family is ObjectFamily.LCEL
    assert dispatch.workflow is runnable
    assert dispatch.builder is None
    assert dispatch.compiled_only is False


def test_the_families_are_tried_in_spec_order() -> None:
    """§2 dispatches "in order", and the order is what makes the rows disjoint.

    A ``CompiledStateGraph`` is a ``Pregel`` is a ``Runnable`` at the pinned substrate
    version, so every compiled object also matches row 3; only the ordering keeps it out of
    LCEL fragment extraction.
    """
    compiled = sentinel_graph.build_sentinel_graph().compile()

    assert classify(compiled).family is ObjectFamily.COMPILED
    assert classify(sentinel_lcel.SENTINEL_PREGEL).family is ObjectFamily.COMPILED


# ── §2 error posture: hard failure at the object boundary ────────────────────────────────


@pytest.mark.parametrize(
    "workflow",
    [{"nodes": ["a"]}, 42, "plan_step", ["plan_step"], None, sentinel_graph.plan_step],
    ids=["dict", "int", "str", "list", "none", "function"],
)
def test_an_unsupported_object_raises_the_typed_error(workflow: object) -> None:
    """§2: an unsupported object "MUST raise a typed ``ExtractionError`` naming the object
    type — never return a silent partial IR"."""
    with pytest.raises(ExtractionError) as caught:
        classify(workflow)

    assert caught.value.reason is ExtractionErrorReason.UNSUPPORTED_OBJECT
    assert caught.value.object_type == f"builtins:{type(workflow).__qualname__}"
    assert caught.value.family is None


def test_the_error_names_the_object_type_for_a_foreign_class() -> None:
    """ "Naming the object type" (§2) is the type identity, package included.

    The state schema is the near-miss worth covering: handing ``extract()`` the state class
    instead of the graph is an easy slip, and the message has to say what it got.
    """
    with pytest.raises(ExtractionError) as caught:
        classify(Path("gebra.toml"))

    assert caught.value.object_type.startswith("pathlib:")

    with pytest.raises(ExtractionError) as caught:
        classify(sentinel_graph.SentinelState)

    assert caught.value.reason is ExtractionErrorReason.UNSUPPORTED_OBJECT
    assert ":" in caught.value.object_type


def test_a_pregel_with_no_usable_surface_raises() -> None:
    """§2 dispatch: no ``.builder`` and no callable ``get_graph()`` is "no usable surface at
    all", and the pseudocode raises there rather than downgrading."""
    with pytest.raises(ExtractionError) as caught:
        classify(sentinel_lcel.SurfacelessPregel())

    assert caught.value.reason is ExtractionErrorReason.NO_EXTRACTABLE_SURFACE
    assert caught.value.object_type == "tests:SurfacelessPregel"


def test_an_empty_builder_raises_the_empty_node_set_error() -> None:
    """§2's one boundary exception to totality: an empty ``.nodes`` dict.

    "A builder with an empty ``.nodes`` dict has no extractable content and cannot satisfy
    the IR's ``nodes`` minItems 1 (IR-SPEC §2.1) — it raises ``ExtractionError`` at the
    object boundary."
    """
    empty: StateGraph[Any] = StateGraph(sentinel_graph.SentinelState)

    assert classify(empty).family is ObjectFamily.BUILDER  # classification alone is fine

    with pytest.raises(ExtractionError) as caught:
        extract(empty)

    assert caught.value.reason is ExtractionErrorReason.EMPTY_NODE_SET
    assert caught.value.family is ObjectFamily.BUILDER


def test_the_empty_node_check_runs_before_the_path_lookup() -> None:
    """The boundary refusal is the object's, not this build's — order matters for the message.

    With a path registered, an empty builder must still be refused rather than handed on: the
    §2 exception is about the object having nothing to extract.
    """
    probe = ProbeExtractor()
    empty: StateGraph[Any] = StateGraph(sentinel_graph.SentinelState)

    with (
        extractor_registered(ObjectFamily.BUILDER, probe),
        pytest.raises(ExtractionError) as caught,
    ):
        extract(empty)

    assert caught.value.reason is ExtractionErrorReason.EMPTY_NODE_SET
    assert probe.calls == []


def test_a_degenerate_but_supported_builder_is_not_an_error() -> None:
    """§2 degenerate-input rule: "extraction is total over supported objects".

    A builder with a node but no ``START`` wiring and no finish edge is exactly the shape §2
    says extracts with ``entry: []``/``finish: []`` plus warnings — well-formedness is P-01's
    verdict, never ``extract()``'s. It classifies, passes the boundary check, reaches the
    §3 path, and comes back as an envelope; what the emitted IR and warnings are is
    ``tests/extraction/test_builder.py``'s to pin, and the dispatcher's job ends at "not an
    error".
    """
    unwired: StateGraph[Any] = StateGraph(sentinel_graph.SentinelState)
    unwired.add_node("plan_step", sentinel_graph.plan_step)

    assert classify(unwired).family is ObjectFamily.BUILDER

    envelope = extract(unwired)

    assert isinstance(envelope, ExtractionEnvelope)
    assert envelope.ir.entry == ()
    assert envelope.ir.finish == ()


# ── The seam the per-family paths plug into ──────────────────────────────────────────────


def test_extract_refuses_a_family_whose_path_this_build_does_not_carry() -> None:
    """A supported object with no registered path is refused, never partially extracted.

    §2 forbids "a silent partial IR" as the answer to an object extraction cannot complete;
    a build that carries no path for a family is one more way not to complete it.
    """
    builder = sentinel_graph.build_sentinel_graph()

    with extractor_registered(ObjectFamily.BUILDER, None), pytest.raises(ExtractionError) as caught:
        extract(builder)

    assert caught.value.reason is ExtractionErrorReason.EXTRACTOR_NOT_REGISTERED
    assert caught.value.family is ObjectFamily.BUILDER


def test_extract_hands_the_decision_and_the_sidecar_to_the_registered_path(
    tmp_path: Path,
) -> None:
    """The dispatcher's whole job: classify, check the boundary, delegate.

    The sidecar is resolved and read **here**, once, and the family path receives the
    reading rather than a path. That placement is ANNOTATION §2's "exactly **one** sidecar
    file per extraction, never merged across directories" made structural: with the lookup at
    the entry point, no family can perform a second one and no two families can disagree
    about which file governs.
    """
    probe = ProbeExtractor()
    builder = sentinel_graph.build_sentinel_graph()
    sidecar = tmp_path / "gebra.toml"
    sidecar.write_bytes(b'schema = "gebra-sidecar-v1"\n[nodes.plan_step]\npure = true\n')

    with extractor_registered(ObjectFamily.BUILDER, probe):
        envelope = extract(builder, sidecar=sidecar)
        bare = extract(builder, sidecar=tmp_path / "absent.toml")

    assert envelope.ir == probe_ir()
    assert bare.extracted_from.family is ObjectFamily.BUILDER
    used, missing = (call[1] for call in probe.calls)
    assert used.path == sidecar.resolve()
    assert list(used.entries) == ["plan_step"]
    assert (missing.path, [issue.rule.value for issue in missing.issues]) == (
        None,
        ["file-unreadable"],
    )
    assert probe.calls[0][0].builder is builder


def test_each_family_dispatches_to_its_own_path() -> None:
    """Three families, three seams: no object reaches another family's rules."""
    builder_probe, compiled_probe, lcel_probe = ProbeExtractor(), ProbeExtractor(), ProbeExtractor()
    builder = sentinel_graph.build_sentinel_graph()

    with (
        extractor_registered(ObjectFamily.BUILDER, builder_probe),
        extractor_registered(ObjectFamily.COMPILED, compiled_probe),
        extractor_registered(ObjectFamily.LCEL, lcel_probe),
    ):
        extract(builder)
        extract(builder.compile())
        extract(sentinel_lcel.SENTINEL_LAMBDA)
        extract(sentinel_lcel.SENTINEL_PREGEL)

    assert len(builder_probe.calls) == 1
    assert len(lcel_probe.calls) == 1
    assert [call[0].compiled_only for call in compiled_probe.calls] == [False, True]


def test_registering_twice_is_refused() -> None:
    """Silently replacing an extraction path is how two of them come to disagree."""
    before = extractor_for(ObjectFamily.LCEL)
    probe = ProbeExtractor()

    with extractor_registered(ObjectFamily.LCEL, probe):
        assert extractor_for(ObjectFamily.LCEL) is probe
        with pytest.raises(ValueError, match="already has a registered extraction path"):
            register_extractor(ObjectFamily.LCEL, ProbeExtractor())

    assert extractor_for(ObjectFamily.LCEL) is before


def test_unregistering_an_absent_path_is_not_an_error() -> None:
    """Removal is idempotent, so a test that cleans up twice does not fail on the second."""
    before = extractor_for(ObjectFamily.LCEL)
    with extractor_registered(ObjectFamily.LCEL, None):
        unregister_extractor(ObjectFamily.LCEL)
        assert extractor_for(ObjectFamily.LCEL) is None
    assert extractor_for(ObjectFamily.LCEL) is before


def test_extract_is_reachable_as_the_spec_spells_it() -> None:
    """INTROSPECTION §2 spells the entry point ``gebra.extract(workflow)``.

    The name is resolved lazily (PEP 562) so that importing ``gebra`` does not pull the
    substrate into the closure of the validator lane; this is the test that the laziness is
    invisible from the outside.
    """
    assert gebra.extract is extract
    assert "extract" in dir(gebra)
    assert gebra.ExtractionError is ExtractionError
    with pytest.raises(AttributeError):
        _ = gebra.no_such_name


def test_dispatch_is_frozen() -> None:
    """The decision is a value: nothing downstream re-points it at another object."""
    dispatch = classify(sentinel_lcel.SENTINEL_LAMBDA)

    with pytest.raises(FrozenInstanceError):
        dispatch.family = ObjectFamily.BUILDER  # type: ignore[misc]


# ── WA-07 — the tripwire for the path this card lands ────────────────────────────────────

#: The guarded child. Every network primitive raises from the first line; socket
#: *construction* only records until the imports are done, for the one reason spelled out in
#: the comment below. Then the raisers close over construction and ``StateGraph.compile``,
#: and every sentinel object is dispatched. ``probe`` arms a control, so a control cannot
#: drift onto a different raiser than the one the claim relies on.
_TRIPWIRE = """
import socket, sys

attempts = []
built = []


def _record(name):
    def _seen(*a, **k):
        attempts.append(name); print("WA07-TRIP", file=sys.stderr)
        raise AssertionError(name + " was reached")
    return _seen


class _CountSocket(socket.socket):
    # Import phase: a socket object may be *constructed* (see below) but never used to reach
    # anything — the resolve and connect primitives are already raising when this runs.
    def __new__(cls, *a, **k):
        built.append(a)
        return super().__new__(cls, *a, **k)


class _TripSocket(socket.socket):
    def __new__(cls, *a, **k):
        attempts.append("socket"); print("WA07-TRIP", file=sys.stderr)
        raise AssertionError("a socket was created on the dispatch path")


socket.socket = _CountSocket
socket.getaddrinfo = _record("getaddrinfo")
socket.gethostbyname = _record("gethostbyname")
socket.create_connection = _record("create_connection")

import gebra
from gebra.extraction import ExtractionError, classify
from langgraph.graph.state import StateGraph
from tests.sample_workflows import sentinel_graph, sentinel_lcel

compiled = sentinel_graph.build_sentinel_graph().compile()

# The import phase is *bounded*, not excluded. Extraction has to import the substrate to
# dispatch on its classes, and importing it runs urllib3's own IPv6 capability probe
# (`HAS_IPV6 = _has_ipv6("::1")`), which constructs an AF_INET6 socket, binds it to loopback
# and closes it without connecting. So construction is counted rather than refused up to
# here, while resolving a name and opening a connection raise from the first line — and the
# assertion below is that nothing during import did either.
#
# From here the run is gebra's own work: construction raises too, and `compile()` goes with
# it, since §1 rule 2 forbids extraction from ever compiling a builder handed to it.
assert attempts == [], attempts
socket.socket = _TripSocket
StateGraph.compile = _record("StateGraph.compile")

objects = [
    sentinel_graph.SENTINEL_GRAPH,
    compiled,
    sentinel_lcel.SENTINEL_PREGEL,
    sentinel_lcel.SENTINEL_LAMBDA,
    sentinel_lcel.SENTINEL_SEQUENCE,
    sentinel_lcel.SurfacelessPregel(),
    {"not": "a workflow"},
    sentinel_graph.plan_step,
]

classified = refused = 0
for workflow in objects:
    for call in (lambda w: classify(w), lambda w: gebra.extract(w)):
        try:
            call(workflow)
        except ExtractionError:
            refused += 1
        else:
            classified += 1

assert (classified, refused) == (10, 6), (classified, refused)
"""

_REPORT = "print(attempts)\n"


def _run_guarded(probe: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", _TRIPWIRE + probe + _REPORT],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_dispatch_invokes_nothing_compiles_nothing_and_opens_no_socket() -> None:
    """The WA-07 claim for the path this card lands, in a fresh interpreter.

    Four claims at once, and the sentinels are what make two of them real rather than
    asserted: every node function, router, LCEL step and Pregel node in the objects below
    raises if it is called, so a dispatch pass that invoked one would fail the run;
    ``StateGraph.compile`` is taken away after the compiled fixture is built, so §1 rule 2 is
    checked rather than reviewed; nothing resolves a name or opens a connection at any point,
    imports included; and nothing so much as constructs a socket while dispatching. Attempts
    are recorded before raising, so a swallowed exception still fails the run.

    The child asserts its own counts — ten successes and six refusals over eight objects, each
    tried twice — so a dispatch that silently stopped reaching the sentinels would fail here
    rather than pass with nothing to prove. (``classify`` succeeds on five: the builder, the
    compiled graph, the builderless Pregel and the two LCEL fragments; the surfaceless Pregel,
    the dict and the function are refused. ``extract`` succeeds on the same five, now that the
    §5 path is registered alongside §3 and §4, and refuses the other three. The compiled
    successes are what make ``StateGraph.compile`` being taken away load-bearing here: the §4
    path reads a live compiled object and never recompiles anything.)

    **One residual, named rather than implied.** Import-closure absence is deliberately not
    claimed, unlike on the validator lane (``tests/verify/test_base.py``): extraction
    dispatches on the substrate's own classes, so langgraph and langchain-core are in this
    closure by construction, and they bring their HTTP clients with them. That is why socket
    *construction* is counted rather than refused during the imports — urllib3's IPv6
    capability probe constructs one, binds it to loopback and closes it without connecting.
    The phase is bounded rather than excluded: resolving and connecting raise from the first
    line of the child, and the child asserts neither happened before dispatch began.
    """
    result = _run_guarded()

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "[]", result.stdout
    assert "WA07-TRIP" not in result.stderr, result.stderr


def test_the_sentinels_are_armed() -> None:
    """A tripwire nobody trips proves nothing: every sentinel really does raise when called.

    All seven, not a sample — an unarmed one is a hole exactly where the claim above is
    strongest, and ``format_fragment`` is half of ``SENTINEL_SEQUENCE``.
    """
    state: sentinel_graph.SentinelState = {"query": "q", "plan": "p", "answer": "a"}
    for node in (sentinel_graph.plan_step, sentinel_graph.act_step, sentinel_graph.summarize_step):
        with pytest.raises(sentinel_graph.SentinelExecutedError):
            node(state)
    with pytest.raises(sentinel_graph.SentinelExecutedError):
        sentinel_graph.route_after_plan(state)
    for step in (
        sentinel_lcel.summarize_fragment,
        sentinel_lcel.format_fragment,
        sentinel_lcel.pregel_step,
    ):
        with pytest.raises(sentinel_graph.SentinelExecutedError):
            step("anything")


def test_the_guarded_child_trips_on_a_socket() -> None:
    """The socket raiser is armed inside the child that the claim above runs in."""
    result = _run_guarded("\nsocket.socket()\n")

    assert result.returncode != 0
    assert "a socket was created" in result.stderr


def test_the_guarded_child_trips_on_compile() -> None:
    """So is the ``compile()`` raiser — §1 rule 2 is checked, not assumed."""
    result = _run_guarded("\nsentinel_graph.build_sentinel_graph().compile()\n")

    assert result.returncode != 0
    assert "StateGraph.compile was reached" in result.stderr


@pytest.mark.parametrize(
    ("call", "name"),
    [
        ("socket.getaddrinfo('example.invalid', 80)", "getaddrinfo"),
        ("socket.gethostbyname('example.invalid')", "gethostbyname"),
        ("socket.create_connection(('example.invalid', 80))", "create_connection"),
    ],
)
def test_each_network_raiser_is_armed(call: str, name: str) -> None:
    """Every raiser has its own control — one that nobody trips proves nothing about itself."""
    result = _run_guarded(f"\n{call}\n")

    assert result.returncode != 0
    assert f"{name} was reached" in result.stderr


def test_a_swallowed_trip_still_fails_the_run() -> None:
    """Recording before raising is what makes a ``try: … except: pass`` path visible."""
    swallow = "\ntry:\n    socket.getaddrinfo('example.invalid', 80)\nexcept Exception:\n    pass\n"

    result = _run_guarded(swallow)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "['getaddrinfo']", result.stdout
