"""The travel-booking agent fixture — TE-05's three acceptance claims, and the shape pins.

Three things are demonstrated here, in the card's own order:

1. **The agent extracts to IR with no errors.** In fact with no *warnings* either, which is
   the stronger claim and is asserted as such — every annotation slot the fixture needs is
   declared, so no ANNOTATION-API-SPEC §4 inference default fires and the document stays
   inside the warning-free strict-mode bar INTROSPECTION-SPEC §8 states and
   PROPERTY-CATALOG-SPEC §0.2 owns.
2. **The wedge five pass clean on v1** — five ``pass`` verdicts, exit code 0, and
   ``snapshot_eligible``. Each property's witness is then pinned to the shape the fixture was
   built to produce, because "passes" alone would also be true of a graph that passed
   *vacuously*, and vacuity is the failure mode a shared substrate has to rule out (see
   :func:`test_the_dataflow_pass_is_not_vacuous`).
3. **No node executes on any test path.** Three layers: an autouse ledger check on entry to
   and exit from every test in this file, an armed control that fires every body to prove the
   ledger is live, and a fresh-interpreter guarded run of the whole extract → verify path with
   name resolution, connection opening, socket construction and ``StateGraph.compile`` taken
   away — each of those armed by a control, including two that swallow the exception to show
   the record-before-raise design does its job. One residual is stated rather than implied:
   during the child's *import* phase socket construction is counted, not refused (the
   substrate's own IPv6 capability probe builds one), and the count is bounded rather than
   ignored.

The rest of the file pins what downstream cards consume — the node inventory, the digest's
stability, and the builder/compiled document split PD-023 D4 ruled — so that a change to the
substrate surfaces here rather than in TE-06, SD-03, SD-08, SD-09, CLI-07 or DOC-05.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from gebra import extract
from gebra.extraction import ExtractionEnvelope
from gebra.ir.canonical import graph_version
from gebra.ir.models import ConditionalEdge, NormalEdge
from gebra.verify import (
    DataflowWitness,
    DeterminismWitness,
    EffectSafetyWitness,
    PropertyReport,
    RunPolicy,
    StrictPolicy,
    TerminationWitness,
    verify,
)
from gebra.verify.properties.termination_witness import strict_promotions
from tests.sample_workflows import travel_booking as tb

REPO_ROOT = Path(__file__).resolve().parents[2]

#: The five wedge properties, in PROPERTY-CATALOG-SPEC order.
WEDGE: tuple[str, ...] = (
    "graph-well-formed",
    "termination-witness",
    "dataflow-completeness",
    "effect-safety",
    "determinism-replay",
)


@pytest.fixture(autouse=True)
def _nothing_was_executed() -> Any:
    """Every test in this file asserts the agent was read, never run — on entry and on exit.

    **On entry as well as exit, and that is not belt-and-braces.** pytest builds
    higher-scoped fixtures first, so ``envelope`` and ``report`` — the module-scoped
    extraction and verification this whole file is about — run *before* the first test's own
    setup. A fixture that cleared the ledger here instead of asserting it would erase exactly
    the evidence the ledger exists to preserve, and the primary extraction would be the one
    run nobody checked. Asserting on entry keeps a trip made during module-scoped setup
    (or leaked by an earlier test) fatal.

    :func:`test_every_body_in_the_fixture_is_armed` is the one test that deliberately fills
    the ledger, and it clears it at its own end so the entry assertion stays honest rather
    than being weakened for it.
    """
    assert tb.TRIPPED == []
    yield
    assert tb.TRIPPED == []


@pytest.fixture(scope="module")
def envelope() -> ExtractionEnvelope:
    """The v1 extraction — the builder level, which PD-023's call makes the subject."""
    return extract(tb.build_travel_booking_agent())


@pytest.fixture(scope="module")
def report(envelope: ExtractionEnvelope) -> Any:
    """The run report ``verify()`` derives over the extracted v1 IR."""
    return verify(envelope.ir)


