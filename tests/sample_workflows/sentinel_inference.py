"""Node fixtures for the ANNOTATION-API-SPEC §4 inference engine and its tripwire (WA-07).

One table, :data:`INFERENCE_FIXTURES`, fully specifying each node's §4 outcome: the keys each
slot is inferred with **and the pattern that licensed each one**, which D-011 default applied,
whether the body could be read, and which blockers the finding has to name. Every closed
pattern appears at least twice — once in a shape that licenses it and once in a shape that
looks like it and does not — because "shallow" is a statement about what is *excluded* as much
as about what is read, and a table with only positive rows could not say so.

Everything here is armed: :func:`_arm` is the first thing every body reaches and it raises, so
a run in which inference invoked a node fails rather than being caught in review. The lambdas
are armed the only way an expression body can be — the dict *values* are ``_arm(...)`` calls —
which leaves the display itself literal, exactly as §4's output pattern (a) requires.

The expectations are written out as plain strings rather than imported from
:mod:`gebra.annotations.inference`, so a fixture states what the spec fixes and not what the
code currently does.

This module deliberately does **not** use ``from __future__ import annotations``: it is the
fixture corpus for two patterns that read annotation *objects*, and the future import would
turn every one of them into a string — which is itself a fixture here
(``reads_a_string_annotation``), and would silently become the only case if it were global.

Nothing here imports langgraph, opens a socket, or executes anything: the module is node
callables and a table.
"""

import functools
from dataclasses import dataclass
from typing import Any, Final, TypedDict

from pydantic import BaseModel


class InferenceSentinelError(RuntimeError):
    """Raised by any node here that gets called.

    Inference must never cause this: §4 reads a node's AST, and an AST is read from source.
    """


def _arm(label: str, *values: object) -> Any:
    """Refuse to run, whatever it is handed — the body of every fixture below.

    Takes ``*values`` so that an expression body can arm itself without stopping being a
    literal: ``{"plan": _arm("x", state["query"])}`` is a dict display with the key ``plan``
    whose value happens to raise if anyone evaluates it.
    """
    raise InferenceSentinelError(f"{label!r} was invoked — inference reads source, never runs it")


# ── The graph's state, and two projections of it ─────────────────────────────────────────


class State(TypedDict):
    """The graph's full state schema — §4's full-state-annotation exclusion applies to it."""

    query: str
    plan: str
    budget: int


class Reads(TypedDict):
    """A projection: what one node reads. §4 input pattern (a) licenses exactly this."""

    query: str
    budget: int


class Writes(TypedDict):
    """A projection: what one node writes. §4 output pattern (b)."""

    plan: str


class InheritedReads(Reads):
    """A projection built on another one — its declared keys are both levels'."""

    plan: str


class PydanticState(BaseModel):
    """The graph's full state schema in its pydantic spelling."""

    query: str
    plan: str


class PydanticReads(BaseModel):
    """A pydantic projection — §4 names ``TypedDict``/pydantic in the same breath."""

    query: str


class PydanticWrites(BaseModel):
    """A pydantic projection used as a *return* annotation, which §4 does not license."""

    plan: str


class UnreadableFields(type(BaseModel)):  # type: ignore[misc]
    """A metaclass whose ``model_fields`` refuses to answer."""

    @property
    def model_fields(cls) -> dict[str, Any]:
        """Raise instead of declaring — the class that will not say what it holds."""
        raise InferenceSentinelError("model_fields was asked and refused")


class Unreadable(BaseModel, metaclass=UnreadableFields):
    """A pydantic projection that answers the field question by raising.

    Not a contrivance for its own sake: ``model_fields`` is a metaclass property, so what a
    model says when asked is the model's business, and an extraction may not stop because one
    said something unhelpful.
    """


#: The schema objects that *are* the graph's state, for the §4 exclusion. Two spellings,
#: because the exclusion is about identity and a graph declares one of them, not a shape.
FULL_STATE_SCHEMAS: Final[tuple[type, ...]] = (State, PydanticState)


# ── input (a) — a projection annotation on the state parameter ───────────────────────────


def reads_a_typed_dict_projection(state: Reads) -> dict[str, Any]:
    """Positive: the annotation declares the keys, so they are the ``input`` set."""
    _arm("reads_a_typed_dict_projection")
    return {"plan": "…"}


