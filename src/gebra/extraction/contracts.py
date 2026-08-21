"""Where a node's contract comes from — ANNOTATION-API-SPEC §3 and §6, as extraction sees it.

:mod:`gebra.annotations.resolve` owns the §3 chain itself: given one contribution per tier it
elects a winner per slot, reports the disagreements, and validates what it assembled. That
module knows nothing about LangGraph, and cannot — the dependency between the annotation
surface and the extractor runs one way only. This module is the seam that gives it the four
contributions and turns what comes back into records of the one warnings taxonomy
(INTROSPECTION §8 / ANNOTATION §4).

Three of the four contributions need something only this layer has.

**Decorator — §6's wrapper walk and the outermost-carrier rule.** §6: "Extraction locates the
innermost user callable by following ``functools.wraps`` chains (``__wrapped__``) and known
LangGraph/LangChain wrapper attributes", and when several callables in one chain carry a
contract, "the **first contract-bearing callable encountered walking inward from the outermost
wrapper wins wholesale**; deeper carriers are ignored entirely — no per-slot merge … and
extraction emits an ``annotation-invalid`` warning naming both carriers". :func:`walk` is that
walk and :func:`read_declarations` applies the rule.

The walk is attribute reads and ``isinstance`` checks — INTROSPECTION §1 rule 3's own list —
and it follows a member only when the value is something §6 names as a wrapper: a Python
function or method, or a ``Runnable`` (which is what ``RunnableCallable``, ``RunnableLambda``,
``RunnableBinding`` and every ``BaseTool`` are). A ``functools.partial`` is therefore *not*
followed, and that is the spec's own disposition rather than an oversight: §6 lists
"``functools.partial`` objects that drop attributes" among the shapes for which "the sidecar is
the designated fallback". Following one would also walk into the substrate's own
``run_in_executor`` trampoline, which is not user code at all.

**Tool-carried — the §3 tier between the decorator and the sidecar.** A LangChain
``BaseTool``'s pydantic ``args_schema`` is read "as a declared source (it is author-written
schema, not inference) and serialized to JSON Schema". Reading it is pydantic model/JSON-schema
introspection, which §1 rule 3 admits by name; the tool itself is never called, and neither is
the callable it wraps.

**Inference — §4, and what it is *not* asked.** Inference "fills what remains", so it is asked
only about the slots the three declaration tiers left open, and it is given the innermost
callable the walk found. A ``RunnableLambda`` in the chain makes the node **opaque**: §4 sends
"opaque nodes (``RunnableLambda`` bodies …)" straight to the D-011 defaults and §5 rule 5 says
the same in the other spec. The floor is ``effect: [write]``, never ``pure``, so opacity can
only cost precision.

**One substitution this module deliberately does not make.** INTROSPECTION §8's
``contract-defaulted`` row adds "For stitched lambdas, ``opaque-lambda`` below is emitted
instead and carries the default". Whether a node is a *stitched* lambda is a §5 fact, and this
seam does not know it: it resolves a contract for whatever bound object it is handed, so every
D-011 default is reported here as ``contract-defaulted`` and :mod:`gebra.extraction.lcel` adds
the ``opaque-lambda`` record on top for the nodes it stitches. Keeping the
``contract-defaulted`` record either way is what keeps ANNOTATION §5's grade lookup sound: its
"iff" names exactly ``contract-inferred``/``contract-defaulted``, so a defaulted slot reported
*only* as ``opaque-lambda`` would read back as **declared**-grade and would unlock the very
``pure`` ⟹ idempotent implication §4's NEVER-SILENT-UPGRADE corollary forbids (for P-06/P-07;
the D-011 default never yields ``deterministic``, so P-08 is untouched). §8 used to say the
substitution *replaced* the record — the standing spec-defect request EX-08 and EX-10 carried
forward — and DEC-20 (2026-08-03) replaced "instead" with "**in addition**", making the
co-emission this seam and §5's path already produced the conforming form.

Nothing here invokes anything (WA-07). No node function, router, tool or ``Runnable`` is
called; the walk reads attributes and asks ``isinstance``; the one call this module makes on a
caller-supplied object is ``model_json_schema()`` on a declared ``args_schema`` class, which is
the introspection §1 rule 3 licenses, and it is guarded so that a schema which answers by
raising becomes a warning rather than an extraction failure.
"""

from __future__ import annotations

import functools
import types
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any, Final