def outcome(report: Any, slug: str) -> PropertyReport:
    """The one :class:`PropertyReport` for ``slug`` — never a not-implemented marker."""
    for entry in report.properties:
        if getattr(entry, "property", None) == slug and isinstance(entry, PropertyReport):
            return entry
    raise AssertionError(f"no PropertyReport for {slug!r}")


# ── Acceptance 1 — the agent extracts, with no errors ────────────────────────────────────


def test_the_agent_extracts_with_no_error_and_no_warning(envelope: ExtractionEnvelope) -> None:
    """Acceptance box 1, at its stronger reading: the extraction is also warning-free.

    The card allows warnings, and the fixture earns not needing the allowance. That is not
    cosmetic: EX-11 recorded that an unannotated workflow falls outside the warning-free
    strict-mode bar — stated at INTROSPECTION-SPEC §8, owned by PROPERTY-CATALOG-SPEC §0.2 as
    the severity-ladder authority — so a substrate that shipped with a ``contract-defaulted``
    warning would hand every consuming card an expectation to carry, and would demote its own
    DEFENSIBLE-A claims to heuristic grade under ANNOTATION-API-SPEC §5. Asserting the codes
    and not just the count means a *different* warning appearing reads as the diff it is.

    One caveat recorded with the card rather than hidden here: this is a hard ``== []`` and
    the version matrix runs plain ``pytest`` per cell, so a substrate-dependent warning would
    land as a fixture failure on a cell this environment cannot run.
    """
    assert [warning.code for warning in envelope.warnings] == []
    assert envelope.ir.ir_version == "1.0"


def test_the_extracted_topology_is_the_declared_one(envelope: ExtractionEnvelope) -> None:
    """The nine nodes, the two routed edges and their labels — the consumers' surface.

    :data:`~tests.sample_workflows.travel_booking.NODE_IDS` and the two label tuples are
    module constants precisely so a downstream card can name them; this holds them to the
    built object, so renaming a node without telling anyone fails here.
    """
    ir = envelope.ir
    # `NODE_IDS` is builder-declaration order; the IR emits the IR-SPEC §6.2 comparator's
    # order, which is UTF-16 code units. Python's `sorted` is code *points*, and the two
    # coincide here only because every id in this set is ASCII — worth knowing before adding
    # a non-ASCII node id to a consumer-facing constant. Both facts are asserted.
    assert tuple(node.id for node in ir.nodes) == tuple(sorted(tb.NODE_IDS))
    assert set(tb.NODE_IDS) == {node.id for node in ir.nodes}
    assert ir.entry == "classify_request"
    assert ir.finish == ("notify_traveler", "release_hotel_hold")

    routed = {edge.from_: edge for edge in ir.edges if edge.kind == "conditional"}
    assert set(routed) == {"availability_check", "check_booking"}
    # Membership is the portable claim — `path_map` is a JSON object and IR-SPEC §6.2 sorts
    # its member names in the canonical bytes, so the serialized order is not this one. The
    # ordered comparison below is a deliberate pin on the model's *emission* behaviour, kept
    # because the constants document builder-declaration order and a consumer may read either.
    assert set(routed["availability_check"].path_map) == set(tb.AVAILABILITY_LABELS)
    assert set(routed["check_booking"].path_map) == set(tb.BOOKING_LABELS)
    assert tuple(routed["availability_check"].path_map) == tb.AVAILABILITY_LABELS
    assert tuple(routed["check_booking"].path_map) == tb.BOOKING_LABELS
    # INTROSPECTION-SPEC §3's `.branches` row: `condition` is the declared branch name —
    # never the router's body, and (on this path) never a guard expression. See the module
    # docstring for why that decides P-02's witness form.
    assert routed["availability_check"].condition == "route_availability"
    assert routed["check_booking"].condition == "route_booking"


