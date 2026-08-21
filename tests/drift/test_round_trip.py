"""The round-trip drift suite — TE-11's two acceptance boxes, and what stands behind them.

Box 1 — *≥ 10 pairs green under pinned versions*. Fourteen of the seventeen designated pairs
round-trip byte-identically (:data:`~tests.drift.pairs.COHERENT`); the other three carry the one
recorded divergence the set found and are asserted to be *exactly* that. The suite runs in
``testpaths = ["tests"]``, so it is carried by the locked test job and by all twelve pinned
compatibility cells with no workflow change.

Box 2 — *a seeded builder-script divergence is caught*. Ten of them, one per way a builder can
move an IR field, each attributable to its own edit because the same module's unseeded baseline
is asserted byte-identical first.

Everything else here exists so that neither box can pass for the wrong reason: the registry is
machine-checked against the corpus, the comparison is held to IR-SPEC §1.2's byte rule rather
than to JSON equality, the constructs the set claims to cover are asserted present, and WA-07's
arming is fired rather than described.
"""

from __future__ import annotations

import dataclasses
import json
import re
from functools import partial
from typing import TYPE_CHECKING, Any

import pytest
from langgraph.graph import StateGraph

from gebra.ir import canonical_bytes
from tests.drift import seeded
from tests.drift.pairs import COHERENT, PAIRS, DriftPair, script_for
from tests.drift.roundtrip import diff_documents, round_trip
from tests.drift.sentinels import TRIPPED, DriftSentinelError

if TYPE_CHECKING:
    from collections.abc import Iterator

#: The OCI digest grammar (IR-SPEC §6.1 step 8).
DIGEST_GRAMMAR = re.compile(r"^sha256:[a-f0-9]{64}$")

#: The card's floor, restated where the assertion can read it.
MIN_COHERENT_PAIRS = 10

#: Every top-level IR field a builder can move. The seeds must reach all of them.
#:
#: ``runtime`` is not among them and the omission is a fact rather than a shortfall:
#: INTROSPECTION-SPEC §7.1 records ``runtime.interrupts`` and ``runtime.checkpointer`` as
#: absent — never guessed — at builder level, and ``runtime.recursion_limit``'s designated
#: source is annotation/sidecar, which no script here carries. No edit to a builder can move
#: the block, so a seed for it would be unwritable rather than missing.
MOVABLE_REGIONS = frozenset({"entry", "finish", "state", "nodes", "edges"})


# ── WA-07: nothing here may run a node body ──────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _ledger_is_clean() -> Iterator[None]:
    """The sentinel ledger, read on entry to *and* exit from every test in this file.

    On entry too, per the TE-05 pre-review's finding: a body fired by an earlier test and left
    in the ledger would otherwise be attributed to whichever test happened to run next.
    """
    assert TRIPPED == [], f"a node body ran before this test: {TRIPPED}"
    yield
    assert TRIPPED == [], f"a node body ran during this test: {TRIPPED}"


def test_every_registered_node_body_is_armed() -> None:
    """Fire every body every graph *registers* — the arming is live, not decorative.

    Without this the WA-07 claim would rest on bodies nobody has ever seen raise. Each records
    itself **before** raising, so the ledger is what the assertion reads.

    The set is derived from the built graphs and not from module-level naming, on the
    pre-review's finding: a collection keyed on ``inspect.isfunction`` plus a name convention
    silently misses a body named ``build_summary``, a body imported from a sibling module, and
    any node that is not a plain function (a lambda, a ``partial``, a callable instance). Those
    are the shapes a later script would most plausibly reach for. Reading
    ``builder.nodes[...].runnable`` instead asks the object that will actually be extracted, and
    the reads are the ones the extractor's own contract path uses.

    Each body is required to record **exactly one** entry and that entry to be its own — a
    copy-pasted neighbour's label would otherwise pass a bare "something got recorded" check.
    """
    registered: list[tuple[str, object]] = []
    for pair in (*PAIRS, *(_seeded_pair(seed) for seed in ("none", *seeded.SEEDS))):
        builder = pair.build()
        for node_id, spec in builder.nodes.items():
            registered.append((f"{pair.script}:{node_id}", _bound_callable(spec.runnable)))

    assert len(registered) >= 3 * len(PAIRS), "every pair registers at least two node bodies"

    labels: set[str] = set()
    for where, body in registered:
        assert callable(body), where
        with pytest.raises(DriftSentinelError):
            body({})
        assert len(TRIPPED) == 1, f"{where} recorded {TRIPPED} rather than exactly one label"
        labels.add(TRIPPED[0])
        TRIPPED.clear()

    # Distinct labels per *distinct* body: the same function is registered by more than one
    # graph (the seeded module reuses the designated pair's three unchanged nodes), so the
    # count is over the set, and a body wearing a neighbour's label collapses it.
    assert len(labels) == len({body for _, body in registered})


