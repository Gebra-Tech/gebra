"""The designated set — which fixtures have a mini builder script, and why only these.

D-10 Deliverable 6 asks for "≥ 10 designated fixtures" with matching builders, and leaves the
choice to the implementer. The set below is **seventeen pairs over sixteen fixtures** (one
evolution fixture carries two IR blocks and therefore two factories), spanning seven of the nine
property directories plus ``mixed/``, and both polarities.

**The rule that picked them: a pair is only a pair if the fixture's IR is something extraction
can actually emit.** Exactly one construct puts the rest of the corpus out of reach, and it is a
fact about the *slot* rather than a defect in the fixtures — the corpus is hermetic serialized IR
and legal as authored.

**``condition`` on a conditional edge.** INTROSPECTION-SPEC §3's ``.branches`` row fills that
slot with the *declared branch name* — for a plain router function, its ``__name__`` (see
``gebra.extraction.builder::_read_router``) — and the same row anticipates the divergence in
terms: "extraction never persists router bodies; **authored IRs may carry richer declared
expressions in the same slot**". Every conditional edge in the corpus carries such an
expression, or an English sentence (``'retry' if booking_status == 'failed' and retry_count < 2
else 'ok'``; ``router decides 'continue' or 'done' from latest observations``), and gebra has no
annotation or sidecar carrier for ``condition`` at all — IR-SPEC §2.4's "taken from gebra
annotations/config" has, at builder level, no such declaration to take. So a conditional fixture
has no pair, and that is the spec's own reading rather than a gap to file.

``send`` edges are **not** excluded, and the distinction is worth stating because a first draft
of this file got it wrong. INTROSPECTION-SPEC §6 admits two surfaces: a ``BranchSpec``
(``add_conditional_edges``) has a declared branch name and its edge carries it, while
``StateNodeSpec.ends`` — ``destinations=`` on a ``Send``-hinted node function — has no
``BranchSpec`` behind it and so emits ``condition=None``
(``builder.py::_node_destinations``; pinned by ``tests/extraction/test_routing.py``). That is
exactly the shape the corpus's send fixtures declare, so
``parallel-safety/negative-02-send-fanout-reducerless-findings`` is designated. The corpus's
other send fixture, ``mixed/09``, also carries a conditional edge and is excluded by the rule
above, not by its send edge.

So the reachable pool is the fixtures whose every edge is ``normal`` or ``send`` — **twenty-one**
of the sixty. Sixteen are designated here. The five left out —
``determinism-replay/negative-02``, ``evolution-safety/negative-01``, ``mixed/03``,
``parallel-safety/positive-02`` and ``signature-soundness/negative-02`` — each repeat a shape a
designated pair already holds (a second seeded/unseeded determinism claim, a second evolution
pair, a second parallel fan-in, a second undeclared-write negative), so they would add pairs
without adding coverage. Nothing about them is unreachable: any of the five could be built the
same way if the floor needed raising.

What the ``condition`` rule costs in coverage is stated rather than papered over:
**``termination-witness`` and ``retry-coherence`` have no pair**, because every fixture in both
directories is conditional. That is a real gap in this suite and it is recorded on the TE-11
card, not hidden by picking a different denominator.

**One divergence was found, and it is recorded rather than selected away.** Three of the
seventeen pairs — every pair whose Σ carries a reducer — differ from their fixture in exactly one
string: the corpus writes ``operator.add`` and extraction writes ``_operator.add``. See
:func:`reducer_spelling` for the two settled positions behind it and why neither is this card's
to move. They stay in :data:`PAIRS` carrying the exact difference, so the suite fails if it
widens *or* if it silently goes away; :data:`COHERENT` is the fourteen that round-trip
byte-identically, and only those fourteen are compared at model level as well as at the bytes —
the three are held to the bytes and to their record.

**What the set does cover**, deliberately, one construct at a time: linear chains,
fan-out/fan-in diamonds and a ``Send`` fan-out template; the ``normal`` and ``send`` edge kinds;
``optional: true`` present, absent and on a reduced key; an ``Annotated[T, reducer]`` Σ value and
its reducerless twin; ``list``, ``int``, ``str`` and a user-defined class as Σ types; and every
annotation slot the designated fixtures carry — ``pure``, ``effect`` (including the empty
declaration), ``idempotent`` bare and keyed, ``deterministic`` bare and with
``seed``/``temperature``, ``input``/``output`` including the empty forms, and ``args_schema``.

**Three declarable slots are not covered, and the reason is the ``condition`` rule again**:
``variant`` (``@gebra.variant``), ``compensation`` (``@gebra.compensation``) and the
builder-level ``retry_policy``. The corpus fixtures that carry the first two —
``termination-witness/positive-03`` and ``effect-safety/positive-03`` — are both conditional, so
neither is in the reachable pool; no fixture in the corpus declares a ``retry_policy`` at all.
Named here rather than left to be discovered from the absence.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING, Any, Final, Literal

from gebra.testing.fixtures import load_fixture
from tests.conftest import FIXTURES_DIR
from tests.drift.builders.dataflow_completeness import (
    negative_02_writer_downstream_of_reader,
    positive_01_linear_itinerary_pipeline,
    positive_03_parallel_fanout_reduced_results,
)
from tests.drift.builders.determinism_replay import (
    negative_01_seedless_deterministic_llm_classifier,
    positive_01_pinned_seed_zero_temp_classifier,
    positive_02_pure_fare_normalizer,
)
from tests.drift.builders.effect_safety import negative_03_keyless_idempotent_on_irreversible
from tests.drift.builders.evolution_safety import positive_02_optional_loyalty_tier_key_added
from tests.drift.builders.graph_well_formed import positive_01_linear_document_pipeline
from tests.drift.builders.mixed import (
    fixture_07_subgraph_leaked_key_collides_with_parallel_sibling,
)
from tests.drift.builders.parallel_safety import (
    negative_01_reducerless_shared_notes_fanout,
    negative_02_send_fanout_reducerless_findings,
    positive_01_reducer_guarded_parallel_enrichment,
)
from tests.drift.builders.signature_soundness import (
    negative_01_read_key_absent_from_sigma,
    negative_03_args_schema_type_mismatch,
    positive_01_linear_booking_declared_io,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from gebra.ir import WorkflowIR

__all__ = [
    "BUILDER_PACKAGE",
    "COHERENT",
    "PAIRS",
    "DriftPair",
    "IrKey",
    "KnownDivergence",
    "reducer_spelling",
    "script_for",
]

#: Which IR block of a fixture a pair is about (``schema.yaml``'s top-level ``oneOf``).
IrKey = Literal["ir", "ir_before", "ir_after"]

#: The dotted root every mini builder script lives under.
BUILDER_PACKAGE: Final = "tests.drift.builders"


def script_for(fixture: str) -> str:
    """The module a fixture's script must live in — the naming convention, as a function.

    ``"graph-well-formed/positive-01-linear-document-pipeline"`` →
    ``"tests.drift.builders.graph_well_formed.positive_01_linear_document_pipeline"``.

    One adjustment, for the one shape the corpus has that Python does not: a ``mixed/`` stem
    begins with its serial (``07-subgraph-…``) and no module name may begin with a digit, so
    such a stem is prefixed with ``fixture_``.
    """
    directory, _, stem = fixture.partition("/")
    module = stem.replace("-", "_")
    if module[:1].isdigit():
        module = f"fixture_{module}"
    return f"{BUILDER_PACKAGE}.{directory.replace('-', '_')}.{module}"


@dataclass(frozen=True)
class KnownDivergence:
    """A difference between a fixture's IR and what extraction emits, recorded rather than hidden.

    A drift suite that quietly dropped every pair it could not make green would report the
    absence of drift it had selected for. So a designated pair whose round trip *does* differ
    stays in :data:`PAIRS` and carries one of these: the exact structural difference, and why
    it is neither side's defect to fix here. The suite then asserts the difference is
    **exactly** what is recorded — so it goes red if the divergence widens, and red again if
    it disappears, which is the direction a stale record would otherwise survive.

    Attributes:
        differences: The lines :func:`tests.drift.roundtrip.diff_documents` must produce, in
            order and in full. Not a substring match: an extra difference is a failure.
        reason: Why the divergence stands, with its ruling cited.
    """

    differences: tuple[str, ...]
    reason: str


def reducer_spelling(key: str) -> KnownDivergence:
    """The corpus writes ``operator.add``; extraction writes ``_operator.add``.

    The one divergence the designated set found, on three pairs — every fixture in the set
    whose Σ carries a reducer. Both spellings are deliberate and neither is available to this
    card to change:

    * **Extraction** spells a reducer ``module.qualname`` as Python itself carries it, and
      ``operator.add`` names its module ``_operator`` because the C accelerator is where the
      object comes from and nothing on it remembers the alias. What settles it is that the
      spelling is **pinned in three EX-14 conformance goldens** (``builder-surface``,
      ``builder-send``, ``builder-dynamic``) under the WA-05 lifecycle, at a gate — G4 — that
      is signed; moving it is a golden change requiring justification, not a local edit. The
      *reasoning* is PD-021 D3, on the reading that IR-SPEC §2.2 "illustrates the slot with
      ``operator.add`` and fixes no spelling"; that record's own status is `proposed`, so it
      is cited as the rationale rather than as the authority.
    * **The corpus** writes the spec's own illustrative spelling. It is a vendored,
      R-05-owned contract surface: WA-04 routes any revision through vault sign-off, and a
      quiet edit is exactly what that agreement forbids.

    So it is logged rather than resolved, and the disposition is stated so it is not mistaken
    for a decision: the WA-04 fixture-revision request is **deferred, not declined**, and it
    is routed on the TE-11 card to **TE-14** — the gap-fixture authoring card, which is the
    next card that opens the vault-first fixture flow and therefore the cheapest place to ask
    R-05 the question. Neither resolution is taken here.

    What it costs today is stated rather than guessed. No **validator** reads the reducer's
    name — P-09 reads presence and absence, and is not implemented in the wedge — so no
    verdict in the corpus moves. Two consumers do read it: ``graph_version``, so a digest
    taken from one of these fixtures and a digest taken from the equivalent live graph are
    different strings; and ``gebra.diff``, whose ``StateFacet.reducer_changed`` compares the
    two strings, so a diff across the two spellings reports a ``reducer`` facet change.
    """
    return KnownDivergence(
        differences=(
            f'state.{key}.reducer: fixture has "operator.add", extraction has "_operator.add"',
        ),
        reason=(
            "PD-021 D3 spells a reducer as Python carries it (`operator.add.__module__` is "
            "`_operator`); the corpus writes IR-SPEC §2.2's illustrative `operator.add`. "
            "Extractor side is golden-pinned (EX-14, G4 signed); corpus side is vendored "
            "read-only (WA-04). Logged, not edited."
        ),
    )


@dataclass(frozen=True)
class DriftPair:
    """One fixture ↔ one mini builder script.

    Attributes:
        fixture: The corpus-relative stem, e.g.
            ``"parallel-safety/positive-01-reducer-guarded-parallel-enrichment"``.
        ir_key: Which of the fixture's IR blocks this pair reproduces.
        build: The factory that returns the live ``StateGraph``. Called once per round trip.
        script: The dotted module name the factory came from.
        warning_codes: The INTROSPECTION-SPEC §8 / ANNOTATION-API-SPEC §4 codes extraction is
            expected to emit, in emission order. Empty for almost every pair — §8 makes a
            warning-free extraction part of the strict-mode bar, and a pair that matched only
            because §4 inference guessed the slot the fixture *declares* would be a weaker
            pair wearing a green tick. The suite asserts equality, so a pair that stopped
            warning fails too.
        divergence: ``None`` when the round trip is byte-identical; otherwise the recorded
            difference the suite holds it to.
    """

    fixture: str
    ir_key: IrKey
    build: Callable[[], Any]
    script: str
    warning_codes: tuple[str, ...] = ()
    divergence: KnownDivergence | None = None

    @property
    def name(self) -> str:
        """The pytest parameter id — the fixture, plus the block when there are two."""
        return self.fixture if self.ir_key == "ir" else f"{self.fixture}[{self.ir_key}]"

    @property
    def fixture_path(self) -> Path:
        """The vendored fixture file this pair is held to."""
        return FIXTURES_DIR / f"{self.fixture}.yaml"

    def fixture_ir(self) -> WorkflowIR:
        """The fixture's IR block, through the corpus's own hermetic loader.

        Read with :func:`gebra.testing.fixtures.load_fixture` rather than with a local
        ``yaml.safe_load`` on purpose: a drift pair must be held to the same document the
        golden harness runs, so a loader-level divergence cannot hide between the two suites.
        """
        fixture = load_fixture(self.fixture_path)
        block: WorkflowIR | None = getattr(fixture, self.ir_key)
        if block is None:  # pragma: no cover - a registry typo, caught by test_round_trip
            raise AssertionError(f"{self.fixture} carries no {self.ir_key!r} block")
        return block


def _pair(
    module: ModuleType,
    *,
    ir_key: IrKey = "ir",
    factory: str = "build",
    warning_codes: tuple[str, ...] = (),
    divergence: KnownDivergence | None = None,
) -> DriftPair:
    """One registry row, with the fixture name read off the script rather than repeated."""
    return DriftPair(
        fixture=module.FIXTURE,
        ir_key=ir_key,
        build=getattr(module, factory),
        script=module.__name__,
        warning_codes=warning_codes,
        divergence=divergence,
    )


#: The designated set, in corpus order. ``tests/drift/test_round_trip.py`` quantifies over it.
PAIRS: Final[tuple[DriftPair, ...]] = (
    _pair(negative_02_writer_downstream_of_reader),
    _pair(positive_01_linear_itinerary_pipeline),
    _pair(positive_03_parallel_fanout_reduced_results, divergence=reducer_spelling("results")),
    _pair(negative_01_seedless_deterministic_llm_classifier),
    _pair(positive_01_pinned_seed_zero_temp_classifier),
    _pair(positive_02_pure_fare_normalizer),
    # The fixture's own P-06 defect is an *annotation*-level one — bare `idempotent: true` on
    # a node whose effects include `irreversible` — which decision D-012 rejects as a design
    # error, so the resolution chain says so, warning-grade, and carries the declaration into
    # the IR unchanged. Expected here rather than tolerated: this is the extractor reading a
    # negative fixture correctly, not a slot nobody declared.
    _pair(negative_03_keyless_idempotent_on_irreversible, warning_codes=("annotation-invalid",)),
    _pair(positive_02_optional_loyalty_tier_key_added, ir_key="ir_before", factory="build_before"),
    _pair(positive_02_optional_loyalty_tier_key_added, ir_key="ir_after", factory="build_after"),
    _pair(positive_01_linear_document_pipeline),
    _pair(
        fixture_07_subgraph_leaked_key_collides_with_parallel_sibling,
        divergence=reducer_spelling("sources"),
    ),
    _pair(negative_01_reducerless_shared_notes_fanout),
    _pair(negative_02_send_fanout_reducerless_findings),
    _pair(
        positive_01_reducer_guarded_parallel_enrichment,
        divergence=reducer_spelling("notes"),
    ),
    _pair(negative_01_read_key_absent_from_sigma),
    _pair(negative_03_args_schema_type_mismatch),
    _pair(positive_01_linear_booking_declared_io),
)

#: The pairs whose round trip is byte-identical — the card's "≥ 10 pairs green" denominator.
COHERENT: Final[tuple[DriftPair, ...]] = tuple(pair for pair in PAIRS if pair.divergence is None)
