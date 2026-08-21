"""LCEL and Pregel-protocol sentinels for the extraction tripwires (D-018/D-023).

The companion to :mod:`tests.sample_workflows.sentinel_graph`, covering the two object
families that a ``StateGraph`` does not reach: the LCEL fragments of INTROSPECTION-SPEC §5
and the Pregel-protocol objects §2 dispatches on. Every callable here raises
``SentinelExecutedError`` if it is ever called, so a pass that touches one fails the run
instead of passing quietly.

**The §5 half is a table, not a pile.** :data:`FRAGMENT_CASES` carries one case per shape, and
each case *declares its own expected IR* — the node ids, the entry/finish wiring and the
fragment-internal edges. That is what makes the card's "each token kind has an extraction test
with stable ids" checkable per kind rather than by counting tests: a stitching rule that
changed fails the case that declares it, and :data:`KIND_COVERAGE` is an equality against the
whole closed vocabulary, so a kind that lost its case fails the suite rather than quietly
shrinking the table.

**The armed objects.** Three shapes exist to be *refused* rather than read, each recording into
:data:`TRIPPED` **before** it acts so a sentinel a ``try`` block swallowed still shows up:
:class:`Holder`, whose property is what ``RunnableLambda.deps`` would run while resolving a
dotted closure name; :class:`ArmedLambdaSubclass`, whose ``deps`` override is what exact-type
matching exists to keep unreachable; and :func:`armed_condition`, a ``RunnableBranch``
condition — §6 makes a guard an opaque reference, so it is never a fragment child and never
read.

Import safety: importing this module *builds* the runnables and one ``Pregel`` (composing
runnables with ``|`` and registering node callables never calls them), contacts no external
service and needs no API keys. Nothing here is compiled from a builder — the ``Pregel`` is
constructed directly, which is exactly the §4.3 rule-4 shape: a Pregel-protocol object with
no ``.builder`` backreference.
"""

from __future__ import annotations

import functools
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from langchain_core import runnables as lc_runnables
from langchain_core.runnables import (
    Runnable,
    RunnableBranch,
    RunnableLambda,
    RunnableParallel,
    RunnablePassthrough,
    RunnableSequence,
)
from langgraph.channels.last_value import LastValue
from langgraph.pregel import NodeBuilder, Pregel
from langgraph.pregel.protocol import PregelProtocol

import gebra
from tests.sample_workflows import sentinel_graph
from tests.sample_workflows.sentinel_graph import SentinelExecutedError

#: Every armed read a fixture here observes, recorded **before** it raises, so a sentinel
#: swallowed by an ``except`` block still fails the run. Cleared per test.
TRIPPED: list[str] = []


def summarize_fragment(value: Any) -> Any:
    raise SentinelExecutedError(
        "LCEL step 'summarize_fragment' was invoked — extraction must never invoke runnables"
    )


def format_fragment(value: Any) -> Any:
    raise SentinelExecutedError(
        "LCEL step 'format_fragment' was invoked — extraction must never invoke runnables"
    )


def render_fragment(value: Any) -> Any:
    raise SentinelExecutedError(
        "LCEL step 'render_fragment' was invoked — extraction must never invoke runnables"
    )


def pregel_step(value: Any) -> Any:
    raise SentinelExecutedError(
        "Pregel node 'pregel_step' was invoked — extraction must never call nodes"
    )


def armed_condition(value: Any) -> bool:
    """A ``RunnableBranch`` condition. §6: a guard is an opaque reference, never evaluated."""
    TRIPPED.append("armed_condition")
    raise SentinelExecutedError(
        "a branch condition was evaluated — INTROSPECTION-SPEC §6 makes guards opaque"
    )


class Holder:
    """A user object on a dotted closure name — the ``deps`` hazard, reduced to what bites.

    ``RunnableLambda.deps`` resolves a dotted nonlocal by walking ``getattr`` from the module
    global, so a body spelling ``HOLDER.chain`` makes this property run inside
    ``gebra.extract()``. It records before raising, so a gate that read it and swallowed the
    result still fails the run.
    """

    @property
    def chain(self) -> Any:
        TRIPPED.append("Holder.chain")
        raise SentinelExecutedError(
            "a user property was read while resolving a lambda's dependencies"
        )