from langchain_core.runnables import Runnable, RunnableLambda
from langchain_core.tools import BaseTool
from pydantic import BaseModel

from gebra.annotations.contract import NodeContract, normalize_declared_value, read_contract
from gebra.annotations.errors import GebraContractError
from gebra.annotations.inference import (
    Inference,
    InferenceFinding,
    SourceCache,
    StateSchema,
    infer_node,
)
from gebra.annotations.resolve import (
    Contribution,
    IssueKind,
    Resolution,
    ResolutionIssue,
    Surface,
    resolve,
)
from gebra.annotations.slots import AnnotationSlot
from gebra.extraction.base import type_identity
from gebra.extraction.inference import contract_warnings
from gebra.extraction.warnings import ExtractionWarning, ExtractionWarningCode

__all__ = [
    "WRAPPER_MEMBERS",
    "CarrierRule",
    "Declarations",
    "NodeContracts",
    "resolve_node",
    "state_schema_of",
    "walk",
]

#: The "known LangGraph/LangChain wrapper attributes" of §6, in the order a chain step tries
#: them. ``__wrapped__`` comes first because it is the one §6 names outright — a user decorator
#: that applied ``functools.wraps`` is exactly the case §6 warns about — and the rest are the
#: members the substrate's own wrappers hold their inner callable in: ``RunnableCallable.func``
#: (and ``.afunc`` for an ``async def`` node, where ``func`` is absent), ``RunnableLambda.func``,
#: ``StructuredTool.func``/``.coroutine``, and ``RunnableBinding.bound``.
WRAPPER_MEMBERS: Final[tuple[str, ...]] = (
    "__wrapped__",
    "func",
    "afunc",
    "coroutine",
    "bound",
)

#: How far the walk descends. A bound rather than a policy: a chain this long is a cycle the
#: identity guard did not catch (an object rebuilt at each step), and the D-011 floor is a
#: better answer than a ``RecursionError`` out of ``gebra.extract()``.
_MAX_DEPTH: Final = 32


class CarrierRule(str, Enum):
    """The §6/§3 rule an ``annotation-invalid`` from *this* layer reports.

    Disjoint from :class:`~gebra.annotations.resolve.ResolutionRule`, which covers the rules
    the chain itself can violate. These three are the ones only the seam can see, because each
    is about the live object rather than about a declared value.

    Attributes:
        MULTIPLE_CARRIERS: §6 — more than one callable in one wrapper chain carries
            ``__gebra_contract__``. The outermost wins wholesale; the deeper ones are ignored
            entirely, with no per-slot merge.
        CARRIER_UNREADABLE: A ``__gebra_contract__`` that is not a
            :class:`~gebra.annotations.contract.NodeContract`. On the decoration surface that
            is an import-time error (§1: gebra owns the attribute and will not overwrite
            something it did not attach); reached from *extraction* it is warning-grade like
            everything else §3 meets, and the tier simply declares nothing.
        TOOL_SCHEMA_UNREADABLE: A ``BaseTool`` whose ``args_schema`` could not be read as a
            JSON Schema object — it answered ``model_json_schema()`` by raising, or it is a
            mapping holding something JSON cannot carry. The tier declares nothing rather than
            declaring a guess.
    """

    MULTIPLE_CARRIERS = "multiple-carriers"
    CARRIER_UNREADABLE = "carrier-unreadable"
    TOOL_SCHEMA_UNREADABLE = "tool-schema-unreadable"


@dataclass(frozen=True)
class Declarations:
    """What §6's walk found on one node's bound object.

    Attributes:
        chain: The wrapper chain, outermost first — the objects §6's walk visited.
        contract: The winning decorator contract (the outermost carrier), or ``None``.
        carriers: Every carrier found, outermost first. More than one is §6's
            multiple-carrier case; the record is what lets the warning name both.
        tool: The outermost ``BaseTool`` in the chain, or ``None`` — the tool-carried tier's
            source.
        innermost: The innermost object the walk reached — what §4 is asked about.
        opaque: Whether a ``RunnableLambda`` sits in the chain, which §4 and INTROSPECTION §5
            rule 5 both make an opaque body.
        issues: The §6 findings, as neutral records; :func:`resolve_node` gives them their
            node id and their code.
    """

    chain: tuple[object, ...]
    contract: NodeContract | None = None
    carriers: tuple[object, ...] = ()
    tool: BaseTool | None = None
    innermost: object = None
    opaque: bool = False
    issues: tuple[tuple[CarrierRule, str, Mapping[str, Any]], ...] = ()


