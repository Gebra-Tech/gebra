"""The ``ir_version`` 1.0/1.1 model surface — IR-SPEC §2–§3.

This module implements the normative pydantic-v2 stubs of IR-SPEC §2.5. The spec fixes
field names, aliases, requiredness, and union discrimination; module layout, helper
structure, and validator organization are this package's to choose.

Two shapes carry the whole surface:

* :class:`WorkflowIR` — the seven top-level fields of IR-SPEC §2.1, holding the node set
  with its contracts (:class:`Node` / :class:`Annotations`), the kinded edge set
  (:data:`Edge`), the state schema Σ (:class:`StateField`), and the graph-level
  :class:`Runtime` block.
* :data:`Edge` — a union discriminated on the existing ``kind`` member, with the default
  ``kind`` injected into tagless edge objects before dispatch (IR-SPEC §2.5 note 1).

**The 1.1 event** (ratified — DEC-28, 2026-08-09; PD-041). The closed ``kind`` vocabulary
gained a fourth token, :class:`DynamicEdge`, for a router whose target set is not statically
known; ``ir_version`` gained ``"1.1"``. Two consequences are written into this module rather
than left to a reader: the surviving three kinds are **untouched** — no requiredness moved,
so no pre-existing document's canonical bytes move — and the version a document carries is a
function of its own content, not of the writer's version (:func:`lowest_ir_version`, IR-SPEC
§8's minimal-stamping policy).

The nine new-in-1.0 slots (IR-SPEC §3, enumerated by PD-003 Appendix A) are the six
optional :class:`Annotations` members ``args_schema``, ``retry_policy``, ``variant``,
``compensation``, ``prompt_digest``, ``config_digest`` and the three optional
:class:`Runtime` sub-slots ``recursion_limit``, ``interrupts``, ``checkpointer``.

**Scope of model validity.** These models decide *shape*: names, aliases, requiredness,
types, and edge discrimination. The cross-field obligations the spec states over that shape
— ``idempotent.key`` appearing in ``input`` (§2.3), ``input``/``output`` being subsets of
``keys(state)`` (§2.3) — and the §6.3 scalar range constraints belong to the property
validators and to canonicalization, neither of which is part of this module. Keeping them
out of model validity is deliberate: a document that violates one has to *load* before
anything can report it.

**Two rules are model validity**, and both are about identity, because identity is the one
thing no later stage can report on its own behalf: the condition-ID registry has no finding
for a malformed or repeated id, and canonicalization would hash the document either way.

1. The node-identity grammar on ``nodes[].id``, where §2.3 writes "``id`` MUST satisfy the
   §5 grammar"; the implementation is :mod:`gebra.ir.identity` and the annotation is
   :data:`~gebra.ir.identity.NodeIdStr`.
2. **Node-id uniqueness across ``nodes[]``** — §2.1's ``nodes`` row, whose MUST is worded
   at the loader ("a duplicate id has no meaning under §5.3's identity rules and loaders
   MUST reject it"; ratified — DEC-22, 2026-08-04, resolving the PD-032 spec defect). It is
   the one rule here that reads more than one member at once, and it is model validity for
   the same reason the grammar is: §6.2's ``nodes[]`` sort is total only *because* ids are
   unique, so on a document that repeats one the canonical form is not canonical
   (:func:`_require_unique_node_ids`).

Reference-role strings (``entry``, ``finish``, ``from``, ``to``, ``path_map`` values,
``interrupts``, ``compensation.hook``) stay unconstrained here: §2.3 states the MUST on the
definition site alone, and whether a reference resolves is the reporting stage's question —
P-01's, for the ones it reads.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Annotated, Any, Final, Literal, TypeAlias

from pydantic import AfterValidator, BeforeValidator, Field

from gebra.ir.base import IRModel
from gebra.ir.identity import NodeIdStr

__all__ = [
    "IR_VERSION",
    "IR_VERSIONS",
    "IR_VERSION_DYNAMIC_EDGES",
    "Annotations",
    "Checkpointer",
    "Compensation",
    "ConditionalEdge",
    "DeterministicSpec",
    "DynamicEdge",
    "DynamicEdgeUnsupportedError",
    "Edge",
    "IdempotentKey",
    "Interrupts",
    "IrVersion",
    "Node",
    "NormalEdge",
    "RecursionLimit",
    "RetryPolicy",
    "Runtime",
    "SendEdge",
    "StateField",
    "StaticEdge",
    "Variant",
    "WorkflowIR",
    "lowest_ir_version",
    "refuse_dynamic_edges",
]

#: Every format version these models implement (IR-SPEC §2.1; 1.0 frozen by DEC-09, 1.1
#: added by DEC-28). The alias and the tuple are kept in step by construction below.
IrVersion: TypeAlias = Literal["1.0", "1.1"]

#: The floor version — what a document carrying only 1.0 constructs is stamped (IR-SPEC §8).
#:
#: Deliberately still spelled ``IR_VERSION``: it is the version this package *writes* for the
#: overwhelming majority of documents, and every caller that meant "the version an ordinary
#: workflow carries" still means exactly this string.
IR_VERSION: Final = "1.0"

#: The lowest minor that admits a ``dynamic`` edge (ratified — DEC-28, 2026-08-09).
IR_VERSION_DYNAMIC_EDGES: Final = "1.1"

#: The versions in ascending order — the same domain as :data:`IrVersion`, as data.
IR_VERSIONS: Final[tuple[IrVersion, ...]] = (IR_VERSION, IR_VERSION_DYNAMIC_EDGES)

#: The edge kind a tagless edge object carries (IR-SPEC §2.4 surface default).
DEFAULT_EDGE_KIND: Final = "normal"

#: The scalar form of ``entry``/``finish`` — one node id, non-empty (IR-SPEC §2.1).
#:
#: The list form carries no cardinality constraint: the empty list is the ratified
#: serialization of "no statically known sentinel wiring" (DEC-18, 2026-08-02). The scalar
#: form carries one, and that asymmetry is the whole point of the constraint — with `[]`
#: meaning the empty set, an admitted ``""`` would be a *second* encoding of it, and the two
#: would digest differently. §2.1 rules it out in terms ("the empty string is NOT a valid
#: encoding of the empty set — a scalar id is non-empty per §5.1").
#:
#: List *members* stay unconstrained, like every other reference-role string in this module
#: (see the module docstring): an empty member is a reference that resolves to no node, which
#: is P-01's `edge-target-undefined` family to report, not a shape error. The ambiguity the
#: constraint above exists to prevent cannot arise there — ``[""]`` is a one-member list, not
#: an empty one.
NodeReference: TypeAlias = Annotated[str, Field(min_length=1)]


class StateField(IRModel):
    """A ``state`` value in object form — the schema Σ of IR-SPEC §2.2.

    A value carrying neither ``reducer`` nor ``optional`` is authored as the bare
    type-name string instead; both surface forms are admitted by
    :attr:`WorkflowIR.state`.
    """

    type: str
    reducer: str | None = None
    """The declared channel-merge function, e.g. ``"operator.add"`` — the P-09 input (§2.2)."""
    optional: bool | None = None
    """``True`` = graph input or default-carrying, i.e. written at START for P-04 (§2.2)."""


class IdempotentKey(IRModel):
    """The object form of ``annotations.idempotent`` (IR-SPEC §2.3).

    Per §2.3 the key names a member of the node's ``input``; that cross-field obligation is
    read by P-06/P-07, not by this model (see the module docstring).
    """

    key: str


class DeterministicSpec(IRModel):
    """The object form of ``annotations.deterministic`` (IR-SPEC §2.3).

    ``temperature`` is the fixture-schema v2.1 addendum (DEC-05 D5).
    """

    seed: int
    temperature: float | None = None


class RetryPolicy(IRModel):
    """``annotations.retry_policy`` — IR-SPEC §3.2.

    A minimal projection of LangGraph's retry policy: ``max_attempts`` counts all attempts
    including the first, and ``retry_on`` entries are opaque exception-name strings. The
    timing members (interval, backoff, jitter) are deliberately not mirrored — they carry
    no verification content.
    """

    max_attempts: int
    retry_on: tuple[str, ...]


class Variant(IRModel):
    """``annotations.variant`` — IR-SPEC §3.3, the P-02 witness form (c) carrier.

    ``key`` names the state key that progresses under ``measure``. What measures are
    admissible, and what discharge requires, are owned by the termination-witness spec;
    IR-SPEC fixes only these field names.
    """

    key: str
    measure: str


class Compensation(IRModel):
    """``annotations.compensation`` — IR-SPEC §3.4: slot now, semantics deferred.

    ``hook`` is a node id under the §5 grammar. Per DEC-05 D7 the slot is declared content
    that validators may surface but must not treat as discharging any P-06/P-07 obligation.
    """

    hook: str


class Annotations(IRModel):
    """A node contract — the ``annotations`` object of IR-SPEC §2.3 plus the §3 slots.

    Every member is optional: the eight retained slots are fixture-proven, and the six
    new-in-1.0 slots (``args_schema`` … ``config_digest``, PD-003 Appendix A rows 1–6) are
    OPTIONAL per DEC-09, so their absence never invalidates a 0.1-era document.
    """

    # Retained, fixture-proven (IR-SPEC §2.3).
    pure: bool | None = None
    effect: tuple[str, ...] | None = None
    idempotent: bool | IdempotentKey | None = None
    deterministic: bool | DeterministicSpec | None = None
    input: tuple[str, ...] | None = None
    output: tuple[str, ...] | None = None
    source: str | None = None
    map: str | None = None
    # New in 1.0 (IR-SPEC §3; DEC-09).
    args_schema: dict[str, Any] | None = None
    """A JSON Schema (draft 2020-12) object describing the node/tool argument shape (§3.1).

    Held as a plain JSON object: 1.0 imposes no schema algebra on its contents.
    """
    retry_policy: RetryPolicy | None = None
    variant: Variant | None = None
    compensation: Compensation | None = None
    prompt_digest: str | None = None
    """``"sha256:<hex>"`` over the exact UTF-8 bytes of the node's prompt template (§3.6)."""
    config_digest: str | None = None
    """``"sha256:<hex>"`` over the node's generation/model config object (§3.6)."""