class ArmedLambdaSubclass(RunnableLambda[Any, Any]):
    """A ``RunnableLambda`` subclass whose ``deps`` is user code.

    Exact-type matching is what keeps this unreachable: a subclass can answer the composition
    members with anything at all, and §1 rule 3's closed operation list admits no call.
    """

    @property
    def deps(self) -> list[Runnable[Any, Any]]:
        TRIPPED.append("ArmedLambdaSubclass.deps")
        raise SentinelExecutedError("a subclass's `deps` override ran during extraction")


#: Members a fixture observed being read and **answered** — the record-and-return half of the
#: fixture set. A fixture that only ever raises can show that extraction stopped, never that it
#: did not call; this is what shows a read happened at all.
PROBED: list[str] = []


class ProbedLambdaSubclass(RunnableLambda[Any, Any]):
    """A ``RunnableLambda`` subclass whose ``func`` is a property that records and answers.

    The companion to :class:`ArmedLambdaSubclass`, and together they pin both halves of what
    exact-type matching does and does not buy. ``deps`` — a **composition** member, and the one
    that would decide this object's children and their ids — is never read, so that subclass can
    raise. ``func`` is read anyway, by ANNOTATION §6's wrapper walk, which looks for a contract
    on every node and which §6 *requires*; so this one records and answers instead of raising,
    because a fixture that only raises could never show that the read happened.

    ``__init__`` is deliberately not ``RunnableLambda``'s: a property is a data descriptor, so
    the base class's ``self.func = func`` could not run.
    """

    def __init__(self) -> None:
        pass

    @property
    def func(self) -> Any:  # type: ignore[override]
        PROBED.append("ProbedLambdaSubclass.func")
        return summarize_fragment


def build_probed_subclass() -> Runnable[Any, Any]:
    return ProbedLambdaSubclass()


HOLDER = Holder()


# ── the shapes the §5 walk reads ─────────────────────────────────────────────────────────


def build_sentinel_lambda() -> RunnableLambda[Any, Any]:
    """A bare ``RunnableLambda`` — the §2 degenerate one-fragment case."""
    return RunnableLambda(summarize_fragment)


def build_sentinel_sequence() -> RunnableSequence[Any, Any]:
    """Two sentinel steps composed with ``|`` — a ``RunnableSequence`` (§5 rule 1)."""
    sequence = RunnableLambda(summarize_fragment) | RunnableLambda(format_fragment)
    assert isinstance(sequence, RunnableSequence)
    return sequence


def build_three_step_sequence() -> Runnable[Any, Any]:
    """Three steps, so the ``%seq[i]`` indices and their chaining edges are both visible."""
    return (
        RunnableLambda(summarize_fragment)
        | RunnableLambda(format_fragment)
        | RunnableLambda(render_fragment)
    )


def build_parallel() -> Runnable[Any, Any]:
    """A ``RunnableParallel`` — its dict keys are the §5 rule-3 source-key selectors."""
    return RunnableParallel(
        docs=RunnableLambda(summarize_fragment),
        meta=RunnableLambda(format_fragment),
    )


def build_branch() -> Runnable[Any, Any]:
    """A ``RunnableBranch``: two declared branches, then the default."""
    return RunnableBranch(
        (armed_condition, RunnableLambda(summarize_fragment)),
        (armed_condition, RunnableLambda(format_fragment)),
        RunnableLambda(render_fragment),
    )


def build_retry() -> Runnable[Any, Any]:
    """``.with_retry()`` — a ``RunnableRetry`` wrapping exactly one runnable."""
    return RunnableLambda(summarize_fragment).with_retry(stop_after_attempt=2)


def build_fallbacks() -> Runnable[Any, Any]:
    """``.with_fallbacks()`` — the primary runnable, then its alternatives in order."""
    return RunnableLambda(summarize_fragment).with_fallbacks(
        [RunnableLambda(format_fragment), RunnableLambda(render_fragment)]
    )


def build_binding() -> Runnable[Any, Any]:
    """``.bind()`` — a ``RunnableBinding`` wrapping exactly one runnable."""
    return RunnableLambda(summarize_fragment).bind(stop=["end"])


def build_with_config() -> Runnable[Any, Any]:
    """``.with_config()`` — the other route to a ``RunnableBinding``, same token."""
    return RunnableLambda(summarize_fragment).with_config({"tags": ["fragment"]})