@dataclass(frozen=True)
class NodeContracts:
    """One node's resolved contract and everything §3/§4/§6 had to say about it.

    Attributes:
        contract: The resolved contract — the slots that survived the chain, the carriability
            pass and the resolved-contract repair. Every one of them has canonical bytes.
        resolution: The chain's own record, for a caller that needs the surface per slot.
        inference: What §4 contributed, or ``None`` when it was not asked (every slot it can
            fill was already taken).
        opaque: Whether §6's walk found a ``RunnableLambda`` in the chain — the input §4 and
            INTROSPECTION §5 rule 5 both call an opaque body. Carried out rather than
            recomputed because the only way to ask again is to walk the caller's wrapper chain
            a second time, and every step of that walk is an attribute read of an object under
            extraction (WA-07). §5's stitching path is the caller that needs it, to decide
            whether a defaulted contract also owes an ``opaque-lambda`` record.
        warnings: The records for the envelope, in one order: §6's carrier findings, then the
            chain's conflicts and invalids, then §4's ``contract-inferred`` /
            ``contract-defaulted``.
    """

    contract: NodeContract
    resolution: Resolution
    inference: Inference | None = None
    opaque: bool = False
    warnings: tuple[ExtractionWarning, ...] = ()


def state_schema_of(builder: object) -> StateSchema:
    """The graph's own schema objects, for §4's full-state-annotation exclusion.

    §4 asks one question of these: is the state-parameter (or return-type) annotation "the
    graph's full state schema itself"? So what belongs here are the **graph-level** schemas —
    the class ``StateGraph(...)`` was constructed with, and the input/output narrowings
    declared beside it — and nothing else.

    ``builder.schemas`` is deliberately *not* the source, and the difference is the whole
    exclusion. That mapping accumulates a schema per registered ``input_schema=``, so
    ``add_node("n", fn)`` where ``fn``'s state parameter is annotated with a projection puts
    the **projection** in it — and reading the exclusion off that set would exclude exactly
    the annotations §4's ``input`` pattern (a) exists to license. :mod:`gebra.extraction.state`
    reads the same mapping for a different question (which keys each schema declares), where
    the accumulation is the point.

    :class:`~gebra.annotations.inference.StateSchema` compares with ``is``, so no schema
    class's own ``__eq__`` or ``__hash__`` decides which schema is which; duplicates among
    the three attributes are harmless for the same reason.
    """
    named = tuple(
        schema
        for attribute in ("state_schema", "input_schema", "output_schema")
        if (schema := getattr(builder, attribute, None)) is not None
    )
    return StateSchema(schemas=named)


def walk(bound: object) -> Declarations:
    """Follow one node's wrapper chain inward and record what §6 asks about (§6).

    Args:
        bound: The node's bound object — ``StateNodeSpec.runnable``, which INTROSPECTION §3
            reads "for exactly three purposes", of which this is purpose (ii), contract
            attachment.

    Returns:
        The :class:`Declarations` for that chain. Total: every way of failing to read a
        carrier is a finding on the record, never an exception, because §3 puts this whole
        surface at warning grade.
    """
    chain: list[object] = []
    carriers: list[tuple[object, NodeContract]] = []
    issues: list[tuple[CarrierRule, str, Mapping[str, Any]]] = []
    tool: BaseTool | None = None
    opaque = False

    seen: set[int] = set()
    current: object = bound
    while current is not None and id(current) not in seen and len(chain) < _MAX_DEPTH:
        seen.add(id(current))
        chain.append(current)
        if tool is None and isinstance(current, BaseTool):
            tool = current
        if isinstance(current, RunnableLambda):
            opaque = True
        _read_carrier(current, carriers, issues)
        current = _inward(current)

    return Declarations(
        chain=tuple(chain),
        contract=_elected_carrier(carriers, issues),
        carriers=tuple(carrier for carrier, _ in carriers),
        tool=tool,
        innermost=chain[-1] if chain else None,
        opaque=opaque,
        issues=tuple(issues),
    )


