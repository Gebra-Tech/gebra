"""Armed graphs for the ANNOTATION-API-SPEC §3/§6 resolution seam (EX-11; WA-07).

Every node here raises if it is called, and every *object* the seam reads on the way to a
contract — a wrapper's ``__wrapped__``, a tool's ``args_schema``, a carrier's namespace —
records the read before it raises, so a sentinel that one of the seam's two guarded
``except`` blocks swallows still fails the run.

The shapes are §6's, one builder each: a plain declaration, a ``functools.wraps`` chain, a
wrapper that forgot ``functools.wraps`` (§6's "indistinguishable from never annotated" case,
which is exactly why the parity test exists), two carriers in one chain, a LangChain tool
whose ``args_schema`` is the §3 tier-2 source, a ``RunnableLambda`` body §4 calls opaque, an
``async def`` node, and a node whose body §4's patterns can actually read.

The module deliberately does **not** use ``from __future__ import annotations``: two of §4's
patterns read annotation *objects*, and the future import would turn every one into a string
— which :mod:`tests.sample_workflows.sentinel_inference` already covers as its own fixture and
which would silently become the only case here.

Nothing here opens a socket or contacts a service. ``compile()`` is guarded behind
:func:`compile_parity_graph`, so importing the module builds only.
"""

import functools
import itertools
from typing import Any, Final, TypedDict

from langchain_core.runnables import RunnableLambda
from langchain_core.tools import StructuredTool
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel

import gebra

#: Every read of an armed surface, in order. The seam guards two calls behind
#: ``except Exception`` — reading a tool's ``args_schema`` and asking it for its JSON schema —
#: so a sentinel raised inside one of them would be *invisible* to a test that only checks
#: that extraction succeeded. Recording the read first makes the hazard visible either way:
#: the tests assert this list is empty for every shape that must not be touched.
TRIPPED: list[str] = []

#: The tool schemas that were asked for their JSON schema. A *positive* control: §1 licenses
#: exactly this read ("pydantic model/JSON-schema introspection", INTROSPECTION §1 rule 3), so
#: it is recorded rather than armed, and a seam that stopped performing it would show up here.
PROBED: list[str] = []


class ResolutionSentinelError(BaseException):
    """Raised by any sentinel here that gets touched.

    Deliberately **not** an :class:`Exception`. :mod:`gebra.extraction.contracts` guards the
    two reads it makes on a caller-supplied schema class with ``except Exception``, because §2
    and §3 put the whole surface at warning grade — and a sentinel caught by that guard would
    be a node execution reported as a warning. Deriving from :class:`BaseException` puts these
    outside every such guard in the package, so an execution ends the run.
    """


class SchemaRefused(RuntimeError):
    """What a *legitimately* unreadable ``args_schema`` raises — an ordinary exception.

    The complement of :class:`ResolutionSentinelError`: this is the case §3 has to survive
    with a warning (a schema class whose author made it answer by raising), so it must be
    caught, and the fixture that raises it is how "caught" is checked.
    """


def _arm(label: str, *values: object) -> Any:
    """Refuse to run, whatever it is handed — the first statement of every body below."""
    TRIPPED.append(label)
    raise ResolutionSentinelError(f"{label!r} was invoked — extraction reads, it never runs")


class ParityState(TypedDict):
    """The graph's full state schema — §4's full-state-annotation exclusion applies to it."""

    query: str
    plan: str
    booking_ref: str


class Reads(TypedDict):
    """A projection of :class:`ParityState` — the shape §4's ``input`` pattern (a) licenses."""

    query: str


# ── The node callables ───────────────────────────────────────────────────────────────────


@gebra.contract(reads=["query"], writes=["plan"], effects=["network"])
def declared_step(state: ParityState) -> dict[str, Any]:
    """A plain declaration: every slot it sets is the decorator's, at full strength."""
    _arm("declared_step")
    return {"plan": "…"}


def user_decorator(fn: Any) -> Any:
    """A user decorator that applies ``functools.wraps`` — §6's supported shape.

    §6: "any user decorator sitting between ``@gebra.contract`` and the function MUST apply
    ``functools.wraps``; otherwise the metadata is invisible". This one does, and the *reason*
    it works is worth naming, because it is not only the ``__wrapped__`` link: ``functools.wraps``
    also copies the wrapped function's ``__dict__`` onto the wrapper, so a contract attached
    below it arrives on the wrapper as well. The declaration therefore survives twice over —
    once by the copy and once by the chain — which is why §6 makes the ``functools.wraps``
    requirement the load-bearing one.
    """

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        _arm("user_decorator.wrapper")
        return None

    return wrapper