#: A chain captured in a module global, so a lambda body can close over it. Its steps are
#: sentinels like everything else here.
CAPTURED_CHAIN: Runnable[Any, Any] = RunnableLambda(summarize_fragment) | RunnableLambda(
    format_fragment
)

#: A second one, so dep *order* is observable.
CAPTURED_MAP: Runnable[Any, Any] = RunnableParallel(only=RunnableLambda(render_fragment))


def calls_captured_chain(value: Any) -> Any:
    """A body whose closure captures one runnable — ``deps`` reads it through ``.invoke``."""
    return CAPTURED_CHAIN.invoke(value)


def calls_two_captured(value: Any) -> Any:
    """A body capturing two runnables; ``deps`` returns them in first-reference order."""
    CAPTURED_CHAIN.invoke(value)
    return CAPTURED_MAP.invoke(value)


def reads_a_user_property(value: Any) -> Any:
    """A body whose dotted closure name resolves through :class:`Holder` — the hazard."""
    return HOLDER.chain


def build_lambda_with_deps() -> Runnable[Any, Any]:
    """A ``RunnableLambda`` whose closure captures a chain — §5 rule 1's "draws like Parallel"."""
    return RunnableLambda(calls_captured_chain)


def build_lambda_with_two_deps() -> Runnable[Any, Any]:
    """Two captured runnables of different kinds, so ``%lambda[i]`` order is checkable."""
    return RunnableLambda(calls_two_captured)


def build_deps_hazard() -> Runnable[Any, Any]:
    """The lambda whose dependency read would run :class:`Holder.chain`."""
    return RunnableLambda(reads_a_user_property)


def build_not_stock() -> Runnable[Any, Any]:
    """A composite subclass, which this path keeps opaque rather than asking for children."""
    return ArmedLambdaSubclass(summarize_fragment)


def build_nested() -> Runnable[Any, Any]:
    """A sequence whose middle step is a parallel — §5 rule 4 containment, one level down."""
    return (
        RunnableLambda(summarize_fragment)
        | RunnableParallel(
            docs=RunnableLambda(format_fragment), meta=RunnableLambda(render_fragment)
        )
        | RunnableLambda(render_fragment)
    )


def build_ordered_sequence() -> Runnable[Any, Any]:
    """Three steps of three *different* kinds, so each index is identifiable from the ids."""
    return (
        RunnableParallel(only=RunnableLambda(summarize_fragment))
        | RunnableBranch((armed_condition, RunnableLambda(format_fragment)), RunnablePassthrough())
        | RunnableLambda(render_fragment).bind(stop=["end"])
    )


def build_ordered_fallbacks() -> Runnable[Any, Any]:
    """Primary and alternatives of different kinds, so the §5 rule-3 order is identifiable."""
    return RunnableParallel(only=RunnableLambda(summarize_fragment)).with_fallbacks(
        [
            RunnableBranch(
                (armed_condition, RunnableLambda(format_fragment)), RunnablePassthrough()
            ),
            RunnableLambda(render_fragment).bind(stop=["end"]),
        ]
    )


def build_ordered_branch() -> Runnable[Any, Any]:
    """Branch bodies of different kinds, then the default — the same identifiability trick."""
    return RunnableBranch(
        (armed_condition, RunnableParallel(only=RunnableLambda(summarize_fragment))),
        (armed_condition, RunnableLambda(format_fragment).bind(stop=["end"])),
        RunnableLambda(render_fragment).with_retry(stop_after_attempt=2),
    )


def build_colliding_map_keys() -> Runnable[Any, Any]:
    """Two parallel keys that differ only below NFC — the §5 rule-3 index fallback.

    The two keys are one string spelled NFC and NFD: distinct Python strings that
    normalize to one
    segment (IR-SPEC §5.1), so keying by source key would collide; the frame falls back to
    structural indices in insertion order, and the two branches are of different kinds so the
    order is identifiable.
    """
    composed = "cafe\u0301"  # spelled NFD in source, so the two keys really do differ
    decomposed = "cafe\u0301"
    branches: dict[str, Runnable[Any, Any]] = {
        unicodedata.normalize("NFC", composed): RunnableParallel(
            only=RunnableLambda(summarize_fragment)
        ),
        decomposed: RunnableLambda(format_fragment).bind(stop=["end"]),
    }
    return RunnableParallel(branches)