def test_the_retry_policy_declared_at_the_call_site_reaches_the_ir(
    envelope: ExtractionEnvelope,
) -> None:
    """The ``retry_policy`` projection, on the one node that declares one.

    The projection rule is INTROSPECTION-SPEC §3's ``StateNodeSpec.retry_policy`` row; the
    slot shape it lands in is IR-SPEC §3.2.
    """
    carriers = {
        node.id
        for node in envelope.ir.nodes
        if node.annotations is not None and node.annotations.retry_policy is not None
    }
    assert carriers == {"availability_check"}


def test_extracting_twice_is_the_same_document(envelope: ExtractionEnvelope) -> None:
    """The digest is stable across extractions — SD-03 stores this agent under it."""
    again = extract(tb.build_travel_booking_agent())
    assert graph_version(again.ir) == graph_version(envelope.ir)
    assert again.ir == envelope.ir


def test_the_compiled_level_is_a_different_document(envelope: ExtractionEnvelope) -> None:
    """PD-023 D4, pinned rather than described: the two levels are not one document.

    The compiled path (INTROSPECTION-SPEC §4) reads the ``runtime`` sub-slots of IR-SPEC
    §3.7, which INTROSPECTION-SPEC §7.1 rates "absent, never guessed" at builder level — so
    the compiled document carries a ``runtime`` block and a different ``graph_version``. The
    card that snapshots this agent has to pick a level; this test is what makes the
    consequence of picking the other one visible.
    """
    compiled = extract(tb.compile_travel_booking_agent())
    assert compiled.ir.runtime is not None
    assert envelope.ir.runtime is None
    assert graph_version(compiled.ir) != graph_version(envelope.ir)
    # The topology is the same document's, though — only the runtime block differs.
    assert compiled.ir.nodes == envelope.ir.nodes
    assert compiled.ir.edges == envelope.ir.edges


def test_the_compiled_level_also_passes_the_wedge_five() -> None:
    """Choosing the compiled level costs no verdict — the wedge five read no ``runtime``.

    Except P-02, which reads ``runtime.recursion_limit`` — and neither of the two extraction
    modules supplies one, which is exactly why the cycle here carries a form-(c) witness.
    """
    compiled = verify(extract(tb.compile_travel_booking_agent()).ir)
    assert [outcome(compiled, slug).result for slug in WEDGE] == ["pass"] * len(WEDGE)


# ── Acceptance 2 — the wedge five pass clean on v1 ───────────────────────────────────────


def test_the_wedge_five_pass_on_v1(report: Any) -> None:
    """Acceptance box 2: five ``pass`` verdicts, exit code 0, snapshot-eligible."""
    assert [outcome(report, slug).result for slug in WEDGE] == ["pass"] * len(WEDGE)
    assert report.gate.exit_code == 0
    assert report.gate.snapshot_eligible is True


def test_each_wedge_pass_carries_a_witness_and_no_failure(report: Any) -> None:
    """PROPERTY-CATALOG-SPEC §0.3's witness-xor-failure, per property, plus the run counters.

    Worth asserting beside the verdicts because ``result == "pass"`` is the gate's input and
    the witness is the *record*; a validator that passed while carrying a failure would be a
    §0.3 violation the exit code cannot see. The run-level counters are asserted too, since
    they are what a ``--gebra-strict`` gate and the CLI's report both read.

    P-02 is the one wedge witness with a structured ``notes`` channel, and its emptiness is
    asserted where the rest of that witness is pinned
    (:func:`test_the_termination_witness_is_one_form_c_carrier`) rather than restated here.
    """
    for slug in WEDGE:
        entry = outcome(report, slug)
        assert entry.witness is not None, slug
        assert entry.failure is None, slug
    counts = report.gate.counts
    assert (counts.fatal, counts.error, counts.warning) == (0, 0, 0)