class Node(IRModel):
    """A node: identity plus contract (IR-SPEC §2.3).

    ``id`` is the escaped path identity of IR-SPEC §5, checked against that grammar as the
    spec's MUST requires: a malformed escape, an empty or reserved segment at any nesting
    level, or a synthetic token outside the closed 1.0 vocabulary is a validation error here
    (:mod:`gebra.ir.identity`).
    """

    id: NodeIdStr
    annotations: Annotations | None = None


class NormalEdge(IRModel):
    """An unconditional edge (IR-SPEC §2.4). ``to`` is REQUIRED for this kind."""

    kind: Literal["normal"]
    from_: str = Field(alias="from")
    """``from`` is a Python keyword; canonical output serializes by alias (§2.5 note 2)."""
    to: str
    """A node id, or the literal ``"END"`` (§4.2)."""
    condition: str | None = None
    """Admitted for fixture fidelity; inert on this kind (§2.4)."""


class ConditionalEdge(IRModel):
    """A router edge (IR-SPEC §2.4): routes via ``path_map``, and carries no ``to``.

    Under the §2.4 label-expansion semantics each ``path_map`` label denotes one logical
    directed edge ``from → path_map[label]``, which the spec has consumers expand before any
    graph algorithm runs. This model stores the map as authored.
    """

    kind: Literal["conditional"]
    from_: str = Field(alias="from")
    condition: str | None = None
    """The declared guard/router expression — declared IR content, never evaluated (§2.4)."""
    path_map: dict[str, str]
    """Label → node id, or the literal ``"END"``."""