def linking_decorator(fn: Any) -> Any:
    """A wrapper that sets ``__wrapped__`` and copies nothing else.

    The half of ``functools.wraps`` §6 names in terms — "following ``functools.wraps`` chains
    (``__wrapped__``)" — without the ``__dict__`` copy that would put the contract on the
    wrapper anyway. So a carrier below this wrapper is reachable **only** by walking, which is
    what makes the walk testable rather than incidentally redundant.
    """

    def wrapper(*args: Any, **kwargs: Any) -> Any:
        _arm("linking_decorator.wrapper")
        return None

    wrapper.__wrapped__ = fn  # type: ignore[attr-defined]
    return wrapper


def forgetful_decorator(fn: Any) -> Any:
    """A user decorator that does *not* apply ``functools.wraps`` — §6's warned-about shape.

    The chain ends at the wrapper, so the inner carrier is unreachable and the node "falls
    through to sidecar/inference — indistinguishable from 'never annotated', which is exactly
    why the parity test exists" (§6). Nothing is warned, because nothing about the object says
    a contract was ever attached.
    """

    def wrapper(*args: Any, **kwargs: Any) -> Any:
        _arm("forgetful_decorator.wrapper")
        return None

    return wrapper


@linking_decorator
@gebra.contract(reads=["query"], writes=["plan"])
def wrapped_step(state: ParityState) -> dict[str, Any]:
    """Declared under a chain-linking wrapper — reachable only by walking ``__wrapped__``."""
    _arm("wrapped_step")
    return {"plan": "…"}


@user_decorator
@gebra.contract(reads=["query"], effects=["billable"])
def copied_step(state: ParityState) -> dict[str, Any]:
    """Declared under a ``functools.wraps`` wrapper — reachable by the copy *and* the walk."""
    _arm("copied_step")
    return {"plan": "…"}


@forgetful_decorator
@gebra.contract(reads=["query"], writes=["plan"])
def hidden_step(state: ParityState) -> dict[str, Any]:
    """Declared under a wrapper that dropped the chain — the declaration is invisible."""
    _arm("hidden_step")
    return {"plan": "…"}


def _two_carrier_step() -> Any:
    """Two contract-bearing callables in one chain — §6's outermost-carrier rule.

    Built rather than written as a decorator stack, because the two declarations have to sit
    on *different objects*: §1's at-most-once rule would refuse a second declaration of one
    slot on one object at import time, and §6's rule is about the other case entirely. The
    link is :func:`linking_decorator` for the same reason — ``functools.wraps`` would copy the
    inner contract onto the wrapper, and then §1's at-most-once rule (not §6's) is what fires.
    """

    @gebra.contract(reads=["plan"], effects=["billable"])
    def inner(state: ParityState) -> dict[str, Any]:
        _arm("two_carriers.inner")
        return {"plan": "…"}

    return gebra.contract(reads=["query"], writes=["booking_ref"])(linking_decorator(inner))


two_carrier_step: Final = _two_carrier_step()


# A tool's author-written argument schema — the §3 tier-2 source. Written without a
# docstring on purpose: pydantic puts one in the JSON Schema as `description`, and this
# class's schema is committed as a golden (WA-05), so its prose would be golden content.
class SearchArgs(BaseModel):
    query: str
    limit: int = 5


def _search_impl(query: str, limit: int = 5) -> str:
    """The tool's implementation. Never called: a tool is read, never invoked (§1)."""
    _arm("search_tool.impl")
    return ""


search_tool: Final = StructuredTool(
    name="search_tool",
    description="Search. Never invoked.",
    args_schema=SearchArgs,
    func=_search_impl,
)


# A schema that records being asked for its JSON schema — the positive control for the one
# read §1 rule 3 licenses on a caller-supplied class.
class ProbedArgs(BaseModel):
    query: str

    @classmethod
    def model_json_schema(cls, *args: Any, **kwargs: Any) -> Any:
        PROBED.append("ProbedArgs")
        return super().model_json_schema(*args, **kwargs)


# A schema whose author made it answer by raising — §3 must warn, never fail.
class RefusingArgs(BaseModel):
    query: str

    @classmethod
    def model_json_schema(cls, *args: Any, **kwargs: Any) -> Any:
        raise SchemaRefused("this schema declines to describe itself")


def _tool_with(schema: Any, name: str) -> StructuredTool:
    """A tool carrying ``schema``, with an armed implementation."""
    return StructuredTool(
        name=name,
        description="Never invoked.",
        args_schema=schema,
        func=lambda *args, **kwargs: _arm(f"{name}.impl"),
    )