def test_strict_mode_promotes_nothing_on_v1(envelope: ExtractionEnvelope, report: Any) -> None:
    """v1 is clean under ``--gebra-strict`` too — TE-07 and SD-09 both inherit this.

    §0.2 splits the record from the gate: a WARNING-grade P-02 note (an SCC covered only by a
    blanket ``recursion_limit``) leaves every verdict untouched and still moves the exit code
    under strict promotion. This agent's witness is form (c), which is a real element rather
    than a blanket, so there is nothing to promote — asserted from both ends, the P-02
    selector and the run-level gate.
    """
    assert strict_promotions(outcome(report, "termination-witness")) == ()
    strict = verify(envelope.ir, RunPolicy(strict=StrictPolicy(mode="all")))
    assert strict.gate.exit_code == 0
    assert strict.gate.promotions == ()


def test_the_termination_witness_is_one_form_c_carrier(report: Any) -> None:
    """P-02: one variant carrier discharging both simple cycles, and no notes.

    TERMINATION-WITNESS-SPEC §2.3 discharges the *carrier node*, so a single annotation
    covers every cycle through it. Both cycles here run through ``replan``, and the census
    says so — which is what makes "one witness" the right count rather than a lucky one.
    """
    witness = outcome(report, "termination-witness").witness
    assert isinstance(witness, TerminationWitness)
    assert len(witness.inventory) == 1
    entry = witness.inventory[0]
    assert entry.form == "c"
    assert entry.discharges == "all-simple-cycles-through-element"
    assert getattr(entry.element, "node", None) == "replan"
    assert witness.notes == ()

    census = witness.cycles
    assert census is not None and census.exhaustive is True
    assert len(census.cycles) == 2
    assert all("replan" in cycle for cycle in census.cycles)


def test_the_termination_certificate_re_checks(envelope: ExtractionEnvelope, report: Any) -> None:
    """The certificate is re-verified here, which is what it exists for.

    TERMINATION-WITNESS-SPEC §6.2 puts ``certificate`` in the witness precisely so that "any
    consumer re-checks it in O(|N|+|E|) with no trust in the checker". For a substrate six
    cards will trust, taking the validator's word for its own witness is the one thing worth
    not doing — so this rebuilds the residual graph from the IR (label expansion by hand, the
    discharged carrier removed) and confirms the certificate really is a topological order of
    it: every listed vertex appears once, and no residual edge runs backwards in that order.

    START and END are the display sentinels the certificate carries at its ends; they are
    positioned but have no residual edges of their own here, so they order trivially.
    """
    witness = outcome(report, "termination-witness").witness
    assert isinstance(witness, TerminationWitness)
    discharged = {"replan"}

    position = {node: index for index, node in enumerate(witness.certificate)}
    assert len(position) == len(witness.certificate)  # no vertex listed twice
    assert set(tb.NODE_IDS) - discharged <= set(position)

    residual: list[tuple[str, str]] = []
    for edge in envelope.ir.edges:
        # Label expansion by hand (IR-SPEC §2.4): each `path_map` label is one logical edge.
        # This fixture carries only `normal` and `conditional` edges — a `send` or `dynamic`
        # edge appearing here would need its own rule, so the walk refuses rather than
        # silently skipping it.
        assert isinstance(edge, (NormalEdge, ConditionalEdge)), edge.kind
        targets = [edge.to] if isinstance(edge, NormalEdge) else list(edge.path_map.values())
        for target in targets:
            if edge.from_ in discharged or target in discharged:
                continue
            residual.append((edge.from_, target))
    assert residual  # the residual is not empty, so the ordering claim is not vacuous
    for source, target in residual:
        assert position[source] < position[target], (source, target)


def optional_keys(envelope: ExtractionEnvelope) -> set[str]:
    """The Σ keys carrying ``optional: true`` — P-04's boundary set $I_0$.

    A Σ value is the object form or, when it carries neither reducer nor flag, the bare type
    string IR-SPEC §6.3 collapses it to, so "optional" is asked of the value rather than
    assumed of its shape.
    """
    state = envelope.ir.state or {}
    return {key for key, field in state.items() if getattr(field, "optional", None) is True}


def dataflow_coverage(ir: Any) -> dict[tuple[str, str], tuple[str, ...]]:
    """``(reader, key) → covering writers``, from a P-04 pass over ``ir``."""
    witness = outcome(verify(ir), "dataflow-completeness").witness
    assert isinstance(witness, DataflowWitness)
    return {(entry.node, entry.key): entry.satisfied_by for entry in witness.coverage}