class SendEdge(IRModel):
    """A dynamic fan-out *template* (IR-SPEC §2.4). ``to`` is REQUIRED for this kind.

    Per §2.4 the IR is deliberately silent on the fan-out's actual N, which is a runtime
    quantity: what this edge carries is the branch template.
    """

    kind: Literal["send"]
    from_: str = Field(alias="from")
    to: str
    """The branch-template target."""
    condition: str | None = None
    """Admitted for fixture fidelity; inert on this kind (§2.4)."""


class DynamicEdge(IRModel):
    """A router whose target set is not statically known (IR-SPEC §2.4; ir 1.1).

    Ratified — DEC-28, 2026-08-09 (PD-041), resolving the disposition DEC-18 D4 deferred. The
    kind "carries neither ``to`` nor ``path_map`` — it declares only that the router's target
    set is not statically known (dynamic dispatch, INTROSPECTION-SPEC §6)": the bare-``Send``
    map-reduce whose targets are computed inside the callable, and the hintless
    ``path_map``-less router.

    **What the absent members mean, and why they are absent rather than empty.** DEC-18 D4
    ruled out both ways of saying this on a ``conditional`` edge, in terms: ``path_map: {}``
    would silently assert "the target set is complete and empty" — §6 makes ``path_map``
    *presence* the discriminator deciding which mode the router-coverage property runs in —
    and omitting the edge would delete the router from hash scope, turning a warning into a
    P-01 FATAL false positive. This kind has no ``path_map`` field at all, so with
    ``extra="forbid"`` on the frozen base (A6 PC-1) the ambiguous "empty-and-present" form is
    a validation error here rather than a silent no-op, on this kind as on the other three.

    A document containing one of these is ``ir_version`` ``"1.1"`` (:func:`lowest_ir_version`).
    """

    kind: Literal["dynamic"]
    from_: str = Field(alias="from")
    condition: str | None = None
    """The declared router expression — the branch name, when the declaration had one (§2.4)."""