class HostileSchemaTool(StructuredTool):
    """A tool whose ``args_schema`` **attribute** raises when it is read.

    Reading a field off a caller-supplied model is not the inert operation it looks like: a
    data descriptor on the class wins over the instance ``__dict__``, so what
    ``tool.args_schema`` does is the tool author's business. That is why the seam guards the
    read as well as the JSON-schema call, and this fixture is what checks the guard.

    The descriptor is installed after class creation on purpose — declaring it in the class
    body would be redefining a pydantic *field*, which the metaclass resolves in favour of the
    field and would leave the fixture silently inert. The refusal is an ordinary
    :class:`SchemaRefused`, not a sentinel: this is a case §3 has to survive with a warning.
    """


def _refuse_args_schema(tool: object) -> Any:
    raise SchemaRefused("this tool declines to expose its argument schema")


HostileSchemaTool.args_schema = property(_refuse_args_schema)  # type: ignore[assignment]


def inferring_step(state: Reads) -> dict[str, Any]:
    """A body §4's closed patterns can actually read — pattern (a) and pattern (a) of output.

    The annotation is a *projection*, so §4's full-state exclusion does not apply to it, and
    the return is a literal dict display. Both are licensed, so this node is where a
    ``contract-inferred`` record comes from rather than a ``contract-defaulted`` one.
    """
    _arm("inferring_step")
    return {"plan": "…"}


def surrogate_reader(state: ParityState) -> dict[str, Any]:
    """A body whose literal state reads include a key the IR cannot carry.

    ``"\\ud800"`` is a lone surrogate: a perfectly good Python string with no UTF-8 encoding,
    so IR-SPEC §6.1 step 6 cannot serialize it. §4's pattern (b) licenses the read anyway —
    it reads source, not meaning — which makes this the shape §3's carriability pass exists
    for: the *inferred* slot has to be dropped, and its ``contract-inferred`` record must stop
    naming a slot the IR does not carry.
    """
    _arm("surrogate_reader")
    # `ParityState` genuinely has no "\ud800" key — that mismatch *is* the fixture. §4
    # pattern (b) reads this subscript as source text (the AST walk in
    # gebra/annotations/inference.py), never at runtime: `_arm` above always raises first,
    # so this line never executes. `--strict` is right to flag a real TypedDict key miss
    # here; silencing it is the fixture's whole point, not a loophole.
    seen = (state["query"], state["\ud800"])  # type: ignore[typeddict-item]
    # `all(seen)` rather than `if seen`: a fixed 2-tuple literal is always truthy, which is
    # exactly what `--strict`'s redundant-expr check (correctly) catches; checking the
    # tuple's *elements* keeps the branch a real runtime question instead.
    return _build_update() if all(seen) else {}


async def async_step(state: ParityState) -> dict[str, Any]:
    """An ``async def`` node — the substrate holds it in ``afunc``, not ``func`` (§6's walk)."""
    _arm("async_step")
    return {"plan": "…"}


@gebra.contract(reads=["query"])
async def declared_async_step(state: ParityState) -> dict[str, Any]:
    """The same, carrying a declaration, so the walk has to reach it through ``afunc``."""
    _arm("declared_async_step")
    return {"plan": "…"}


def opaque_body(state: ParityState) -> dict[str, Any]:
    """The body inside a ``RunnableLambda`` — readable, and read anyway is what §4 forbids."""
    _arm("opaque_body")
    return {"plan": "…"}


opaque_step: Final = RunnableLambda(opaque_body)


def foreign_carrier_step(state: ParityState) -> dict[str, Any]:
    """A node whose ``__gebra_contract__`` was set by something that is not gebra."""
    _arm("foreign_carrier_step")
    return _build_update()


foreign_carrier_step.__gebra_contract__ = {"pure": True}  # type: ignore[attr-defined]


def _build_update() -> dict[str, Any]:
    """A helper that builds the update — deliberately out of §4's reach (DEC-08 shallow-only)."""
    return {"plan": "…"}


def plain_step(state: ParityState) -> dict[str, Any]:
    """No declaration of any kind, and no body §4 can read a pattern out of.

    The return site is a helper call, which §4's closed table does not license: "any key that
    only appears inside a called function" is out. So this node is the D-011
    no-write-evidence default — "a no-evidence-found result, not a proof".
    """
    _arm("plain_step")
    return _build_update()


# ── The builders ─────────────────────────────────────────────────────────────────────────


