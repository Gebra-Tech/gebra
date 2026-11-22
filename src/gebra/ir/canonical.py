"""Canonical serialization and the ``graph_version`` content hash — IR-SPEC §6.

This module implements the DEC-10 canonicalization pipeline (IR-SPEC §6.1) over an
already-validated :class:`~gebra.ir.models.WorkflowIR`:

1. **Parse** — owned by the caller: the input here *is* the §2 data model, so surface bytes
   (YAML styling, key order) are out of reach by construction and are never hashed.
2. **Project to hash scope** — the identity on a ``WorkflowIR``: every §6.4 exclusion row
   (``version``, ``extracted_from``, ``graph_version``, ``source_snippet``, notes fields) is
   a non-model field that ``extra="forbid"`` already refuses, exactly as §6.4 records.
3. **Omit- and representation-normalize** (§6.3) — drop optional members that are ``null``
   or equal their schema-declared default (the complete default list is
   ``edges[].kind = "normal"``) or are empty optional arrays; collapse ``entry``/``finish``
   to a scalar iff the wired set is a singleton, a ``state`` value to the bare type string
   iff it carries no ``reducer``, no ``optional`` and no ``managed`` flag, ``join_key`` to a
   scalar iff it declares one key, and a ``codomain`` equal to its edge's ``path_map`` keys
   to absence (the last three from ``ir_version`` 1.2 — DEC-40).
4. **Sort arrays** (§6.2) — ``nodes[]`` by escaped id as UTF-16 code units; ``edges[]``
   bytewise by each edge object's own canonical JCS serialization; the set-valued string
   arrays in UTF-16 code-unit order; a node's ``barriers`` groups each sorted as a set and
   the groups bytewise by their own JCS serialization (1.2); every other array (the
   ``args_schema`` interior) preserves authored order.
5. **Enforce scalar constraints** — IR validity, checked before any bytes or digest exist:
   identifier-role strings NFC, NaN/Infinity forbidden, integers within the I-JSON exact
   range ±(2⁵³−1). Per the ratified IR-D1 ruling (PD-004), an out-of-range integer is a
   :class:`CanonicalizationError`, and canonicalization never rewrites an integer as a
   string; per the same ruling's adjacent-gap closure the number constraints apply to every
   JSON number serialized, ``args_schema`` interiors included.
6. **Serialize** per RFC 8785 (JCS) to UTF-8 bytes — member names sorted as UTF-16 code
   units, no whitespace, ES number formatting.
7. **Digest** — SHA-256 over those bytes.
8. **Render** — ``"sha256:" + lowercase hex`` (the OCI digest grammar).
9. **Verify** — recompute and string-compare (:func:`verify_graph_version`).

:func:`canonical_bytes` performs steps 2–6, :func:`graph_version` adds 7–8, and
:func:`verify_graph_version` is step 9.

From ``ir_version`` 1.2 a node MAY carry a ``subgraph`` subdocument, a *level* of its own
(DEC-39): the same rules run over it, member by member and recursively, with no new rule —
§6.2's rows name a collection by its member name wherever it occurs.

**JCS is implemented in-house** rather than through a third-party dependency. The emitter's
input domain is closed (the trees this module itself builds), the two non-trivial parts —
the UTF-16 member sort and ES number formatting — are small and pinned by RFC-8785-derived
unit and property tests, and a digest pipeline this central should not float on an external
package's behavior.

**Where the rules run out, this module keeps to their letter.** Four consequences worth
knowing, each carried by a test:

* An **empty object member is preserved** (``annotations: {}``, ``runtime: {}``,
  ``state: {}``, and the ``interrupts`` object left empty after its empty arrays are
  omitted): §6.3 removes members that are ``null``, equal a declared default, or are empty
  optional *arrays* — its enumerations are exhaustive, and ``{}`` is none of the three.
* ``entry``/``finish`` **serialize the wired set**: duplicates collapse, so a duplicated
  singleton is a scalar. §6.3 makes the scalar form conditional on "the wired set is a
  singleton", and §4.2 (m5) requires each tuple's canonical surface to be unique — the
  edge set ``{(START, a)}`` cannot have two canonical spellings.
* The **other set-valued arrays sort but never dedupe** — no §6 rule removes their
  duplicates, so none are removed.
* Inside foreign content (``args_schema``), **``null``-valued members are dropped and
  ``null`` array items are kept**. The §6.1 step-3 null rule is not one of the
  Gebra-model-specific steps §3.6 enumerates when it exempts foreign objects, so it applies
  to every object serialized; array items are not members, and nothing authorizes touching
  them (array *order* in foreign content is likewise untouched, §6.2).

**Node-id-role strings** (``nodes[].id``, ``entry``/``finish``, ``from``/``to``,
``path_map`` values, ``runtime.interrupts`` entries, ``compensation.hook``, ``barriers``
members) get the step-5
NFC check on their *decoded* segments via :func:`~gebra.ir.identity.parse_node_id` — an
escape can end next to a combining mark, so the escaped text is the wrong thing to test. A
reference the §5.1 grammar does not admit at all is byte-preserved: NFC is the only step-5
string constraint, and whether a reference resolves is the reporting stage's question
(P-01's), not canonicalization's. The state-key-role strings (``state`` keys, ``input``/
``output`` entries, ``idempotent.key``, ``variant.key``, ``path_map`` labels, and from 1.2
the keys and values of ``projection.in``/``projection.out``, the ``codomain`` labels and the
``join_key`` keys) carry no escaping grammar and are NFC-checked verbatim. All other strings are byte-preserved
(§6.3) — except that every serialized string must consist of Unicode scalar values, since
step 6 emits UTF-8; a lone surrogate is an error, not a substitution.

Errors are :class:`CanonicalizationError` — a :class:`ValueError` carrying a stable
:class:`CanonicalizationErrorReason` code, the path of the offending value in authored
shape (aliased member names, authored array indexes), and the value itself. They are
IR-validity errors, never condition IDs: no verification envelope reports them.

Nothing here executes anything: the pipeline is a pure function from an in-memory model to
bytes (WA-07) — no I/O, no imports of workflow machinery, no callable ever invoked on
foreign content (foreign scalars and containers are read through unbound built-in
accessors, so no subclass hook runs).
"""