def test_the_dataflow_pass_is_not_vacuous(envelope: ExtractionEnvelope) -> None:
    """P-04 does real work here — the PD-021 D1 pin, demonstrated against its counterfactual.

    D1 reads IR-SPEC §2.2 and INTROSPECTION-SPEC §3's state row literally: ``StateGraph(S)``
    leaves ``input_schema`` equal to ``S``, every key extracts ``optional: true``, §2.2 makes
    that "written at START", and **P-04 has nothing to report on such a graph**. A pass would
    then be a fact about the declaration style rather than about the agent, and the DoD's
    seeded read-key defect would be uncatchable on this substrate.

    That is the claim, and it is *run* rather than asserted: the same nine nodes and the same
    wiring are built both ways, and the two coverages are compared.

    * Counterfactual (``narrow_input_schema=False``): all eleven Σ keys optional, and **every**
      obligation carries the START sentinel — so no read can be unwritten on any path, which
      is what "nothing to report" means concretely.
    * v1: four keys optional, seven not, and every obligation on an internal key is discharged
      by a *writing node* with no START in sight. Those are the obligations a seeded defect
      can break.

    Both graphs pass. The difference is not the verdict — it is whether the verdict could have
    been anything else.
    """
    assert optional_keys(envelope) == {
        "request",
        "traveler_id",
        "booking_request_id",
        "replan_budget",
    }
    internal = set(envelope.ir.state or {}) - optional_keys(envelope)
    assert internal  # Σ is not all-optional; P-04's obligation set is non-empty

    covered = dataflow_coverage(envelope.ir)
    assert covered  # reachable readers exist at all
    internal_obligations = {
        key: writers for (_n, key), writers in covered.items() if key in internal
    }
    assert internal_obligations, "no internal-key obligation — the pass would be vacuous"
    for key, writers in internal_obligations.items():
        assert writers, key
        assert "START" not in writers, key

    # The counterfactual, built from the same nodes and the same wiring.
    unnarrowed = extract(tb.build_travel_booking_agent(narrow_input_schema=False))
    assert unnarrowed.ir.nodes == envelope.ir.nodes
    assert unnarrowed.ir.edges == envelope.ir.edges
    assert optional_keys(unnarrowed) == set(unnarrowed.ir.state or {})
    assert all("START" in writers for writers in dataflow_coverage(unnarrowed.ir).values()), (
        "every obligation discharged at START — the vacuity D1 names"
    )


def test_the_effect_witness_carries_both_protection_forms(report: Any) -> None:
    """P-06: the two remedies §6.2 admits, one each, both *bound* rather than merely present.

    §6.3 makes protection a binding question — a keyed declaration whose key is not among the
    node's declared ``input`` is not protection, and a hook naming no node is not protection
    (DEC-05 D7's side condition). Both bindings are checked here against the IR they bind to,
    which is why this test reads the node contracts and not only the witness.
    """
    witness = outcome(report, "effect-safety").witness
    assert isinstance(witness, EffectSafetyWitness)
    records = {record.node: record for record in witness.effects}
    assert set(records) == {"book_flight", "book_hotel"}

    flight = records["book_flight"]
    assert flight.protection == "idempotency_key"
    assert flight.key == "booking_request_id"
    assert set(flight.effect) >= {"irreversible", "billable"}

    hotel = records["book_hotel"]
    assert hotel.protection == "compensation_hook"
    assert hotel.hook == "release_hotel_hold"
    assert "billable" in hotel.effect


def test_both_p06_protections_bind_to_the_ir_they_name(envelope: ExtractionEnvelope) -> None:
    """The §6.3 binding side conditions, read off the document rather than the witness."""
    nodes = {node.id: node for node in envelope.ir.nodes}
    flight = nodes["book_flight"].annotations
    assert flight is not None and flight.input is not None
    assert getattr(flight.idempotent, "key", None) in flight.input

    hotel = nodes["book_hotel"].annotations
    assert hotel is not None and hotel.compensation is not None
    assert hotel.compensation.hook in nodes