def resolve_node(
    node_id: str,
    bound: object,
    *,
    sidecar_entry: NodeContract | None = None,
    state_schema: StateSchema | None = None,
    cache: SourceCache | None = None,
) -> NodeContracts:
    """Resolve one node's contract through the whole §3 chain, and say how (§3, §4, §6).

    Args:
        node_id: The node's escaped IR-SPEC §5 id — the first half of §5's (node id, slot)
            lookup key, and what every record here is filed under.
        bound: The node's bound object (``StateNodeSpec.runnable``).
        sidecar_entry: The ``gebra.toml`` entry keyed by ``node_id``, or ``None``. The lookup
            is the caller's, because §2 puts exactly one sidecar read per extraction and the
            entry point is where it happens.
        state_schema: The graph's state schema, for §4's full-state exclusion. ``None``
            withdraws §4's two annotation patterns, which is what the engine does with an
            unknown schema.
        cache: A per-extraction :class:`~gebra.annotations.inference.SourceCache`.

    Returns:
        The :class:`NodeContracts` record. Nothing here raises: a contract that cannot be
        read, a schema that cannot be serialized and a resolved contract that violates a §1
        invariant are all findings, because "extraction stays total".
    """
    declarations = walk(bound)
    warnings: list[ExtractionWarning] = [
        _invalid(node_id, rule, message, detail) for rule, message, detail in declarations.issues
    ]

    contributions: list[Contribution] = []
    if declarations.contract is not None:
        contributions.append(Contribution(Surface.DECORATOR, declarations.contract))
    tool_contract, tool_issue = _tool_contribution(declarations.tool)
    if tool_issue is not None:
        warnings.append(_invalid(node_id, *tool_issue))
    if tool_contract is not None:
        contributions.append(Contribution(Surface.TOOL, tool_contract))
    if sidecar_entry is not None:
        contributions.append(Contribution(Surface.SIDECAR, sidecar_entry))

    taken = _declared_slots(contributions)
    inference = infer_node(
        declarations.innermost,
        state_schema=state_schema,
        declared=taken,
        declared_writes=_declares_writes(contributions),
        opaque=declarations.opaque,
        cache=cache,
    )
    contributions.append(Contribution(Surface.INFERENCE, inference.contract))

    resolution = resolve(contributions)
    warnings.extend(_issue_warnings(node_id, resolution.issues))
    warnings.extend(_surviving_findings(node_id, inference, resolution))

    return NodeContracts(
        contract=resolution.contract,
        resolution=resolution,
        inference=inference,
        opaque=declarations.opaque,
        warnings=tuple(warnings),
    )


# ── §6's walk ────────────────────────────────────────────────────────────────────────────


def _inward(current: object) -> object | None:
    """The next object inward, or ``None`` when the chain ends here (§6).

    The first followable member wins, in :data:`WRAPPER_MEMBERS` order. "Followable" is the
    narrow test the module docstring records: a Python function or method, or a ``Runnable``.
    Anything else — a ``functools.partial``, a raw string, a mapping — ends the walk, since §6
    sends exactly those shapes to the sidecar rather than through the chain.
    """
    if isinstance(current, functools.partial):
        # §6 lists "``functools.partial`` objects that drop attributes" among the shapes for
        # which "the sidecar is the designated fallback", so the chain ends here rather than
        # reaching through. Descending would also be the one way into the substrate's own
        # ``run_in_executor`` trampoline, which a ``RunnableCallable`` holds in ``afunc`` — not
        # user code at all, and the last thing §4 should be handed as a node body.
        return None
    for member in WRAPPER_MEMBERS:
        value: object = getattr(current, member, None)
        if value is not None and value is not current and _followable(value):
            return value
    return None


def _followable(value: object) -> bool:
    """Whether ``value`` is a wrapper §6's walk descends into."""
    return isinstance(value, (types.FunctionType, types.MethodType, Runnable))


def _read_carrier(
    current: object,
    carriers: list[tuple[object, NodeContract]],
    issues: list[tuple[CarrierRule, str, Mapping[str, Any]]],
) -> None:
    """Record whether ``current`` itself carries a contract (§1's ``__gebra_contract__``)."""
    try:
        carried = read_contract(current)
    except GebraContractError as error:
        issues.append(
            (
                CarrierRule.CARRIER_UNREADABLE,
                (
                    f"{type_identity(current)} carries a __gebra_contract__ that is not a "
                    f"gebra contract ({error}); it declares nothing and the lower "
                    "precedence tiers stand (ANNOTATION-API-SPEC §3)"
                ),
                {"carrier": type_identity(current)},
            )
        )
        return
    if carried is not None:
        carriers.append((current, carried))