def _inject_default_edge_kind(value: Any) -> Any:
    """Tag a tagless edge object with the default kind (IR-SPEC §2.5 note 1).

    The surface admits edges with ``kind`` omitted (default ``normal``) while a
    discriminated union needs the tag present, so the tag is injected before dispatch.
    Canonical serialization omit-normalizes the default back out, so the two rules compose
    to the identity on fixture-proven surface forms.

    The trigger is *absence of the member*, exactly as §2.5 note 1 words it — not a falsy
    or ``null`` value. §2.4 closes the member's domain to
    ``normal|conditional|send|dynamic``, so a payload writing ``kind: null`` is malformed and
    stays an error rather than being read as the default.

    Anything that is not a ``dict`` — an already-built edge model, a stray scalar, a
    foreign mapping — is passed through untouched so that pydantic reports its own error.
    The narrow ``dict`` test is deliberate on two counts: strict mode admits nothing wider
    for a model field anyway, and reading members off an arbitrary mapping would mean
    calling that object's own code, which this package does not do (WA-07).
    """
    if isinstance(value, dict) and "kind" not in value:
        return {**value, "kind": DEFAULT_EDGE_KIND}
    return value


#: A kinded edge, discriminated on ``kind`` (IR-SPEC §2.4/§2.5). The before-validator rides
#: on the type itself rather than on :attr:`WorkflowIR.edges`, so validating an edge
#: directly (e.g. through a ``TypeAdapter``) admits the tagless surface form too.
Edge: TypeAlias = Annotated[
    NormalEdge | ConditionalEdge | SendEdge | DynamicEdge,
    Field(discriminator="kind"),
    BeforeValidator(_inject_default_edge_kind),
]