from __future__ import annotations

import hashlib
import math
import unicodedata
from enum import Enum
from typing import Final, TypeAlias

from gebra.ir.identity import NodeIdError, NodeIdErrorReason, parse_node_id
from gebra.ir.models import (
    Annotations,
    ConditionalEdge,
    DynamicEdge,
    Edge,
    Interrupts,
    Node,
    NormalEdge,
    Projection,
    Runtime,
    StateField,
    Subgraph,
    WorkflowIR,
)

__all__ = [
    "I_JSON_MAX_INT",
    "I_JSON_MIN_INT",
    "CanonicalizationError",
    "CanonicalizationErrorReason",
    "canonical_annotations_bytes",
    "canonical_bytes",
    "canonical_foreign_bytes",
    "graph_version",
    "render_digest",
    "verify_graph_version",
]

#: The I-JSON exact integer range (RFC 7493 §2.2), the bound IR-SPEC §6.3 and the ratified
#: IR-D1 ruling (PD-004) place on every integer the pipeline serializes.
I_JSON_MAX_INT: Final = 2**53 - 1
I_JSON_MIN_INT: Final = -(2**53 - 1)

#: The rendered digest prefix (IR-SPEC §6.1 step 8; OCI digest grammar).
_DIGEST_PREFIX: Final = "sha256:"

#: A JSON value as this module's canonical tree holds it between steps 5 and 6.
Json: TypeAlias = "None | bool | int | float | str | list[Json] | dict[str, Json]"

#: Where in the document a value sits — aliased member names, authored array indexes.
_Path: TypeAlias = tuple[str | int, ...]

#: The escapes RFC 8785 §3.2.2.2 requires beyond the generic control-character form.
_SHORT_ESCAPES: Final = {
    '"': '\\"',
    "\\": "\\\\",
    "\b": "\\b",
    "\f": "\\f",
    "\n": "\\n",
    "\r": "\\r",
    "\t": "\\t",
}


class CanonicalizationErrorReason(str, Enum):
    """Why canonicalization refused a document — a stable code to branch on.

    These are IR-validity codes, exactly like :class:`~gebra.ir.identity.NodeIdErrorReason`:
    they never reach a verification envelope, and the PROPERTY-CATALOG-SPEC §0.4 registry
    neither contains nor needs them. A document that raises one has no canonical bytes and
    no digest (IR-SPEC §6.1 step 5; PD-004).
    """

    INTEGER_OUT_OF_RANGE = "integer-out-of-range"
    NON_FINITE_NUMBER = "non-finite-number"
    IDENTIFIER_NOT_NFC = "identifier-not-nfc"
    NOT_A_SCALAR_VALUE = "not-a-scalar-value"
    NON_STRING_KEY = "non-string-key"
    UNSUPPORTED_TYPE = "unsupported-type"


class CanonicalizationError(ValueError):
    """A document the §6.1 step-5 scalar constraints (or step-6 serializability) refuse.

    Raised before any canonical bytes or digest exist — per PD-004 a failing document has
    neither. Subclassing :class:`ValueError` mirrors :class:`~gebra.ir.identity.NodeIdError`.

    Attributes:
        reason: The :class:`CanonicalizationErrorReason` code — match on this, not on text.
        path: Where the offending value sits, in authored shape: aliased member names
            (``"from"``), authored array indexes (pre-sort), foreign keys as written.
        value: The offending value itself.
    """

    def __init__(
        self,
        message: str,
        *,
        reason: CanonicalizationErrorReason,
        path: _Path,
        value: object,
    ) -> None:
        super().__init__(message)
        self.reason = reason
        self.path = path
        self.value = value


def canonical_bytes(ir: WorkflowIR) -> bytes:
    """The canonical serialization of ``ir`` — IR-SPEC §6.1 steps 2–6.

    The returned bytes are the RFC 8785 (JCS) UTF-8 serialization of the hash-scope
    projection of ``ir``, omit- and representation-normalized per §6.3 and array-sorted per
    §6.2. Byte-identical output for the same document is the §1.2 document-conformance
    contract; a single differing byte is non-conformance.

    Raises:
        CanonicalizationError: if the document violates a step-5 scalar constraint (non-NFC
            identifier, NaN/Infinity, an integer outside ±(2⁵³−1) — PD-004) or carries
            content JSON cannot represent (a lone surrogate, a non-string key, a foreign
            non-JSON type). No bytes are produced for such a document.
    """
    return _emit(_canonical_tree(ir))