def reads_an_inherited_projection(state: InheritedReads) -> dict[str, Any]:
    """Positive: a projection's declared keys include the ones it inherits."""
    _arm("reads_an_inherited_projection")
    return {"plan": "…"}


def reads_a_pydantic_projection(state: PydanticReads) -> dict[str, Any]:
    """Positive: pydantic is the other spelling §4 licenses."""
    _arm("reads_a_pydantic_projection")
    return {"plan": "…"}


def reads_the_full_state(state: State) -> dict[str, Any]:
    """Negative: §4's exclusion — ``def node(state: State)`` infers nothing from annotations."""
    _arm("reads_the_full_state")
    return {"plan": "…"}


def reads_the_full_pydantic_state(state: PydanticState) -> dict[str, Any]:
    """Negative: the exclusion is about identity, so it holds in both spellings."""
    _arm("reads_the_full_pydantic_state")
    return {"plan": "…"}


def reads_a_bare_dict_annotation(state: dict) -> dict[str, Any]:  # type: ignore[type-arg]
    """Negative: a ``dict`` declares no keys, so there is nothing to project."""
    _arm("reads_a_bare_dict_annotation")
    return {"plan": "…"}


def reads_a_string_annotation(state: "Reads") -> dict[str, Any]:
    """Negative: resolving a string annotation means evaluating it, which §4 rules out."""
    _arm("reads_a_string_annotation")
    return {"plan": "…"}


def reads_without_an_annotation(state: Any) -> dict[str, Any]:
    """Negative: no annotation, so pattern (a) has nothing to read."""
    _arm("reads_without_an_annotation")
    return {"plan": "…"}


def reads_a_projection_that_will_not_answer(state: Unreadable) -> dict[str, Any]:
    """Negative: a projection that raises when asked for its fields is no projection to
    read — and an extraction does not stop because one did."""
    _arm("reads_a_projection_that_will_not_answer")
    return {"plan": "…"}


# ── input (b) — literal access on the state parameter ────────────────────────────────────


def reads_literal_subscripts(state: Any) -> dict[str, Any]:
    """Positive: ``state["k"]`` is the licensed subscript form."""
    _arm("reads_literal_subscripts")
    return {"plan": _arm("plan", state["query"], state["budget"])}


def reads_literal_attributes(state: Any) -> dict[str, Any]:
    """Positive: ``state.k`` is the licensed attribute form."""
    _arm("reads_literal_attributes")
    return {"plan": _arm("plan", state.query, state.budget)}


def reads_a_computed_subscript(state: Any, key: str = "query") -> dict[str, Any]:
    """Negative: a computed key is not literal, so no key is read off it."""
    _arm("reads_a_computed_subscript")
    return {"plan": _arm("plan", state[key])}


def reads_through_a_method_call(state: Any) -> dict[str, Any]:
    """Negative: ``state.get("query")`` reads no state key named ``get``, and ``.get`` is
    not one of the two forms §4 licenses, so it contributes nothing either way."""
    _arm("reads_through_a_method_call")
    return {"plan": _arm("plan", state.get("query", ""))}


def reads_a_private_attribute(state: Any) -> dict[str, Any]:
    """Negative: ``state._cache`` is the object's own business, not a graph state key."""
    _arm("reads_a_private_attribute")
    return {"plan": _arm("plan", state._cache)}


def reads_at_depth(state: Any) -> dict[str, Any]:
    """Half-positive: the direct key is read, the nested one is not — §4 says "direct"."""
    _arm("reads_at_depth")
    return {"plan": _arm("plan", state["query"]["nested"])}


def reads_inside_a_helper(state: Any) -> dict[str, Any]:
    """Negative: DEC-08 rules out closures, so a nested function's reads are not this
    node's — even though the name it closes over is the state parameter."""
    _arm("reads_inside_a_helper")

    def helper() -> Any:
        return state["query"]

    return {"plan": _arm("plan", helper())}


def reads_in_a_comprehension(state: Any) -> dict[str, Any]:
    """Positive: a comprehension is written in the node's own body, not in a helper."""
    _arm("reads_in_a_comprehension")
    return {"plan": _arm("plan", [item for item in state["query"]])}


def reads_in_a_class_body(state: Any) -> dict[str, Any]:
    """Positive: a class body runs where it is written, unlike a method body."""
    _arm("reads_in_a_class_body")

    class Local:
        budget = state["budget"]

        def method(self) -> Any:
            return state["query"]

    return {"plan": _arm("plan", Local)}