def lowest_ir_version(edges: Iterable[Edge]) -> IrVersion:
    """The lowest ``ir_version`` sufficient for an edge set (IR-SPEC §8; ratified DEC-28).

    §8's stamping policy, general rather than per-construct: "emitters stamp the LOWEST minor
    sufficient for the document's constructs — ``"1.1"`` iff a ``dynamic`` edge is present,
    ``"1.0"`` otherwise". Three properties come with that choice, and they are why the policy
    is a function of content rather than of the writing build's version:

    * **Deterministic.** Two conforming emitters given equal content stamp equal versions.
    * **Zero golden churn.** Nothing that carried ``"1.0"`` starts carrying ``"1.1"``, so no
      committed golden and no vendored fixture moves (the byte-diff EX-03 owes is the check).
    * **Honest.** A document using no 1.1 construct does not advertise a feature it makes no
      use of, so a 1.0-only consumer is never turned away from a document it can read.

    ``edges`` is consumed once, so a generator is fine.
    """
    for edge in edges:
        if isinstance(edge, DynamicEdge):
            return IR_VERSION_DYNAMIC_EDGES
    return IR_VERSION


class DynamicEdgeUnsupportedError(NotImplementedError):
    """A 1.0-vocabulary consumer was handed a document carrying a ``dynamic`` edge.

    ``NotImplementedError`` by inheritance because that is exactly the fact: the construct is
    ratified and emitted, and *this consumer* has no semantics for it yet. Anything that
    catches broadly — ``gebra verify`` turns any escaping exception into a §2.4 tool error —
    therefore reports "no verdict was reached" rather than a verdict, which is the only honest
    outcome available before the semantics land.
    """


#: An edge whose target set is statically known — the three ir 1.0 kinds.
#:
#: What a consumer written against the 1.0 ``kind`` vocabulary handles, named so that such a
#: consumer can *say* so in its signature rather than discovering the fourth kind at runtime.
StaticEdge: TypeAlias = NormalEdge | ConditionalEdge | SendEdge


def refuse_dynamic_edges(edges: Iterable[Edge], *, consumer: str) -> tuple[StaticEdge, ...]:
    """Decline a ``dynamic``-bearing edge set on behalf of a consumer with no 1.1 semantics.

    One decline, one wording, every consumer that needs it — the shared validator graph model,
    the topology-diff graph, and (SD-12) the snapshot recorder and the freshness check, each of
    which declines on both the document handed in and the one the store already holds. The
    reason is the same in all of them, so a reader who meets it in one place recognizes it in
    the next; the call sites are deliberately not counted here, because the count is the part
    that goes stale.

    **Why a decline rather than a default.** A ``dynamic`` edge contributes no member to the
    graph $G$ (PROPERTY-CATALOG-SPEC §0.3, ratified — DEC-28), and *silently* dropping it is
    the one thing that must not happen: P-01's condition (i) would then report
    ``node-unreachable-from-start`` for every node reachable only through the router — the
    false FATAL DEC-28 clause 1 forbids in terms — and the topology diff would report "no
    change" between two documents whose ``graph_version``s differ. Both consumers' correct
    behaviour is ruled and neither is implemented here: DEC-28 assigns the validator skip
    branches, P-01's over-approximation and the two optional diagnostics to a paired validator
    regression card, and the diff's representation of a headless edge is unruled altogether.
    So both decline until then.

    Args:
        edges: The document's edge set.
        consumer: What is declining, named the way its own docs name it — it goes into the
            message a caller reads.

    Returns:
        The same edges, typed as :data:`StaticEdge` — so the caller's own walk is checked
        against the three kinds it handles rather than carrying an unreachable fourth branch.

    Raises:
        DynamicEdgeUnsupportedError: if any edge is a ``dynamic`` edge.
    """
    static: list[StaticEdge] = []
    for index, edge in enumerate(edges):
        if not isinstance(edge, DynamicEdge):
            static.append(edge)
            continue
        raise DynamicEdgeUnsupportedError(
            f"{consumer} has no semantics for the `dynamic` edge kind, and edges[{index}] "
            f"(from {edge.from_!r}) is one. The kind is ratified (ir 1.1 — DEC-28, "
            "2026-08-09) and `gebra.extract()` emits it for a router whose target set is not "
            "statically known; its consumer-side semantics land with the paired validator "
            "regression card. Declining is deliberate: a `dynamic` edge contributes no member "
            "to the graph, so reading this document under 1.0 rules would answer with a "
            "verdict or a diff that is wrong rather than absent."
        )
    return tuple(static)