def graph_version(ir: WorkflowIR) -> str:
    """The content digest of ``ir`` — §6.1 steps 2–8: ``"sha256:" + lowercase hex``.

    This string is the ``graph_version`` envelope field (§4.1) and the ``graph.version``
    telemetry attribute (§6.6). It matches the OCI grammar ``sha256:[a-f0-9]{64}``.

    Raises:
        CanonicalizationError: as for :func:`canonical_bytes`; an invalid document has no
            digest.
    """
    return render_digest(canonical_bytes(ir))


def render_digest(payload: bytes) -> str:
    """Digest-and-render — §6.1 steps 7–8: ``"sha256:" + lowercase hex``.

    The one digest renderer in the package. ``graph_version`` reaches it through the whole
    §6.1 pipeline; INTROSPECTION §7.4's ``prompt_digest``/``config_digest`` reach it with
    their own byte sources (the ratified DEC-15 pre-pass, whose finding 5 is that all three
    share one JCS emitter, one number formatter and one digest renderer). The output matches
    the OCI grammar ``sha256:[a-f0-9]{64}`` the three slots share.
    """
    return _DIGEST_PREFIX + hashlib.sha256(payload).hexdigest()


def canonical_foreign_bytes(value: object) -> bytes:
    """The JCS serialization of foreign JSON content — §3.6's foreign-object pipeline.

    IR-SPEC §3.6 states the pipeline for a foreign object in terms: "the Gebra-model-specific
    steps … act as the identity on a foreign config object, whose ``null``-valued members are
    still dropped … equivalently, drop nulls, serialize the object as-is per RFC 8785 JCS,
    digest per steps 7–8". This is the "drop nulls, serialize as-is" half, in the *same*
    emitter :func:`canonical_bytes` uses — which is why it exists here rather than beside its
    caller. INTROSPECTION §7.4 (c) composes it with :func:`render_digest` for ``config_digest``,
    and §7.4 (b) with the prompt canonical form.

    The step-5 number constraints (PD-004) still apply, exactly as they do inside an
    ``args_schema``: an out-of-range integer or a non-finite float is a
    :class:`CanonicalizationError` rather than a silently altered digest. A caller that must
    stay total pre-resolves those values before calling — which is what §7.4 (d)'s coercion
    does, and why this function raising is a caller's bug rather than a document's invalidity.

    Raises:
        CanonicalizationError: for content JSON cannot carry — a non-string mapping key, a
            lone surrogate, a non-finite number, an out-of-I-JSON-range integer, or a type
            outside the JSON data model.
    """
    return _emit(_foreign(value, ()))


def canonical_annotations_bytes(annotations: Annotations) -> bytes:
    """The canonical serialization of one ``annotations`` object, on its own.

    Steps 3–6 of §6.1 applied to the sub-document rather than to a whole ``WorkflowIR``, in
    the *same* emitter :func:`canonical_bytes` uses — which is the point of it existing.
    ANNOTATION-API-SPEC §3 decides whether two declarations of one slot are "identical
    values" structurally: "two slot values are identical **iff** their ledger §6
    canonicalizations (omit-normalize → RFC 8785 JCS bytes) are byte-equal". A second
    implementation of that projection would be a second opinion about a question whose whole
    purpose is that there is only one, so the precedence chain asks this function instead of
    re-deriving §6.3 for a slot.

    Nothing about the result is a digest and nothing here reads a document: the bytes are
    the contract's own JCS object, so ``{}`` comes back for a contract whose every member is
    absent or omit-normalized away.

    Raises:
        CanonicalizationError: exactly as :func:`canonical_bytes` — a non-NFC identifier, a
            lone surrogate, a non-finite number, an out-of-I-JSON-range integer, or foreign
            content JSON cannot carry. A caller resolving contracts uses this to find out
            *before* it emits a node whether the node it is about to emit has a
            ``graph_version``.
    """
    return _emit(_annotations(annotations, ("annotations",)))


def verify_graph_version(ir: WorkflowIR, digest: str) -> bool:
    """Recompute-and-compare (§6.1 step 9, the §1.2 conformance operation).

    Recomputes the digest of ``ir`` and compares it to ``digest`` as strings — exact,
    case-sensitive equality, per §1.2 ("string-compares equal"). No parsing or
    normalization is applied to ``digest``.

    Raises:
        CanonicalizationError: as for :func:`canonical_bytes`.
    """
    return graph_version(ir) == digest


# ── Steps 2–5: the typed walk ────────────────────────────────────────────────────────────
#
# One function per model shape, each returning its member's canonical JSON subtree. Member
# insertion order is irrelevant throughout — the emitter sorts names (step 6) — so each
# function reads in declaration order and lets the constraints fire with authored paths.


def _canonical_tree(ir: WorkflowIR) -> Json:
    """Steps 2–5 over the whole document. Projection (step 2) is the identity here: a
    ``WorkflowIR`` cannot carry a §6.4-excluded field in the first place."""
    tree: dict[str, Json] = {"ir_version": ir.ir_version}
    tree.update(_level(ir, ()))
    return tree