def _elected_carrier(
    carriers: Sequence[tuple[object, NodeContract]],
    issues: list[tuple[CarrierRule, str, Mapping[str, Any]]],
) -> NodeContract | None:
    """§6's outermost-carrier rule: the first carrier wins wholesale, and both are named.

    "No per-slot merge, which would reintroduce the in-stack duplicate ambiguity §1 forbids —
    and extraction emits an ``annotation-invalid`` warning naming both carriers. Warning, not
    error: the §3 extraction-stays-total posture applies, and the outermost attachment is the
    latest-applied author intent on the object LangGraph actually received."

    **The warning is scoped to carriers that declare *different* contracts**, and that scoping
    is what keeps it from firing on the shape §6 mandates. ``functools.wraps`` copies the
    wrapped function's ``__dict__`` onto the wrapper, ``__gebra_contract__`` included — so the
    supported chain (``@user_decorator`` over ``@gebra.contract``) has a carrier at *both*
    levels holding one contract, by construction rather than by anyone decorating twice.
    Warning there would put every correctly-wrapped node outside §8's strict-mode bar for
    following §6's own instruction, and §6's rule is about ambiguity — "both a wrapper and the
    function it wraps were **independently** decorated" — of which there is none when the two
    say the same thing. Equality is the frozen model's, i.e. slot by slot.
    """
    if not carriers:
        return None
    kept = carriers[0][1]
    disagreeing = [carrier for carrier, contract in carriers[1:] if contract != kept]
    if disagreeing:
        named = [type_identity(carriers[0][0]), *(type_identity(one) for one in disagreeing)]
        issues.append(
            (
                CarrierRule.MULTIPLE_CARRIERS,
                (
                    f"{len(named)} callables in this node's wrapper chain carry different "
                    f"contracts ({', '.join(named)}); the outermost one wins wholesale and the "
                    "deeper ones are ignored entirely — there is no per-slot merge "
                    "(ANNOTATION-API-SPEC §6)"
                ),
                {"carriers": named, "kept": named[0], "ignored": named[1:]},
            )
        )
    return kept


# ── The tool-carried tier (§1, §3) ───────────────────────────────────────────────────────


def _tool_contribution(
    tool: BaseTool | None,
) -> tuple[NodeContract | None, tuple[CarrierRule, str, Mapping[str, Any]] | None]:
    """A tool's author-written ``args_schema`` as the §3 tier-2 contribution.

    §1: "a LangChain ``BaseTool``'s pydantic ``args_schema`` is read by extraction as a
    declared source (it is author-written schema, not inference) and serialized to JSON
    Schema". Two shapes reach the member on the pinned substrate — a pydantic model class,
    which is asked for its JSON schema, and a JSON Schema object written directly, which is
    already the thing. Anything else declares nothing.

    The value is normalized through :func:`~gebra.annotations.contract.normalize_declared_value`
    — the seam the decorator and the sidecar share — so a tool-carried schema is the same
    *value* a decorator writing the same schema would produce. That is what makes §3's
    "identical values are not a conflict" true across the two tiers rather than nearly true.
    """
    if tool is None:
        return None, None
    try:
        declared = tool.args_schema
    except Exception as error:  # noqa: BLE001 - a foreign property; see below
        return None, _tool_issue(tool, f"reading args_schema raised {type_identity(error)}")
    if declared is None:
        return None, None
    if isinstance(declared, type) and issubclass(declared, BaseModel):
        try:
            schema: object = declared.model_json_schema()
        except Exception as error:  # noqa: BLE001 - see below
            return None, _tool_issue(tool, f"model_json_schema() raised {type_identity(error)}")
    else:
        schema = declared
    try:
        value = normalize_declared_value("args_schema", schema)
    except GebraContractError as error:
        return None, _tool_issue(tool, str(error))
    return NodeContract(args_schema=value), None  # type: ignore[arg-type]


def _tool_issue(tool: BaseTool, why: str) -> tuple[CarrierRule, str, Mapping[str, Any]]:
    """One ``tool-schema-unreadable`` finding.

    The two broad ``except`` clauses above are deliberate and narrow in effect. ``args_schema``
    is a pydantic field on a class the caller wrote, so reading it can run a validator or a
    property, and ``model_json_schema()`` runs whatever ``__get_pydantic_json_schema__`` the
    author supplied — both are the introspection §1 rule 3 admits, and neither is allowed to
    end an extraction that §2 says must be total. What is *not* swallowed is a sentinel: the
    tripwire's schemas raise :class:`BaseException` subclasses that are not ``Exception``,
    so a schema that executed something still fails the run.
    """
    return (
        CarrierRule.TOOL_SCHEMA_UNREADABLE,
        (
            f"the tool {type_identity(tool)} carries an args_schema this build could not read "
            f"as a JSON Schema object ({why}); the tool-carried tier declares nothing and the "
            "sidecar and inference tiers stand (ANNOTATION-API-SPEC §1/§3)"
        ),
        {"tool": type_identity(tool), "why": why},
    )