class RecursionLimit(IRModel):
    """``runtime.recursion_limit`` — IR-SPEC §3.5, the P-02 witness form (b) carrier.

    The witness is this structured object, never a bare number and never prose alone;
    ``justification`` is REQUIRED so the declared limit is auditable (§3.5).
    """

    value: int
    justification: str


class Interrupts(IRModel):
    """``runtime.interrupts`` — IR-SPEC §3.7, a P-13 carrier.

    Static interrupt-gate placement. Per §3.7 these are read off a compiled object and are
    absent — never guessed — at builder level, and an emitter omits an empty
    ``before``/``after`` rather than serializing it, canonicalization mapping an empty array
    onto absence. Both surface forms therefore load here.
    """

    before: tuple[str, ...] | None = None
    after: tuple[str, ...] | None = None


class Checkpointer(IRModel):
    """``runtime.checkpointer`` — IR-SPEC §3.7, a P-13 carrier.

    ``present`` is REQUIRED inside the object and carries no default, so
    omit-normalization can never strip it: ``{present: false}`` is representable and
    distinct from the slot's absence.
    """

    present: bool


class Runtime(IRModel):
    """Graph-level declared/extracted configuration (IR-SPEC §2.1, §3.5, §3.7).

    All three sub-slots are OPTIONAL and all three are in ``graph_version`` hash scope.
    """

    recursion_limit: RecursionLimit | None = None
    interrupts: Interrupts | None = None
    checkpointer: Checkpointer | None = None


def _require_unique_node_ids(nodes: tuple[Node, ...]) -> tuple[Node, ...]:
    """Refuse a ``nodes`` array that declares one id twice (IR-SPEC §2.1; ratified DEC-22).

    The rule is worded at the loader — "**Node ``id``s MUST be unique within a document**
    … a duplicate id has no meaning under §5.3's identity rules and loaders MUST reject
    it" — so this is where it is enforced, on the array it constrains. Everything in the
    package downstream of loading keys on the id: §6.2 sorts ``nodes[]`` by it and calls
    the order total, §4.1's model view has one vertex per id, `gebra.diff` anchors every
    delta on it, and every P-01…P-13 consumer looks a node up by it.

    Until DEC-22 the uniqueness was an unstated *premise* of §6.2's totality rather than a
    rule, and the gap was reachable: two authorings of one node set tie on the sort key,
    the tie is broken by authored order, and authored order is exactly what §6.4 excludes
    from the digest — so one node set had two ``graph_version`` values (PD-032, reproduced
    at ratification). With the constraint here that document no longer loads, and the
    §6.2 sort is total by construction rather than by assumption.

    Both the dict key and the message go through ``str``'s own methods called **unbound**, so
    no ``__hash__``/``__eq__``/``__repr__`` an exotic ``str`` subclass defines is ever run
    here (WA-07, the :func:`~gebra.ir.identity.synthetic_segment` precedent). Strict mode
    already coerces ``Node.id`` to an exact ``str`` on every validated path, so this is
    belt-and-braces for the one residual reach — a ``Node`` whose ``id`` was replaced through
    ``model_copy``, which skips validation — and it costs one call per node.

    Args:
        nodes: The validated ``nodes`` array, in authored order.

    Returns:
        ``nodes`` unchanged — this validator refuses, and never rewrites. Deduplicating
        would be the one thing worse than accepting: it silently discards a declared node
        contract and changes the digest of a document the author wrote.

    Raises:
        ValueError: naming the repeated id and both positions that declare it. A
            ``ValueError`` because that is what pydantic renders as an ordinary
            ``ValidationError`` at ``loc = ("nodes",)``, which is where a consumer's own
            error handling already looks.
    """
    first_seen: dict[str, int] = {}
    for index, node in enumerate(nodes):
        node_id = str.__str__(node.id)
        earlier = first_seen.setdefault(node_id, index)
        if earlier != index:
            raise ValueError(
                f"node id {str.__repr__(node_id)} is declared twice, at nodes[{earlier}] and "
                f"nodes[{index}]: IR-SPEC §2.1 makes node ids unique within a document "
                "(ratified — DEC-22, 2026-08-04), and one id names at most one node "
                "(§5.3). A repeated id ties §6.2's `nodes[]` sort key, so authored order "
                "would reach the digest that §6.4 excludes it from and one node set would "
                "have two canonical forms (PD-032). Give the second node its own id"
            )
    return nodes