def test_extraction_never_compiles_a_graph(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every pair extracts with ``StateGraph.compile`` armed.

    PD-023 D4 makes the builder document and the compiled document of one workflow different
    documents; this suite's subject is the builder throughout, and a pair that reached
    ``compile()`` would be comparing the fixture against the other one.

    The raiser **records before it raises**, and raises the same ``BaseException`` grade the
    node bodies do — per the pre-review's finding that a bare ``AssertionError`` here would be
    swallowable by an ``except Exception`` on an extraction path, which is the exact failure
    mode :mod:`tests.drift.sentinels` exists to prevent. The ledger it writes to is local, so
    the autouse fixture's own claim about ``TRIPPED`` stays about node bodies.
    """
    attempts: list[str] = []

    def refuse(*_: object, **__: object) -> Any:
        attempts.append("StateGraph.compile")
        raise DriftSentinelError("StateGraph.compile was called — the drift suite is builder-level")

    monkeypatch.setattr(StateGraph, "compile", refuse)
    for pair in (*PAIRS, *(_seeded_pair(seed) for seed in ("none", *seeded.SEEDS))):
        round_trip(pair)
    assert attempts == []


# ── The designated set: what it is, and that it is what the registry says ─────────────────


def test_the_designated_set_meets_the_card_floor() -> None:
    """≥ 10 coherent pairs, over both polarities and most of the corpus."""
    assert len(COHERENT) >= MIN_COHERENT_PAIRS
    directories = {pair.fixture.partition("/")[0] for pair in PAIRS}
    assert len(directories) >= 8, sorted(directories)
    stems = [pair.fixture.rpartition("/")[2] for pair in PAIRS]
    assert any(stem.startswith("positive") for stem in stems)
    assert any(stem.startswith("negative") for stem in stems)


@pytest.mark.parametrize("pair", PAIRS, ids=lambda pair: pair.name)
def test_a_pair_names_a_vendored_fixture_and_lives_where_the_convention_says(
    pair: DriftPair,
) -> None:
    """The pairing is mechanical, so it is checked rather than trusted.

    A script that moved, or a registry row pointing at the wrong module, is a pair that would
    still run — against the wrong graph. Both halves are asserted: the fixture file exists in
    the vendored corpus, and the script sits exactly where :func:`script_for` puts it.
    """
    assert pair.fixture_path.is_file(), f"{pair.fixture} is not in the vendored corpus"
    assert pair.script == script_for(pair.fixture)
    assert pair.fixture_ir() is not None


def test_no_two_rows_claim_the_same_fixture_block() -> None:
    """One (fixture, block) is one pair — a duplicated row would double-count the floor."""
    keys = [(pair.fixture, pair.ir_key) for pair in PAIRS]
    assert len(keys) == len(set(keys))


def test_the_set_reaches_the_constructs_it_claims() -> None:
    """The coverage the registry's docstring states, asserted so the set cannot quietly narrow.

    A drift suite loses its value by attrition: a pair dropped because it went red takes its
    construct with it, and nothing says so. Each line below is one construct the designated set
    exists to hold the extractor to.
    """
    documents = [json.loads(canonical_bytes(pair.fixture_ir())) for pair in PAIRS]
    states = [value for document in documents for value in document["state"].values()]
    types = {_declared_type(value) for value in states}
    annotations = [node["annotations"] for document in documents for node in document["nodes"]]

    assert any(isinstance(value, dict) and "reducer" in value for value in states)
    assert {"list", "int", "str", "UserProfile"} <= types, sorted(types)
    assert any(
        isinstance(value, dict) and value.get("optional") and "reducer" in value for value in states
    ), "an optional key that also carries a reducer"
    assert any(
        not any(_is_optional(value) for value in document["state"].values())
        for document in documents
    ), "a Σ with no graph-input key at all"

    assert any(slots.get("idempotent") is True for slots in annotations), "bare idempotence"
    assert any(isinstance(slots.get("idempotent"), dict) for slots in annotations), "keyed"
    assert any(slots.get("deterministic") is True for slots in annotations), "bare determinism"
    assert any(isinstance(slots.get("deterministic"), dict) for slots in annotations), "seeded"
    assert any("args_schema" in slots for slots in annotations)
    assert any(len(slots.get("effect", ())) == 2 for slots in annotations), "two effect tags"

    # Edge kinds. `normal` and `send` are the two a designated pair can carry: `conditional`
    # and `dynamic` both put a `condition` in the document, and the corpus writes authored
    # expressions there rather than the declared branch name extraction emits — the rule that
    # picked the set (see `tests.drift.pairs`).
    kinds = {edge.get("kind", "normal") for document in documents for edge in document["edges"]}
    assert kinds == {"normal", "send"}, sorted(kinds)

    # The empty declarations are asserted on the *models*, not on the canonical documents:
    # IR-SPEC §6.3 omit-normalizes an empty `input`/`output` away, so they are outside the
    # digest — but `()` and `None` are still different declarations, and the set covers both.
    declared = [
        node.annotations
        for pair in PAIRS
        for node in pair.fixture_ir().nodes
        if node.annotations is not None
    ]
    assert any(slots.input == () for slots in declared), "an empty declared input"
    assert any(slots.output == () for slots in declared), "an empty declared output"
    assert any(slots.effect is None for slots in declared), "an undeclared effect slot"


# ── Box 1: the round trip ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("pair", COHERENT, ids=lambda pair: pair.name)
def test_a_designated_pair_round_trips_to_its_fixture(pair: DriftPair) -> None:
    """Build it live, extract it, and require IR-SPEC §1.2's conformance against the fixture.

    Canonical bytes byte-identical **and** ``graph_version`` string-equal — both, because the
    digest is what a snapshot, a diff and a report all carry, and bytes equality is what §1.2
    actually fixes. The structural report is attached to the failure, never consulted for the
    verdict.
    """
    result = round_trip(pair)
    assert result.matched, result.report()
    assert result.extracted_version == result.fixture_version
    assert DIGEST_GRAMMAR.match(result.extracted_version)


def test_a_coherent_pair_agrees_at_model_level_too_up_to_one_named_residue() -> None:
    """Beyond the bytes: the two documents agree field for field, with one stated exception.

    Canonical bytes are the verdict, but they are also *lossy in one direction that matters
    here*: IR-SPEC §6.3 omit-normalizes an empty ``effect`` away, so a node whose fixture
    leaves the slot **undeclared** (``effect: None``) and a node whose script declares
    **no effects** (``effect: ()``) canonicalize identically. The scripts take the second form
    deliberately — an open slot is what ANNOTATION-API-SPEC §4 shallow inference fills, and a
    pair that matched because inference guessed right would be a weaker pair — so the residue
    is a consequence of the warning-free discipline rather than an accident.

    It is asserted rather than tolerated: every model-level difference across the coherent set
    must be exactly that one, on a node whose fixture declares neither ``effect`` nor ``pure``,
    with every other slot equal. Anything else — a different slot, a different direction, an
    edge, a Σ value — fails here even though the digests agree.

    Scope, stated because it is narrower than the suite's: this runs over
    :data:`~tests.drift.pairs.COHERENT` only. The three pairs carrying the recorded reducer
    divergence are held to the canonical bytes and to their record, so a *second* §6.3-invisible
    residue on one of those three would not surface here.
    """
    residue: list[str] = []
    for pair in COHERENT:
        result = round_trip(pair)
        fixture_nodes = {node.id: node for node in result.fixture.nodes}
        extracted_nodes = {node.id: node for node in result.extracted.nodes}
        assert set(fixture_nodes) == set(extracted_nodes)
        assert sorted(result.fixture.edges, key=repr) == sorted(result.extracted.edges, key=repr)
        assert result.fixture.ir_version == result.extracted.ir_version
        assert result.fixture.entry == result.extracted.entry
        assert result.fixture.finish == result.extracted.finish
        assert result.fixture.state == result.extracted.state
        assert result.fixture.runtime == result.extracted.runtime

        for node_id, authored in fixture_nodes.items():
            extracted = extracted_nodes[node_id]
            if authored == extracted:
                continue
            assert authored.annotations is not None
            assert extracted.annotations is not None
            assert authored.annotations.effect is None, f"{pair.name}/{node_id}"
            assert authored.annotations.pure is None, f"{pair.name}/{node_id}"
            assert extracted.annotations.effect == ()
            assert authored.annotations.model_copy(update={"effect": ()}) == extracted.annotations
            residue.append(f"{pair.name}/{node_id}")

    assert residue, "the empty-effect closure is claimed but never exercised"


@pytest.mark.parametrize(
    "pair",
    [pair for pair in PAIRS if pair.divergence is not None],
    ids=lambda pair: pair.name,
)
def test_a_recorded_divergence_is_still_exactly_what_was_recorded(pair: DriftPair) -> None:
    """The three reducer-spelling pairs, held to their record in both directions.

    Asserted as **equality** with the recorded difference list, not as a substring or a
    minimum: a divergence that widened would pass a containment check, and a divergence that
    was fixed upstream would leave a stale record standing. Either is a fact this suite exists
    to report.
    """
    assert pair.divergence is not None
    result = round_trip(pair)
    assert not result.matched, (
        f"{pair.name} no longer diverges — the record in tests/drift/pairs.py is stale: "
        f"{pair.divergence.reason}"
    )
    observed = diff_documents(json.loads(result.fixture_bytes), json.loads(result.extracted_bytes))
    assert observed == list(pair.divergence.differences), result.report()
    assert result.extracted_version != result.fixture_version


@pytest.mark.parametrize("pair", PAIRS, ids=lambda pair: pair.name)
def test_a_pair_warns_exactly_what_it_declares(pair: DriftPair) -> None:
    """INTROSPECTION-SPEC §8's strict-mode bar, per pair.

    Almost every pair declares no warning at all: every annotation slot its fixture carries is
    declared on the builder at the §3 decorator tier, so nothing is inferred and nothing is
    defaulted. A pair that matched only because §4 inference guessed the slot would be a weaker
    pair wearing a green tick, and this is what keeps that from happening quietly. Equality,
    not containment: a pair that *stopped* warning has also changed.
    """
    result = round_trip(pair)
    assert [warning.code.value for warning in result.warnings] == list(pair.warning_codes)


def test_a_single_differing_byte_is_non_conformance() -> None:
    """§1.2: "a single differing byte in canonical form is non-conformance", executed.

    Two tampers, because they close different holes. Byte-position substitution over the whole
    document shows the comparison has no tolerated region. The JSON-semantically-equal variant
    — the same object with its keys re-ordered — shows the comparison is over *canonical bytes*
    and not over parsed JSON, which is the looser contract a reader might assume from the
    structural report.
    """
    result = round_trip(COHERENT[0])
    assert result.matched

    for position in range(len(result.fixture_bytes)):
        tampered = bytearray(result.fixture_bytes)
        tampered[position] = (tampered[position] + 1) % 256
        assert not dataclasses.replace(result, fixture_bytes=bytes(tampered)).matched

    reordered = json.dumps(
        json.loads(result.fixture_bytes), sort_keys=False, separators=(", ", ": ")
    ).encode()
    assert reordered != result.fixture_bytes
    assert not dataclasses.replace(result, fixture_bytes=reordered).matched


# ── Box 2: a seeded builder-script divergence is caught ──────────────────────────────────


def _seeded_pair(seed: seeded.Seed) -> DriftPair:
    """The seeded module as a pair against the fixture its baseline reproduces."""
    return DriftPair(
        fixture=seeded.FIXTURE,
        ir_key="ir",
        build=partial(seeded.build_seeded, seed),
        script=seeded.__name__,
    )


def test_the_unseeded_baseline_reproduces_its_designated_pair() -> None:
    """``build_seeded("none")`` is the designated script, byte for byte.

    This is what makes the ten negatives below non-vacuous. Without it, a comparison that had
    broken in some general way would fail every seed for a reason that has nothing to do with
    the seed.
    """
    result = round_trip(_seeded_pair("none"))
    assert result.matched, result.report()


@pytest.mark.parametrize("seed", seeded.SEEDS)
def test_a_seeded_builder_script_divergence_is_caught(seed: seeded.Seed) -> None:
    """One deliberate edit to the builder, and the fixture comparison goes red.

    Both halves are asserted, because "went red" alone would be satisfied by a comparison that
    failed everything: the round trip does not match, the digests differ, **and** the rendered
    report names the IR region the seed actually moved — so a seed that went red for some other
    reason is a different failure from a seed that was caught.
    """
    result = round_trip(_seeded_pair(seed))
    assert not result.matched, f"the {seed!r} edit was not caught"
    assert result.extracted_version != result.fixture_version

    region = seeded.SEEDED_REGION[seed]
    differences = diff_documents(
        json.loads(result.fixture_bytes), json.loads(result.extracted_bytes)
    )
    assert differences, "a mismatch with nothing to name is a report, not a diagnosis"
    assert any(line.startswith((region, f"{region}.")) for line in differences), (
        f"the {seed!r} edit moved {region}, but the report names none of it:\n" + result.report()
    )


def test_the_seeds_reach_every_movable_ir_field() -> None:
    """Every top-level field a builder can move carries at least one seed.

    A negative box satisfied by ten edits to the same field would say nothing about the other
    four. ``ir_version`` is deliberately not in the set: no edit to this builder can move it —
    it follows from the constructs used (DEC-28's ``dynamic`` edge is the only 1.1 carrier),
    and the designated set uses none of them.
    """
    assert set(seeded.SEEDED_REGION.values()) == MOVABLE_REGIONS
    assert set(seeded.SEEDED_REGION) == set(seeded.SEEDS)


# ── The structural report, which renders failures and must not invent them ───────────────


def test_the_report_is_empty_exactly_when_the_pair_matched() -> None:
    """A green pair renders nothing; a red one renders both digests and every difference."""
    green = round_trip(COHERENT[0])
    assert green.report() == ""

    red = round_trip(_seeded_pair("dropped-edge"))
    report = red.report()
    assert red.pair.fixture in report
    assert red.fixture_version in report
    assert red.extracted_version in report
    assert "edges" in report


@pytest.mark.parametrize(
    ("expected", "actual", "wanted"),
    [
        ({"a": 1}, {"a": 1}, []),
        ({"a": 1}, {"a": 2}, ["a: fixture has 1, extraction has 2"]),
        ({"a": 1}, {}, ["a: only the fixture has it (1)"]),
        ({}, {"a": 1}, ["a: only extraction has it (1)"]),
        ({"a": [1]}, {"a": [1, 2]}, ["a[1]: only extraction has it (2)"]),
        ({"a": [1, 2]}, {"a": [1]}, ["a[1]: only the fixture has it (2)"]),
        ({"a": 1}, {"a": "1"}, ['a: fixture has 1, extraction has "1"']),
        ({"a": 1}, {"a": 1.0}, []),
        ({"a": True}, {"a": 1}, ["a: fixture has true, extraction has 1"]),
    ],
)
def test_the_differ_names_each_kind_of_difference(
    expected: object, actual: object, wanted: list[str]
) -> None:
    """The differ's own rows — including the two JSON traps it has to get right.

    ``1`` and ``1.0`` are the same JSON number and must not read as a difference; ``True`` and
    ``1`` are not, even though ``bool`` is an ``int`` in Python, and a differ that let those
    collapse would render a real annotation change as no change at all.
    """
    assert diff_documents(expected, actual) == wanted


# ── Helpers ──────────────────────────────────────────────────────────────────────────────


def _declared_type(value: object) -> str:
    """A canonical Σ value's ``type``, whether it is the collapsed bare form or the object one.

    IR-SPEC §6.3 collapses a value carrying neither ``reducer`` nor ``optional`` to its type
    string, so a test that read only ``value["type"]`` would see half the corpus's types.
    """
    return value["type"] if isinstance(value, dict) else str(value)


def _is_optional(value: object) -> bool:
    """Whether a canonical Σ value declares ``optional: true`` — the collapsed form never does."""
    return isinstance(value, dict) and bool(value.get("optional"))


def _bound_callable(runnable: object) -> object:
    """The node body inside whatever the substrate wrapped it in.

    ``add_node`` coerces a plain function into a ``RunnableCallable``, which holds it on
    ``.func``; the two other members here are the ones ``gebra.extraction.contracts`` walks for
    the same purpose (``RunnableLambda.func``, ``RunnableBinding.bound``), so a script that
    later registers a wrapped node is unwrapped the same way the extractor unwraps it. Bounded
    rather than recursive-until-fixpoint, and it falls back to the object itself — a node that
    *is* the callable needs no unwrapping.
    """
    current = runnable
    for _ in range(4):
        for member in ("func", "bound"):
            inner = getattr(current, member, None)
            if inner is not None and callable(inner):
                current = inner
                break
        else:
            return current
    return current  # pragma: no cover - four wrappers deep is not a shape this suite builds