def reads_after_rebinding_the_parameter(state: Any) -> dict[str, Any]:
    """Negative: after ``state = …`` a later ``state["k"]`` reads something else, so
    pattern (b) is dropped rather than attributed to the graph's state."""
    _arm("reads_after_rebinding_the_parameter")
    state = dict(state)
    return {"plan": _arm("plan", state["query"])}


def reads_and_augments(state: Any) -> dict[str, Any]:
    """Positive on both counts: ``state["k"] += 1`` reads ``k`` and writes state."""
    _arm("reads_and_augments")
    state["budget"] += 1
    return {"plan": "…"}


# ── output (a) — a literal dict display in a return ──────────────────────────────────────


def writes_a_literal_dict(state: Any) -> dict[str, Any]:
    """Positive: the licensed return form."""
    _arm("writes_a_literal_dict")
    return {"plan": "…", "budget": 1}


def writes_an_empty_dict(state: Any) -> dict[str, Any]:
    """Positive-with-no-keys: ``return {}`` is literal and writes nothing, so no key is
    inferred and no write evidence is found."""
    _arm("writes_an_empty_dict")
    return {}


def writes_through_dict_call(state: Any) -> dict[str, Any]:
    """Negative: ``dict(**kwargs)`` is the non-literal construction §4 excludes by name."""
    _arm("writes_through_dict_call")
    return dict(plan="…")  # noqa: C408 - the non-literal construction is the fixture


def writes_through_a_spread(state: Any) -> dict[str, Any]:
    """Negative: ``{**other}`` has keys the display does not spell."""
    _arm("writes_through_a_spread")
    return {**state, "plan": "…"}


def writes_a_computed_key(state: Any, key: str = "plan") -> dict[str, Any]:
    """Negative: a computed key is not a written key."""
    _arm("writes_a_computed_key")
    return {key: "…"}


def writes_through_a_helper(state: Any) -> dict[str, Any]:
    """Negative: the dict is built where §4 cannot see it — DEC-08's whole point."""
    _arm("writes_through_a_helper")
    return _build_update()


def _build_update() -> dict[str, Any]:
    """A helper that builds the update — deliberately out of inference's reach, and armed
    like everything else: a node's helper is as much not-to-be-run as the node."""
    return _arm("_build_update")  # type: ignore[no-any-return]


# ── output (b) — a TypedDict return annotation ───────────────────────────────────────────


def writes_a_typed_dict_return(state: Any) -> Writes:
    """Positive: the return annotation declares the written keys."""
    _arm("writes_a_typed_dict_return")
    return {"plan": "…"}


def writes_the_full_state_return(state: Any) -> State:
    """Negative: the §4 exclusion covers the return annotation in the same sentence."""
    _arm("writes_the_full_state_return")
    return {"query": "…", "plan": "…", "budget": 1}


def writes_a_pydantic_return(state: Any) -> PydanticWrites:
    """Negative, and the one asymmetry in §4's table: the ``input`` row licenses "a
    ``TypedDict``/pydantic projection" while the ``output`` row licenses "a ``TypedDict``
    return-type annotation". The table is closed, so a pydantic return declares nothing here."""
    _arm("writes_a_pydantic_return")
    return PydanticWrites(plan="...")


def writes_only_by_its_return_annotation(state: Any) -> Writes:
    """Positive on both counts, and the pair is the point: the annotation licenses the
    ``output`` key **and** is a matched licensed output pattern, so the node is a writer under
    §4's two-part test even though its body shows no write at all."""
    _arm("writes_only_by_its_return_annotation")
    raise InferenceSentinelError("unreachable: the body writes nothing a pattern can read")


# ── output (c) — a literal Command(update={...}) ─────────────────────────────────────────


def writes_a_command_update(state: Any) -> Any:
    """Positive: the licensed ``Command`` form."""
    _arm("writes_a_command_update")
    return Command(update={"plan": "…"}, goto="act_step")


def writes_a_command_without_update(state: Any) -> Any:
    """Positive-with-no-keys: a route with no update writes no state, literally."""
    _arm("writes_a_command_without_update")
    return Command(goto="act_step")


def writes_a_command_built_elsewhere(state: Any) -> Any:
    """Negative: ``update=`` is a name, so the written keys are not in this body."""
    _arm("writes_a_command_built_elsewhere")
    update = _build_update()
    return Command(update=update)