def _wire(builder: "StateGraph[ParityState]", *names: str) -> "StateGraph[ParityState]":
    """Wire the given node names into a single chain from START to END."""
    builder.add_edge(START, names[0])
    for source, target in itertools.pairwise(names):
        builder.add_edge(source, target)
    builder.add_edge(names[-1], END)
    return builder


def build_declared_graph() -> "StateGraph[ParityState]":
    """One declared node beside one undeclared one — the §3 chain's two ordinary outcomes."""
    builder: StateGraph[ParityState] = StateGraph(ParityState)
    builder.add_node("declared_step", declared_step)
    builder.add_node("plain_step", plain_step)
    return _wire(builder, "declared_step", "plain_step")


def build_wrapper_graph() -> "StateGraph[ParityState]":
    """§6's three wrapper outcomes on one graph: reached, hidden, and two carriers."""
    builder: StateGraph[ParityState] = StateGraph(ParityState)
    builder.add_node("wrapped_step", wrapped_step)
    builder.add_node("copied_step", copied_step)
    builder.add_node("hidden_step", hidden_step)
    builder.add_node("two_carrier_step", two_carrier_step)
    return _wire(builder, "wrapped_step", "copied_step", "hidden_step", "two_carrier_step")


def build_tool_graph() -> "StateGraph[ParityState]":
    """A LangChain tool as a node — the §3 tier-2 ``args_schema`` source."""
    builder: StateGraph[ParityState] = StateGraph(ParityState)
    # A ``BaseTool`` is a ``Runnable`` over its own argument type rather than over the
    # graph state, which the substrate's own signature refuses; using one as a node is what
    # the §3 tool-carried tier is *for*, so the fixture is the shape the tier reads.
    builder.add_node("search_tool", search_tool)  # type: ignore[type-var]
    builder.add_node("plain_step", plain_step)
    return _wire(builder, "search_tool", "plain_step")


def build_probed_tool_graph() -> "StateGraph[ParityState]":
    """The schema controls: the licensed read recorded, and the three ways it can fail.

    ``schemaless_tool`` carries no ``args_schema`` at all (the tier simply says nothing),
    ``dict_schema_tool`` carries one written directly as a JSON Schema object rather than as a
    pydantic class (§2's own transliteration shape, arriving on the tool surface),
    ``refusing_tool``'s class answers by raising, ``hostile_tool``'s *attribute* raises, and
    ``foreign_schema_tool``'s object holds something JSON cannot carry.
    """
    builder: StateGraph[ParityState] = StateGraph(ParityState)
    builder.add_node("probed_tool", _tool_with(ProbedArgs, "probed_tool"))  # type: ignore[type-var]
    builder.add_node("schemaless_tool", _tool_with(None, "schemaless_tool"))  # type: ignore[type-var]
    builder.add_node(  # type: ignore[type-var]
        "dict_schema_tool",
        _tool_with({"type": "object", "title": "written directly"}, "dict_schema_tool"),
    )
    builder.add_node("refusing_tool", _tool_with(RefusingArgs, "refusing_tool"))  # type: ignore[type-var]
    builder.add_node(  # type: ignore[type-var]
        "foreign_schema_tool",
        _tool_with({"default": object()}, "foreign_schema_tool"),
    )
    builder.add_node(  # type: ignore[type-var]
        "hostile_tool",
        HostileSchemaTool(
            name="hostile_tool",
            description="Never invoked.",
            args_schema=ProbedArgs,
            func=lambda *args, **kwargs: _arm("hostile_tool.impl"),
        ),
    )
    return _wire(
        builder,
        "probed_tool",
        "schemaless_tool",
        "dict_schema_tool",
        "refusing_tool",
        "foreign_schema_tool",
        "hostile_tool",
    )


def build_opaque_graph() -> "StateGraph[ParityState]":
    """A ``RunnableLambda`` node — §4/§5 rule 5's opaque body, sent straight to the floor."""
    builder: StateGraph[ParityState] = StateGraph(ParityState)
    builder.add_node("opaque_step", opaque_step)
    builder.add_node("plain_step", plain_step)
    return _wire(builder, "opaque_step", "plain_step")


def build_async_graph() -> "StateGraph[ParityState]":
    """Two ``async def`` nodes — the member the substrate holds an async callable in."""
    builder: StateGraph[ParityState] = StateGraph(ParityState)
    builder.add_node("async_step", async_step)
    builder.add_node("declared_async_step", declared_async_step)
    return _wire(builder, "async_step", "declared_async_step")


def build_inference_graph() -> "StateGraph[ParityState]":
    """A node §4's patterns license, beside one that falls to the D-011 default."""
    builder: StateGraph[ParityState] = StateGraph(ParityState)
    builder.add_node("inferring_step", inferring_step)
    builder.add_node("plain_step", plain_step)
    return _wire(builder, "inferring_step", "plain_step")