def _level(level: WorkflowIR | Subgraph, path: _Path) -> dict[str, Json]:
    """The six members a level carries (§2.1; a ``subgraph`` subdocument from 1.2 — §3.8).

    The top-level document and every subdocument share these members, their shapes and their
    §6 rules, so one function serves both: a ``subgraph`` is the same walk one level down, its
    REQUIRED members (``entry``, ``finish``, ``nodes``, ``edges``) never omitted (§6.3).
    """
    tree: dict[str, Json] = {}
    tree["entry"] = _wired_set(level.entry, (*path, "entry"))
    tree["finish"] = _wired_set(level.finish, (*path, "finish"))
    if level.state is not None:
        tree["state"] = _state(level.state, (*path, "state"))
    tree["nodes"] = _nodes(level.nodes, (*path, "nodes"))
    tree["edges"] = _edges(level.edges, (*path, "edges"))
    if level.runtime is not None:
        tree["runtime"] = _runtime(level.runtime, (*path, "runtime"))
    return tree


def _wired_set(value: str | tuple[str, ...], path: _Path) -> Json:
    """``entry``/``finish``: a scalar node id iff the wired set is a singleton (§6.3).

    The list form is a set of wired sentinels' neighbors (§2.1, §4.2 m1/m2), so duplicates
    collapse and the survivors sort as UTF-16 code units (§6.2). §4.2 (m5) is why the
    collapse is not optional: the edge set ``{(START, a)}`` has exactly one canonical
    surface, and ``["a", "a"]`` must land on it.
    """
    if isinstance(value, str):
        return _node_reference(value, path)
    for index, item in enumerate(value):
        _node_reference(item, (*path, index))
    wired = sorted(set(value), key=_utf16_sort_key)
    if len(wired) == 1:
        return wired[0]
    return [*wired]


def _state(state: dict[str, str | StateField], path: _Path) -> Json:
    """The Σ mapping (§2.2): NFC keys; values collapse per §6.3."""
    members: dict[str, Json] = {}
    for key, value in state.items():
        key_path = (*path, key)
        _identifier(key, key_path)
        if isinstance(value, str):
            members[key] = _plain_string(value, key_path)
        else:
            members[key] = _state_value(value, key_path)
    return members


def _state_value(value: StateField, path: _Path) -> Json:
    """A ``state`` value collapses to the bare type string iff it carries no ``reducer``,
    no ``optional`` and no ``managed`` flag (§6.3; the third from 1.2 — DEC-40); an explicit
    ``optional: false`` is a carried flag, not the schema default (``null``), so it keeps the
    object form. ``managed`` admits only ``true``, so a carried flag is always serialized."""
    if value.reducer is None and value.optional is None and value.managed is None:
        return _plain_string(value.type, (*path, "type"))
    members: dict[str, Json] = {"type": _plain_string(value.type, (*path, "type"))}
    if value.reducer is not None:
        members["reducer"] = _plain_string(value.reducer, (*path, "reducer"))
    if value.optional is not None:
        members["optional"] = value.optional
    if value.managed is not None:
        members["managed"] = value.managed
    return members


def _nodes(nodes: tuple[Node, ...], path: _Path) -> Json:
    """``nodes[]``, sorted by ``id`` (escaped form) as UTF-16 code units (§6.2).

    From 1.2 a node's ``subgraph`` is a level of its own, walked recursively (§3.8), and its
    ``barriers`` groups are omitted when empty and sorted per §6.2 otherwise (§3.11).
    """
    keyed: list[tuple[str, Json]] = []
    for index, node in enumerate(nodes):
        node_path = (*path, index)
        tree: dict[str, Json] = {"id": _node_reference(node.id, (*node_path, "id"))}
        if node.annotations is not None:
            tree["annotations"] = _annotations(node.annotations, (*node_path, "annotations"))
        if node.subgraph is not None:
            tree["subgraph"] = _level(node.subgraph, (*node_path, "subgraph"))
        if node.barriers is not None and node.barriers != ():
            tree["barriers"] = _barriers(node.barriers, (*node_path, "barriers"))
        keyed.append((node.id, tree))
    keyed.sort(key=lambda pair: _utf16_sort_key(pair[0]))
    return [tree for _, tree in keyed]