def test_the_determinism_witness_carries_both_claim_shapes(report: Any) -> None:
    """P-08: one pinned LLM-backed claim, one non-LLM claim, and the mandatory caveat.

    §8.3's model validator requires the ``provider-seed-reproducibility-not-guaranteed``
    caveat exactly when a claim is LLM-backed, and §8.1 is why: pinning is a claim about a
    provider, not about the graph. Both claim shapes are here so that a consumer of this
    substrate sees the coherent form of each — and so that SD-09's false-determinism defect
    is one keyword away from the node the catalog §8.2 names.
    """
    witness = outcome(report, "determinism-replay").witness
    assert isinstance(witness, DeterminismWitness)
    claims = {claim.node: claim for claim in witness.claims}
    assert set(claims) == {"classify_request", "compile_itinerary"}

    llm = claims["classify_request"]
    assert llm.llm_backed is True
    assert (llm.seed, llm.temperature) == (42, 0.0)

    local = claims["compile_itinerary"]
    assert local.llm_backed is False
    assert local.basis == "pure-local-computation"
    assert local.pinning_required is False

    assert witness.caveat == "provider-seed-reproducibility-not-guaranteed"
    assert witness.claim_class == "heuristic"


# ── Acceptance 3 — nothing executes, on any path ─────────────────────────────────────────


def test_every_body_in_the_fixture_is_armed() -> None:
    """The armed control: fire every node and router, and require the ledger to see it.

    The autouse fixture above asserts the ledger stays empty; on its own that is a claim
    about a guard nobody has shown to be live. This fires all nine node functions and both
    routers and asserts, per body, that it raised **and** that the raise was preceded by a
    ledger entry — the property that keeps a swallowed exception visible.

    The bodies are reached through the *built graph* rather than by name, so a node added to
    :func:`~tests.sample_workflows.travel_booking.build_travel_booking_agent` and forgotten
    here is still fired: the count assertion at the end is against
    :data:`~tests.sample_workflows.travel_booking.NODE_IDS`, which the topology test holds to
    the same object.
    """
    builder = tb.build_travel_booking_agent()
    callables: list[Any] = [spec.runnable for spec in builder.nodes.values()]
    callables += [spec.path for group in builder.branches.values() for spec in group.values()]

    fired = 0
    for runnable in callables:
        function = runnable
        while hasattr(function, "func"):
            function = function.func
        before = len(tb.TRIPPED)
        with pytest.raises(tb.TravelBookingSentinelError):
            function({})
        assert len(tb.TRIPPED) == before + 1
        fired += 1

    assert fired == len(tb.NODE_IDS) + 2  # nine nodes, two routers
    del tb.TRIPPED[:]


def test_the_sentinel_error_is_not_an_exception_subclass() -> None:
    """``BaseException``, so no ``except Exception`` guard can turn a trip into a warning."""
    assert issubclass(tb.TravelBookingSentinelError, BaseException)
    assert not issubclass(tb.TravelBookingSentinelError, Exception)


#: The guarded child: the whole extract → verify path over this agent, in a fresh
#: interpreter where resolving a name or opening a connection raises from the first line and
#: where ``StateGraph.compile`` is taken away before gebra is handed anything. Socket
#: *construction* is counted rather than refused during imports for the reason
#: ``tests/extraction/test_dispatch.py`` records: importing the substrate runs urllib3's own
#: IPv6 capability probe, which builds a loopback socket and closes it without connecting.
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
    def __new__(cls, *a, **k):
        built.append(a)
        return super().__new__(cls, *a, **k)


class _TripSocket(socket.socket):
    def __new__(cls, *a, **k):
        attempts.append("socket"); print("WA07-TRIP", file=sys.stderr)
        raise AssertionError("a socket was created on the travel-booking path")