def build_escaped_map_key() -> Runnable[Any, Any]:
    """A parallel key holding the two characters the §5.1 grammar escapes."""
    return RunnableParallel({"a/b%c": RunnableLambda(summarize_fragment)})


#: How deep :func:`build_deep_composition` nests — comfortably past the walk's own bound, so
#: the bound is exercised rather than approached.
DEEP_LEVELS = 40


def build_deep_composition() -> Runnable[Any, Any]:
    """Parallels nested past the walk's depth bound, so the bound is exercised.

    Nesting rather than chaining: ``.bind()`` on a binding merges into one wrapper instead of
    wrapping it, so a run of bindings is one level deep however long it is.
    """
    runnable: Runnable[Any, Any] = RunnableLambda(summarize_fragment)
    for _ in range(DEEP_LEVELS):
        runnable = RunnableParallel(only=runnable)
    return runnable


class CallableStep:
    """A callable *object* rather than a function — a body with no definition to read.

    Two things at once. It has no ``__code__``, so the source reader answers "no definition"
    and the substrate's own helper answers "no dependencies" — the same outcome by two routes.
    And its ``__bool__`` is armed, because a ``RunnableLambda`` accepts any callable and
    ``func or afunc`` would evaluate exactly this: truthiness is user code, and it is not on
    INTROSPECTION §1 rule 3's list.
    """

    def __bool__(self) -> bool:
        TRIPPED.append("CallableStep.__bool__")
        raise SentinelExecutedError(
            "a callable step's `__bool__` ran — truthiness is user code, and extraction "
            "selects a member by presence, never by truth"
        )

    def __call__(self, value: Any) -> Any:
        raise SentinelExecutedError(
            "a callable-object step was invoked — extraction must never invoke runnables"
        )


def captures_in_a_closure(inner: Runnable[Any, Any]) -> Any:
    """Build a body whose captured runnable is a *free variable* rather than a global."""

    def body(value: Any) -> Any:
        return inner.invoke(value)

    return body


def reads_through_a_stock_module(value: Any) -> Any:
    """A dotted capture rooted at a stock *module*, plus a plain-name capture beside it.

    The module chain is admitted — a PEP 562 ``__getattr__`` on ``langchain_core`` would be
    LangChain's own code — and resolves to a class, which is not a dependency. The plain name
    is: a body may capture a runnable without calling anything on it.
    """
    assert lc_runnables.RunnableLambda is not None
    assert str(value).strip() is not None
    return CAPTURED_MAP


def reads_through_a_user_module(value: Any) -> Any:
    """A dotted capture rooted at a *user* module, whose ``__getattr__`` would be user code."""
    return sentinel_graph.SENTINEL_GRAPH


def reads_a_member_that_is_not_there(value: Any) -> Any:
    """A dotted capture that resolves to nothing — the walk stops without a dependency."""
    return CAPTURED_CHAIN.no_such_member  # type: ignore[attr-defined]


def _wrap(function: Callable[[Any], Any]) -> Callable[[Any], Any]:
    """A ``functools.wraps`` decorator — §6's own example, and a second closure to resolve."""

    @functools.wraps(function)
    def wrapper(value: Any) -> Any:
        return function(value)

    return wrapper


@_wrap
def wrapped_capture(value: Any) -> Any:
    """A decorated body: its source is the inner function's, its closure the wrapper's."""
    return CAPTURED_MAP.invoke(value)


@gebra.contract(effects=["network"])
def declared_root(value: Any) -> Any:
    """A declared body that also captures a runnable — a *frame* root with a contract.

    It raises before reaching the capture, like :func:`recursive_step`, so the sentinel can be
    checked by calling it while the AST still names what it closes over.
    """
    if value is not None:
        raise SentinelExecutedError(
            "LCEL step 'declared_root' was invoked — extraction must never invoke runnables"
        )
    return CAPTURED_MAP


def build_declared_frame_root() -> Runnable[Any, Any]:
    """A frame root carrying a contract that a whole-object extraction has no node to hold."""
    return RunnableLambda(declared_root)