def _annotations(annotations: Annotations, path: _Path) -> Json:
    """A node contract (§2.3 + §3). Empty optional arrays are treated as absent (§6.3);
    an annotations object left with no members serializes as ``{}`` — see the module
    docstring."""
    members: dict[str, Json] = {}
    if annotations.pure is not None:
        members["pure"] = annotations.pure
    if annotations.effect is not None and annotations.effect != ():
        members["effect"] = _string_set(annotations.effect, (*path, "effect"), identifiers=False)
    if annotations.idempotent is not None:
        if isinstance(annotations.idempotent, bool):
            members["idempotent"] = annotations.idempotent
        else:
            key_path = (*path, "idempotent", "key")
            members["idempotent"] = {"key": _identifier(annotations.idempotent.key, key_path)}
    if annotations.deterministic is not None:
        if isinstance(annotations.deterministic, bool):
            members["deterministic"] = annotations.deterministic
        else:
            spec_path = (*path, "deterministic")
            spec: dict[str, Json] = {
                "seed": _integer(annotations.deterministic.seed, (*spec_path, "seed"))
            }
            if annotations.deterministic.temperature is not None:
                temperature_path = (*spec_path, "temperature")
                spec["temperature"] = _finite(
                    annotations.deterministic.temperature, temperature_path
                )
            members["deterministic"] = spec
    if annotations.input is not None and annotations.input != ():
        members["input"] = _string_set(annotations.input, (*path, "input"), identifiers=True)
    if annotations.output is not None and annotations.output != ():
        members["output"] = _string_set(annotations.output, (*path, "output"), identifiers=True)
    if annotations.source is not None:
        members["source"] = _plain_string(annotations.source, (*path, "source"))
    if annotations.map is not None:
        members["map"] = _plain_string(annotations.map, (*path, "map"))
    if annotations.args_schema is not None:
        members["args_schema"] = _foreign(annotations.args_schema, (*path, "args_schema"))
    if annotations.retry_policy is not None:
        policy_path = (*path, "retry_policy")
        members["retry_policy"] = {
            # `retry_on` is REQUIRED within its object (§2.5), so an empty tuple is
            # serialized, never omitted — the §6.3 empty-array rule covers optional
            # members only.
            "max_attempts": _integer(
                annotations.retry_policy.max_attempts, (*policy_path, "max_attempts")
            ),
            "retry_on": _string_set(
                annotations.retry_policy.retry_on, (*policy_path, "retry_on"), identifiers=False
            ),
        }
    if annotations.variant is not None:
        members["variant"] = {
            "key": _identifier(annotations.variant.key, (*path, "variant", "key")),
            "measure": _plain_string(annotations.variant.measure, (*path, "variant", "measure")),
        }
    if annotations.compensation is not None:
        hook_path = (*path, "compensation", "hook")
        members["compensation"] = {
            "hook": _node_reference(annotations.compensation.hook, hook_path)
        }
    if annotations.prompt_digest is not None:
        members["prompt_digest"] = _plain_string(
            annotations.prompt_digest, (*path, "prompt_digest")
        )
    if annotations.config_digest is not None:
        members["config_digest"] = _plain_string(
            annotations.config_digest, (*path, "config_digest")
        )
    if annotations.projection is not None:
        members["projection"] = _projection(annotations.projection, (*path, "projection"))
    if annotations.join_key is not None:
        members["join_key"] = _join_key(annotations.join_key, (*path, "join_key"))
    return members


def _projection(projection: Projection, path: _Path) -> Json:
    """``annotations.projection`` (§3.9; 1.2 — DEC-39): two REQUIRED maps, never omitted —
    an empty one is written ``{}``. Keys and values are state keys of two levels, so both are
    identifier-role (NFC, §6.3); JCS sorts the member names and no Gebra rule is needed."""
    return {
        "in": _identifier_map(projection.in_, (*path, "in")),
        "out": _identifier_map(projection.out, (*path, "out")),
    }


def _identifier_map(mapping: dict[str, str], path: _Path) -> Json:
    """A state-key → state-key map: both sides NFC-checked verbatim (§6.3)."""
    members: dict[str, Json] = {}
    for key, value in mapping.items():
        key_path = (*path, key)
        _identifier(key, key_path)
        members[key] = _identifier(value, key_path)
    return members


def _join_key(join_key: str | tuple[str, ...], path: _Path) -> Json:
    """``annotations.join_key`` (§3.10; 1.2 — DEC-40): a scalar string iff the declared key
    set is a singleton, a sorted list otherwise (§6.3, the ``entry``/``finish`` rule; §6.2).

    Never deduplicated: the model refuses a repeated member (§3.10's validity MUST), so a
    one-member list is the singleton it looks like and collapses to its scalar.
    """
    if isinstance(join_key, str):
        return _identifier(join_key, path)
    for index, key in enumerate(join_key):
        _identifier(key, (*path, index))
    keys = sorted(join_key, key=_utf16_sort_key)
    if len(keys) == 1:
        return keys[0]
    return [*keys]


def _edges(edges: tuple[Edge, ...], path: _Path) -> Json:
    """``edges[]``, sorted bytewise by each edge object's own canonical JCS serialization
    (§6.2) — a total order over the *normalized* edge (a ``normal`` edge sorts without its
    omitted ``kind``, exactly as the §6.5 worked example shows). Constraint errors fire
    while each edge is serialized for its sort key, so their paths carry authored indexes.
    """
    trees = [_edge(edge, (*path, index)) for index, edge in enumerate(edges)]
    blobs = [_emit(tree) for tree in trees]
    order = sorted(range(len(trees)), key=blobs.__getitem__)
    return [trees[index] for index in order]