# ── Records for the envelope ─────────────────────────────────────────────────────────────


def _declared_slots(contributions: Iterable[Contribution]) -> tuple[AnnotationSlot, ...]:
    """The slots the declaration tiers already fill — what §4 is told not to look for.

    §4's engine takes this as its ``declared`` argument and withdraws from those slots
    entirely: "a slot named here gets neither a value nor a warning: a ``contract-inferred``
    record naming a declared slot would make §5's grade lookup call it heuristic-grade".
    """
    return tuple(
        slot for contribution in contributions for slot in contribution.contract.declared_slots()
    )


def _declares_writes(contributions: Iterable[Contribution]) -> bool:
    """Whether a declaration tier said this node writes state — §4's D-011 precondition.

    A non-empty declared ``output`` is the author's own statement that the node writes, which
    is why it is write evidence for the default and why the gap-filling tier must not then
    resolve the node ``pure``. An **empty** ``output`` is the opposite declaration and is not
    counted: an author who wrote ``writes=[]`` said the node writes nothing.
    """
    return any(contribution.contract.output for contribution in contributions)


def _issue_warnings(
    node_id: str, issues: Iterable[ResolutionIssue]
) -> tuple[ExtractionWarning, ...]:
    """The chain's findings as taxonomy records — the code follows the §4 registry row."""
    return tuple(
        ExtractionWarning(
            code=(
                ExtractionWarningCode.ANNOTATION_CONFLICT
                if issue.kind is IssueKind.CONFLICT
                else ExtractionWarningCode.ANNOTATION_INVALID
            ),
            message=issue.message,
            node=node_id,
            slots=issue.slots,
            detail={"scope": "node", **issue.detail},
        )
        for issue in issues
    )


def _invalid(
    node_id: str, rule: CarrierRule, message: str, detail: Mapping[str, Any]
) -> ExtractionWarning:
    """One ``annotation-invalid`` from this layer, carrying §4's "scope; surface(s); rule"."""
    return ExtractionWarning(
        code=ExtractionWarningCode.ANNOTATION_INVALID,
        message=message,
        node=node_id,
        detail={
            "scope": "node",
            "surface": Surface.DECORATOR.value
            if rule is not CarrierRule.TOOL_SCHEMA_UNREADABLE
            else Surface.TOOL.value,
            "rule": rule.value,
            **detail,
        },
    )


def _surviving_findings(
    node_id: str, inference: Inference, resolution: Resolution
) -> tuple[ExtractionWarning, ...]:
    """§4's records, narrowed to the slots the resolution actually emitted.

    A ``contract-inferred`` naming a slot the chain went on to discard would tell §5's lookup
    that a slot which does not exist is heuristic-grade — the same falsehood
    :mod:`gebra.extraction.inference` refused to emit before the chain existed, now avoidable
    only by asking what survived. In the ordinary case nothing is dropped and this is the
    identity, since the inference tier is asked only about open slots.
    """
    inferred = frozenset(
        slot for slot, surface in resolution.surfaces.items() if surface is Surface.INFERENCE
    )
    if inferred == frozenset(inference.contract.declared_slots()):
        return contract_warnings(node_id, inference)
    narrowed = tuple(
        _narrow(finding, inferred)
        for finding in inference.findings
        if inferred.intersection(finding.slots)
    )
    return contract_warnings(node_id, _replacing(inference, narrowed))


def _narrow(finding: InferenceFinding, inferred: frozenset[AnnotationSlot]) -> InferenceFinding:
    """``finding`` restricted to the slots that survived."""
    return InferenceFinding(
        grade=finding.grade,
        slots=tuple(slot for slot in finding.slots if slot in inferred),
        message=finding.message,
        detail=finding.detail,
    )


def _replacing(inference: Inference, findings: tuple[InferenceFinding, ...]) -> Inference:
    """``inference`` with its findings replaced — the seam's only edit to §4's output."""
    return Inference(
        contract=inference.contract,
        source=inference.source,
        keys=inference.keys,
        default=inference.default,
        blockers=inference.blockers,
        findings=findings,
    )