def writes_a_command_bound_to_a_name(state: Any) -> Any:
    """Negative for ``output``, positive for write evidence: the construction is literal,
    but the return site is a name, and §4's multi-return rule is about the sites."""
    _arm("writes_a_command_bound_to_a_name")
    command = Command(update={"plan": "…"})
    return command


def writes_a_command_with_spread_keywords(state: Any) -> Any:
    """Negative: ``Command(**kwargs)`` may or may not carry an update."""
    _arm("writes_a_command_with_spread_keywords")
    return Command(**{"update": {"plan": "…"}})  # noqa: PIE804 - the spread is the fixture


class Command:
    # A local stand-in rather than the substrate's `langgraph.types.Command`: §4's pattern (c)
    # is about the *construction as written*, and this module must not import langgraph (the
    # engine is substrate-free and its tripwire asserts as much). What inference reads is the
    # name in the source, which is identical either way.
    def __init__(self, **kwargs: Any) -> None:
        raise InferenceSentinelError("Command was constructed — inference never evaluates")


# ── The multi-return rule ────────────────────────────────────────────────────────────────


def returns_two_licensed_sites(state: Any) -> dict[str, Any]:
    """Positive: every site is licensed, so ``output`` is the union of their keys."""
    _arm("returns_two_licensed_sites")
    if state["query"]:
        return {"plan": "…"}
    return {"budget": 1}


def returns_a_licensed_and_an_unlicensed_site(state: Any) -> dict[str, Any]:
    """Negative: one unlicensed site abandons ``output`` wholesale — a partial union
    would under-report writes — while the licensed one still evidences a write."""
    _arm("returns_a_licensed_and_an_unlicensed_site")
    if state["query"]:
        return {"plan": "…"}
    return _build_update()


def returns_a_bare_return(state: Any) -> dict[str, Any] | None:
    """Positive: ``return`` and ``return None`` are literal statements of writing nothing,
    so they do not abandon the union the other site licensed."""
    _arm("returns_a_bare_return")
    if state["query"]:
        return {"plan": "…"}
    if state["budget"]:
        return None
    return  # type: ignore[return-value]


def returns_an_unlicensed_site_with_an_annotation(state: Any) -> Writes:
    """Negative on the keys, positive on the evidence — the two halves of §4 come apart here.

    "Abandoned wholesale" is read as written, so the return annotation goes with the literals
    and no ``output`` key survives: a node whose writes are partly invisible has no known
    output set. But the annotation still *matched* a licensed output pattern, which is what
    §4's D-011 precondition asks about, so the node is a writer and takes the floor rather
    than being called pure.
    """
    _arm("returns_an_unlicensed_site_with_an_annotation")
    return _build_update()  # type: ignore[return-value]


def returns_from_a_nested_function_only(state: Any) -> None:
    """Negative on the sites, positive on the scope rule: the ``return`` inside the helper is
    not one of this node's return sites, so nothing is abandoned and nothing is inferred."""
    _arm("returns_from_a_nested_function_only")

    def helper() -> dict[str, Any]:
        return _build_update()

    _arm("unused", helper)


# ── The decision D-011 defaults ──────────────────────────────────────────────────────────


def writes_by_assignment(state: Any) -> None:
    """Positive for write evidence: an assignment to the state parameter."""
    _arm("writes_by_assignment")
    state["plan"] = "…"


def writes_by_attribute_assignment(state: Any) -> None:
    """Positive for write evidence: the attribute spelling of the same thing."""
    _arm("writes_by_attribute_assignment")
    state.plan = "…"


def writes_by_deletion(state: Any) -> None:
    """Positive for write evidence: deleting a key is a state change."""
    _arm("writes_by_deletion")
    del state["plan"]


def writes_by_mutation(state: Any) -> None:
    """Positive for write evidence: a mutating method on the state parameter."""
    _arm("writes_by_mutation")
    state.update({"plan": "…"})


def writes_by_mutating_a_value(state: Any) -> None:
    """Positive for write evidence: mutating a value *inside* the state is a state write."""
    _arm("writes_by_mutating_a_value")
    state["messages"].append("…")


def writes_by_a_loop_target(state: Any) -> None:
    """Positive for write evidence: a ``for`` target is an assignment like any other."""
    _arm("writes_by_a_loop_target")
    for state["plan"] in ["…"]:
        pass