def _edge(edge: Edge, path: _Path) -> Json:
    """One edge (§2.4). ``kind: "normal"`` is the one non-null schema-declared default of
    ir 1.0 and is omitted (§6.3); the discriminating kinds are content and stay.

    The three target shapes are the three kinds' own: a ``conditional`` edge carries
    ``path_map`` and no ``to``, a ``dynamic`` edge (ir 1.1 — DEC-28) carries **neither**, and
    ``normal``/``send`` carry ``to``. The ``dynamic`` branch adds no member and removes none,
    which is the mechanical half of DEC-28's digest-invariance ruling: nothing on this path
    changes for a document that has no ``dynamic`` edge in it.
    """
    members: dict[str, Json] = {"from": _node_reference(edge.from_, (*path, "from"))}
    if not isinstance(edge, NormalEdge):
        members["kind"] = edge.kind
    if isinstance(edge, ConditionalEdge):
        members["path_map"] = _path_map(edge.path_map, (*path, "path_map"))
        codomain = _codomain(edge, (*path, "codomain"))
        if codomain is not None:
            members["codomain"] = codomain
    elif not isinstance(edge, DynamicEdge):
        members["to"] = _node_reference(edge.to, (*path, "to"))
    if edge.condition is not None:
        members["condition"] = _plain_string(edge.condition, (*path, "condition"))
    return members


def _path_map(mapping: dict[str, str], path: _Path) -> Json:
    """``path_map`` — a JSON object, so JCS member sorting needs no Gebra rule (§6.2).
    Labels are identifier-role (NFC, §6.3); values are node-id-role references."""
    members: dict[str, Json] = {}
    for label, target in mapping.items():
        label_path = (*path, label)
        _identifier(label, label_path)
        members[label] = _node_reference(target, label_path)
    return members


def _codomain(edge: ConditionalEdge, path: _Path) -> Json | None:
    """A ``conditional`` edge's ``codomain`` (§2.4; 1.2 — DEC-40), or ``None`` for absence.

    ``[]`` is an empty optional array, omitted (§6.3). Otherwise every member is NFC-checked
    first — "the constraint is enforced on every authored member before this rule removes one"
    (§6.3) — and then the set is **omitted iff it equals the NFC key set of the same edge's
    ``path_map``**: an agreeing declaration restates the edge, so one canonical form carries it.
    A distinct set is a set-valued array, sorted and never deduplicated (§6.2; the model refuses
    a repeated label). The ``path_map`` labels have been NFC-checked by :func:`_path_map`
    already, so both sides compare as the NFC sets they are.
    """
    if edge.codomain is None or edge.codomain == ():
        return None
    labels = _string_set(edge.codomain, path, identifiers=True)
    if set(edge.codomain) == set(edge.path_map):
        return None
    return labels


def _barriers(groups: tuple[tuple[str, ...], ...], path: _Path) -> Json:
    """A node's ``barriers`` (§3.11; 1.2 — DEC-40), canonical per §6.2's two rows.

    Each group is a set of node ids — node-id-role strings, NFC-checked on their decoded
    segments — sorted in UTF-16 code-unit order; the outer array is a set of groups, sorted
    bytewise by each group's own canonical JCS serialization (the ``edges[]`` comparator
    applied to the inner arrays after each is sorted). Nothing is deduplicated at either level:
    distinct members and distinct groups are the model's validity MUSTs, refused at load.
    """
    trees = [_node_reference_set(group, (*path, index)) for index, group in enumerate(groups)]
    blobs = [_emit(tree) for tree in trees]
    order = sorted(range(len(trees)), key=blobs.__getitem__)
    return [trees[index] for index in order]


def _runtime(runtime: Runtime, path: _Path) -> Json:
    """The graph-level config block (§3.5, §3.7); all sub-slots optional, all in scope."""
    members: dict[str, Json] = {}
    if runtime.recursion_limit is not None:
        limit_path = (*path, "recursion_limit")
        members["recursion_limit"] = {
            "value": _integer(runtime.recursion_limit.value, (*limit_path, "value")),
            "justification": _plain_string(
                runtime.recursion_limit.justification, (*limit_path, "justification")
            ),
        }
    if runtime.interrupts is not None:
        members["interrupts"] = _interrupts(runtime.interrupts, (*path, "interrupts"))
    if runtime.checkpointer is not None:
        # `present` is REQUIRED within its object and has no default (§3.7), so
        # `{present: false}` serializes and stays distinct from slot absence.
        members["checkpointer"] = {"present": runtime.checkpointer.present}
    return members


def _interrupts(interrupts: Interrupts, path: _Path) -> Json:
    """``runtime.interrupts`` (§3.7): an empty ``before``/``after`` is omitted, so the
    empty-array form and member absence share one canonical form."""
    members: dict[str, Json] = {}
    if interrupts.before is not None and interrupts.before != ():
        members["before"] = _node_reference_set(interrupts.before, (*path, "before"))
    if interrupts.after is not None and interrupts.after != ():
        members["after"] = _node_reference_set(interrupts.after, (*path, "after"))
    return members


# ── Step 5: the scalar constraints (IR validity, pre-hash) ───────────────────────────────


def _integer(value: int, path: _Path) -> int:
    """§6.3 integer range, per the ratified IR-D1 ruling (PD-004): within ±(2⁵³−1) or an
    IR validity error — never stringified. Applies to every integer serialized, model
    fields and foreign interiors alike (the PD-004 adjacent-gap closure)."""
    if not I_JSON_MIN_INT <= value <= I_JSON_MAX_INT:
        raise CanonicalizationError(
            f"{_at(path)} is {value}, outside the I-JSON exact integer range "
            "±(2**53−1) (IR-SPEC §6.3; PD-004: an out-of-range integer is an IR validity "
            "error before hashing, and canonicalization never rewrites an integer as a "
            "string)",
            reason=CanonicalizationErrorReason.INTEGER_OUT_OF_RANGE,
            path=path,
            value=value,
        )
    return value