def captures_one_runnable_twice(value: Any) -> Any:
    """Two chains rooted at one captured runnable — one dependency, not two."""
    if value is not None:
        raise SentinelExecutedError(
            "LCEL step 'captures_one_runnable_twice' was invoked — extraction never invokes"
        )
    CAPTURED_MAP.invoke(value)
    return CAPTURED_MAP.batch([value])


def build_double_capture() -> Runnable[Any, Any]:
    return RunnableLambda(captures_one_runnable_twice)


def build_chain() -> Runnable[Any, Any]:
    """A factory the body below calls, so an attribute chain can be rooted at a *call*."""
    return CAPTURED_MAP


def captures_through_a_call(value: Any) -> Any:
    """Chains rooted at calls, which the substrate's visitor records and this one mirrors.

    ``f().attr`` records ``f``; ``obj.m().attr`` records ``obj.m``. Neither resolves to a
    runnable here, which is the point: the *names* are collected the same way the substrate
    collects them, so the derived dependency set stays equal to ``deps`` on this shape too.
    """
    if value is not None:
        raise SentinelExecutedError(
            "LCEL step 'captures_through_a_call' was invoked — extraction never invokes"
        )
    named = build_chain().name
    return (named, CAPTURED_MAP.batch.__doc__)


def build_call_rooted_capture() -> Runnable[Any, Any]:
    return RunnableLambda(captures_through_a_call)


def build_closure_dep() -> Runnable[Any, Any]:
    """A lambda capturing a runnable as a closure free variable rather than as a global."""
    return RunnableLambda(captures_in_a_closure(CAPTURED_CHAIN))


def build_stock_module_dep() -> Runnable[Any, Any]:
    return RunnableLambda(reads_through_a_stock_module)


def build_user_module_dep() -> Runnable[Any, Any]:
    return RunnableLambda(reads_through_a_user_module)


def build_missing_member_dep() -> Runnable[Any, Any]:
    return RunnableLambda(reads_a_member_that_is_not_there)


def build_wrapped_dep() -> Runnable[Any, Any]:
    return RunnableLambda(wrapped_capture)


def build_sourceless_lambda() -> Runnable[Any, Any]:
    """A lambda over a callable object, whose body has no source to parse."""
    return RunnableLambda(CallableStep())


def recursive_step(value: Any) -> Any:
    """A body that closes over the very chain it is a step of — §2's termination rule.

    It raises *before* reaching the chain, so the sentinel can be checked by calling it; the
    call it would otherwise make recurs without bound, which is the shape §2's visited set
    exists for and not something a test can afford to run.
    """
    if value is not None:
        raise SentinelExecutedError(
            "LCEL step 'recursive_step' was invoked — extraction must never invoke runnables"
        )
    return SELF_REFERENTIAL.invoke(value)


#: A chain one of whose steps captures the chain itself. §2 requires the walk to keep such an
#: object as one opaque node rather than expanding it again.
SELF_REFERENTIAL: Runnable[Any, Any] = RunnableLambda(recursive_step) | RunnableLambda(
    format_fragment
)


def build_self_referential() -> Runnable[Any, Any]:
    return SELF_REFERENTIAL


def build_unnameable() -> Runnable[Any, Any]:
    """A stock runnable that composes nothing and that no §5.2 token names."""
    return RunnablePassthrough()


# ── the case table ───────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class FragmentCase:
    """One §5 shape and the IR it must extract to.

    Attributes:
        kind: The §5.2 token this case exercises, or ``None`` for a case that exercises a
            rule rather than a token (the termination rule, the depth bound, a hazard).
        build: Builds the runnable. A factory rather than a value so that each test gets an
            object with its own identity — ``deps`` is a ``cached_property``, and a shared
            instance would make "read once" and "read again" indistinguishable.
        nodes: The expected ``nodes[]`` ids, in the order the IR carries them (sorted).
        entry: The expected ``entry``, in canonical representation (scalar iff singleton).
        finish: The expected ``finish``, likewise.
        edges: The expected fragment-internal edges as ``(from, to)`` pairs.
        constructs: The ``unsupported-construct`` slugs this shape must produce.
    """

    kind: str | None
    build: Callable[[], Runnable[Any, Any]]
    nodes: tuple[str, ...]
    entry: str | tuple[str, ...]
    finish: str | tuple[str, ...]
    edges: tuple[tuple[str, str], ...] = ()
    constructs: tuple[str, ...] = field(default_factory=tuple)