def writes_to_something_that_is_not_the_state(state: Any) -> dict[str, Any]:
    """Negative: the write-evidence rule is rooted at the state parameter, not at any
    subscript or attribute in sight — a local scratch dict is the node's own business."""
    _arm("writes_to_something_that_is_not_the_state")
    scratch: Any = {}
    scratch["plan"] = 1
    scratch.total = 2
    del scratch["plan"]
    seen = 0
    seen += 1
    return {}


def augments_by_attribute_and_by_computed_key(state: Any, key: str = "budget") -> None:
    """Positive on both writes, half-positive on the reads: ``state.budget += 1`` reads the
    key it augments, while ``state[key] += 1`` writes a key it does not spell."""
    _arm("augments_by_attribute_and_by_computed_key")
    state.budget += 1
    state[key] += 1


def returns_two_unlicensed_sites(state: Any) -> dict[str, Any]:
    """Negative twice over: two unlicensed sites abandon ``output`` once, not twice —
    the blocker is a reason, and a reason is recorded once."""
    _arm("returns_two_unlicensed_sites")
    if state["query"]:
        return _build_update()
    return _build_update()


def reads_only(state: Any) -> Any:
    """Positive for the read-only default: no licensed output pattern and no assignment,
    so D-011's ``pure: true`` — "a no-evidence-found result, not a proof"."""
    _arm("reads_only")
    return _arm("checked", state["query"] == state["budget"])


def reads_only_through_methods(state: Any) -> Any:
    """Positive for the read-only default: ``get``/``keys`` read, and reading is not
    writing — the closed mutating-method set is what separates them."""
    _arm("reads_only_through_methods")
    return _arm("checked", state.get("query"), state.keys())


def takes_no_parameter() -> dict[str, Any]:
    """Negative: no positional parameter, so §4's state parameter does not exist. The
    literal return still licenses ``output``; only the input patterns lose their subject."""
    _arm("takes_no_parameter")
    return {"plan": "…"}


# ── Shapes of callable ───────────────────────────────────────────────────────────────────


async def an_async_node(state: Reads) -> Writes:
    """§4: "``async def`` nodes are treated identically (the patterns read the async body)"."""
    _arm("an_async_node")
    return {"plan": _arm("plan", state["query"])}


def _passthrough(function: Any) -> Any:
    """A decorator that keeps the wrapped function's identity — the ordinary case."""

    @functools.wraps(function)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        return function(*args, **kwargs)

    return wrapper


@_passthrough
def a_decorated_node(state: Reads) -> Writes:
    """A decorated definition: its code object's first line is the ``@``, not the ``def``.

    The fixture reads the *inner* function (``__wrapped__``); following the wrapper chain to
    it is §6's rule and belongs to the resolution card, so the table names it directly.
    """
    _arm("a_decorated_node")
    return {"plan": _arm("plan", state["query"])}


class Nodes:
    """Node callables that arrive bound — §4's ``self``/``cls`` clause."""

    def a_method(self, state: Reads) -> Writes:
        """A bound method: the state parameter is the one after ``self``."""
        _arm("a_method")
        return {"plan": _arm("plan", state["query"])}

    @classmethod
    def a_classmethod(cls, state: Reads) -> Writes:
        """A bound classmethod: the state parameter is the one after ``cls``."""
        _arm("a_classmethod")
        return {"plan": _arm("plan", state["query"])}

    @staticmethod
    def a_staticmethod(state: Reads) -> Writes:
        """A staticmethod arrives as a plain function, so nothing is skipped."""
        _arm("a_staticmethod")
        return {"plan": _arm("plan", state["query"])}


#: A ``lambda`` node with a dict-display body — §4 states this case outright.
a_lambda_node = lambda state: {"plan": _arm("a_lambda_node", state["query"])}

#: A ``lambda`` whose body is not a display: the one return site is unlicensed.
an_opaque_lambda_node = lambda state: _arm("an_opaque_lambda_node", state)


class CallableNode:
    """A callable object — not a Python function, so it has no body §4 can read."""

    def __call__(self, state: Any) -> dict[str, Any]:
        """Never reached: inference stops at the object, and §6's walk is a later card."""
        _arm("CallableNode")
        return {"plan": "…"}