def _finite(value: float, path: _Path) -> float:
    """§6.1 step 5: NaN/Infinity forbidden. A finite double always has one JCS rendering,
    so no other constraint applies to non-integer numbers."""
    if not math.isfinite(value):
        raise CanonicalizationError(
            f"{_at(path)} is {value!r} (IR-SPEC §6.1 step 5: NaN and Infinity are "
            "forbidden — they have no JSON representation)",
            reason=CanonicalizationErrorReason.NON_FINITE_NUMBER,
            path=path,
            value=value,
        )
    return value


def _plain_string(value: str, path: _Path) -> str:
    """Any serialized string: byte-preserved verbatim (§6.3), but it must consist of
    Unicode scalar values — step 6 emits UTF-8, and a lone surrogate has no encoding."""
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        raise CanonicalizationError(
            f"{_at(path)} contains a lone surrogate (IR-SPEC §6.1 step 6 serializes to "
            "UTF-8, and a surrogate code point is not a Unicode scalar value)",
            reason=CanonicalizationErrorReason.NOT_A_SCALAR_VALUE,
            path=path,
            value=value,
        ) from None
    return value


def _identifier(value: str, path: _Path) -> str:
    """A state-key-role string (§6.3: ``state`` keys, ``input``/``output`` entries,
    ``idempotent.key``, ``variant.key``, ``path_map`` labels): NFC, checked verbatim —
    these carry no escaping grammar."""
    _plain_string(value, path)
    if not unicodedata.is_normalized("NFC", value):
        raise CanonicalizationError(
            f"{_at(path)} is not NFC-normalized (IR-SPEC §6.3: identifier-role strings "
            "are NFC; byte equality is only a sound comparison over one normal form)",
            reason=CanonicalizationErrorReason.IDENTIFIER_NOT_NFC,
            path=path,
            value=value,
        )
    return value


def _node_reference(value: str, path: _Path) -> str:
    """A node-id-role string: the step-5 NFC check runs on the *decoded* segments, via the
    §5 parser, because an escape can leave a combining mark next to a composable base
    character in the escaped text. A string §5.1 does not admit at all (a malformed
    escape, a reserved or empty segment) is byte-preserved: NFC is the only step-5 string
    constraint, and whether the reference resolves is the reporting stage's question."""
    _plain_string(value, path)
    try:
        parse_node_id(value)
    except NodeIdError as error:
        if error.reason is NodeIdErrorReason.NOT_NFC:
            raise CanonicalizationError(
                f"{_at(path)} is not NFC-normalized: {error} (IR-SPEC §6.3: node-id "
                "segments are identifier-role strings, checked on the decoded form)",
                reason=CanonicalizationErrorReason.IDENTIFIER_NOT_NFC,
                path=path,
                value=value,
            ) from error
    return value


def _string_set(values: tuple[str, ...], path: _Path, *, identifiers: bool) -> Json:
    """A set-valued string array (§6.2): UTF-16 code-unit order. Sorted, never deduped —
    no §6 rule removes duplicates from these arrays (contrast :func:`_wired_set`)."""
    for index, item in enumerate(values):
        if identifiers:
            _identifier(item, (*path, index))
        else:
            _plain_string(item, (*path, index))
    return [*sorted(values, key=_utf16_sort_key)]


def _node_reference_set(values: tuple[str, ...], path: _Path) -> Json:
    """A set-valued array of node-id-role references (``interrupts.before``/``after``)."""
    for index, item in enumerate(values):
        _node_reference(item, (*path, index))
    return [*sorted(values, key=_utf16_sort_key)]


def _foreign(value: object, path: _Path) -> Json:
    """Foreign JSON content, carried verbatim (§6.2 — the ``args_schema`` interior).

    The Gebra-model-specific steps are the identity here, but two generic rules still
    apply (§3.6's clarification pattern): ``null``-valued members are dropped, and the
    step-5 number constraints hold everywhere (PD-004 adjacent-gap closure). Array items —
    ``null`` included — and array order are untouched.

    Scalars and containers are read through unbound built-in accessors so that no subclass
    hook ever runs on foreign content (WA-07 discipline; the same pattern
    :func:`~gebra.ir.identity.synthetic_segment` uses). Anything that is not JSON data is
    an error — never coerced, since coercion here would be silent digest divergence.
    """
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        return _integer(int.__index__(value), path)
    if isinstance(value, float):
        return _finite(float.__float__(value), path)
    if isinstance(value, str):
        return _plain_string(str.__str__(value), path)
    if isinstance(value, dict):
        members: dict[str, Json] = {}
        for key, member in dict.items(value):
            if not isinstance(key, str):
                # `repr()` on a foreign object would run its own code; describe the
                # exact builtins and name every other type (WA-07).
                described = repr(key) if type(key) in (bool, int, float) else type(key).__name__
                raise CanonicalizationError(
                    f"{_at(path)} has the non-string key {described} (a JSON object "
                    "member name is a string; coercing one would be silent digest "
                    "divergence)",
                    reason=CanonicalizationErrorReason.NON_STRING_KEY,
                    path=path,
                    value=key,
                )
            # The exact-str copy rides in the path too, so no error path ever formats
            # a foreign str subclass (WA-07).
            name = str.__str__(key)
            _plain_string(name, (*path, name))
            if member is None:
                continue
            members[name] = _foreign(member, (*path, name))
        return members
    if isinstance(value, list):
        return [_foreign(item, (*path, index)) for index, item in enumerate(list.__iter__(value))]
    if isinstance(value, tuple):
        return [_foreign(item, (*path, index)) for index, item in enumerate(tuple.__iter__(value))]
    raise CanonicalizationError(
        f"{_at(path)} is of type {type(value).__name__}, which JSON cannot carry "
        "(IR-SPEC §6.1 step 6 serializes JSON data only)",
        reason=CanonicalizationErrorReason.UNSUPPORTED_TYPE,
        path=path,
        value=value,
    )