class WorkflowIR(IRModel):
    """A workflow definition in ``ir_version`` 1.0 — the seven fields of IR-SPEC §2.1.

    START and END are implicit sentinels: ``entry`` names the node(s) wired from START and
    ``finish`` the node(s) wired to END, each a scalar node id when the wired set is a
    singleton and a list otherwise (§4.2, §6.3).

    **The empty list is a value, not a gap** (ratified — DEC-18, 2026-08-02). On ``entry`` it
    means "no statically known sentinel wiring" — deliberately covering both the genuinely
    unwired builder and the dynamically-dispatched entry, with the distinguishing warning
    riding the provenance envelope, outside hash scope. On ``finish`` it means there is no
    (m2) member: END reachability, if any, is declared through (m3) ``path_map`` labels
    valued ``"END"``, which is what an ordinary router-terminated workflow looks like. Both
    stay REQUIRED, so the empty form is written explicitly and never confused with absence.

    The five REQUIRED members carry no model default (§2.5 note 6), so omit-normalization
    can never strip them — a workflow with no edges carries an explicitly authored
    ``edges`` of length zero.

    **Node ids are unique within a document** — §2.1's MUST, ratified DEC-22 — so a document
    declaring one ``id`` twice is a validation error naming the repeated id and both positions
    that declare it, not a document with two nodes of one identity. See the ``nodes`` field
    below for why the check lives there and what it deliberately does not constrain.
    """

    ir_version: IrVersion
    """``"1.0"``, or ``"1.1"`` for a document carrying a ``dynamic`` edge (§8; DEC-28).

    The member is the document's own declaration and is validated as *shape* only: this model
    does not require the stamp to be the lowest sufficient one, because a document is authored
    as well as emitted and §8's minimal-stamping policy binds **emitters**. What gebra writes
    goes through :func:`lowest_ir_version`; what gebra reads is admitted at either version.
    """

    entry: NodeReference | tuple[str, ...]
    finish: NodeReference | tuple[str, ...]
    state: dict[str, str | StateField] | None = None
    """State key → bare type-name string, or the object form (§2.2)."""
    nodes: Annotated[
        tuple[Node, ...], Field(min_length=1), AfterValidator(_require_unique_node_ids)
    ]
    """The node set $N$ (§2.1), non-empty and with **unique** ids (DEC-22).

    The uniqueness MUST is checked here rather than on :attr:`Node.id`, because it is a
    property of the array and no single element can violate it; the error therefore lands at
    ``loc = ("nodes",)`` and names both positions (:func:`_require_unique_node_ids`).

    It is an ``AfterValidator`` and not a JSON-Schema ``uniqueItems`` constraint: the rule is
    uniqueness of the ``id`` member, not of whole node objects — two nodes sharing an id and
    differing in their annotations are distinct items — and keeping it out of the generated
    schema leaves ``model_json_schema()`` agreeing with the vendored ``schema.yaml``, which
    IR-05's lockstep check compares against.
    """

    edges: tuple[Edge, ...]
    runtime: Runtime | None = None
