"""State-schema (Σ) extraction, and the never-invokes tripwire for that path.

Normative authority: INTROSPECTION-SPEC §3 (the ``.channels``/state-schema row), §7.1 (the
knowability entries), §7.3 item 4 (managed values), §8 (the warnings taxonomy); IR-SPEC §2.2
(the Σ shape), §6.3 (representation-normalization) and §7 (H4), under §1's never-invokes
discipline.

The suite is organized around the card's two acceptance boxes. The first — representative
schemas extract to spec-shaped state blocks — is an equality against
:data:`tests.sample_workflows.sentinel_state.STATE_CASES`, where each case declares its own
expected Σ, so a projection that changed fails the case that declares it rather than a
hand-written assertion somewhere. The second — representation collapse verified against the
IR-03 normalization — is checked as the property it is: the emitted form and the admitted
object form of the *same* content canonicalize to the same bytes and the same
``graph_version``.

Every schema in the fixture module is armed: pydantic validators, a metaclass property, a
channel's type properties and every declared reducer raise if they are reached, so "extraction
inspects, it never invokes" is checked by the fixtures on every test in this file, not only in
the guarded subprocess at the bottom.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from gebra.extraction import (
    UNREPRESENTABLE_REDUCER,
    UNREPRESENTABLE_TYPE,
    ExtractionWarningCode,
    extract,
    read_state,
)
from gebra.ir.canonical import canonical_bytes, graph_version
from gebra.ir.models import Annotations, Node, StateField, WorkflowIR
from gebra.ir.serialization import dump_json, load_json
from gebra.verify.properties.dataflow_completeness import check_dataflow_completeness
from tests.sample_workflows import sentinel_state as ss


def state_warnings(envelope: Any) -> tuple[Any, ...]:
    """The ``unsupported-construct`` records — the only code the §3 state row emits.

    Since EX-11 wired the ANNOTATION §3 chain into the builder path, every node also carries
    its own contract records. Those belong to ``tests/extraction/test_contracts.py``, so the
    "warns for this and for nothing else" claims below are quantified over the state row's
    own code and stay exactly as strong as they were.
    """
    return tuple(
        warning
        for warning in envelope.warnings
        if warning.code is ExtractionWarningCode.UNSUPPORTED_CONSTRUCT
    )


REPO_ROOT = Path(__file__).resolve().parents[2]

CASE_NAMES = sorted(ss.STATE_CASES)


def state_of(name: str) -> dict[str, str | StateField] | None:
    """The ``state`` block one fixture case extracts to."""
    return extract(ss.STATE_CASES[name].make()).ir.state


def block(name: str) -> dict[str, str | StateField]:
    """The same, for a case that is known to declare keys."""
    state = state_of(name)
    assert state is not None
    return state


# ── The card's first box: representative schemas extract to spec-shaped state blocks ─────


@pytest.mark.parametrize("name", CASE_NAMES)
def test_every_case_extracts_to_its_declared_state(name: str) -> None:
    """Σ is an equality against the table, not a spot check.

    The case declares the whole block — keys, types, reducers, flags, and which values are
    already collapsed — so this one assertion covers §3's projection and §6.3's
    representation at once, per shape.
    """
    case = ss.STATE_CASES[name]

    assert extract(case.make()).ir.state == case.state, case.why


@pytest.mark.parametrize("name", CASE_NAMES)
def test_every_case_extracts_to_its_declared_provenance(name: str) -> None:
    """The managed keys are provenance, and the table declares those too (§3; §7.3 item 4)."""
    case = ss.STATE_CASES[name]

    assert extract(case.make()).extracted_from.managed_state_keys == case.managed, case.why


@pytest.mark.parametrize("name", CASE_NAMES)
def test_every_case_emits_exactly_the_warnings_it_declares(name: str) -> None:
    """A shape warns for what it declares and for nothing else.

    Both halves matter: a missing warning hides a construct the IR did not carry, and an
    extra one puts a workflow outside §8's strict-mode bar for a shape that extracted fine.
    """
    case = ss.STATE_CASES[name]
    envelope = extract(case.make())

    constructs = tuple(warning.detail["construct"] for warning in state_warnings(envelope))

    assert constructs == case.constructs, case.why


def test_the_representative_schemas_are_all_covered() -> None:
    """The card names four representative schemas; each is a case here, by name.

    Written as an equality against the whole required set rather than as four ``in`` checks,
    so dropping one fails this test rather than shrinking the claim silently. "Optional" is
    the shape where a key is *not* the mandatory input — a defaulted pydantic field and a
    declared-input narrowing are both that shape, and both are named.
    """
    representative = {
        "plain": ("plain",),
        "reducer": ("reducer",),
        "optional": ("declared-input", "pydantic-defaults-only"),
        "pydantic": ("pydantic", "pydantic-defaults-only"),
    }

    named = {name for names in representative.values() for name in names}

    assert set(representative) == {"plain", "reducer", "optional", "pydantic"}
    assert named <= set(ss.STATE_CASES)
    for shape, names in representative.items():
        for name in names:
            assert ss.STATE_CASES[name].state is not None, shape


@pytest.mark.parametrize("name", CASE_NAMES)
def test_every_extracted_state_block_is_the_ir_model_shape(name: str) -> None:
    """Spec-shaped means it survives the model: serialize, reload, compare (IR-SPEC §2.2).

    A block that carried something outside ``str | StateField`` — a bare dict, a non-string
    type — would validate here rather than at some later stage, which is the point: the
    extractor's output is an IR document or it is nothing.
    """
    ir = extract(ss.STATE_CASES[name].make()).ir

    reloaded = load_json(WorkflowIR, dump_json(ir))

    assert reloaded == ir
    for key, value in (ir.state or {}).items():
        assert isinstance(key, str)
        assert isinstance(value, (str, StateField))


@pytest.mark.parametrize("name", CASE_NAMES)
def test_every_extracted_state_block_canonicalizes(name: str) -> None:
    """Σ's keys are identifier-role strings, so canonicalization must accept them (§6.3).

    Not a formality: canonicalization *refuses* a non-NFC identifier rather than normalizing
    one, so an extractor that emitted authored bytes would produce an IR that exists and
    cannot be digested — extraction total in name only.
    """
    envelope = extract(ss.STATE_CASES[name].make())

    assert envelope.graph_version().startswith("sha256:")


# ── The card's second box: the collapse, against the IR-03 normalization ─────────────────


def expanded(state: dict[str, str | StateField] | None) -> dict[str, str | StateField] | None:
    """The same Σ with every collapsed value written back in its object form.

    The other admitted surface variant of the same content (§2.2: a value is "either a bare
    type-name string or an object"), which §6.3 says canonicalization maps onto the collapsed
    one.
    """
    if state is None:
        return None
    return {
        key: StateField(type=value) if isinstance(value, str) else value
        for key, value in state.items()
    }


@pytest.mark.parametrize("name", CASE_NAMES)
def test_the_emitted_representation_is_the_canonical_one(name: str) -> None:
    """The extracted form and the expanded form are one document (IR-SPEC §6.3).

    This is the card's second acceptance box, checked as the property it is rather than by
    inspecting the emitter: "a ``state`` value collapses to the bare type-name string iff it
    carries no ``reducer`` and no ``optional`` flag … ``gebra.extract()`` emits these
    collapsed forms directly, and canonicalization maps any admitted surface variant onto
    them". So the two spellings must produce byte-identical canonical form and one
    ``graph_version`` — which is also what makes an extracted IR comparable against a
    hand-written golden that spelled a value the other way.
    """
    ir = extract(ss.STATE_CASES[name].make()).ir
    variant = ir.model_copy(update={"state": expanded(ir.state)})

    assert canonical_bytes(variant) == canonical_bytes(ir)
    assert graph_version(variant) == graph_version(ir)


@pytest.mark.parametrize("name", CASE_NAMES)
def test_no_emitted_object_form_could_collapse_further(name: str) -> None:
    """Every object-form value carries a ``reducer`` or an ``optional`` — the "iff", one way.

    Emitting an object that canonicalization would collapse is not a byte-level defect (the
    digest is the same, which the test above shows) but it *is* a model-level one: goldens,
    caches and round-trip comparisons compare models, and two extractions that disagreed
    about the representation would compare unequal while digesting the same.
    """
    for key, value in (state_of(name) or {}).items():
        if isinstance(value, StateField):
            assert value.reducer is not None or value.optional is not None, key


@pytest.mark.parametrize("name", CASE_NAMES)
def test_no_emitted_value_that_carries_neither_stayed_expanded(name: str) -> None:
    """…and the other way: a value with no reducer and no flag is already a bare string.

    Quantified over the *expanded* spelling of the same block, so the check is "would this
    have collapsed" rather than a restatement of what the emitter did.
    """
    for key, value in (expanded(state_of(name)) or {}).items():
        collapsible = value.reducer is None and value.optional is None  # type: ignore[union-attr]
        emitted = (state_of(name) or {})[key]
        assert collapsible == isinstance(emitted, str), key


@pytest.mark.parametrize("name", CASE_NAMES)
def test_optional_is_never_emitted_false(name: str) -> None:
    """Absence, never ``optional: false`` — an explicit ``false`` is a *carried* flag.

    §6.3 omit-normalizes a member equal to its schema default, and the default here is
    ``null``; an explicit ``false`` is neither, so it survives into canonical bytes and blocks
    the collapse while saying exactly what absence says.
    """
    for key, value in (state_of(name) or {}).items():
        if isinstance(value, StateField):
            assert value.optional is not False, key


# ── `optional`: the graph-input/defaulted rule (§2.2, §3, §7.1; PD-021 D1) ───────────────


def test_every_key_of_a_single_schema_builder_is_a_graph_input() -> None:
    """``StateGraph(S)`` leaves ``input_schema`` equal to ``S``, so every key is optional.

    The literal reading of §2.2 ("the key is graph input or carries a default") over §7.1's
    builder-level source (``builder.input_schema``): with no narrowing, the caller may supply
    any key at invocation, so each one is a declared graph input.
    """
    assert block("plain") == {
        "task": StateField(type="str", optional=True),
        "count": StateField(type="int", optional=True),
    }


def test_a_declared_input_schema_is_what_makes_the_flag_discriminate() -> None:
    """A narrowed input schema marks exactly the keys the graph takes from outside.

    This is the authoring surface the rule above hands back to the author, and the reason it
    is the reading this build implements: the extractor never has to guess which keys arrive
    at ``START``, because ``StateGraph(S, input_schema=I)`` is where LangGraph lets that be
    said. The result is the shape the hand-written corpus writes by hand — one graph-input
    key, the rest internal.
    """
    narrowed = block("declared-input")

    assert narrowed["task"] == StateField(type="str", optional=True)
    assert narrowed["draft"] == "str"
    assert narrowed["answer"] == "str"


def test_a_key_outside_the_input_schema_is_optional_when_it_carries_a_default() -> None:
    """The second disjunct, alone: no key is a graph input and the defaulted ones still flag.

    Both declaration surfaces that *have* defaults are covered — a pydantic field default and
    a dataclass ``default``/``default_factory`` — because §7.1's "schema-default inspection"
    is one phrase over two different objects.
    """
    for name in ("pydantic-defaults-only", "dataclass"):
        keys = block(name)
        assert keys["task"] == "str", name
        assert keys["note"] == StateField(type="str", optional=True), name
        assert keys["tags"] == StateField(
            type="list[str]", reducer="_operator.add", optional=True
        ), name


def test_what_the_flag_costs_and_what_declaring_the_input_schema_buys() -> None:
    """The consequence of the rule, demonstrated on P-04 rather than described.

    §2.2 makes ``optional: true`` mean "written at ``START``", and P-04 reads it as the
    boundary set $I_0$. So on a single-schema builder — where every key is a graph input —
    P-04 has nothing to report about a key no node writes, while the *same* graph with a
    declared input schema is analysed precisely. Contracts are attached here by hand because
    no extraction path fills ``annotations`` yet (that is the precedence chain's card); what
    the extraction supplies is the ``state`` block, which is exactly the input under test.
    """
    reader = Node(id="a", annotations=Annotations(input=("draft",)))

    def ir_for(name: str) -> WorkflowIR:
        extracted = extract(ss.STATE_CASES[name].make()).ir
        return extracted.model_copy(update={"nodes": (reader,)})

    assert check_dataflow_completeness(ir_for("plain-wide")).result == "pass"
    assert check_dataflow_completeness(ir_for("declared-input")).result == "fail"


# ── Managed values: provenance, never Σ (§3; §7.3 item 4) ────────────────────────────────


def test_a_managed_key_is_recorded_in_provenance_and_is_not_a_state_key() -> None:
    """Both halves of §3's sentence, on one graph.

    "ir 1.0 has no managed marker slot — extraction records presence in provenance as P-02
    corroborating evidence only." So the key is absent from Σ (there is no slot that could
    say what it is) and present on the envelope, where P-02's witness reasoning can see it.
    """
    envelope = extract(ss.STATE_CASES["managed"].make())

    assert set(envelope.ir.state or {}) == {"task", "answer"}
    assert envelope.extracted_from.managed_state_keys == ("remaining",)


def test_a_managed_key_emits_no_warning() -> None:
    """Declaring ``RemainingSteps`` is not a defect, and §8 has no row for it.

    A warning here would put every graph that uses a supported substrate feature outside the
    strict-mode bar, and it would have to borrow a code from a closed vocabulary to do it.
    """
    assert state_warnings(extract(ss.STATE_CASES["managed"].make())) == ()


def test_a_managed_key_does_not_move_the_digest() -> None:
    """Provenance is outside hash scope (§6.4), which the envelope makes structural."""
    envelope = extract(ss.STATE_CASES["managed"].make())
    without = envelope.model_copy(
        update={
            "extracted_from": envelope.extracted_from.model_copy(update={"managed_state_keys": ()})
        }
    )

    assert without.graph_version() == envelope.graph_version()


# ── What Σ cannot carry: the §8 records, and why the key survives anyway ─────────────────


@pytest.mark.parametrize("name", CASE_NAMES)
def test_every_state_warning_carries_its_row(name: str) -> None:
    """One code, and the four facts §8's ``unsupported-construct`` row names.

    The location is the state key: §8 asks for "location (node/edge)", a state key is
    neither, and naming the key is the honest answer to the same question. The key names a
    Σ member for every construct that kept the key — which is all of them but the one whose
    whole content is that the key has no ir 1.0 form.
    """
    envelope = extract(ss.STATE_CASES[name].make())
    kept = envelope.ir.state or {}

    for warning in state_warnings(envelope):
        named = warning.detail["location"]["state_key"]
        assert warning.code is ExtractionWarningCode.UNSUPPORTED_CONSTRUCT
        assert set(warning.detail) == {"construct", "location", "why", "ir_partial"}
        assert set(warning.detail["location"]) == {"state_key"}
        assert warning.detail["ir_partial"] is True
        if warning.detail["construct"] == "state-key-unserializable":
            assert named not in kept
        else:
            assert named in kept


def test_a_key_bound_to_a_user_written_channel_keeps_its_place_in_sigma() -> None:
    """The type is not readable; the key still exists, and the marker says which is which.

    Dropping it would turn "this type has no spelling" into "this key does not exist" — a
    stronger claim, and the one that P-03 would then report against whichever node reads it.
    """
    guarded = block("custom-channel")

    assert guarded["guarded"] == StateField(type=UNREPRESENTABLE_TYPE, optional=True)


def test_an_unnameable_reducer_is_marked_rather_than_omitted() -> None:
    """An absent ``reducer`` is a positive claim, so it is not how "unnameable" is spelled.

    "No reducer" is what P-09 reads as an unreduced shared write — an ERROR grade inside a
    ``send`` template (IR-SPEC §2.4) — so the two must not share a spelling.
    """
    total = block("unnameable-reducer")["total"]

    assert total == StateField(type="int", reducer=UNREPRESENTABLE_REDUCER, optional=True)


def test_neither_marker_can_collide_with_a_rendered_spelling() -> None:
    """Both markers carry a ``:``, and no rendered type or reducer name contains one.

    Quantified over every rendered value in the whole table rather than argued: that is what
    makes the markers unambiguous rather than merely unlikely.
    """
    assert ":" in UNREPRESENTABLE_TYPE
    assert ":" in UNREPRESENTABLE_REDUCER
    for name in CASE_NAMES:
        for value in (state_of(name) or {}).values():
            rendered = [value] if isinstance(value, str) else [value.type, value.reducer]
            for item in rendered:
                if item in (None, UNREPRESENTABLE_TYPE, UNREPRESENTABLE_REDUCER):
                    continue
                assert ":" not in str(item), name


def test_a_stock_channel_keeps_its_type_and_reports_the_semantics_it_loses() -> None:
    """``Topic`` accumulates; ir 1.0 says "type plus an optional declared reducer".

    So the type is projected and the merge semantics is warned — the IR is honestly partial
    at that key rather than silently claiming last-write-wins.
    """
    envelope = extract(ss.STATE_CASES["stock-channel"].make())

    assert (envelope.ir.state or {})["items"] == StateField(type="Sequence[str]", optional=True)
    assert state_warnings(envelope)[0].detail["construct"] == "state-channel-semantics-not-carried"


def test_two_keys_that_are_one_identifier_lose_one_of_them_loudly() -> None:
    """NFC makes the two spellings one key downstream; the drop is warned, never silent."""
    envelope = extract(ss.STATE_CASES["colliding-keys"].make())

    assert set(envelope.ir.state or {}) == {"café"}
    assert state_warnings(envelope)[0].detail["construct"] == "state-key-collision"


def test_a_schema_with_no_key_emits_no_state_block() -> None:
    """``state: {}`` is the positive claim "Σ is empty" and reaches the digest as one.

    Canonical form preserves an empty object (§6.3 omits ``null``, defaults and empty
    *arrays*, and ``{}`` is none of the three), so absence and the empty object are two
    different documents. A schema that declares nothing is the first, not the second.
    """
    envelope = extract(ss.STATE_CASES["keyless"].make())

    assert envelope.ir.state is None
    assert b'"state"' not in canonical_bytes(envelope.ir)


# ── The projection is a value ────────────────────────────────────────────────────────────


@pytest.mark.parametrize("name", CASE_NAMES)
def test_the_state_block_repeats_exactly(name: str) -> None:
    """Two extractions of one schema agree as models and as digests.

    Worth pinning: the block is built from mappings the substrate populates, and a projection
    that depended on iteration order or on object identity would only show up as goldens that
    fail on some runs.
    """
    case = ss.STATE_CASES[name]
    first, second = extract(case.make()), extract(case.make())

    assert first.ir.state == second.ir.state
    assert first.graph_version() == second.graph_version()


def test_read_state_reads_nothing_off_an_object_that_declares_nothing() -> None:
    """The row's own entry point is total: no channels, no managed values, no Σ.

    ``read_state`` is public — a caller that has a builder can ask for the state row alone —
    so it answers rather than raising for an object that carries neither mapping.
    """
    reading = read_state(SimpleNamespace())  # type: ignore[arg-type]

    assert reading.state is None
    assert reading.managed == ()
    assert reading.warnings == ()


# ── WA-07 — the tripwire for the path this card lands ────────────────────────────────────

#: The guarded child. Network primitives raise from the first line; socket construction is
#: only counted until the imports are done, and the builders are built while the substrate
#: still has everything it needs. Then ``StateGraph.compile``, ``typing.get_type_hints``,
#: ``eval`` and ``exec`` are all replaced by raisers and every case is extracted.
#:
#: ``get_type_hints`` is the one that makes this path's claim specific: §1 rule 3 permits it
#: but warns that it *evaluates* string annotations, and §3's row names it as a source. This
#: path never calls it — the substrate already did, at ``StateGraph(...)`` construction — and
#: arming it after the builders exist is what turns that into a checked claim.
_TRIPWIRE = """
import socket, sys, typing, builtins

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
        raise AssertionError("a socket was created on the state extraction path")


socket.socket = _CountSocket
socket.getaddrinfo = _record("getaddrinfo")
socket.gethostbyname = _record("gethostbyname")
socket.create_connection = _record("create_connection")

import gebra
from langgraph.graph.state import StateGraph
from tests.sample_workflows import sentinel_state as ss

# Build every case while the substrate still has its own tools: constructing a StateGraph is
# where the type hints are resolved, and that is the substrate's call, not extraction's.
builders = {name: case.make() for name, case in ss.STATE_CASES.items()}

assert attempts == [], attempts

# The canonical emitter sorts node ids as UTF-16 code units, and Python loads a codec
# module on first use — through the import machinery, which runs the module with `exec`.
# Warming it here keeps `exec` armed for the extraction itself instead of trading the
# stronger claim away for a lazy import that has nothing to do with this path.
"warm the utf-16 codec".encode("utf-16-be")

_real_import = builtins.__import__


def _no_new_modules(name, *a, **k):
    if name not in sys.modules:
        attempts.append("import:" + name); print("WA07-TRIP", file=sys.stderr)
        raise AssertionError("a new module (" + name + ") was imported")
    return _real_import(name, *a, **k)


socket.socket = _TripSocket
StateGraph.compile = _record("StateGraph.compile")
typing.get_type_hints = _record("typing.get_type_hints")
builtins.eval = _record("eval")
builtins.exec = _record("exec")
builtins.__import__ = _no_new_modules

# The fixtures' own record, cleared once the builders exist: everything before this line is
# the substrate building graphs, and everything after it is extraction.
ss.TRIPPED.clear()
ss.PROBED.clear()

extracted = 0
for name, builder in builders.items():
    envelope = gebra.extract(builder)
    assert envelope.ir.nodes, name
    envelope.graph_version()          # canonicalize and digest, still under the guard
    extracted += 1

assert extracted == %d, extracted
# A sentinel that fired inside one of this path's two `except Exception` reads would have
# been swallowed; the fixtures record before they raise, so it is still a failure here.
assert ss.TRIPPED == [], ss.TRIPPED
# And the probe that cannot raise — the substrate needs `__name__` to answer — is observable
# the same way: nothing asked a reducer instance for anything.
assert ss.PROBED == [], ss.PROBED
"""

_REPORT = "print(attempts)\n"


def _run_guarded(probe: str = "") -> subprocess.CompletedProcess[str]:
    body = _TRIPWIRE % len(ss.STATE_CASES)
    return subprocess.run(
        [sys.executable, "-c", body + probe + _REPORT],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_state_extraction_invokes_nothing_and_resolves_no_hint() -> None:
    """The WA-07 claim for the §3 state row, in a fresh interpreter.

    Five claims at once, and the fixtures are what make them real: every node function,
    reducer, validator and channel property in the table raises if it is reached, so an
    extraction that touched one fails the run; ``StateGraph.compile`` is taken away (§1 rule
    2); ``typing.get_type_hints`` is taken away, so the "resolves no hint of its own" claim
    is checked rather than reviewed; ``eval``/``exec`` are taken away, so a string annotation
    cannot be quietly evaluated by another route; and nothing resolves a name or constructs a
    socket while extracting.
    """
    result = _run_guarded()

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "[]", result.stdout
    assert "WA07-TRIP" not in result.stderr, result.stderr


@pytest.mark.parametrize(
    ("probe", "expected"),
    [
        ("builders['plain'].compile()\n", "StateGraph.compile was reached"),
        ("typing.get_type_hints(ss.Plain)\n", "typing.get_type_hints was reached"),
        ("eval('1')\n", "eval was reached"),
        ("exec('pass')\n", "exec was reached"),
        ("import this\n", "a new module (this) was imported"),
        (
            "ss.TRIPPED.append('a control')\nassert ss.TRIPPED == [], ss.TRIPPED\n",
            "AssertionError: ['a control']",
        ),
        (
            (
                "try:\n    ss.Merger().anything\nexcept AttributeError:\n    pass\n"
                "assert ss.PROBED == [], ss.PROBED\n"
            ),
            "AssertionError: ['anything']",
        ),
        ("socket.socket()\n", "a socket was created"),
        ("socket.getaddrinfo('example.invalid', 80)\n", "getaddrinfo was reached"),
        ("socket.gethostbyname('example.invalid')\n", "gethostbyname was reached"),
        ("socket.create_connection(('example.invalid', 80))\n", "create_connection was reached"),
    ],
    ids=[
        "compile",
        "get_type_hints",
        "eval",
        "exec",
        "import",
        "tripped",
        "probed",
        "socket",
        "getaddrinfo",
        "gethostbyname",
        "create_connection",
    ],
)
def test_each_raiser_is_armed(probe: str, expected: str) -> None:
    """A tripwire nobody trips proves nothing, so every raiser gets its own control.

    All eleven, run *after* the child's own assertions, so each control proves its raiser was
    live at the end of the very run that made the claim. The last two are controls for the
    *assertions* rather than for a raiser: they put one entry in the fixtures' own record and
    re-run the check, which is what shows that a swallowed sentinel — or a probe of a reducer
    instance that could not raise — would really have failed the run.
    """
    result = _run_guarded(probe)

    assert result.returncode != 0
    assert expected in result.stderr


def test_the_tripwire_covers_the_shapes_this_path_handles() -> None:
    """The claim above is only as wide as the table it quantifies over, so the table has a floor."""
    assert len(ss.STATE_CASES) >= 18
    assert all(case.why for case in ss.STATE_CASES.values())


def test_the_schema_fixtures_are_armed() -> None:
    """Every armed member of the fixture schemas raises when it is reached.

    Not a sample: an unarmed fixture is a hole exactly where the tripwire's claim is
    strongest, since that is the surface whose extraction would then prove nothing. Each one
    is checked to **record** as well as raise, because two of this path's reads sit inside an
    ``except Exception`` — a sentinel that fired there would be swallowed, and the record is
    what the guarded child asserts on instead.
    """
    ss.TRIPPED.clear()

    for index, probe in enumerate(ss.ARMED_PROBES):
        with pytest.raises(ss.SentinelExecutedError):
            probe()
        assert len(ss.TRIPPED) == index + 1

    assert len(ss.ARMED_PROBES) >= 14
    ss.TRIPPED.clear()


def test_the_one_read_this_path_cannot_guard_is_the_stdlib_s_own() -> None:
    """``dataclasses.fields()`` reads ``_field_type`` off members before extraction sees them.

    The honest boundary of the guards above: gebra checks a member's type *after*
    ``fields()`` returns, and ``fields()`` itself performs one attribute read on every member
    on the way — on an object the caller controls, where a property is executable. It is
    swallowed by the ``except`` around that call, so extraction stays total and Σ is
    unaffected; what makes it visible rather than silent is that the fixtures record before
    they raise. This test is that residual, stated and pinned rather than left for a reader
    to discover — which is also why this fixture is deliberately not in ``STATE_CASES``: the
    guarded child asserts the record empty, and this shape is the one that would fill it.
    """
    ss.TRIPPED.clear()

    envelope = extract(ss.build(ss.ForgedFieldTypeDataclass, input_schema=ss.NoInput))

    assert envelope.ir.state == {"task": "str", "note": "str"}
    assert ss.TRIPPED == ["`_field_type` was read off a forged dataclass field"]
    ss.TRIPPED.clear()


def test_the_refusing_model_is_not_dressed_as_forbidden_execution() -> None:
    """``model_fields`` raising is a *permitted* introspection declining, and says so.

    §1 rule 3 permits "pydantic model/JSON-schema introspection" by name, so the metaclass
    property body genuinely runs and extraction genuinely swallows the refusal. Sharing an
    exception class with "user code that must never run" would make that swallow look like a
    hole in the tripwire instead of the degradation it is.
    """
    ss.TRIPPED.clear()

    with pytest.raises(ss.ModelFieldsRefused):
        _ = ss.HostileModel.model_fields

    assert not issubclass(ss.ModelFieldsRefused, ss.SentinelExecutedError)
    assert ss.TRIPPED == []


def test_every_node_in_the_state_fixtures_is_armed() -> None:
    """…and so is every node function, so no case can extract by running the graph."""
    checked = 0
    for case in ss.STATE_CASES.values():
        for spec in case.make().nodes.values():
            runnable: Any = spec.runnable
            function = getattr(runnable, "func", runnable)
            with pytest.raises(ss.SentinelExecutedError):
                function({})
            checked += 1

    assert checked == len(ss.STATE_CASES)