#: Every §5 shape this build extracts, each declaring its own expected IR.
FRAGMENT_CASES: dict[str, FragmentCase] = {
    "degenerate-lambda": FragmentCase(
        kind="lambda",
        build=build_sentinel_lambda,
        nodes=("%lambda[0]",),
        entry="%lambda[0]",
        finish="%lambda[0]",
    ),
    "degenerate-parallel": FragmentCase(
        kind="map",
        build=lambda: RunnableParallel(),
        nodes=("%map[0]",),
        entry="%map[0]",
        finish="%map[0]",
    ),
    "sequence-two": FragmentCase(
        kind="seq",
        build=build_sentinel_sequence,
        nodes=("%seq[0]", "%seq[1]"),
        entry="%seq[0]",
        finish="%seq[1]",
        edges=(("%seq[0]", "%seq[1]"),),
    ),
    "sequence-three": FragmentCase(
        kind="seq",
        build=build_three_step_sequence,
        nodes=("%seq[0]", "%seq[1]", "%seq[2]"),
        entry="%seq[0]",
        finish="%seq[2]",
        edges=(("%seq[0]", "%seq[1]"), ("%seq[1]", "%seq[2]")),
    ),
    "parallel": FragmentCase(
        kind="map",
        build=build_parallel,
        nodes=("%map[docs]", "%map[meta]"),
        entry=("%map[docs]", "%map[meta]"),
        finish=("%map[docs]", "%map[meta]"),
    ),
    "branch": FragmentCase(
        kind="branch",
        build=build_branch,
        nodes=("%branch[0]", "%branch[1]", "%branch[2]"),
        entry=("%branch[0]", "%branch[1]", "%branch[2]"),
        finish=("%branch[0]", "%branch[1]", "%branch[2]"),
    ),
    "retry": FragmentCase(
        kind="retry",
        build=build_retry,
        nodes=("%retry[0]",),
        entry="%retry[0]",
        finish="%retry[0]",
    ),
    "fallbacks": FragmentCase(
        kind="fallback",
        build=build_fallbacks,
        nodes=("%fallback[0]", "%fallback[1]", "%fallback[2]"),
        entry=("%fallback[0]", "%fallback[1]", "%fallback[2]"),
        finish=("%fallback[0]", "%fallback[1]", "%fallback[2]"),
    ),
    "binding": FragmentCase(
        kind="bind",
        build=build_binding,
        nodes=("%bind[0]",),
        entry="%bind[0]",
        finish="%bind[0]",
    ),
    "with-config": FragmentCase(
        kind="bind",
        build=build_with_config,
        nodes=("%bind[0]",),
        entry="%bind[0]",
        finish="%bind[0]",
    ),
    "lambda-deps": FragmentCase(
        kind="lambda",
        build=build_lambda_with_deps,
        nodes=("%lambda[0]", "%lambda[0]/%seq[0]", "%lambda[0]/%seq[1]"),
        entry="%lambda[0]",
        finish="%lambda[0]",
        edges=(("%lambda[0]/%seq[0]", "%lambda[0]/%seq[1]"),),
    ),
    "lambda-deps-ordered": FragmentCase(
        kind="lambda",
        build=build_lambda_with_two_deps,
        nodes=(
            "%lambda[0]",
            "%lambda[0]/%seq[0]",
            "%lambda[0]/%seq[1]",
            "%lambda[1]",
            "%lambda[1]/%map[only]",
        ),
        entry=("%lambda[0]", "%lambda[1]"),
        finish=("%lambda[0]", "%lambda[1]"),
        edges=(("%lambda[0]/%seq[0]", "%lambda[0]/%seq[1]"),),
        # `CAPTURED_CHAIN` is referenced first, so it is dep 0 — the order this build derives
        # from the code object rather than from the substrate's process-dependent `deps`.
    ),
    "nested": FragmentCase(
        kind="seq",
        build=build_nested,
        nodes=(
            "%seq[0]",
            "%seq[1]",
            "%seq[1]/%map[docs]",
            "%seq[1]/%map[meta]",
            "%seq[2]",
        ),
        entry="%seq[0]",
        finish="%seq[2]",
        edges=(("%seq[0]", "%seq[1]"), ("%seq[1]", "%seq[2]")),
    ),
    "ordered-sequence": FragmentCase(
        kind="seq",
        build=build_ordered_sequence,
        nodes=(
            "%seq[0]",
            "%seq[0]/%map[only]",
            "%seq[1]",
            "%seq[1]/%branch[0]",
            "%seq[1]/%branch[1]",
            "%seq[2]",
            "%seq[2]/%bind[0]",
        ),
        entry="%seq[0]",
        finish="%seq[2]",
        edges=(("%seq[0]", "%seq[1]"), ("%seq[1]", "%seq[2]")),
    ),
    "ordered-fallbacks": FragmentCase(
        kind="fallback",
        build=build_ordered_fallbacks,
        nodes=(
            "%fallback[0]",
            "%fallback[0]/%map[only]",
            "%fallback[1]",
            "%fallback[1]/%branch[0]",
            "%fallback[1]/%branch[1]",
            "%fallback[2]",
            "%fallback[2]/%bind[0]",
        ),
        entry=("%fallback[0]", "%fallback[1]", "%fallback[2]"),
        finish=("%fallback[0]", "%fallback[1]", "%fallback[2]"),
    ),
    "ordered-branch": FragmentCase(
        kind="branch",
        build=build_ordered_branch,
        nodes=(
            "%branch[0]",
            "%branch[0]/%map[only]",
            "%branch[1]",
            "%branch[1]/%bind[0]",
            "%branch[2]",
            "%branch[2]/%retry[0]",
        ),
        entry=("%branch[0]", "%branch[1]", "%branch[2]"),
        finish=("%branch[0]", "%branch[1]", "%branch[2]"),
    ),
    "colliding-map-keys": FragmentCase(
        kind="map",
        build=build_colliding_map_keys,
        nodes=("%map[0]", "%map[0]/%map[only]", "%map[1]", "%map[1]/%bind[0]"),
        entry=("%map[0]", "%map[1]"),
        finish=("%map[0]", "%map[1]"),
        constructs=("lcel-map-key-not-carried",),
    ),
    "escaped-map-key": FragmentCase(
        kind="map",
        build=build_escaped_map_key,
        nodes=("%map[a%2Fb%25c]",),
        entry="%map[a%2Fb%25c]",
        finish="%map[a%2Fb%25c]",
    ),
    "deps-hazard": FragmentCase(
        kind=None,
        build=build_deps_hazard,
        nodes=("%lambda[0]",),
        entry="%lambda[0]",
        finish="%lambda[0]",
        constructs=("lcel-deps-not-read",),
    ),
    "probed-subclass": FragmentCase(
        kind=None,
        build=build_probed_subclass,
        nodes=("%lambda[0]",),
        entry="%lambda[0]",
        finish="%lambda[0]",
        constructs=("lcel-composition-not-stock",),
    ),
    "not-stock": FragmentCase(
        kind=None,
        build=build_not_stock,
        nodes=("%lambda[0]",),
        entry="%lambda[0]",
        finish="%lambda[0]",
        constructs=("lcel-composition-not-stock",),
    ),
    "declared-frame-root": FragmentCase(
        kind="lambda",
        build=build_declared_frame_root,
        nodes=("%lambda[0]", "%lambda[0]/%map[only]"),
        entry="%lambda[0]",
        finish="%lambda[0]",
        constructs=("fragment-root-contract-not-carried",),
    ),
    "double-capture": FragmentCase(
        kind="lambda",
        build=build_double_capture,
        nodes=("%lambda[0]", "%lambda[0]/%map[only]"),
        entry="%lambda[0]",
        finish="%lambda[0]",
    ),
    "call-rooted-capture": FragmentCase(
        # Neither chain resolves to a runnable — `f().attr` names `f`, and the root of a chain
        # is not itself a plain capture — so the lambda is a leaf. The point of the case is the
        # *collection*: the substrate records call-rooted chains and so does this build.
        kind="lambda",
        build=build_call_rooted_capture,
        nodes=("%lambda[0]",),
        entry="%lambda[0]",
        finish="%lambda[0]",
    ),
    "closure-dep": FragmentCase(
        kind="lambda",
        build=build_closure_dep,
        nodes=("%lambda[0]", "%lambda[0]/%seq[0]", "%lambda[0]/%seq[1]"),
        entry="%lambda[0]",
        finish="%lambda[0]",
        edges=(("%lambda[0]/%seq[0]", "%lambda[0]/%seq[1]"),),
    ),
    "stock-module-dep": FragmentCase(
        kind="lambda",
        build=build_stock_module_dep,
        nodes=("%lambda[0]", "%lambda[0]/%map[only]"),
        entry="%lambda[0]",
        finish="%lambda[0]",
    ),
    "wrapped-dep": FragmentCase(
        kind="lambda",
        build=build_wrapped_dep,
        nodes=("%lambda[0]", "%lambda[0]/%map[only]"),
        entry="%lambda[0]",
        finish="%lambda[0]",
    ),
    "user-module-dep": FragmentCase(
        kind=None,
        build=build_user_module_dep,
        nodes=("%lambda[0]",),
        entry="%lambda[0]",
        finish="%lambda[0]",
        constructs=("lcel-deps-not-read",),
    ),
    "missing-member-dep": FragmentCase(
        kind=None,
        build=build_missing_member_dep,
        nodes=("%lambda[0]",),
        entry="%lambda[0]",
        finish="%lambda[0]",
    ),
    "sourceless-lambda": FragmentCase(
        kind=None,
        build=build_sourceless_lambda,
        nodes=("%lambda[0]",),
        entry="%lambda[0]",
        finish="%lambda[0]",
    ),
    "self-referential": FragmentCase(
        kind=None,
        build=build_self_referential,
        nodes=("%seq[0]", "%seq[0]/%lambda[0]", "%seq[1]"),
        entry="%seq[0]",
        finish="%seq[1]",
        edges=(("%seq[0]", "%seq[1]"),),
        constructs=("self-referential-composition",),
    ),
}