socket.socket = _CountSocket
socket.getaddrinfo = _record("getaddrinfo")
socket.gethostbyname = _record("gethostbyname")
socket.create_connection = _record("create_connection")

import gebra
from gebra.verify import verify
from langgraph.graph.state import StateGraph
from tests.sample_workflows import travel_booking as tb

compiled = tb.compile_travel_booking_agent()

# The import phase is bounded, not excluded — see the note on the constant. From here the
# run is gebra's own work: socket construction raises too, and `compile()` goes with it,
# since INTROSPECTION §1 rule 2 forbids extraction from ever compiling a builder handed to it.
assert attempts == [], attempts
socket.socket = _TripSocket
StateGraph.compile = _record("StateGraph.compile")

wedge = (
    "graph-well-formed",
    "termination-witness",
    "dataflow-completeness",
    "effect-safety",
    "determinism-replay",
)
verdicts = []
for workflow in (tb.build_travel_booking_agent(), compiled):
    ir = gebra.extract(workflow).ir
    # Identity, not only health: a wedge-five pass over some *other* well-formed document
    # would satisfy the verdict check below, so the document is pinned to this agent first.
    assert tuple(node.id for node in ir.nodes) == tuple(sorted(tb.NODE_IDS)), ir.nodes
    report = verify(ir)
    outcomes = {p.property: getattr(p, "result", None) for p in report.properties}
    verdicts.append([outcomes[slug] for slug in wedge])
    assert report.gate.exit_code == 0, outcomes