def build_uncarriable_inference_graph() -> "StateGraph[ParityState]":
    """A node whose *inferred* input the canonical form cannot carry (§3, IR-SPEC §6.3)."""
    builder: StateGraph[ParityState] = StateGraph(ParityState)
    builder.add_node("surrogate_reader", surrogate_reader)
    builder.add_node("plain_step", plain_step)
    return _wire(builder, "surrogate_reader", "plain_step")


def build_foreign_carrier_graph() -> "StateGraph[ParityState]":
    """A ``__gebra_contract__`` gebra did not attach — warning-grade at extraction."""
    builder: StateGraph[ParityState] = StateGraph(ParityState)
    builder.add_node("foreign_carrier_step", foreign_carrier_step)
    return _wire(builder, "foreign_carrier_step")


def build_parity_graph() -> "StateGraph[ParityState]":
    """The §6 parity workflow: every tier of the chain represented on one graph.

    The declared node exercises the decorator tier, the wrapped one the §6 chain walk, the
    tool the tier-2 ``args_schema``, the lambda the opaque floor, and the plain node the
    D-011 default — so "the resolved contracts are identical before and after ``.compile()``"
    is a statement about the whole chain rather than about one slot.
    """
    builder: StateGraph[ParityState] = StateGraph(ParityState)
    builder.add_node("declared_step", declared_step)
    builder.add_node("wrapped_step", wrapped_step)
    builder.add_node("search_tool", search_tool)  # type: ignore[type-var]
    builder.add_node("opaque_step", opaque_step)
    builder.add_node("plain_step", plain_step)
    return _wire(
        builder, "declared_step", "wrapped_step", "search_tool", "opaque_step", "plain_step"
    )


def compile_parity_graph() -> Any:
    """Compile the parity graph on demand.

    ``compile()`` is graph construction rather than execution, but it stays behind a function
    so that importing this module builds only — and because INTROSPECTION §1 rule 2 forbids
    *extraction* from calling it, which a module-level compile would make easy to confuse.
    """
    return build_parity_graph().compile()


#: The §3/§6 shapes that extract, as (name, factory). The tripwire runs the whole list, so a
#: shape added here joins the never-invokes claim with it.
RESOLUTION_BUILDERS: Final[dict[str, Any]] = {
    "declared": build_declared_graph,
    "wrapper": build_wrapper_graph,
    "tool": build_tool_graph,
    "probed_tool": build_probed_tool_graph,
    "opaque": build_opaque_graph,
    "async": build_async_graph,
    "inference": build_inference_graph,
    "uncarriable_inference": build_uncarriable_inference_graph,
    "foreign_carrier": build_foreign_carrier_graph,
    "parity": build_parity_graph,
}


# ── Sidecars, as text ────────────────────────────────────────────────────────────────────

SCHEMA_LINE: Final = 'schema = "gebra-sidecar-v1"'

#: A sidecar that disagrees with the decorator on one slot and fills two it left open — the
#: DEC-07 shape: the decorator wins its slot, the sidecar fills the gaps, and the
#: disagreement is warned rather than silently dropped.
CONFLICTING_SIDECAR: Final = f"""
{SCHEMA_LINE}

[nodes.declared_step]
reads        = ["budget"]
writes       = ["plan"]
idempotent   = {{ key = "query" }}
compensation = {{ hook = "plan_step" }}
"""

#: A sidecar declaring exactly what the decorator declares, in another spelling — §3's
#: "identical values are not a conflict", which is decided on canonicalized bytes.
IDENTICAL_SIDECAR: Final = f"""
{SCHEMA_LINE}

[nodes.declared_step]
reads   = ["query"]
writes  = ["plan"]
effects = ["network"]
"""

#: A sidecar whose ``args_schema`` disagrees with the tool-carried one — §3's tier-2 rule:
#: "the tool-carried value is kept and an ``annotation-conflict`` warning is emitted".
TOOL_CONFLICT_SIDECAR: Final = f"""
{SCHEMA_LINE}

[nodes.search_tool]
pure = true

[nodes.search_tool.args_schema]
type = "object"
title = "written in config"
"""

#: A sidecar that assembles the §3 worked example across two surfaces: the decorator declares
#: nothing about effects and the sidecar adds them beside a ``pure`` this file also declares.
PURE_WITH_EFFECTS_SIDECAR: Final = f"""
{SCHEMA_LINE}

[nodes.plain_step]
pure    = true

[nodes.hidden_step]
effects = ["irreversible"]
"""