#: The §5 shapes this build refuses at the object boundary (§2's error posture).
REFUSED_FRAGMENTS: dict[str, Callable[[], Runnable[Any, Any]]] = {
    "unnameable": build_unnameable,
}

#: kind → the cases that exercise it. An equality against the closed IR-SPEC §5.2 vocabulary
#: is what keeps the table from shrinking silently.
KIND_COVERAGE: dict[str, tuple[str, ...]] = {
    kind: tuple(name for name, case in FRAGMENT_CASES.items() if case.kind == kind)
    for kind in ("seq", "map", "branch", "lambda", "retry", "fallback", "bind")
}


# ── the Pregel-protocol half (unchanged; §2 dispatch, not §5) ────────────────────────────


def build_builderless_pregel() -> Pregel[Any, Any, Any, Any]:
    """A ``Pregel`` built directly — the §4.3 rule-4 object, with no ``.builder``.

    Constructed rather than compiled: ``StateGraph.compile()`` is what attaches the
    ``.builder`` backreference, so the only honest way to get a builderless Pregel is to not
    involve a builder at all. The node's callable is a sentinel, so this doubles as the
    tripwire fixture for the compiled-only dispatch path.
    """
    node = NodeBuilder().subscribe_only("question").do(pregel_step).write_to("answer")
    return Pregel(
        nodes={"pregel_step": node},
        channels={"question": LastValue(str), "answer": LastValue(str)},
        input_channels="question",
        output_channels="answer",
    )


class SurfacelessPregel:
    """A Pregel-protocol object with neither a ``.builder`` nor a callable ``get_graph``.

    §2's dispatch has a branch for exactly this — ``raise ExtractionError(type(workflow))``,
    "no usable surface at all" — and no real LangGraph class can reach it, since every
    ``Pregel`` carries ``get_graph``. The shape a third-party implementation *can* reach is
    this one: registered as a virtual subclass through the protocol's own ``register``, so
    ``isinstance(x, PregelProtocol)`` — which is how §2 defines ``is_pregel`` — is true while
    neither surface is there.

    Every attribute access is answered from the class; nothing is callable, so a dispatch
    that tried to probe by calling would raise :class:`TypeError` rather than pass.
    """

    builder = None
    get_graph = None


PregelProtocol.register(SurfacelessPregel)

#: Built at import time — import-safe by construction (see the module docstring).
SENTINEL_LAMBDA: Runnable[Any, Any] = build_sentinel_lambda()
SENTINEL_SEQUENCE: Runnable[Any, Any] = build_sentinel_sequence()
SENTINEL_PREGEL: Pregel[Any, Any, Any, Any] = build_builderless_pregel()