def _at(path: _Path) -> str:
    """Render a path for an error message: ``nodes[0].annotations.args_schema.maximum``."""
    if not path:
        return "the document"
    rendered = ""
    for part in path:
        if isinstance(part, int):
            rendered += f"[{part}]"
        elif rendered:
            rendered += f".{part}"
        else:
            rendered = part
    return rendered


# ── Step 6: RFC 8785 (JCS) emission ──────────────────────────────────────────────────────


def _utf16_sort_key(value: str) -> bytes:
    """The RFC 8785 §3.2.3 comparator: UTF-16 code units, compared as unsigned values.

    Big-endian UTF-16 makes bytewise comparison identical to code-unit-wise comparison —
    and it differs from code-*point* order exactly where the plane-1+ characters sit: a
    surrogate pair's lead unit (D800–DBFF) sorts *below* the BMP range E000–FFFF.
    """
    return value.encode("utf-16-be")


def _emit(value: object) -> bytes:
    """Serialize a canonical tree per RFC 8785 to UTF-8 bytes: member names sorted as
    UTF-16 code units, no whitespace, ES number formatting.

    The walk (steps 2–5) has already vetted every scalar, so a tree this module built
    emits without raising; handing the emitter anything else is a :class:`TypeError` — a
    programming error, not document invalidity.
    """
    if value is None:
        return b"null"
    if value is True:
        return b"true"
    if value is False:
        return b"false"
    if isinstance(value, str):
        return _emit_string(value)
    if isinstance(value, int):
        return str(value).encode("ascii")
    if isinstance(value, float):
        return _format_double(value).encode("ascii")
    if isinstance(value, list):
        return b"[" + b",".join(_emit(item) for item in value) + b"]"
    if isinstance(value, dict):
        members = sorted(value.items(), key=lambda item: _utf16_sort_key(item[0]))
        return (
            b"{"
            + b",".join(_emit_string(name) + b":" + _emit(member) for name, member in members)
            + b"}"
        )
    raise TypeError(f"not a canonical-tree value: {type(value).__name__}")


def _emit_string(value: str) -> bytes:
    """RFC 8785 §3.2.2.2: escape ``"``, ``\\``, and the C0 controls (short forms where
    defined, lowercase ``\\u00xx`` otherwise); everything else is literal UTF-8."""
    pieces = ['"']
    for character in value:
        if character in _SHORT_ESCAPES:
            pieces.append(_SHORT_ESCAPES[character])
        elif character < " ":
            pieces.append(f"\\u{ord(character):04x}")
        else:
            pieces.append(character)
    pieces.append('"')
    return "".join(pieces).encode("utf-8")


def _format_double(value: float) -> str:
    """A finite double per RFC 8785 §3.2.2.3 — ECMAScript ``Number::toString`` base 10.

    CPython's ``repr`` supplies exactly the digits ECMAScript requires (the shortest
    decimal significand that round-trips); what differs is the *rendering*, so this
    function re-formats those digits under the ES rules: plain integer up to 10²¹,
    positional decimal down to 10⁻⁶, exponent notation (sign always on the exponent,
    no zero padding) beyond either bound. ``-0.0`` renders as ``"0"``.

    The caller has excluded NaN and the infinities (step 5); they reach ``repr`` never.
    """
    if value == 0.0:
        return "0"
    if value < 0.0:
        return "-" + _format_double(-value)
    shortest = repr(value)
    mantissa, _, exponent_text = shortest.partition("e")
    integral, _, fraction = mantissa.partition(".")
    combined = integral + fraction
    digits = combined.strip("0")
    leading_zeros = len(combined) - len(combined.lstrip("0"))
    point = len(integral) + int(exponent_text or "0") - leading_zeros
    length = len(digits)
    if length <= point <= 21:
        return digits + "0" * (point - length)
    if 0 < point <= 21:
        return digits[:point] + "." + digits[point:]
    if -6 < point <= 0:
        return "0." + "0" * -point + digits
    exponent = point - 1
    head = digits if length == 1 else digits[0] + "." + digits[1:]
    return f"{head}e{'+' if exponent >= 0 else '-'}{abs(exponent)}"