assert verdicts == [["pass"] * 5] * 2, verdicts
"""

#: Printed last, after any probe. Two things ride here rather than in the body.
#:
#: The **ledger assertion** is here so that a probe firing a node body is caught by this leg
#: too: a probe appended after an assertion it should trip would prove only that the sentinel
#: raises, never that the assertion is live.
#:
#: The **import-phase socket count** is *reported* rather than gated. It is the residual the
#: constant's own note names — construction is counted, not refused, while the substrate
#: imports — and reporting it is what keeps that note a checked statement instead of a
#: collected-and-ignored list. It is deliberately not asserted against a bound: the count is
#: a property of whichever third-party import ran a capability probe, so a ceiling here would
#: eventually go red for a reason that has nothing to do with WA-07.
_REPORT = (
    "assert tb.TRIPPED == [], tb.TRIPPED\n"
    "print('import-phase sockets constructed:', len(built))\n"
    "print(attempts)\n"
)


def _run_guarded(probe: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", _TRIPWIRE + probe + _REPORT],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_extracting_and_verifying_the_agent_runs_nothing_and_opens_no_socket() -> None:
    """Acceptance box 3, in a fresh interpreter and over the whole path the card ships.

    Four claims at once. Every node function and router in the agent raises if it is called,
    so an extraction or a validator that reached one would fail the run;
    ``StateGraph.compile`` is taken away after the compiled fixture is built, so
    INTROSPECTION-SPEC §1 rule 2 is checked rather than reviewed; nothing resolves a name or
    opens a connection at any point, imports included; and nothing so much as constructs a
    socket once gebra's own work starts. Attempts are recorded before raising, so a swallowed
    exception still fails the run.

    **One residual, named rather than implied.** During the import phase socket
    *construction* is counted, not refused — importing the substrate runs urllib3's own IPv6
    capability probe, which builds a loopback socket and closes it without connecting. What
    is refused from the first line, imports included, is resolving a name and opening a
    connection; construction joins them the moment gebra's own work begins. The child reports
    that count rather than collecting it silently — asserted below — and deliberately does not
    gate on it, since the number belongs to whichever third-party import ran a capability
    probe.

    The child asserts its own document identity and its own verdicts — this agent's nine node
    ids, then the wedge five ``pass`` at both levels — so a run that silently stopped reaching
    the agent, or reached some other document, would fail here rather than pass with nothing
    left to prove.
    """
    finished = _run_guarded()
    assert finished.returncode == 0, finished.stderr
    assert "WA07-TRIP" not in finished.stderr
    assert "import-phase sockets constructed:" in finished.stdout
    assert finished.stdout.strip().endswith("[]")


@pytest.mark.parametrize(
    ("probe", "expected"),
    [
        ("socket.socket()\n", "a socket was created on the travel-booking path"),
        ("socket.getaddrinfo('example.invalid', 443)\n", "getaddrinfo was reached"),
        (
            "StateGraph.compile(tb.build_travel_booking_agent())\n",
            "StateGraph.compile was reached",
        ),
    ],
)
def test_the_guarded_run_is_armed(probe: str, expected: str) -> None:
    """A guard nobody trips proves nothing — each raiser the claim rests on is fired.

    Matched on the raiser's **full** message, not a substring: ``"socket"`` alone would be
    satisfied by any socket-adjacent traceback, so a control could drift onto a different
    raiser than the one the claim rests on and still look green.
    """
    finished = _run_guarded(probe)
    assert finished.returncode != 0
    assert "WA07-TRIP" in finished.stderr
    assert expected in finished.stderr


@pytest.mark.parametrize(
    ("probe", "recorded"),
    [
        (
            "try:\n    socket.getaddrinfo('example.invalid', 443)\nexcept Exception:\n    pass\n",
            "['getaddrinfo']",
        ),
        (
            "try:\n    socket.socket()\nexcept Exception:\n    pass\n",
            "['socket']",
        ),
    ],
)
def test_a_swallowed_attempt_still_fails_the_run(probe: str, recorded: str) -> None:
    """The record-before-raise design, exercised: swallowing the exception does not help.

    This is the leg the ``attempts`` report exists for. A path that reached a network
    primitive inside a ``try/except`` would raise nothing a caller could see, so the raiser
    appends to ``attempts`` *before* raising and the child prints that list last. The probe
    runs to completion — exit 0 — and the ledger it printed is what fails the assertion here.
    """
    finished = _run_guarded(probe)
    assert finished.returncode == 0, finished.stderr
    assert finished.stdout.strip().endswith(recorded)
    assert not finished.stdout.strip().endswith("[]")


def test_the_guarded_run_would_see_a_node_body_run() -> None:
    """The child's own ledger leg is live: firing a body there fails that run.

    The probe is appended *before* ``_REPORT``, which is where the child's
    ``assert tb.TRIPPED == []`` lives — so this exercises that assertion and not only the
    sentinel's raise.
    """
    finished = _run_guarded("tb.classify_request({})\n")
    assert finished.returncode != 0
    assert "TravelBookingSentinelError" in finished.stderr

    # And the same body fired with its exception swallowed: `_trip` records before it raises,
    # so the child's ledger assertion catches what the traceback would not have shown.
    swallowed = _run_guarded("try:\n    tb.classify_request({})\nexcept BaseException:\n    pass\n")
    assert swallowed.returncode != 0
    assert "travel-booking.classify_request" in swallowed.stderr


#: The import-safety probe: ``StateGraph.__init__`` and ``StateGraph.compile`` both raise
#: before the fixture module is imported for the first time in a fresh interpreter.
_IMPORT_PROBE = """
from langgraph.graph.state import StateGraph


def _no(*a, **k):
    raise AssertionError("a graph was built or compiled at import time")


StateGraph.__init__ = _no
StateGraph.compile = _no

from tests.sample_workflows import travel_booking as tb

assert tb.TRIPPED == []
print("ok")
"""


def test_importing_the_fixture_builds_no_graph_and_compiles_nothing() -> None:
    """Import safety, as the module docstring claims it: definitions only.

    ``StateGraph.__init__`` and ``StateGraph.compile`` are both replaced before the module is
    imported for the first time in a fresh interpreter; either one running would fail the
    child. This is what keeps the fixture cheap to import for the cards that only want a
    constant off it.
    """
    finished = subprocess.run(
        [sys.executable, "-c", _IMPORT_PROBE],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert finished.returncode == 0, finished.stderr
    assert finished.stdout.strip() == "ok"