# ── The table ────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class InferenceFixture:
    """One node callable and the §4 outcome the spec fixes for it.

    Attributes:
        node: The callable, as extraction would hand it to inference.
        input: The expected ``input`` keys as ``(key, pattern)`` pairs, **in order**. Empty
            means the slot is left unset — never set to ``[]``.
        output: The same for ``output``.
        default: The applied :class:`~gebra.annotations.inference.DefaultRule` value, or
            ``None`` when no D-011 default applies.
        source: The expected :class:`~gebra.annotations.inference.SourceRule` value.
        blockers: Blocker values the outcome must name. A subset requirement, not the whole
            list: what matters per fixture is that the *specific* reason it did not match is
            recorded, and several reasons can be true of one node at once.
        schema: Whether to infer with the graph's state schema supplied. ``False`` is how the
            "Σ not known" case is exercised, which withdraws the annotation patterns.
    """

    node: Any
    input: tuple[tuple[str, str], ...] = ()
    output: tuple[tuple[str, str], ...] = ()
    default: str | None = "no-write-evidence"
    source: str = "read"
    blockers: tuple[str, ...] = ()
    schema: bool = True


#: Every §4 pattern, positive and negative, plus the D-011 defaults and the callable shapes.
#: Keyed by a name that says what the row is *about*, since the failure message quotes it.
INFERENCE_FIXTURES: Final[dict[str, InferenceFixture]] = {
    # input (a) — projection annotations
    "input_annotation_typed_dict": InferenceFixture(
        node=reads_a_typed_dict_projection,
        input=(("query", "state-annotation-keys"), ("budget", "state-annotation-keys")),
        output=(("plan", "return-literal"),),
        default="writes-state",
    ),
    "input_annotation_inherited": InferenceFixture(
        node=reads_an_inherited_projection,
        input=(
            ("query", "state-annotation-keys"),
            ("budget", "state-annotation-keys"),
            ("plan", "state-annotation-keys"),
        ),
        output=(("plan", "return-literal"),),
        default="writes-state",
    ),
    "input_annotation_pydantic": InferenceFixture(
        node=reads_a_pydantic_projection,
        input=(("query", "state-annotation-keys"),),
        output=(("plan", "return-literal"),),
        default="writes-state",
    ),
    "input_annotation_full_state": InferenceFixture(
        node=reads_the_full_state,
        output=(("plan", "return-literal"),),
        default="writes-state",
        blockers=("full-state-annotation",),
    ),
    "input_annotation_full_pydantic_state": InferenceFixture(
        node=reads_the_full_pydantic_state,
        output=(("plan", "return-literal"),),
        default="writes-state",
        blockers=("full-state-annotation",),
    ),
    "input_annotation_bare_dict": InferenceFixture(
        node=reads_a_bare_dict_annotation,
        output=(("plan", "return-literal"),),
        default="writes-state",
        blockers=("not-a-projection",),
    ),
    "input_annotation_string": InferenceFixture(
        node=reads_a_string_annotation,
        output=(("plan", "return-literal"),),
        default="writes-state",
        blockers=("string-annotation",),
    ),
    "input_annotation_absent": InferenceFixture(
        node=reads_without_an_annotation,
        output=(("plan", "return-literal"),),
        default="writes-state",
        blockers=("not-a-projection",),
    ),
    "input_annotation_unreadable": InferenceFixture(
        node=reads_a_projection_that_will_not_answer,
        output=(("plan", "return-literal"),),
        default="writes-state",
        blockers=("projection-unreadable",),
    ),
    "input_annotation_without_a_schema": InferenceFixture(
        node=reads_a_typed_dict_projection,
        output=(("plan", "return-literal"),),
        default="writes-state",
        blockers=("state-schema-unknown",),
        schema=False,
    ),
    # input (b) — literal access
    "input_subscript": InferenceFixture(
        node=reads_literal_subscripts,
        input=(("query", "state-access"), ("budget", "state-access")),
        output=(("plan", "return-literal"),),
        default="writes-state",
    ),
    "input_attribute": InferenceFixture(
        node=reads_literal_attributes,
        input=(("query", "state-access"), ("budget", "state-access")),
        output=(("plan", "return-literal"),),
        default="writes-state",
    ),
    "input_computed_subscript": InferenceFixture(
        node=reads_a_computed_subscript,
        output=(("plan", "return-literal"),),
        default="writes-state",
    ),
    "input_method_call": InferenceFixture(
        node=reads_through_a_method_call,
        output=(("plan", "return-literal"),),
        default="writes-state",
    ),
    "input_private_attribute": InferenceFixture(
        node=reads_a_private_attribute,
        output=(("plan", "return-literal"),),
        default="writes-state",
    ),
    "input_nested_subscript": InferenceFixture(
        node=reads_at_depth,
        input=(("query", "state-access"),),
        output=(("plan", "return-literal"),),
        default="writes-state",
    ),
    "input_inside_a_helper": InferenceFixture(
        node=reads_inside_a_helper,
        output=(("plan", "return-literal"),),
        default="writes-state",
    ),
    "input_in_a_comprehension": InferenceFixture(
        node=reads_in_a_comprehension,
        input=(("query", "state-access"),),
        output=(("plan", "return-literal"),),
        default="writes-state",
    ),
    "input_in_a_class_body": InferenceFixture(
        node=reads_in_a_class_body,
        input=(("budget", "state-access"),),
        output=(("plan", "return-literal"),),
        default="writes-state",
    ),
    "input_after_rebinding": InferenceFixture(
        node=reads_after_rebinding_the_parameter,
        output=(("plan", "return-literal"),),
        default="writes-state",
        blockers=("state-parameter-rebound",),
    ),
    "input_augmented_assignment": InferenceFixture(
        node=reads_and_augments,
        input=(("budget", "state-access"),),
        output=(("plan", "return-literal"),),
        default="writes-state",
    ),
    # output (a) — literal dict displays
    "output_literal_dict": InferenceFixture(
        node=writes_a_literal_dict,
        output=(("plan", "return-literal"), ("budget", "return-literal")),
        default="writes-state",
    ),
    "output_empty_dict": InferenceFixture(node=writes_an_empty_dict),
    "output_dict_call": InferenceFixture(
        node=writes_through_dict_call,
        default="no-write-evidence",
        blockers=("return-not-literal",),
    ),
    "output_spread": InferenceFixture(
        node=writes_through_a_spread,
        default="writes-state",
        blockers=("return-not-literal",),
    ),
    "output_computed_key": InferenceFixture(
        node=writes_a_computed_key,
        default="no-write-evidence",
        blockers=("return-not-literal",),
    ),
    "output_from_a_helper": InferenceFixture(
        node=writes_through_a_helper,
        default="no-write-evidence",
        blockers=("return-not-literal",),
    ),
    # output (b) — return annotations
    "output_annotation_typed_dict": InferenceFixture(
        node=writes_a_typed_dict_return,
        output=(("plan", "return-annotation-keys"),),
        default="writes-state",
    ),
    "output_annotation_full_state": InferenceFixture(
        node=writes_the_full_state_return,
        output=(
            ("query", "return-literal"),
            ("plan", "return-literal"),
            ("budget", "return-literal"),
        ),
        default="writes-state",
        blockers=("full-state-annotation",),
    ),
    "output_annotation_pydantic": InferenceFixture(
        node=writes_a_pydantic_return,
        default="no-write-evidence",
        blockers=("not-a-typed-dict", "return-not-literal"),
    ),
    "output_annotation_only": InferenceFixture(
        node=writes_only_by_its_return_annotation,
        output=(("plan", "return-annotation-keys"),),
        default="writes-state",
    ),
    # output (c) — Command(update=...)
    "output_command_update": InferenceFixture(
        node=writes_a_command_update,
        output=(("plan", "command-update"),),
        default="writes-state",
    ),
    "output_command_without_update": InferenceFixture(node=writes_a_command_without_update),
    "output_command_built_elsewhere": InferenceFixture(
        node=writes_a_command_built_elsewhere,
        default="writes-state",
        blockers=("command-update-not-literal",),
    ),
    "output_command_bound_to_a_name": InferenceFixture(
        node=writes_a_command_bound_to_a_name,
        default="writes-state",
        blockers=("return-not-literal",),
    ),
    "output_command_spread_keywords": InferenceFixture(
        node=writes_a_command_with_spread_keywords,
        default="no-write-evidence",
        blockers=("command-update-not-literal",),
    ),
    # the multi-return rule
    "multi_return_all_licensed": InferenceFixture(
        node=returns_two_licensed_sites,
        input=(("query", "state-access"),),
        output=(("plan", "return-literal"), ("budget", "return-literal")),
        default="writes-state",
    ),
    "multi_return_one_unlicensed": InferenceFixture(
        node=returns_a_licensed_and_an_unlicensed_site,
        input=(("query", "state-access"),),
        default="writes-state",
        blockers=("return-not-literal",),
    ),
    "multi_return_bare_returns": InferenceFixture(
        node=returns_a_bare_return,
        input=(("query", "state-access"), ("budget", "state-access")),
        output=(("plan", "return-literal"),),
        default="writes-state",
    ),
    "multi_return_annotation_abandoned": InferenceFixture(
        node=returns_an_unlicensed_site_with_an_annotation,
        default="writes-state",
        blockers=("return-not-literal",),
    ),
    "multi_return_nested_only": InferenceFixture(node=returns_from_a_nested_function_only),
    # the D-011 defaults
    "default_assignment": InferenceFixture(node=writes_by_assignment, default="writes-state"),
    "default_attribute_assignment": InferenceFixture(
        node=writes_by_attribute_assignment, default="writes-state"
    ),
    "default_deletion": InferenceFixture(node=writes_by_deletion, default="writes-state"),
    "default_mutation": InferenceFixture(node=writes_by_mutation, default="writes-state"),
    "default_nested_mutation": InferenceFixture(
        node=writes_by_mutating_a_value,
        input=(("messages", "state-access"),),
        default="writes-state",
    ),
    "default_loop_target": InferenceFixture(node=writes_by_a_loop_target, default="writes-state"),
    "default_not_the_state": InferenceFixture(node=writes_to_something_that_is_not_the_state),
    "default_augmented_targets": InferenceFixture(
        node=augments_by_attribute_and_by_computed_key,
        input=(("budget", "state-access"),),
        default="writes-state",
    ),
    "multi_return_two_unlicensed": InferenceFixture(
        node=returns_two_unlicensed_sites,
        input=(("query", "state-access"),),
        default="no-write-evidence",
        blockers=("return-not-literal",),
    ),
    "default_read_only": InferenceFixture(
        node=reads_only,
        input=(("query", "state-access"), ("budget", "state-access")),
        default="no-write-evidence",
    ),
    "default_read_only_methods": InferenceFixture(
        node=reads_only_through_methods, default="no-write-evidence"
    ),
    "default_no_state_parameter": InferenceFixture(
        node=takes_no_parameter,
        output=(("plan", "return-literal"),),
        default="writes-state",
        blockers=("no-state-parameter",),
    ),
    # shapes of callable
    "shape_async": InferenceFixture(
        node=an_async_node,
        input=(("query", "state-annotation-keys"), ("budget", "state-annotation-keys")),
        output=(("plan", "return-annotation-keys"),),
        default="writes-state",
    ),
    "shape_decorated": InferenceFixture(
        node=a_decorated_node.__wrapped__,
        input=(("query", "state-annotation-keys"), ("budget", "state-annotation-keys")),
        output=(("plan", "return-annotation-keys"),),
        default="writes-state",
    ),
    "shape_bound_method": InferenceFixture(
        node=Nodes().a_method,
        input=(("query", "state-annotation-keys"), ("budget", "state-annotation-keys")),
        output=(("plan", "return-annotation-keys"),),
        default="writes-state",
    ),
    "shape_classmethod": InferenceFixture(
        node=Nodes.a_classmethod,
        input=(("query", "state-annotation-keys"), ("budget", "state-annotation-keys")),
        output=(("plan", "return-annotation-keys"),),
        default="writes-state",
    ),
    "shape_staticmethod": InferenceFixture(
        node=Nodes.a_staticmethod,
        input=(("query", "state-annotation-keys"), ("budget", "state-annotation-keys")),
        output=(("plan", "return-annotation-keys"),),
        default="writes-state",
    ),
    "shape_lambda": InferenceFixture(
        node=a_lambda_node,
        input=(("query", "state-access"),),
        output=(("plan", "return-literal"),),
        default="writes-state",
    ),
    "shape_lambda_call_body": InferenceFixture(
        node=an_opaque_lambda_node,
        default="no-write-evidence",
        blockers=("return-not-literal",),
    ),
    "shape_callable_object": InferenceFixture(
        node=CallableNode(),
        default="body-unavailable",
        source="not-a-python-function",
        blockers=("body-unavailable",),
    ),
    "shape_builtin": InferenceFixture(
        node=len,
        default="body-unavailable",
        source="not-a-python-function",
        blockers=("body-unavailable",),
    ),
}
