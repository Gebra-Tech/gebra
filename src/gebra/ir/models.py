"""The ``ir_version`` 1.0/1.1/1.2 model surface — IR-SPEC §2–§3.

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

**The 1.2 event** (ratified — DEC-39, 2026-11-03, part A; DEC-40, 2026-11-10, part B).
``ir_version`` gained ``"1.2"`` and, with it, OPTIONAL omit-normalized members only — no edge
kind, no requiredness moved, no §6 rule that reaches an existing document:

* part A — :attr:`Node.subgraph`, the child :class:`Subgraph` a node mounts, carried as a
  document of its own *level* (the six top-level members other than ``ir_version``), and
  :attr:`Annotations.projection`, P-10's declared :class:`Projection`;
* part B — :attr:`Node.barriers` (the ``waiting_edges`` all-of barrier on its target node; the
  edges into it stay the ordinary ``normal`` ones), :attr:`ConditionalEdge.codomain` (a
  router's declared return-label set where it differs from ``keys(path_map)``),
  :attr:`StateField.managed` (a key the substrate computes per task), and
  :attr:`Annotations.join_key` (P-11's declared key set) — plus the three §5.2 tokens
  ``assign``, ``each`` and ``leaf``, a vocabulary rather than members
  (:data:`~gebra.ir.identity.SYNTHETIC_KINDS`).

The minor a document needs is read over the **whole document**, every level included
(:func:`lowest_ir_version`), and the format-migration down-projection beside it removes what
the 1.2 event's extraction-populated constructs added (:func:`down_project`).

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

**Beyond shape, the rules below are model validity**, and each is here for the same reason:
the spec words it at the loader ("loaders MUST reject …"), and no later stage is specified to
report it on its own behalf — the condition-ID registry has no finding for any of them, and
canonicalization would hash the document either way. Each refuses and never rewrites — the
DEC-22 pattern.

1. The node-identity grammar on ``nodes[].id``, where §2.3 writes "``id`` MUST satisfy the
   §5 grammar"; the implementation is :mod:`gebra.ir.identity` and the annotation is
   :data:`~gebra.ir.identity.NodeIdStr`.
2. **Node-id uniqueness** — §2.1's ``nodes`` row, whose MUST is worded at the loader ("a
   duplicate id has no meaning under §5.3's identity rules and loaders MUST reject it";
   ratified — DEC-22, 2026-08-04, resolving the PD-032 spec defect), read from 1.2 **over
   every level of the document** (DEC-39 §3.2). It is model validity for the same reason the
   grammar is: §6.2's ``nodes[]`` sort is total only *because* ids are unique, so on a
   document that repeats one the canonical form is not canonical
   (:func:`_require_unique_node_ids`, :func:`_require_unique_node_ids_over_every_level`).
3. **The ``ir_version`` stamp floor** — §2.5 note 7, carried at §2.1, §2.4 and §8: the stamp
   MUST be at least the lowest minor the document's constructs require, and "loaders MUST
   reject a document stamped below it, and never re-stamp it" (ratified — DEC-34,
   2026-09-06, resolving the PD-055 spec defect; read over the whole document from 1.2 —
   DEC-39 §3.3, DEC-40 §3.6). Over-stamping stays admitted: §8's minimal-stamping MUST binds
   emitters, not documents (:func:`_require_sufficient_ir_version`).
4. **The carrier prefix** (1.2 — DEC-39 §3.2): every id in a carrier's ``subgraph.nodes[]``
   carries the carrier's id as a proper segment-prefix (:func:`_require_carrier_prefix`).
5. **The four ``barriers`` MUSTs** (1.2 — DEC-40 §3.3): every group has two or more members,
   members are distinct within a group, groups are distinct as sets
   (:func:`_require_valid_barrier_groups`), and every member names a node of the level that is
   the source of a ``normal`` edge into the node (:func:`_require_barrier_wiring`).
6. **The 1.2 member MUSTs of part B** (DEC-40 §3.1, §3.2, §3.4): a ``codomain`` repeats no
   member, a ``join_key`` is no empty string and no empty, repeating or empty-membered list,
   and a ``managed`` state entry carries neither ``optional`` nor ``reducer``.

Reference-role strings (``entry``, ``finish``, ``from``, ``to``, ``path_map`` values,
``interrupts``, ``compensation.hook``) stay unconstrained here: §2.3 states the MUST on the
definition site alone, and whether a reference resolves is the reporting stage's question —
P-01's, for the ones it reads. A ``barriers`` member is the one reference the spec words at the
loader (DEC-40 §3.3's fourth MUST, its node-existence half recorded in §3.11), so it is the one
reference this module resolves.

**WA-07 discipline in the 1.2 reads.** A validated model holds exact values (strict mode), but
``model_copy(update=...)`` skips validation and can plant a ``str``, ``tuple`` or ``dict``
subclass — or any object — inside a model that a later document is built from, and pydantic does
not re-validate a model instance it is handed, an instance of a subclass of a model class
included. What the construct scan behind :func:`lowest_ir_version` and the stamp floor, the 1.2
validity rules and :func:`down_project` do with such a model, as measured:

* every string they hash, compare, format or hand on is first copied to an exact ``str`` through
  ``str.__str__`` called unbound (messages use ``str.__repr__`` unbound and name no type);
* a model's array and map members are read through ``tuple``'s and ``dict``'s own methods called
  unbound (:func:`_members`, ``tuple.__len__``, ``dict.__iter__``, ``dict.items``,
  ``dict.values``); a member that is not the container its field declares is never iterated —
  the scan refuses it with ``TypeError``, and the projection drops a member it removes unread;
* a class is tested with ``issubclass(type(x), C)``, which reads the object's type and nothing of
  the object, and keeps subclasses: an instance of a subclass of a model class is read as its
  base kind, as pydantic admitted it — never skipped; and an edge or Σ value whose type is none
  of the models its field declares — pydantic admits an object whose ``__class__`` claims a
  model class — is refused by the scan, never read as no construct;
* model-typed members (a ``nodes`` element, ``annotations``, ``subgraph``) are read by attribute
  access, the surface INTROSPECTION-SPEC §1 rule 3 permits and the one ``node.id`` was always
  read through; their classes are not tested in the scan or the validity rules;
* :func:`down_project` calls no method of an instance it keeps: it rebuilds every kept node, edge
  and Σ value, the stamp and the wiring from exact copies through the model constructors, after a
  class test of each (a member that is not the model its field declares is refused with
  ``TypeError``), and hands on ``annotations`` and ``runtime`` as the class-tested instances they
  are — each read once, and not re-validated (pydantic does not re-validate an instance), so a
  member planted inside one reaches the result as it was; the constructor then validates the
  result's own members.

The rest of the package's reads of such a model are their own modules' — canonicalization reads
a model through its members' own methods.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Iterable, Iterator
from typing import Annotated, Any, Final, Literal, TypeAlias, TypeVar, cast

from pydantic import AfterValidator, BeforeValidator, Field, ValidationInfo

from gebra.ir.base import IRModel
from gebra.ir.identity import NodeIdStr

_T = TypeVar("_T")

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
    "Projection",
    "RecursionLimit",
    "RetryPolicy",
    "Runtime",
    "SendEdge",
    "StateField",
    "StaticEdge",
    "Subgraph",
    "Variant",
    "WorkflowIR",
    "down_project",
    "lowest_ir_version",
    "refuse_dynamic_edges",
]

#: Every format version these models implement (IR-SPEC §2.1; 1.0 frozen by DEC-09, 1.1
#: added by DEC-28, 1.2 by DEC-39 and DEC-40). The alias and the tuple are kept in step by
#: construction below.
IrVersion: TypeAlias = Literal["1.0", "1.1", "1.2"]

#: The floor version — what a document carrying only 1.0 constructs is stamped (IR-SPEC §8).
#:
#: Deliberately still spelled ``IR_VERSION``: it is the version this package *writes* for the
#: overwhelming majority of documents, and every caller that meant "the version an ordinary
#: workflow carries" still means exactly this string.
IR_VERSION: Final = "1.0"

#: The lowest minor that admits a ``dynamic`` edge (ratified — DEC-28, 2026-08-09).
IR_VERSION_DYNAMIC_EDGES: Final = "1.1"

#: The lowest minor that admits a construct of the 1.2 event (ratified — DEC-39, 2026-11-03;
#: DEC-40, 2026-11-10). Private on purpose: the event introduces several constructs rather than
#: one, so there is no single construct to name a public constant after, and the frozen export
#: set (IR-MODELS-FREEZE §1) gains only what the two records name. ``IR_VERSIONS[-1]`` reads it.
_IR_VERSION_1_2: Final = "1.2"

#: The versions in ascending order — the same domain as :data:`IrVersion`, as data.
IR_VERSIONS: Final[tuple[IrVersion, ...]] = (
    IR_VERSION,
    IR_VERSION_DYNAMIC_EDGES,
    _IR_VERSION_1_2,
)

#: The edge kind a tagless edge object carries (IR-SPEC §2.4 surface default).
DEFAULT_EDGE_KIND: Final = "normal"

#: The §5.2 tokens the 1.2 event added (DEC-40 §3.5). A node id carrying a synthetic segment
#: of one of these kinds requires ``"1.2"``; the 1.0/1.1 grammar refused them.
_TOKENS_1_2: Final = ("assign", "each", "leaf")

#: The two of them that name a *frame*, whose children the format-migration down-projection
#: removes (DEC-40 §3.5's reverse mapping); ``leaf`` names nothing beneath it.
_FRAME_TOKENS_1_2: Final = ("assign", "each")

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


def _exact(value: str) -> str:
    """An exact ``str`` copy of ``value``, through ``str``'s own method called unbound.

    The one primitive every validator here uses before it hashes, compares or formats a string
    that could have arrived through ``model_copy`` (see the module docstring, WA-07).
    """
    return str.__str__(value)


def _quoted(value: str) -> str:
    """``repr`` of an exact copy — for messages, with no object-defined method run."""
    return str.__repr__(_exact(value))


def _members(values: tuple[_T, ...]) -> Iterator[_T]:
    """Iterate a model's array member through ``tuple``'s own iterator, called unbound.

    A member planted past validation as a ``tuple`` subclass is iterated without its own
    ``__iter__``; one that is not a ``tuple`` at all is refused with ``TypeError`` (WA-07; see
    the module docstring).
    """
    return tuple.__iter__(values)


class _NotAModelError(TypeError):
    """An edge or Σ value whose type is none of the models its field declares (the scan's refusal).

    Pydantic admits an object whose ``__class__`` claims a model class (``type.__instancecheck__``
    reads ``__class__`` when the type test misses), and the scan's class tests read only the
    type, so such a member is refused rather than read as no construct. A ``TypeError`` from
    :func:`lowest_ir_version`; the stamp-floor validator re-raises it as a ``ValueError``, which
    pydantic reports as an ordinary ``ValidationError`` at ``loc = ("edges",)``.
    """


def _admit_only_true(value: Any) -> Any:
    """Refuse every ``managed`` value but the boolean ``true`` (IR-SPEC §2.2; DEC-40 §3.4).

    The member "admits only ``true``" (``Literal[True]`` in the stub, ``enum: [true]`` in the
    fixture schema), but pydantic matches a ``Literal`` by equality even in strict mode, and
    ``1 == True`` in Python — so ``1`` and ``1.0`` would load and canonicalize as ``true``, a
    second surface form JSON Schema's ``enum: [true]`` itself refuses. An exact ``bool`` type
    test closes it before the literal check; ``None`` (absence) passes through.
    """
    if value is None or type(value) is bool:
        return value
    raise ValueError(
        "`managed` admits only the boolean true, and this value is not a boolean: the flag has "
        "no other form, and absence is its only alternative (IR-SPEC §2.2; ratified — DEC-40, "
        "2026-11-10)"
    )


def _require_managed_alone(
    managed: Literal[True] | None, info: ValidationInfo
) -> Literal[True] | None:
    """Refuse a ``managed`` entry that also carries ``optional`` or ``reducer`` (DEC-40 §3.4).

    IR-SPEC §2.2: "a managed entry carries neither ``optional`` nor ``reducer``: loaders MUST
    reject an entry carrying ``managed`` beside either (the DEC-22 pattern)". The substrate
    forbids a managed key in a distinct input/output schema and ignores a node update naming
    it, so neither member could be true of one; a carried pair would be a second encoding no
    conforming emitter writes. ``managed`` is declared after both, so ``info.data`` holds them.
    """
    if managed is None:
        return managed
    present = [name for name in ("optional", "reducer") if info.data.get(name) is not None]
    if present:
        raise ValueError(
            "a managed state entry carries neither `optional` nor `reducer`, and this one "
            f"carries {' and '.join(f'`{name}`' for name in present)}: the substrate computes a "
            "managed key for each task, no caller supplies it and no node update writes it, so "
            "loaders MUST reject the pair (IR-SPEC §2.2; ratified — DEC-40, 2026-11-10). "
            "Drop the other member, or drop `managed` if the key is an ordinary channel"
        )
    return managed


class StateField(IRModel):
    """A ``state`` value in object form — the schema Σ of IR-SPEC §2.2.

    A value carrying none of ``reducer``, ``optional`` and ``managed`` is authored as the bare
    type-name string instead; both surface forms are admitted by :attr:`WorkflowIR.state`.
    """

    type: str
    reducer: str | None = None
    """The declared channel-merge function, e.g. ``"operator.add"`` — the P-09 input (§2.2)."""
    optional: bool | None = None
    """``True`` = graph input or default-carrying, i.e. written at START for P-04 (§2.2)."""
    managed: Annotated[
        Literal[True] | None,
        BeforeValidator(_admit_only_true),
        AfterValidator(_require_managed_alone),
    ] = None
    """``True`` = a key the substrate computes for each task (``ir_version`` ≥ 1.2; DEC-40).

    ``RemainingSteps``/``IsLastStep``-style managed values: ``type`` is the manager's declared
    value type, the key is a member of P-04's START-written set, and it is never a termination
    witness by itself (IR-SPEC §2.2). Only ``True`` is admitted — a carried ``False`` would be a
    second, digest-bearing encoding of "not managed", and an ``int`` equal to it is no boolean
    (:func:`_admit_only_true`) — and the entry carries neither ``optional`` nor ``reducer`` (a
    loader MUST, enforced here).
    """


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


class Projection(IRModel):
    """``annotations.projection`` — IR-SPEC §3.9 (``ir_version`` ≥ 1.2; ratified — DEC-39).

    P-10's declared parent↔child state projection on a node that mounts a compiled graph:
    ``in`` maps keys of the carrier's level Σ to keys of the child's Σ, ``out`` maps the
    child's keys back. Both members are REQUIRED and carry no default (§2.5 note 8), so
    omit-normalization never strips them — an empty map is written ``{}``, "nothing crosses in
    this direction". Keys and values are state keys in the NFC identifier role (§6.3), checked
    at canonicalization, not here. The slot is declared-only and carried, not read, until P-10's
    catalog section lands; a hand-authored document MAY carry it on any node (§3.9), so no
    carrier condition is model validity — that rule binds the annotation surfaces.
    """

    in_: dict[str, str] = Field(alias="in")
    """``in`` is a Python keyword; the field is ``in_`` and serializes by alias (§2.5 note 8)."""
    out: dict[str, str]


def _require_valid_join_key(
    join_key: str | tuple[str, ...] | None,
) -> str | tuple[str, ...] | None:
    """Refuse the ``join_key`` forms IR-SPEC §3.10 words at the loader (DEC-40 §3.2).

    "Loaders MUST reject a ``join_key`` that is an empty string, or a list that is empty or
    carries an empty, non-string or repeated member" — the forms both annotation surfaces
    already refuse and the fixture schema's ``minLength``/``minItems``/``uniqueItems`` encode.
    A non-string member is strict mode's to refuse before this runs. Refused, never repaired:
    the list form is sorted and never deduplicated (§6.2), so a repeated member would otherwise
    reach the §6.3 scalar collapse with two canonical forms for one key set.
    """
    if join_key is None:
        return join_key
    if issubclass(type(join_key), str):
        if _exact(cast(str, join_key)) == "":
            raise ValueError(
                "`join_key` is the empty string, which declares no key: IR-SPEC §3.10 admits "
                "a non-empty string or a non-empty list of distinct non-empty strings, and "
                "loaders MUST reject the empty forms (ratified — DEC-40, 2026-11-10). Omit "
                "the member to declare no join key"
            )
        return join_key
    keys = cast(tuple[str, ...], join_key)
    if tuple.__len__(keys) == 0:
        raise ValueError(
            "`join_key` is the empty list, which declares no key: IR-SPEC §3.10 admits a "
            "non-empty string or a non-empty list of distinct non-empty strings, and loaders "
            "MUST reject the empty forms (ratified — DEC-40, 2026-11-10). Omit the member to "
            "declare no join key"
        )
    seen: dict[str, int] = {}
    for index, member in enumerate(_members(keys)):
        key = _exact(member)
        if key == "":
            raise ValueError(
                f"`join_key[{index}]` is the empty string: a declared key is a non-empty data "
                "key, and loaders MUST reject an empty member (IR-SPEC §3.10; ratified — "
                "DEC-40, 2026-11-10)"
            )
        earlier = seen.setdefault(key, index)
        if earlier != index:
            raise ValueError(
                f"`join_key` repeats the key {_quoted(key)}, at [{earlier}] and [{index}]: the "
                "list form is a set of distinct keys, sorted and never deduplicated, so "
                "loaders MUST reject a repeated member (IR-SPEC §3.10, §6.2; ratified — "
                "DEC-40, 2026-11-10). Declare each key once"
            )
    return join_key


class Annotations(IRModel):
    """A node contract — the ``annotations`` object of IR-SPEC §2.3 plus the §3 slots.

    Every member is optional: the eight retained slots are fixture-proven, the six
    new-in-1.0 slots (``args_schema`` … ``config_digest``, PD-003 Appendix A rows 1–6) are
    OPTIONAL per DEC-09, and the two 1.2 slots (``projection`` — DEC-39; ``join_key`` —
    DEC-40) are OPTIONAL and omit-normalized, so their absence never invalidates an earlier
    document.
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
    # New in 1.2 (IR-SPEC §3.9, §3.10; DEC-39, DEC-40).
    projection: Projection | None = None
    """P-10's declared parent↔child state projection (§3.9; ``ir_version`` ≥ 1.2 — DEC-39)."""
    join_key: Annotated[str | tuple[str, ...] | None, AfterValidator(_require_valid_join_key)] = (
        None
    )
    """P-11's declared join key set (§3.10; ``ir_version`` ≥ 1.2 — DEC-40).

    A non-empty string, or a non-empty list of distinct non-empty strings, each a data key in
    the NFC identifier role; canonical as a scalar iff one key (§6.3). Any node MAY carry it.
    """


def _require_carrier_prefix(subgraph: Subgraph | None, info: ValidationInfo) -> Subgraph | None:
    """Refuse a child id that does not carry its carrier's id as a proper segment-prefix.

    IR-SPEC §2.1/§3.8 (ratified — DEC-39, 2026-11-03, §3.2): "every id in a carrier's
    ``subgraph.nodes[]`` MUST carry the carrier's id as a proper segment-prefix over the §5.1
    delimiter … loaders MUST reject a document breaking [it]" — the DEC-22 pattern. It is what
    makes (H3) containment hold by construction: a child is written under its full path
    wherever an id is written, so a child id outside its carrier's prefix would name a node of
    another level, or of no level.

    Only the subdocument's own ``nodes[]`` is read: a deeper level is checked against its own
    carrier when that carrier validates, and the prefix relation is transitive. ``subgraph``
    is declared after ``id``, so ``info.data`` holds the carrier's id; when it does not (the id
    itself failed the §5 grammar) the check stands down and the grammar error stands alone.
    """
    if subgraph is None or "id" not in info.data:
        return subgraph
    carrier = _exact(info.data["id"])
    prefix = carrier + "/"
    for index, child in enumerate(_members(subgraph.nodes)):
        child_id = _exact(child.id)
        if not child_id.startswith(prefix):
            raise ValueError(
                f"subgraph.nodes[{index}] has the id {_quoted(child_id)}, which does not carry "
                f"its carrier's id {_quoted(carrier)} as a proper segment-prefix: every id in a "
                "carrier's subgraph is the child's full §5 path, so loaders MUST reject a "
                "child written outside its carrier's prefix (IR-SPEC §2.1, §3.8; ratified — "
                f"DEC-39, 2026-11-03). Write it as {_quoted(prefix + child_id)} or as another "
                f"path under {_quoted(prefix)}"
            )
    return subgraph


def _require_valid_barrier_groups(
    barriers: tuple[tuple[str, ...], ...] | None,
) -> tuple[tuple[str, ...], ...] | None:
    """The three ``barriers`` MUSTs that one node's member can break on its own (DEC-40 §3.3).

    IR-SPEC §3.11: "every group has two or more members; members distinct within a group;
    groups distinct as sets … loaders MUST reject a document breaking any". A group of one is
    the plain edge (a second canonical form of one wiring fact), a repeated member or group is
    a fact the emitter deduplicates as the substrate does — so none is something a conforming
    emitter writes, and canonicalization dedupes nothing (§6.2). The fourth MUST, the wiring
    one, needs the level's nodes and edges and lives on the level
    (:func:`_require_barrier_wiring`).

    An empty outer array is admitted: it is the omit-normalized absence of the member (§6.3).
    """
    if barriers is None:
        return barriers
    groups: dict[frozenset[str], int] = {}
    for index, group in enumerate(_members(barriers)):
        members = tuple(_exact(member) for member in _members(group))
        if len(members) < 2:
            raise ValueError(
                f"barriers[{index}] has {len(members)} member(s): every group carries two or "
                "more distinct member node ids — a group of one is the plain `normal` edge "
                "itself, so loaders MUST reject a group of fewer than two (IR-SPEC §3.11; "
                "ratified — DEC-40, 2026-11-10)"
            )
        seen: dict[str, int] = {}
        for position, member in enumerate(members):
            earlier = seen.setdefault(member, position)
            if earlier != position:
                raise ValueError(
                    f"barriers[{index}] repeats the member {_quoted(member)}, at [{earlier}] and "
                    f"[{position}]: a group is a set of distinct node ids, and loaders MUST "
                    "reject a repeated member rather than deduplicate it (IR-SPEC §3.11, §6.2; "
                    "ratified — DEC-40, 2026-11-10)"
                )
        key = frozenset(members)
        earlier_group = groups.setdefault(key, index)
        if earlier_group != index:
            raise ValueError(
                f"barriers[{earlier_group}] and barriers[{index}] are one group: the groups "
                "are a set, each distinct as a set of members, and loaders MUST reject a "
                "repeated group rather than deduplicate it (IR-SPEC §3.11, §6.2; ratified — "
                "DEC-40, 2026-11-10)"
            )
    return barriers


class Node(IRModel):
    """A node: identity plus contract (IR-SPEC §2.3), and from 1.2 its mounted child and barriers.

    ``id`` is the escaped path identity of IR-SPEC §5, checked against that grammar as the
    spec's MUST requires: a malformed escape, an empty or reserved segment at any nesting
    level, or a synthetic token outside the closed vocabulary is a validation error here
    (:mod:`gebra.ir.identity`).
    """

    id: NodeIdStr
    annotations: Annotations | None = None
    subgraph: Annotated[Subgraph | None, AfterValidator(_require_carrier_prefix)] = None
    """The compiled graph this node mounts, as a document of its own level (§3.8; 1.2 — DEC-39).

    The node stays **one vertex of its own level** — its incident edges, ``entry``/``finish``
    membership and ``annotations`` are what they would be without the member. Every id inside
    carries this node's id as a proper segment-prefix (enforced here,
    :func:`_require_carrier_prefix`).
    """
    barriers: Annotated[
        tuple[tuple[str, ...], ...] | None, AfterValidator(_require_valid_barrier_groups)
    ] = None
    """The ``waiting_edges`` groups whose target is this node (§3.11; 1.2 — DEC-40).

    Each inner array is one all-of group of two or more distinct member node ids of this node's
    level; the edges into the node are the ordinary ``normal`` edges, one per distinct member,
    untouched. ``[]`` is omit-normalized to absence (§6.3). Three of the four validity MUSTs are
    checked here (:func:`_require_valid_barrier_groups`); the wiring MUST is the level's
    (:func:`_require_barrier_wiring`).
    """


class NormalEdge(IRModel):
    """An unconditional edge (IR-SPEC §2.4). ``to`` is REQUIRED for this kind."""

    kind: Literal["normal"]
    from_: str = Field(alias="from")
    """``from`` is a Python keyword; canonical output serializes by alias (§2.5 note 2)."""
    to: str
    """A node id, or the literal ``"END"`` (§4.2)."""
    condition: str | None = None
    """Admitted for fixture fidelity; inert on this kind (§2.4)."""


def _admit_json_array(value: Any) -> Any:
    """Admit a JSON array for an array-valued **edge** member (IR-SPEC §2.5 note 8; DEC-40 §3.6).

    The tagless-edge default is injected by a pre-validator (:func:`_inject_default_edge_kind`),
    and that moves validation of every edge member into a mode where a JSON array arrives as a
    Python ``list`` — which strict mode refuses for a tuple. Note 8 states the consequence and
    its remedy: "a conforming implementation MUST admit a JSON array for the member on every
    ingestion path … and relaxes that member alone rather than the base model". So an exact
    ``list`` becomes a ``tuple`` here, before strict validation of the members, and nothing else
    is touched: a subclass of ``list``, a set or a generator still reaches strict validation and
    is refused. The ``list`` is read by ``tuple()``'s C-level iteration of an exact ``list``, so
    no object-defined method runs (WA-07).
    """
    if type(value) is list:
        return tuple(value)
    return value


def _require_distinct_codomain(codomain: tuple[str, ...] | None) -> tuple[str, ...] | None:
    """Refuse a ``codomain`` that repeats a label (IR-SPEC §2.4; DEC-40 §3.1).

    "NFC identifiers, distinct (loaders MUST reject a repeated member)" — the DEC-22 pattern:
    the member is a set, sorted under §6.2 and never deduplicated by canonicalization, so a
    repeated label would give one declared set two canonical forms. Whether the member agrees
    with ``keys(path_map)`` is not validity: an agreeing set is admitted and collapses to
    absence by §6.3's representation-normalization.
    """
    if codomain is None:
        return codomain
    seen: dict[str, int] = {}
    for index, label in enumerate(_members(codomain)):
        key = _exact(label)
        earlier = seen.setdefault(key, index)
        if earlier != index:
            raise ValueError(
                f"`codomain` repeats the label {_quoted(key)}, at [{earlier}] and [{index}]: "
                "the member is the router's declared set of return labels, sorted and never "
                "deduplicated, so loaders MUST reject a repeated member (IR-SPEC §2.4; "
                "ratified — DEC-40, 2026-11-10). Declare each label once"
            )
    return codomain


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
    codomain: Annotated[
        tuple[str, ...] | None,
        BeforeValidator(_admit_json_array),
        AfterValidator(_require_distinct_codomain),
    ] = None
    """The router's declared return-label set (§2.4; ``ir_version`` ≥ 1.2 — DEC-40).

    Declared router content in the same role as ``path_map`` keys: distinct NFC labels (a loader
    MUST, enforced here), a set under §6.2, ``[]`` ≡ absent, and a set equal to
    ``keys(path_map)`` after NFC collapsed to absence by §6.3 — so a member *present in
    canonical form* is declared and distinct, and only such a member requires ``"1.2"``. It
    narrows nothing: label expansion runs over ``path_map`` alone. A JSON array is admitted on
    every ingestion path (:func:`_admit_json_array`, §2.5 note 8).
    """


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

    A document containing one of these, and no 1.2 construct, is ``ir_version`` ``"1.1"``
    (:func:`lowest_ir_version`).
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

    One consequence for array-valued edge members, recorded by IR-SPEC §2.5 note 8: behind
    this pre-validator a JSON array reaches the member as a ``list``, which strict mode refuses
    for a tuple — so the one such member, :attr:`ConditionalEdge.codomain`, admits it alone
    (:func:`_admit_json_array`).
    """
    if isinstance(value, dict) and "kind" not in value:
        return {**value, "kind": DEFAULT_EDGE_KIND}
    return value


#: A kinded edge, discriminated on ``kind`` (IR-SPEC §2.4/§2.5). The before-validator rides
#: on the type itself rather than on :attr:`WorkflowIR.edges`, so validating an edge
#: directly (e.g. through a ``TypeAdapter``) admits the tagless surface form too. The four
#: kinds are the whole vocabulary at 1.2 too: the all-of barrier rides its target node
#: (:attr:`Node.barriers`), never an edge kind (DEC-40).
Edge: TypeAlias = Annotated[
    NormalEdge | ConditionalEdge | SendEdge | DynamicEdge,
    Field(discriminator="kind"),
    BeforeValidator(_inject_default_edge_kind),
]


# ── The construct → minor map (IR-SPEC §8's event bullets) ────────────────────────────────
#
# One generator per level member, each yielding ``(minor, where, what)`` for every construct
# that requires a minor above "1.0" — in document order: ``state``, then ``nodes`` (each
# node's own constructs, then its subgraph level), then ``edges``. The floor of anything is
# the maximum of what these yield; the offender a refusal names is the first construct whose
# own minor *is* that floor. Keeping the decomposition per construct is what lets one
# function both compute the floor and name the construct that raises it (DEC-39 §3.3:
# "keeping the per-construct decomposition").

#: One construct that raises the floor: its minor, where it sits, and what it is.
_Construct: TypeAlias = tuple[IrVersion, str, str]


def _codomain_present(edge: ConditionalEdge) -> bool:
    """Whether a ``codomain`` is present **in canonical form** (DEC-40 §3.6, IR-SPEC §6.3).

    "Present" is the canonical reading: non-empty and, after NFC, distinct from the same edge's
    ``keys(path_map)`` — an agreeing set collapses to absence, so a ``"1.1"``-stamped document
    carrying one is not under-stamped. Both sides are NFC-normalized here because the floor is
    read before canonicalization's step-5 check, and an exact-``str`` copy is taken first so no
    object-defined hook runs while the sets hash.
    """
    if edge.codomain is None or tuple.__len__(edge.codomain) == 0:
        return False
    declared = {unicodedata.normalize("NFC", _exact(label)) for label in _members(edge.codomain)}
    mapped = {unicodedata.normalize("NFC", _exact(label)) for label in dict.__iter__(edge.path_map)}
    return declared != mapped


def _edge_constructs(edges: Iterable[Edge], where: str) -> Iterator[_Construct]:
    """The edge constructs of one level: ``dynamic`` (1.1) and a canonical ``codomain`` (1.2).

    ``edges`` arrives already wrapped: a model's member through :func:`_members`, or the edge
    set a caller hands :func:`lowest_ir_version`, iterated as the caller's own object. An edge
    whose type is none of the four edge models is refused (:class:`_NotAModelError`).
    """
    for index, edge in enumerate(edges):
        if issubclass(type(edge), DynamicEdge):
            yield (
                IR_VERSION_DYNAMIC_EDGES,
                f"{where}edges[{index}]",
                f"is of kind {_quoted(edge.kind)}",
            )
        elif issubclass(type(edge), ConditionalEdge):
            if _codomain_present(cast(ConditionalEdge, edge)):
                yield (
                    _IR_VERSION_1_2,
                    f"{where}edges[{index}]",
                    "carries a `codomain` distinct from its `path_map` keys",
                )
        elif not (issubclass(type(edge), NormalEdge) or issubclass(type(edge), SendEdge)):
            raise _NotAModelError(
                f"{where}edges[{index}] is not an instance of one of the four edge models — its "
                "type is none of them, whatever its `__class__` claims — so this document's "
                "floor cannot be read from it (IR-SPEC §2.5 note 7)"
            )


def _token_kind(node_id: str) -> str | None:
    """The first 1.2 synthetic token a node id carries, if any (DEC-40 §3.5).

    A user segment escapes ``%`` to ``%25``, so a segment that starts with ``%assign[``,
    ``%each[`` or ``%leaf[`` is that synthetic token and nothing else (§5.1–§5.2). Read with
    ``str``'s own methods over an exact copy: no grammar error is raised here, because the
    floor is computed over ids that already passed the grammar, or — for a model built past
    validation — must not raise on one that did not.
    """
    for segment in str.split(_exact(node_id), "/"):
        for kind in _TOKENS_1_2:
            if segment.startswith(f"%{kind}["):
                return kind
    return None


def _node_constructs(nodes: Iterable[Node], where: str) -> Iterator[_Construct]:
    """The node constructs of one level, then each carrier's own level, recursively.

    ``nodes`` arrives through :func:`_members`.
    """
    for index, node in enumerate(nodes):
        at = f"{where}nodes[{index}]"
        token = _token_kind(node.id)
        if token is not None:
            yield (
                _IR_VERSION_1_2,
                at,
                f"({_quoted(node.id)}) carries a synthetic segment of kind {_quoted(token)}",
            )
        if node.subgraph is not None:
            yield (_IR_VERSION_1_2, at, f"({_quoted(node.id)}) carries `subgraph`")
        if node.annotations is not None:
            if node.annotations.projection is not None:
                yield (
                    _IR_VERSION_1_2,
                    at,
                    f"({_quoted(node.id)}) carries `annotations.projection`",
                )
            if node.annotations.join_key is not None:
                yield (_IR_VERSION_1_2, at, f"({_quoted(node.id)}) carries `annotations.join_key`")
        if node.barriers is not None and tuple.__len__(node.barriers) > 0:
            yield (_IR_VERSION_1_2, at, f"({_quoted(node.id)}) carries `barriers`")
        if node.subgraph is not None:
            yield from _level_constructs(
                node.subgraph.state, node.subgraph.nodes, node.subgraph.edges, f"{at}.subgraph."
            )


def _state_constructs(
    state: dict[str, str | StateField] | None, where: str
) -> Iterator[_Construct]:
    """The ``state`` constructs of one level: a ``managed`` entry (1.2).

    A value whose type is neither ``str`` nor :class:`StateField` is refused
    (:class:`_NotAModelError`).
    """
    if state is None:
        return
    for key, value in dict.items(state):
        if issubclass(type(value), StateField):
            if cast(StateField, value).managed is not None:
                yield (_IR_VERSION_1_2, f"{where}state[{_quoted(key)}]", "carries `managed`")
        elif not issubclass(type(value), str):
            raise _NotAModelError(
                f"{where}state[{_quoted(key)}] is neither a type string nor a StateField — its "
                "type is neither, whatever its `__class__` claims — so this document's floor "
                "cannot be read from it (IR-SPEC §2.5 note 7)"
            )


def _level_constructs(
    state: dict[str, str | StateField] | None,
    nodes: tuple[Node, ...] | None,
    edges: tuple[Edge, ...] | None,
    where: str,
) -> Iterator[_Construct]:
    """Every construct of one level and the levels it carries, in document order."""
    yield from _state_constructs(state, where)
    if nodes is not None:
        yield from _node_constructs(_members(nodes), where)
    if edges is not None:
        yield from _edge_constructs(_members(edges), where)


def _floor(constructs: Iterable[_Construct]) -> IrVersion:
    """The maximum minor a construct stream requires — ``"1.0"`` for an empty one."""
    floor: IrVersion = IR_VERSION
    for minor, _, _ in constructs:
        if IR_VERSIONS.index(minor) > IR_VERSIONS.index(floor):
            floor = minor
    return floor


def lowest_ir_version(edges: WorkflowIR | Iterable[Edge]) -> IrVersion:
    """The lowest ``ir_version`` sufficient for a document — or for an edge set (IR-SPEC §8).

    §8's stamping policy, general rather than per-construct: "emitters **MUST** stamp the
    LOWEST minor sufficient for the document's constructs — ``"1.2"`` iff a 1.2 construct is
    present at any level, else ``"1.1"`` iff a ``dynamic`` edge is present, else ``"1.0"``"
    (the RFC 2119 keyword promoted at DEC-34, 2026-09-06; the 1.2 constructs ratified at DEC-39
    and DEC-40). Three properties come with that choice, and they are why the policy is a
    function of content rather than of the writing build's version:

    * **Deterministic.** Two conforming emitters given equal content stamp equal versions.
    * **Zero golden churn.** Nothing that carried ``"1.0"`` or ``"1.1"`` starts carrying a
      later minor, so no committed golden and no vendored fixture moves.
    * **Honest.** A document using no later construct does not advertise a feature it makes no
      use of, so an older consumer is never turned away from a document it can read.

    **The whole document** (DEC-39 §3.3, DEC-40 §3.6): handed a :class:`WorkflowIR`, the scan
    reads every level — at each, ``state`` entries (``managed``), nodes (``subgraph``,
    ``barriers``, ``annotations.projection``, ``annotations.join_key``, an id carrying an
    ``assign``/``each``/``leaf`` segment) and edges (``dynamic``; a ``codomain`` present in
    canonical form — non-empty and, after NFC, distinct from ``keys(path_map)``), then each
    carrier's ``subgraph`` level the same way. "Present" is the canonical reading for every
    member: ``barriers`` iff non-empty, ``codomain`` as just said, ``managed`` iff ``True`` (its
    only value), ``subgraph``/``projection``/``join_key`` iff non-null.

    **An edge set** is still accepted, and gives the floor of those edges alone (``dynamic`` →
    ``"1.1"``, a canonical ``codomain`` → ``"1.2"``): an emitter that stamps before it builds the
    document — and writes no node or ``state`` construct of a later minor — reads it there.

    The MUST binds **emitters**, and the loader's own rule is only half of it: §2.5 note 7
    refuses a document stamped *below* this value and admits one stamped above it
    (:func:`_require_sufficient_ir_version`). So this function is what gebra writes, and the
    floor — not equality with it — is what gebra reads.

    **The property the floor check depends on**, recorded here because it is this function's
    to keep rather than the validator's to rediscover: the result is the **maximum** of the
    per-construct floors, so the document's floor exceeds a stamp only if some single construct
    does — which is how the validator names one offender. A future minor floored by a
    *combination* of constructs rather than by any one of them would break that decomposition
    and needs the search re-sited, not just this function extended.

    The parameter keeps the name it was frozen with (IR-MODELS-FREEZE §1), so a keyword call
    ``lowest_ir_version(edges=…)`` written against 1.1 still works; a document is passed in the
    same place. An iterable of edges is consumed once, so a generator is fine.

    Raises:
        TypeError: if an edge, or a ``state`` value at any level of a document, is none of the
            models its field declares — an object whose ``__class__`` claims a model class
            included, which pydantic admits — or a document's array or map member is not the
            container its field declares. Such a member is refused, never read as no construct.
    """
    if issubclass(type(edges), WorkflowIR):
        return _floor(_document_constructs(cast(WorkflowIR, edges)))
    return _floor(_edge_constructs(cast(Iterable[Edge], edges), ""))


def _document_constructs(ir: WorkflowIR) -> Iterator[_Construct]:
    return _level_constructs(ir.state, ir.nodes, ir.edges, "")


class DynamicEdgeUnsupportedError(NotImplementedError):
    """A 1.0-vocabulary consumer was handed a document carrying a ``dynamic`` edge.

    ``NotImplementedError`` by inheritance because that is what such a consumer's position is:
    the construct is ratified and emitted, and the consumer implements the three ir 1.0 kinds.

    **No consumer in this package raises it any more.** Every one that once did now reads the
    kind under its own ruled representation — the validators since VAL-14 (PROPERTY-CATALOG-SPEC
    §0.3's convention), the topology diff, the snapshot recorder and the freshness check since
    SD-13 (PD-059 D1: the headless edge is carried on its source and reported with no target),
    and the display emitter since CLI-11 (PD-060: the same source-carried representation, drawn
    as a marker and a dispatch note — DIAGRAM-STYLE-GUIDE §3.3). The class stays on this frozen
    export surface for the consumers it was written for: a caller outside this package written
    against the 1.0 ``kind`` vocabulary, which :func:`refuse_dynamic_edges` lets it decline in
    one wording. Removing it would be a §4 change to the frozen export set (IR-MODELS-FREEZE),
    which routes through a vault decision record — not through a card's own latitude (PD-060).
    """


#: An edge whose target set is statically known — the three ir 1.0 kinds.
#:
#: What a consumer written against the 1.0 ``kind`` vocabulary handles, named so that such a
#: consumer can *say* so in its signature rather than discovering the fourth kind at runtime.
#: It stays at three at 1.2: no edge kind was added (DEC-40 §3.3).
StaticEdge: TypeAlias = NormalEdge | ConditionalEdge | SendEdge


def refuse_dynamic_edges(edges: Iterable[Edge], *, consumer: str) -> tuple[StaticEdge, ...]:
    """Decline a ``dynamic``-bearing edge set on behalf of a consumer with no 1.1 semantics.

    One decline, one wording, for any consumer that needs it. **No consumer in this package
    does any more, and none is expected to return** — the helper is kept for callers outside
    it. Each of gebra's own left the list on a ruling of its own: the validators at VAL-14
    (PROPERTY-CATALOG-SPEC §0.3's convention — no member of $G$, a participating source, so
    ``gebra.verify`` reaches a verdict); the topology-diff graph, the snapshot recorder and the
    freshness check at SD-13 (PD-059 D1 — the edge is carried on its source vertex and reported
    with no target, so the store above them extends and compares a 1.1 document like any
    other); and the display emitter at CLI-11 (PD-060 — the same source-carried representation
    on the page, a marker on the source and a rendered dispatch note, so no head is invented
    and no target set implied; DIAGRAM-STYLE-GUIDE §3.3).

    **What it is still for.** A consumer written against the three ir 1.0 ``kind`` values — a
    plugin, a downstream tool, a script walking ``ir.edges`` — meets a fourth kind it has no
    branch for. This says so once, in one wording, naming the consumer, and hands back the edge
    set typed as :data:`StaticEdge` so that consumer's own walk is checked against the kinds it
    actually handles. Declining is a legitimate posture; what the ruled representations replace
    is *gebra's* reason for taking it, not the posture itself.

    **Why a decline rather than a default, for a consumer that still needs one.** A ``dynamic``
    edge contributes no member to the graph $G$ (§0.3, ratified — DEC-28), and *silently*
    dropping it is the one thing that must not happen; inventing a target for it would name a
    vertex the document does not declare — the phantom class DEC-26 §3 closed. A consumer with
    no representation of its own has no third option.

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
            "statically known. Every consumer gebra ships reads it: `gebra.verify` reaches a "
            "verdict (VAL-14), `gebra.snapshot`, `gebra diff` and the freshness check carry "
            "the edge on its source and report it with no target (PD-059), and `gebra "
            "display` draws it the same way — a marker on the source and a dispatch note, "
            "never an invented head (PD-060, DIAGRAM-STYLE-GUIDE §3.3). A consumer with no "
            "representation of its own declines here rather than guessing: the edge "
            "contributes no member to the graph, and inventing a target would name a vertex "
            "the document does not declare."
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

    All three sub-slots are OPTIONAL and all three are in ``graph_version`` hash scope. From
    ``ir_version`` 1.2 the same block exists on every level (``subgraph.runtime``), each level's
    being its own fact (§3.8).
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

    This is the per-level check — the one a :class:`Subgraph` level runs on its own
    ``nodes[]``. The document reads the same MUST over every level
    (:func:`_require_unique_node_ids_over_every_level`, DEC-39 §3.2).

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


def _every_node(nodes: tuple[Node, ...], where: str) -> Iterator[tuple[str, Node]]:
    """Every node of a level and of each level it carries, with its position, in document order."""
    for index, node in enumerate(_members(nodes)):
        at = f"{where}nodes[{index}]"
        yield at, node
        if node.subgraph is not None:
            yield from _every_node(node.subgraph.nodes, f"{at}.subgraph.")


def _require_unique_node_ids_over_every_level(nodes: tuple[Node, ...]) -> tuple[Node, ...]:
    """Refuse a document that declares one id twice at any two places of its tree (DEC-39 §3.2).

    IR-SPEC §2.1 as amended at 1.2: "the uniqueness MUST then reads over every level of the
    document … loaders MUST reject a breach". Each level's own ``nodes[]`` has already refused a
    repeat within itself (:func:`_require_unique_node_ids`, run by every :class:`Subgraph` and
    by the top level here first); what is left is a repeat across levels — a top-level LCEL
    fragment child ``booking/search`` beside a mounted child of the same full path, say, which
    the carrier-prefix MUST does not exclude. Ids are full §5 paths at every level, so one id
    in two places names one node twice (§5.3).

    Same discipline as the per-level check: refuses and never rewrites, exact-``str`` copies
    for the dict keys and the message (WA-07).
    """
    _require_unique_node_ids(nodes)
    first_seen: dict[str, str] = {}
    for at, node in _every_node(nodes, ""):
        node_id = _exact(node.id)
        earlier = first_seen.setdefault(node_id, at)
        if earlier != at:
            raise ValueError(
                f"node id {_quoted(node_id)} is declared twice, at {earlier} and {at}: from "
                "ir_version 1.2 node ids are unique over the whole document, every subgraph "
                "level included (IR-SPEC §2.1, §3.8; ratified — DEC-22, 2026-08-04, and "
                "DEC-39, 2026-11-03), because an id is the node's full §5 path wherever it "
                "is written and one id names at most one node (§5.3). Give one of them its "
                "own id"
            )
    return nodes


def _require_barrier_wiring(edges: tuple[Edge, ...], info: ValidationInfo) -> tuple[Edge, ...]:
    """The fourth ``barriers`` MUST, read over one level (IR-SPEC §3.11; DEC-40 §3.3).

    "Every member names a node of the same level that is the source of a ``normal`` edge into
    this node; loaders MUST reject a document breaking [it]". The group restates wiring the
    edges already carry — the emitter writes one ``normal`` edge per distinct member and the
    group over the same set — so a member with no such edge is a fact no conforming emitter
    writes. Its node-existence half is deliberately stricter than an edge endpoint, which P-01
    reports rather than the loader (recorded at DEC-40 §3.11).

    Placed on ``edges`` for the reason IR-08 put the stamp floor there: ``nodes`` is declared
    before ``edges``, so ``info.data`` holds the level's validated nodes, and a field validator
    reports alongside the document's other field errors. When ``nodes`` failed, the check
    stands down — the document fails on ``nodes`` already.
    """
    nodes = info.data.get("nodes")
    if not nodes:
        return edges
    declared = {_exact(node.id) for node in _members(nodes)}
    wired = {
        (_exact(edge.from_), _exact(cast(NormalEdge, edge).to))
        for edge in _members(edges)
        if issubclass(type(edge), NormalEdge)
    }
    for index, node in enumerate(_members(nodes)):
        if node.barriers is None or tuple.__len__(node.barriers) == 0:
            continue
        target = _exact(node.id)
        for group_index, group in enumerate(_members(node.barriers)):
            for member in _members(group):
                source = _exact(member)
                if source not in declared:
                    problem = "names no node of this level"
                elif (source, target) not in wired:
                    problem = f"is the source of no `normal` edge into {_quoted(target)}"
                else:
                    continue
                raise ValueError(
                    f"nodes[{index}] ({_quoted(target)}) barriers[{group_index}] has the member "
                    f"{_quoted(source)}, which {problem}: every member of a barrier group names "
                    "a node of the same level that is the source of a `normal` edge into the "
                    "group's target — the group records the compiled all-of channel over edges "
                    "the document already carries — so loaders MUST reject it (IR-SPEC §3.11; "
                    "ratified — DEC-40, 2026-11-10)"
                )
    return edges


class Subgraph(IRModel):
    """``nodes[].subgraph`` — the child subdocument (IR-SPEC §3.8; ``ir_version`` ≥ 1.2, DEC-39).

    A document **of its own level**: the six members of :class:`WorkflowIR` other than
    ``ir_version``, with the same shapes, requiredness and §6 rules. ``entry``/``finish`` are
    the child's own (m1)/(m2) sentinel incidences, ``state`` its own Σ, ``nodes``/``edges`` its
    own $N$/$E$, ``runtime`` its own configuration. The child's nodes are nested, never
    flattened: they are members of this ``nodes[]`` and of no other level's, and a node here
    MAY carry a ``subgraph`` of its own (nesting; the format bounds the depth by nothing).

    A level validates what a level can: non-empty ``nodes`` with unique ids within it
    (DEC-22), and the ``barriers`` wiring over its own nodes and edges (DEC-40). What needs the
    carrier — the carrier-prefix MUST — is :attr:`Node.subgraph`'s, and what needs the whole
    tree — uniqueness across levels, the stamp floor — is :class:`WorkflowIR`'s.
    """

    entry: NodeReference | tuple[str, ...]
    """The child's own (m1) wiring — full-path ids (§3.8, §4.2)."""
    finish: NodeReference | tuple[str, ...]
    """The child's own (m2) wiring — full-path ids (§3.8, §4.2)."""
    state: dict[str, str | StateField] | None = None
    """The child's own Σ (§2.2): two entries of one name at two levels are two keys."""
    nodes: Annotated[
        tuple[Node, ...], Field(min_length=1), AfterValidator(_require_unique_node_ids)
    ]
    """The child's own node set, non-empty, each id under the carrier's prefix (§3.8)."""
    edges: Annotated[tuple[Edge, ...], AfterValidator(_require_barrier_wiring)]
    """The child's own edge set — REQUIRED with no default; ``[]`` is authored explicitly."""
    runtime: Runtime | None = None
    """The child's own compile-time and declared configuration (§3.8)."""


Node.model_rebuild()
Subgraph.model_rebuild()


def _require_sufficient_ir_version(
    edges: tuple[Edge, ...], info: ValidationInfo
) -> tuple[Edge, ...]:
    """Refuse a document stamped below the minor its constructs need (§2.5 note 7; DEC-34).

    The rule is worded at the loader — "``ir_version`` MUST be ≥ the lowest minor its
    constructs require; loaders MUST reject a document stamped below it, and never re-stamp
    it" — so this is where it is enforced, beside the §2.1 uniqueness MUST it was ratified on
    the precedent of (DEC-22/IR-07).

    **Read over the whole document** (DEC-39 §3.3, DEC-40 §3.6). Most 1.2 constructs are not
    edges — a ``subgraph``, a ``barriers`` group, a ``projection`` or ``join_key``, a token-bearing
    id, a ``managed`` state entry — so the floor is computed from everything a document
    carries, every level included, through :func:`lowest_ir_version`'s per-construct map. The
    validator stays on ``edges`` for IR-08's reasons, and the move works because §2.1's field
    order puts ``state`` and ``nodes`` before ``edges``: ``info.data`` holds all three
    construct-bearing members by the time this runs (``runtime`` carries no floor construct).
    A member that failed its own validation is absent from ``info.data`` and contributes
    nothing — the document fails on it already.

    **One offender, with its level.** The message names one node, one edge or one ``state``
    key, by its position — ``nodes[2].subgraph.edges[0]`` locates both the construct and the
    level — and it is the first construct, in document order, whose own minor *is* the
    document's floor, so "the lowest sufficient minor" the message states is that construct's.
    The error is always reported at ``loc = ("edges",)``, where the whole document is first in
    view; the message carries the offender's own path.

    **Never re-stamps.** ``edges`` comes back unchanged: ``ir_version`` is inside the §6.4
    hash scope, so silently raising it would move the ``graph_version`` of a document its
    author wrote, and the twin stamped correctly is a *different* document, not the same one
    repaired.

    **Over-stamping is admitted** and is not an oversight here: §8's minimal-stamping MUST
    binds emitters, so a document stamped above its constructs' floor uses no construct its
    loader lacks and is loaded, verified and recorded exactly as before (DEC-34 §3).

    Args:
        edges: The validated ``edges`` array, in authored order.
        info: Pydantic's field-validation context. ``ir_version`` is declared before
            ``edges``, so ``info.data`` already carries the validated stamp; when it does
            not — the stamp itself failed, or a caller validated ``edges`` on its own — the
            check stands down rather than guessing, leaving pydantic's own ``ir_version``
            error to stand alone. The ``in``/``index`` comparisons below are ``str``'s own
            only because :data:`IrVersion` is a ``Literal``: pydantic returns the stored
            canonical value, never the caller's ``str`` subclass. Widening that annotation to
            a bare ``str`` would make those two operations dispatch to a subclass's reflected
            ``__eq__``, which the unbound-``str`` calls in the message do **not** cover —
            they guard the formatting, not the comparison
            (``tests/ir/test_ir_version_stamp_floor.py`` pins the coercion for that reason).

    Returns:
        ``edges`` unchanged — this validator refuses, and never rewrites.

    Raises:
        ValueError: naming the stamp, the lowest sufficient minor and the offending construct —
            or naming an edge or ``state`` value whose type is none of the models its field
            declares, from which no floor can be read (:class:`_NotAModelError`). A
            ``ValueError`` because that is what pydantic renders as an ordinary
            ``ValidationError``, here at ``loc = ("edges",)``.
    """
    stamp = info.data.get("ir_version")
    if stamp not in IR_VERSIONS:
        return edges
    try:
        constructs = tuple(
            _level_constructs(info.data.get("state"), info.data.get("nodes"), edges, "")
        )
    except _NotAModelError as error:
        raise ValueError(str(error)) from None
    floor = _floor(constructs)
    if IR_VERSIONS.index(floor) <= IR_VERSIONS.index(stamp):
        return edges

    where, what = next((where, what) for minor, where, what in constructs if minor == floor)
    raise ValueError(
        f"ir_version {_quoted(stamp)} is below the lowest minor this document's constructs "
        f"require: {where} {what}, which IR-SPEC §8 introduces at {_quoted(floor)}, so "
        f"{_quoted(floor)} is the lowest sufficient minor. A document stamped below it is "
        "non-conforming and loaders MUST reject it (§2.5 note 7; §2.4; ratified — DEC-34, "
        "2026-09-06; read over every level from 1.2 — DEC-39, DEC-40). A loader never "
        "re-stamps one instead: `ir_version` is inside the §6.4 hash scope, so raising it "
        "here would move the graph_version of the document you wrote. Stamp the document "
        f"ir_version {_quoted(floor)}"
    )


class WorkflowIR(IRModel):
    """A workflow definition — the seven fields of IR-SPEC §2.1 (``ir_version`` 1.0–1.2).

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

    **Node ids are unique within a document** — §2.1's MUST, ratified DEC-22, read over every
    subgraph level from 1.2 (DEC-39) — so a document declaring one ``id`` twice is a validation
    error naming the repeated id and both positions that declare it, not a document with two
    nodes of one identity. See the ``nodes`` field below for why the check lives there and
    what it deliberately does not constrain.

    **The ``ir_version`` stamp is floored by the document's own constructs** — §2.5 note 7's
    MUST, ratified DEC-34 and read over the whole document from 1.2 — so a document stamped
    below the lowest minor its constructs require is a validation error naming the stamp, that
    minor and one offending node, edge or ``state`` key. A document stamped *above* the floor
    is admitted unchanged. See the ``edges`` field below.
    """

    ir_version: IrVersion
    """``"1.0"``, ``"1.1"`` or ``"1.2"`` — the lowest the document's constructs need (§8).

    The member is the document's own declaration, and the model floors it against that
    document's constructs (§2.5 note 7; ratified — DEC-34, 2026-09-06): a stamp *below* the
    lowest sufficient minor is a validation error, reported at ``edges``
    (:func:`_require_sufficient_ir_version`). A stamp *above* it is admitted — §8's
    minimal-stamping MUST binds **emitters**, and a document is authored as well as emitted, so
    an over-stamped document uses no construct its loader lacks. What gebra writes is therefore
    exactly :func:`lowest_ir_version`; what gebra reads is anything at or above it.

    The loader never re-stamps: the member is inside the §6.4 hash scope, so correcting it
    would move the ``graph_version`` of a document its author wrote.
    """

    entry: NodeReference | tuple[str, ...]
    finish: NodeReference | tuple[str, ...]
    state: dict[str, str | StateField] | None = None
    """State key → bare type-name string, or the object form (§2.2)."""
    nodes: Annotated[
        tuple[Node, ...],
        Field(min_length=1),
        AfterValidator(_require_unique_node_ids_over_every_level),
    ]
    """The node set $N$ (§2.1), non-empty and with **unique** ids over every level (DEC-22).

    The uniqueness MUST is checked here rather than on :attr:`Node.id`, because it is a
    property of the array — and from 1.2 of the tree the array carries — and no single element
    can violate it; the error therefore lands at ``loc = ("nodes",)`` and names both positions
    (:func:`_require_unique_node_ids_over_every_level`).

    It is an ``AfterValidator`` and not a JSON-Schema ``uniqueItems`` constraint: the rule is
    uniqueness of the ``id`` member, not of whole node objects — two nodes sharing an id and
    differing in their annotations are distinct items — and keeping it out of the generated
    schema leaves ``model_json_schema()`` agreeing with the vendored ``schema.yaml``, which
    IR-05's lockstep check compares against.
    """

    edges: Annotated[
        tuple[Edge, ...],
        AfterValidator(_require_barrier_wiring),
        AfterValidator(_require_sufficient_ir_version),
    ]
    """The kinded edge set $E$ (§2.4), and where the document's cross-member rules are read.

    The §2.5 note 7 stamp floor is checked here rather than in a
    ``model_validator(mode="after")``, for the reason IR-07 put the uniqueness MUST on
    ``nodes``: a model-after validator runs only once *every* field has validated, so a
    document that is also missing ``nodes`` would report the missing member alone and the
    author would fix one fault to discover the next. A field validator with a
    ``ValidationInfo`` reads the already-validated ``ir_version``, ``state`` and ``nodes`` out
    of ``info.data`` — declared first, in §2.1's field order, which is the spec's, not a
    convenience — so both faults come back together and the error lands at
    ``loc = ("edges",)``. The top level's ``barriers`` wiring MUST is read here for the same
    reason (:func:`_require_barrier_wiring`).

    Like ``nodes``' constraint these are ``AfterValidator`` s, which add nothing to
    ``model_json_schema()``: the rules are relations between members that JSON Schema's
    vocabulary does not express, and IR-05's lockstep check compares the generated schema
    against the vendored ``schema.yaml``, which carries no such rule either.
    """

    runtime: Runtime | None = None


# ── The format-migration down-projection (IR-SPEC §8; DEC-39 §3.7, DEC-40 §3.7) ──────────


def _frame_child(node_id: str) -> bool:
    """Whether a node id lies beneath an ``assign`` or ``each`` frame (DEC-40 §3.5).

    The reverse mapping removes "every node whose id carries an ``assign`` or ``each`` segment
    in any position" — the 1.1 emitter named that frame's object as one leaf child of its
    enclosing frame and read nothing beneath it, so everything under it is new. The frame's own
    node carries no such segment (its id is its enclosing frame's selector) and stays. The one
    position exempt is the first: a first segment of kind ``assign`` or ``each`` is a root
    frame's own token, and such a root "names nothing" — the 1.1 build refused it, so it has no
    older document. A frame nested beneath it is a frame like any other, and its children go.
    """
    segments = str.split(_exact(node_id), "/")
    return any(
        segment.startswith(f"%{kind}[") for segment in segments[1:] for kind in _FRAME_TOKENS_1_2
    )


def _edge_ends(edge: Edge) -> tuple[str, ...]:
    """Every node id an edge names: its source and its target(s) — ``path_map`` values included.

    A subclass of an edge model is read as its base kind; anything else is refused.
    """
    if issubclass(type(edge), ConditionalEdge):
        return (edge.from_, *dict.values(cast(ConditionalEdge, edge).path_map))
    if issubclass(type(edge), DynamicEdge):
        return (edge.from_,)
    if issubclass(type(edge), NormalEdge) or issubclass(type(edge), SendEdge):
        return (edge.from_, cast(NormalEdge | SendEdge, edge).to)
    raise TypeError("a document's edge is not one of the four edge models")


def _optional_text(value: str | None) -> str | None:
    """An exact copy of an optional string member, or ``None``."""
    return None if value is None else _exact(value)


def _rebuilt_edge(edge: Edge) -> Edge:
    """A kept edge rebuilt through its kind's constructor from exact copies of its members.

    The projection's result is validated by the :class:`WorkflowIR` constructor, which hashes and
    compares what it is handed (the ``kind`` discriminator among them), so a kept edge is never
    handed on as the instance it was: it is read by attribute access and rebuilt. A subclass of an
    edge model is read as its base kind. A ``conditional`` edge is rebuilt without ``codomain`` —
    part B's reverse mapping (IR-SPEC §8).
    """
    source = {"from": _exact(edge.from_)}
    condition = _optional_text(edge.condition)
    if issubclass(type(edge), ConditionalEdge):
        path_map = {
            _exact(label): _exact(target)
            for label, target in dict.items(cast(ConditionalEdge, edge).path_map)
        }
        return ConditionalEdge(
            kind="conditional", **source, condition=condition, path_map=path_map, codomain=None
        )
    if issubclass(type(edge), DynamicEdge):
        return DynamicEdge(kind="dynamic", **source, condition=condition)
    if issubclass(type(edge), NormalEdge):
        target = _exact(cast(NormalEdge, edge).to)
        return NormalEdge(kind="normal", **source, to=target, condition=condition)
    if issubclass(type(edge), SendEdge):
        target = _exact(cast(SendEdge, edge).to)
        return SendEdge(kind="send", **source, to=target, condition=condition)
    raise TypeError("a document's edge is not one of the four edge models")


def _checked_node(node: Node) -> tuple[str, Annotations | None]:
    """A node's id, copied exact, and its ``annotations`` — each read once, after the node's class
    test, the ``annotations`` then class-tested too; anything else is refused."""
    if not issubclass(type(node), Node):
        raise TypeError("a document's node is not a Node model")
    node_id = _exact(node.id)
    annotations = node.annotations
    if annotations is not None and not issubclass(type(annotations), Annotations):
        raise TypeError("a document's node carries annotations that are not an Annotations model")
    return node_id, annotations


def _rebuilt_node(node_id: str, annotations: Annotations | None) -> Node:
    """A kept node rebuilt from its exact id and its ``annotations``, with no 1.2 member.

    ``subgraph`` and ``barriers`` are what the projection removes (part A and part B); the
    ``annotations`` are the value :func:`_checked_node` read and class-tested, handed on as that
    instance, not re-validated.
    """
    return Node(id=node_id, annotations=annotations)


def _rebuilt_state_value(value: str | StateField) -> str | StateField:
    """A kept Σ value rebuilt from exact copies: a bare type string, or the object form."""
    if issubclass(type(value), str):
        return _exact(cast(str, value))
    if issubclass(type(value), StateField):
        field = cast(StateField, value)
        return StateField(
            type=_exact(field.type), reducer=_optional_text(field.reducer), optional=field.optional
        )
    raise TypeError("a document's state value is neither a type string nor a StateField model")


def _rebuilt_wiring(wiring: str | tuple[str, ...]) -> str | tuple[str, ...]:
    """``entry``/``finish`` rebuilt from exact copies: a scalar id, or a tuple of ids."""
    if issubclass(type(wiring), str):
        return _exact(cast(str, wiring))
    return tuple(_exact(member) for member in _members(cast(tuple[str, ...], wiring)))


def down_project(ir: WorkflowIR, floor: IrVersion) -> WorkflowIR:
    """``ir`` with every extraction-populated construct above ``floor`` removed (IR-SPEC §8).

    The format-migration pair's down-projection (ratified — DEC-39 §3.7, DEC-40 §3.7): two
    documents of one extracted source are a format-migration pair iff the older's floor
    (:func:`lowest_ir_version`) is below the newer's, and the pair's *residual* is what a diff
    reports between the older document and the newer one down-projected to the older's floor.
    An empty residual — canonical forms byte-equal apart from ``ir_version`` — is a pure format
    migration. Kept here, beside :func:`lowest_ir_version`, so the store, the diff and lineage
    share one definition.

    What each event bullet above ``floor`` names, and only that (the reverse mappings stated
    exactly in §8):

    * **1.1** — nothing: a ``dynamic`` edge arises from the source, never from re-extraction.
    * **1.2, part A** — ``subgraph``, at every level (removing the member removes the levels).
    * **1.2, part B** — ``barriers`` (the member; the edges, which it never changed, stay);
      ``codomain`` on every ``conditional`` edge; every ``state`` entry carrying ``managed``,
      removed whole, the key with it (declared ``input``/``output`` lists naming it stay as
      written); every node beneath an ``assign`` or ``each`` frame, with every edge incident to
      it and the declared content it carries (the frame's own node stays).

    Never removed, because never produced by re-extraction alone or naming nothing:
    ``projection`` and ``join_key`` (declared), ``leaf`` and an ``assign``/``each`` root (no
    older document exists for either). A construct both declared and extracted would not be
    down-projectable at all; none of the ruled ones is (§8's one-route rule).

    The stamp is left as it is — never re-stamped: removing constructs only lowers a
    document's floor, so the result is stamped at or above its own floor, and the pair's
    comparison is defined apart from ``ir_version``. A caller that wants the result at its own
    floor reads :func:`lowest_ir_version` of it. What it keeps — nodes, edges, Σ values, the stamp
    and the ``entry``/``finish`` wiring — is rebuilt from exact copies through the model
    constructors (the module docstring's WA-07 paragraph), and the constructor validates the
    result; a node's ``annotations`` and the ``runtime`` are handed on as the class-tested
    instances they are, not re-validated.

    One document has no projection: a 1.2 document whose every node lies beneath a non-root
    ``assign`` or ``each`` frame loses every node, and a document needs one (IR-SPEC §2.1,
    ``nodes`` minItems 1) — so it is refused, never returned empty. A conforming emitter writes
    the frame's own node beside its children (§8's parenthetical), so such a document is
    hand-built.

    Args:
        ir: The newer document of the pair.
        floor: The older document's floor — the minor to project down to.

    Returns:
        A new :class:`WorkflowIR`, built through its constructor — rebuilt even when ``ir``
        carries nothing above ``floor``; ``ir`` itself when ``floor`` is ``"1.2"``, above which
        this build implements no minor.

    Raises:
        ValueError: if ``floor`` is not a version this build implements, or if every node of
            ``ir`` lies beneath an ``assign`` or ``each`` frame that is not the root, so the
            projection would leave no node.
        TypeError: when projecting below ``"1.2"``, if a node, edge or Σ value ``ir`` holds, a
            node's ``annotations`` or the document's ``runtime`` is not the model its field
            declares (a value planted past validation, or an object whose ``__class__`` claims
            the model; a subclass of the model is read as its base kind).
    """
    if not issubclass(type(floor), str) or _exact(floor) not in IR_VERSIONS:
        raise ValueError(
            f"the floor is not an ir_version this build implements ({', '.join(IR_VERSIONS)})"
        )
    if IR_VERSIONS.index(_exact(floor)) >= IR_VERSIONS.index(_IR_VERSION_1_2):
        return ir

    checked = tuple(_checked_node(node) for node in _members(ir.nodes))
    removed = {node_id for node_id, _ in checked if _frame_child(node_id)}
    nodes = tuple(
        _rebuilt_node(node_id, annotations)
        for node_id, annotations in checked
        if node_id not in removed
    )
    if not nodes:
        raise ValueError(
            "the down-projection removes every node of this document — each lies beneath an "
            "`assign` or `each` frame that is not the root — and a document needs one (IR-SPEC "
            "§2.1, `nodes` minItems 1), so it has no projection; a conforming emitter writes the "
            "frame's own node beside its children (§8)"
        )
    edges = tuple(
        _rebuilt_edge(edge)
        for edge in _members(ir.edges)
        if not any(_exact(end) in removed for end in _edge_ends(edge))
    )
    state = (
        None
        if ir.state is None
        else {
            _exact(key): _rebuilt_state_value(value)
            for key, value in dict.items(ir.state)
            if not (
                issubclass(type(value), StateField) and cast(StateField, value).managed is not None
            )
        }
    )
    runtime = ir.runtime
    if runtime is not None and not issubclass(type(runtime), Runtime):
        raise TypeError("a document's runtime is not a Runtime model")
    return WorkflowIR(
        ir_version=cast(IrVersion, _exact(ir.ir_version)),
        entry=_rebuilt_wiring(ir.entry),
        finish=_rebuilt_wiring(ir.finish),
        state=state,
        nodes=nodes,
        edges=edges,
        runtime=runtime,
    )
