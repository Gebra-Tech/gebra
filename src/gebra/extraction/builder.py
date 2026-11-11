"""``StateGraph`` (builder) extraction — the INTROSPECTION-SPEC §3 rule set.

Normative authority: INTROSPECTION-SPEC §3 (the per-attribute mapping table), §2 (the
degenerate-input rule and the error posture), §8 (the warnings taxonomy), and IR-SPEC §4.2
(what ``entry``/``finish`` mean as sentinel incidences), all under the §1 never-invokes
discipline and DEC-06's builder-authoritative ruling.

**The whole path is attribute reads.** §1 rule 3 fixes the permitted operations; this module
uses the narrowest subset of them — it reads ``builder.nodes``, ``.edges``, ``.waiting_edges``
and ``.branches``, plus four members of each ``StateNodeSpec`` — and calls nothing on the
objects it finds there. No node function, router or ``Runnable`` is invoked, ``compile()`` is
never called (§1 rule 2), no type hint is evaluated, and no network connection is opened.
``tests/extraction/test_builder.py`` is the tripwire that holds this to account, in a fresh
interpreter where every sentinel raises and ``StateGraph.compile`` is taken away.

**Reading the code against the spec.** :func:`_read` is a transcription of §3's table, one
private function per row, so a reviewer can check the rows off one at a time. The rows that
belong to other cards are named where they would go rather than left to be noticed:

* ``StateNodeSpec.runnable`` — §3 reads this member "for exactly three purposes", and this
  path performs the second: **contract attachment**, through
  :mod:`gebra.extraction.contracts`, which walks the ANNOTATION §6 wrapper chain and runs the
  §3 precedence chain (decorator > tool-carried > sidecar > inference) over what it finds. The
  other two — fragment discovery (§5) and digest computation (§7.4) — are their own cards, and
  nothing here reads the member for either. So a node's ``annotations`` now carries the
  resolved contract together with the ``retry_policy`` §3 projects from the builder, and a
  node with neither carries none at all.
* ``.channels``/state schema — read here, by :mod:`gebra.extraction.state`, which owns the
  §3 ``state`` row end to end (the type/reducer/optional projection, the §6.3 collapse, and
  the managed-value split that keeps those keys in provenance rather than in Σ).
* ``runtime`` — interrupts and the checkpointer are compiled-level surfaces that §3 records
  as "absent (never guessed) at builder level" (§7.1), and ``recursion_limit`` is
  annotation-only. So the block is absent here by all three routes.

**Where this path stops — the boundary refusals, and why only these.** §2 puts hard failure
at the object boundary and nowhere else ("extraction is total over supported objects"), so a
construct this path cannot map is warned inside the IR rather than raised. Three routing
shapes are still refused, because for each every other option is ruled out in terms:

* A non-string routing label outside the one form INTROSPECTION-SPEC §6 admits. ir 1.0/1.1
  types a ``path_map`` key ``str`` and the substrate types it ``Hashable``; §6 spells a ``str``
  instance verbatim and a plain ``Enum`` member whose stored value is an exact ``str`` by that
  value (DEC-32, amended by DEC-38 — the dispatch is
  :func:`gebra.extraction.routing.spell_routing_label`), and refuses everything else. Coercing
  would fix a digest surface by improvisation *and* run the label's own ``__str__``.
* A routing *target* that is not a string. Targets are node names or END; the admission is
  for labels only (DEC-38 §3.5), so a member in a target position is refused before any
  comparison, hashing or escaping can run one of its methods.
* Two declared routing labels resolving to one ``path_map`` key after projection — NFC
  normalization, or an admitted enum member's stored value meeting a string label (DEC-32
  ruling 2, its reach restated at DEC-38: an error, never a merge — a merged key silently drops
  a declared edge from ``graph_version``).

Everything else extracts. In particular ``StateNodeSpec.ends`` — which the substrate fills
from ``destinations=`` **and from a ``Command[Literal[...]]`` return annotation** — is
emitted, not refused; and a router that declares **no** targets is no longer refused either
(below).

**§6's classification, which is this module's other half.** Two rules meet on every routing
declaration:

* *The kind.* :mod:`gebra.extraction.routing` reads the declaration's own **declared
  return-type hint** — never its body (§6, §1) — and a hint naming ``Send`` classifies the
  declaration ``kind: send``. Everything else, including an unreadable hint and no hint at
  all, is ``kind: conditional``: the pole §6 sends an unclassifiable router to, because a
  conditional edge over declared targets claims strictly less than a send template does.
* *The targets.* Classification "licenses the kind only": emitting either kind needs declared
  targets. A declaration with none is §6's targetless form and emits
  ``{from, kind: dynamic, condition}`` (ratified — DEC-28, 2026-08-09, ir 1.1; PD-041
  resolves the disposition DEC-18 D4 deferred) plus the ``unsupported-construct`` §8 keeps for
  dynamic dispatch. The DEC-18 fences are untouched and are why the new kind exists at all:
  ``path_map: {}`` would silently assert "complete and empty" on a ``conditional`` edge, and
  omitting the edge would delete the router from hash scope and turn a warning into a P-01
  FATAL false positive. The ``dynamic`` kind has no ``path_map`` member to leave empty and is
  in hash scope like any other edge.

**And §6's third rule, which has no ir carrier.** A ``Literal[...]`` return hint declaring a
codomain *distinct* from the declared ``path_map`` is read and recorded in provenance —
``extracted_from.router_codomains`` — never merged into ``path_map``. ir 1.0 has no codomain
slot (§7.3 item 5), so beside the IR is the only place it can go. The record is a ``.branches``
router's only: a node routing declaration (``StateNodeSpec.ends``) is keyed by its *targets*,
and the ``Command[Literal[...]]`` hint beside it names goto targets too, so comparing that hint
with the declaration's labels would record a disagreement on every ``destinations=`` dict whose
labels are not its targets.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Final, Literal, TypeGuard, cast

from langgraph.graph import END, START
from langgraph.types import RetryPolicy as SubstrateRetryPolicy

from gebra.annotations.contract import NodeContract
from gebra.annotations.inference import SourceCache
from gebra.annotations.sidecar import SidecarReading
from gebra.extraction.base import ObjectFamily, type_identity
from gebra.extraction.contracts import resolve_node, state_schema_of
from gebra.extraction.digests import NodeDigests, digests_for
from gebra.extraction.envelope import ExtractedFrom, ExtractionEnvelope, RouterCodomain
from gebra.extraction.errors import ExtractionError, ExtractionErrorReason
from gebra.extraction.routing import RouterHint, declared_return_hint, spell_routing_label
from gebra.extraction.sidecar import sidecar_warnings, unknown_node_warnings
from gebra.extraction.state import read_state
from gebra.extraction.warnings import ExtractionWarning, ExtractionWarningCode
from gebra.ir.identity import RESERVED_SEGMENTS, NodeIdError, node_id_from_names
from gebra.ir.models import (
    Annotations,
    ConditionalEdge,
    DynamicEdge,
    Edge,
    Node,
    NormalEdge,
    RetryPolicy,
    SendEdge,
    StateField,
    WorkflowIR,
    lowest_ir_version,
)

if TYPE_CHECKING:
    from langgraph.graph.state import StateGraph

    from gebra.extraction.dispatch import Dispatch

__all__ = ["extract_builder"]

#: The IR spelling of the END sentinel inside a ``path_map`` (IR-SPEC §2.4/§4.2 (m3)).
#:
#: The substrate stores the raw ``"__end__"`` in ``BranchSpec.ends``, while the ledger and
#: IR-SPEC bless only the literal ``"END"``; §3 says "``BranchSpec.ends`` → ``path_map`` when
#: present" and never states the translation. This is the forced reading recorded with
#: DEC-18: ``"__end__"`` is a reserved segment the IR never emits (§5.1), so passing it
#: through would make P-01 report a target that does not exist — one direction is viable and
#: this is it.
END_LABEL: Final = "END"


def extract_builder(
    dispatch: Dispatch, /, *, sidecar: SidecarReading | None = None
) -> ExtractionEnvelope:
    """Extract an uncompiled ``StateGraph`` into the core IR and its provenance envelope.

    The §3 rule set, and only it: topology, entry/finish wiring, and the per-node surfaces
    the builder itself declares. Compiled-only surfaces are recorded absent (§2 dispatch
    table, "§3 only"), never guessed.

    Args:
        dispatch: The §2 classification decision. Its ``builder`` is the ``StateGraph`` §3
            applies to and is what this path reads; ``workflow`` is what any boundary
            refusal names, per §2.
        sidecar: The ANNOTATION §2 sidecar reading for this extraction — already discovered,
            parsed and validated by the entry point. Its **path** is recorded in
            ``extracted_from``, its findings ride the envelope, and its entries are the §3
            tier-3 contribution to each node's resolved contract — filling only the slots the
            decorator and the tool-carried schema left open (DEC-07). ``None`` — for a direct
            call that bypasses the entry point — means "no sidecar", not "not looked for":
            this path never runs the discovery walk itself, since §2 puts exactly one lookup
            per extraction and the entry point is where it happens.

    Returns:
        The envelope: the core IR, its provenance, and the structured warnings. Order is by
        source: the sidecar's own file-level findings, then the §3 reading's, then the
        unmatched-key findings — which come last because they are the one sidecar fact that
        cannot be known before the node set exists.

    Raises:
        ExtractionError: at the object boundary — a node name or a routing target with no
            representable node id (a target that is not a string has none), a routing label
            §6's dispatch cannot spell, or two routing labels that collide after projection.
            Never a silent partial IR (§2); nothing about the sidecar is ever raised (§2 puts
            that surface wholly at warning grade).
    """
    builder = dispatch.builder
    if builder is None:  # pragma: no cover - classify() sets it for every BUILDER dispatch
        raise ExtractionError.for_object(
            dispatch.workflow,
            "the builder extraction path was reached without a StateGraph to read",
            reason=ExtractionErrorReason.EXTRACTOR_NOT_REGISTERED,
            family=ObjectFamily.BUILDER,
        )
    annotations = SidecarReading() if sidecar is None else sidecar
    reading = _read(builder, workflow=dispatch.workflow, sidecar=annotations)
    ir = reading.ir()
    return ExtractionEnvelope(
        ir=ir,
        extracted_from=ExtractedFrom(
            source=type_identity(dispatch.workflow),
            family=ObjectFamily.BUILDER,
            sidecar=None if annotations.path is None else str(annotations.path),
            managed_state_keys=reading.managed_state_keys,
            router_codomains=tuple(reading.router_codomains),
        ),
        warnings=(
            *sidecar_warnings(annotations),
            *reading.warnings,
            *unknown_node_warnings(annotations, (node.id for node in ir.nodes)),
        ),
    )


@dataclass
class _Reading:
    """What one pass over a builder has read so far.

    A mutable collector rather than threaded return values, because four §3 rows contribute
    to overlapping outputs: ``.edges`` and ``.waiting_edges`` both produce ``normal`` edges
    *and* finish members, and ``.edges`` and ``.branches[START]`` both produce entry members.
    Keeping one collector lets each row function stay a readable transcription of its row.

    Every collection is emitted in a **sorted** order rather than in the substrate's
    iteration order. That is not cosmetic: ``builder.edges`` and ``builder.waiting_edges``
    are ``set``s, whose iteration order varies with the process's string-hash seed, so an
    unsorted emission would make two extractions of one unchanged builder compare unequal as
    models. Canonicalization sorts everything again before hashing (IR-SPEC §6.2), so this
    fixes the *model*, which is what a test, a golden or a cache compares.

    The comparator here is Python's own code-point order, not the UTF-16 code-unit order
    §6.2 fixes for canonical form. The two differ only between supplementary-plane characters
    and U+E000–U+FFFF, and the difference is unobservable: what the model needs is *a* total
    deterministic order, and canonicalization re-sorts before any byte is hashed, so the two
    can never disagree about a digest or a golden.
    """

    node_ids: dict[str, str] = field(default_factory=dict)
    normal_edges: set[tuple[str, str]] = field(default_factory=set)
    conditional_edges: list[Edge] = field(default_factory=list)
    """Every routing-declaration edge, in reading order — ``conditional``, ``send``, ``dynamic``.

    The name is §3's ("one ``conditional`` edge group per §6") and predates the classification;
    what it holds is the whole §6 output for the ``.branches`` and ``ends`` rows, which is a
    single list precisely because the kind is decided per declaration rather than per row.
    """

    router_codomains: list[RouterCodomain] = field(default_factory=list)
    """§6's codomain evidence, for the provenance envelope — never for ``path_map``."""

    entry: set[str] = field(default_factory=set)
    finish: set[str] = field(default_factory=set)
    retry_policies: dict[str, RetryPolicy] = field(default_factory=dict)
    contracts: dict[str, NodeContract] = field(default_factory=dict)
    """The ANNOTATION §3 resolved contract per node id — the four tiers, already elected."""

    digests: dict[str, NodeDigests] = field(default_factory=dict)
    """What INTROSPECTION §7.4 had to say per node id — only the carriers get an entry."""

    state: dict[str, str | StateField] | None = None
    """Σ in canonical representation, or ``None`` when the schema declares no key (§2.2)."""

    managed_state_keys: tuple[str, ...] = ()
    """The managed-value keys, for provenance — never members of Σ (§3, §7.3 item 4)."""

    warnings: list[ExtractionWarning] = field(default_factory=list)
    end_labelled: bool = False
    """Whether some ``path_map`` label is valued ``"END"`` — the (m3) half of the D2 test."""

    conditional_entry: bool = False
    """Whether ``branches[START]`` exists at all — the other half of the D2 entry test."""

    def warn_unsupported(
        self,
        construct: str,
        why: str,
        *,
        location: Mapping[str, Any],
        ir_partial: bool,
        node: str | None = None,
    ) -> None:
        """Record one ``unsupported-construct``, carrying its §8 row's four facts."""
        self.warnings.append(
            ExtractionWarning(
                code=ExtractionWarningCode.UNSUPPORTED_CONSTRUCT,
                message=f"{construct}: {why}",
                node=node,
                detail={
                    "construct": construct,
                    "location": dict(location),
                    "why": why,
                    "ir_partial": ir_partial,
                },
            )
        )

    def ir(self) -> WorkflowIR:
        """Assemble the core IR from what was read (IR-SPEC §2.1)."""
        nodes = tuple(
            Node(
                id=node_id,
                annotations=_annotations(
                    self.retry_policies.get(node_id),
                    self.contracts.get(node_id),
                    self.digests.get(node_id),
                ),
            )
            for node_id in sorted(self.node_ids.values())
        )
        normal = tuple(
            NormalEdge(kind="normal", **{"from": source}, to=target)
            for source, target in sorted(self.normal_edges)
        )
        edges: tuple[Edge, ...] = (*normal, *self.conditional_edges)
        return WorkflowIR(
            # IR-SPEC §8's minimal-stamping policy (ratified — DEC-28): the lowest minor
            # sufficient for what this document actually contains, which is "1.1" iff some
            # router declared no targets and "1.0" otherwise. Deriving it from the edges rather
            # than from a flag on this collector means the stamp cannot disagree with the
            # document — there is no second place to keep in step.
            ir_version=lowest_ir_version(edges),
            entry=_collapse(self.entry),
            finish=_collapse(self.finish),
            state=self.state,
            nodes=nodes,
            edges=edges,
            runtime=None,
        )


def _collapse(wired: set[str]) -> str | tuple[str, ...]:
    """A wired sentinel set in its canonical representation (IR-SPEC §6.3).

    "``entry``/``finish`` serialize as a scalar node id iff the wired set is a singleton, and
    as a list otherwise … ``gebra.extract()`` emits these collapsed forms **directly**." So
    the collapse happens here rather than being left to canonicalization: an extracted model
    is compared against goldens and against other extractions as a *model*, and only one of
    the two representations is the canonical one.

    The empty set collapses to the empty list — the ratified form for "no statically known
    sentinel wiring" (DEC-18), and the reason the list branch carries no lower bound.
    """
    if len(wired) == 1:
        return next(iter(wired))
    return tuple(sorted(wired))


def _annotations(
    retry_policy: RetryPolicy | None,
    contract: NodeContract | None,
    digests: NodeDigests | None,
) -> Annotations | None:
    """The node's ``annotations``: the resolved contract, the retry policy, the §7.4 digests.

    Three sources, and none of them can collide: ``retry_policy`` is the one slot §3 projects
    from the builder and ``prompt_digest``/``config_digest`` are the two the extractor computes
    (§7.4), and ANNOTATION §1 puts all three "out of annotation reach" precisely so that the
    declaration surfaces cannot reach them ("extracted or computed, never annotated").
    Everything else comes from the ANNOTATION §3 chain, already elected per slot.

    A node with none of the three carries no ``annotations`` object rather than an empty one,
    so the absence round-trips through omit-normalization as absence (IR-SPEC §6.3). An *empty*
    resolved contract is the same absence: §3 fills a slot or leaves it open, and a contract
    that filled none says nothing.
    """
    members: dict[str, object] = (
        {slot: contract.slot_value(slot) for slot in contract.declared_slots()}
        if contract is not None
        else {}
    )
    if retry_policy is not None:
        members["retry_policy"] = retry_policy
    if digests is not None:
        if digests.prompt is not None:
            members["prompt_digest"] = digests.prompt
        if digests.config is not None:
            members["config_digest"] = digests.config
    if not members:
        return None
    return Annotations.model_validate(members)


def _read(builder: StateGraph[Any], *, workflow: object, sidecar: SidecarReading) -> _Reading:
    """One pass over the builder — §3's table, row by row, in dependency order."""
    reading = _Reading()
    _read_nodes(builder, reading, workflow=workflow)
    _read_node_specs(builder, reading, workflow=workflow)
    _read_edges(builder, reading, workflow=workflow)
    _read_waiting_edges(builder, reading, workflow=workflow)
    _read_branches(builder, reading, workflow=workflow)
    _read_state(builder, reading)
    _read_contracts(builder, reading, sidecar=sidecar)
    _read_digests(builder, reading)
    _warn_missing_wiring(reading)
    return reading


def _read_contracts(
    builder: StateGraph[Any], reading: _Reading, *, sidecar: SidecarReading
) -> None:
    """``StateNodeSpec.runnable`` → the resolved node contract (§3 row 2, purpose ii).

    INTROSPECTION §3 reads this member "for exactly three purposes", and this is the second:
    "**contract attachment** — the innermost user callable is located by following
    ``functools.wraps``/``__wrapped__`` chains per ANNOTATION-API-SPEC §6, then
    ``__gebra_contract__`` and the DEC-08 shallow-inference patterns are read from it". Purpose
    (iii), digest computation, is :func:`_read_digests`; purpose (i), fragment discovery, is
    not wired at this level (see there).

    :mod:`gebra.extraction.contracts` is the whole rule set; this is the seam that gives it
    the three things only a builder pass knows: the node id each contract is filed under, the
    ``gebra.toml`` entry keyed by that id (§2's lookup ran once, at the entry point), and the
    graph's own state schema, which §4's full-state-annotation exclusion needs.

    It runs after the topology and state rows so that a reader meets a node's contract after
    the graph it sits in, and one :class:`~gebra.annotations.inference.SourceCache` is shared
    across the pass — a graph's nodes usually live in a handful of files, and §4 bounds
    inference per node rather than the parsing around it.

    Node **order** does not reach the result: each node is resolved from its own four tiers
    and nothing is threaded between them, which is half of why extracting the same workflow
    twice — or before and after ``.compile()`` — yields the same resolved contracts (§6).
    """
    schema = state_schema_of(builder)
    cache = SourceCache()
    for name in sorted(builder.nodes):
        node_id = reading.node_ids[name]
        resolved = resolve_node(
            node_id,
            getattr(builder.nodes[name], "runnable", None),
            sidecar_entry=sidecar.entries.get(node_id),
            state_schema=schema,
            cache=cache,
        )
        reading.contracts[node_id] = resolved.contract
        reading.warnings.extend(resolved.warnings)


def _read_digests(builder: StateGraph[Any], reading: _Reading) -> None:
    """``StateNodeSpec.runnable`` → ``prompt_digest``/``config_digest`` (§3 row 2, purpose iii).

    §3's third purpose for this member: "**digest computation** — ``prompt_digest``/
    ``config_digest`` are computed over templates/config reachable from it (ledger §3) per the
    §7.4 semantics (DEC-15)". :mod:`gebra.extraction.digests` is the whole rule set; this is
    the seam that hands it the node id and the bound object, once per node.

    **What "reachable from it" reaches at this level, said exactly.** §7.4 (a) computes a
    digest "after §5 stitching" for the node whose *own bound object* is the template or the
    model, and this path does no §5 stitching: purpose (i) — fragment discovery inside a
    ``StateNodeSpec.runnable`` — is not wired (:mod:`gebra.extraction.lcel` extracts a fragment
    handed to ``extract()`` and takes the rule-4 mount path, but no builder-level extraction
    calls it). So a node bound *directly* to a template or a model is a carrier and a node
    bound to a chain that merely contains one is not — which is (a)'s own "never aggregated
    onto parents" rather than a shortfall of it, and it is the forward-compatible direction:
    when §5 discovery lands here, the contained template gets its own child node and the digest
    appears there, on a node that does not exist today, instead of moving off one that does.
    """
    for name in sorted(builder.nodes):
        node_id = reading.node_ids[name]
        digests = digests_for(node_id, getattr(builder.nodes[name], "runnable", None))
        reading.warnings.extend(digests.warnings)
        if digests:
            reading.digests[node_id] = digests


def _read_state(builder: StateGraph[Any], reading: _Reading) -> None:
    """``.channels``/state schema → the ``state`` block (§3 row 10).

    The row itself is :mod:`gebra.extraction.state`; this is the seam. It runs after the
    topology rows so that the state warnings follow the topology ones in the envelope, which
    is the order a reader meets the graph in — and before the missing-wiring check, which is
    a statement about the whole reading.
    """
    state = read_state(builder)
    reading.state = state.state
    reading.managed_state_keys = state.managed
    reading.warnings.extend(state.warnings)


def _read_nodes(builder: StateGraph[Any], reading: _Reading, *, workflow: object) -> None:
    """``.nodes`` → one ``nodes[]`` entry per key (§3 row 1).

    The reserved ``__start__``/``__end__`` never appear here — the substrate refuses them as
    node names — so the ledger §5 escaping of a literal ``/`` or ``%`` is the only
    transformation a top-level name ever needs.
    """
    for name in builder.nodes:
        reading.node_ids[name] = _node_id(name, workflow=workflow, role="node name")


def _read_node_specs(builder: StateGraph[Any], reading: _Reading, *, workflow: object) -> None:
    """The ``StateNodeSpec`` rows §3 maps: ``retry_policy`` and ``ends``.

    ``metadata``, ``cache_policy``, ``defer``, ``timeout`` and the error-handler members are
    the row §3 marks "read but **not mirrored** in ir 1.0 (no ledger slot)" — so they are not
    read at all, which is the same observable behaviour and one fewer attribute touched.
    """
    for name, spec in builder.nodes.items():
        node_id = reading.node_ids[name]
        _read_declared_destinations(spec, name, node_id, reading, workflow=workflow)
        policy = _project_retry_policy(spec.retry_policy, node_id, reading)
        if policy is not None:
            reading.retry_policies[node_id] = policy


def _read_declared_destinations(
    spec: Any,
    name: str,
    node_id: str,
    reading: _Reading,
    *,
    workflow: object,
) -> None:
    """``StateNodeSpec.ends`` → one routing edge group, kind per §6 (§3 row 4 → §6).

    §3 routes this row to §6: "Static routing declaration → ``conditional``/``send`` edges per
    §6; dict-valued ``ends`` supplies ``path_map``". §6 decides which: the node function's own
    **declared return-type hint** licenses ``kind: send`` when it names ``Send``, and
    "``destinations=`` without a ``Send`` hint" is ``kind: conditional``. Both live shapes reach
    here — ``add_node(…, destinations=("book_leg",))`` on a function hinted ``-> list[Send]``,
    and the ``Command[Literal[...]]`` idiom, which names no ``Send`` and so is conditional.

    **Why this is not refused.** The member is not only populated by ``destinations=``: the
    substrate also fills it from a ``Command[Literal[...]]`` **return annotation**, with no
    argument at the call site — verified on the pinned substrate. Refusing the member would
    therefore refuse the whole ``Command``-routing idiom, and §2 puts hard failure at the
    object boundary only: "extraction is total over supported objects", with unmappable
    constructs warned "inside the IR", never raised.

    There is no ``BranchSpec`` behind this declaration and so no branch name, so the edge
    carries no ``condition``: ``condition`` is "the declared branch name", and inventing one
    would put a string this build made up inside ``graph_version``.

    **The dict's orientation is the substrate's: keys are targets, values are labels.**
    ``add_node`` documents a dict-valued ``destinations=`` as ``{target node: edge label}``, its
    own ``validate()`` checks the keys as targets, its drawing labels each target's edge with the
    value, and the vendored A1 memo records the same orientation. So ``{"tool": "go to the
    tool"}`` is ``path_map: {"go to the tool": "tool"}`` — the edge to ``tool``, labelled. (This
    path read the dict the other way round until EX-27 corrected it — a changelog-named
    correction that moves ``graph_version`` for a graph declaring a dict whose labels are not
    its targets; PD-067's ruling.) A label is spelled by the dispatch every label takes, so a
    label value that is an admitted enum member carries its stored value, and two targets
    declared under one label are a ``LABEL_COLLISION``: a ``path_map`` cannot hold both edges.

    **One recorded reading.** §3 says only "*dict-valued* ``ends`` supplies ``path_map``",
    and a ``Command[Literal[...]]`` hint yields a **tuple**. The tuple projects to the
    identity map ``{target: target}`` — which is the substrate's own conversion for the
    equivalent list-valued ``path_map`` of ``add_conditional_edges`` (verified: ``["n2"]``
    becomes ``{"n2": "n2"}``), so it is that convention read across rather than a new one.
    It is latitude resolved, not semantics improvised, and it is recorded as such.

    **What is read, and how** (WA-07; DEC-38 §3.2's discipline, the re-probe PD-067
    records). The member is the author's own object, stored as handed to ``add_node``, so it
    is read only through unbound accessors of a type it has been checked to be — see
    :func:`_declared_destinations` — and never through a truthiness test or a bound method,
    which a ``dict`` or ``tuple`` subclass could answer with code of its own.

    An empty ``ends`` is not the §6 targetless form and emits no ``dynamic`` edge: the member is
    ``()`` on every node that declares no routing at all, so reading it as "a router with
    unknowable targets" would put a dynamic edge on every plain node in every graph. §6's
    targetless form is a *router* that declares no targets, and a router is a ``BranchSpec``.

    No codomain is recorded for this declaration: §6's codomain-capture rule is a ``.branches``
    router's (the module docstring says why), so :func:`_emit_routing` is told so.
    """
    declared = _declared_destinations(
        getattr(spec, "ends", None), reading, node=node_id, name=name, workflow=workflow
    )
    if not declared:
        return
    where = f"node {name!r}'s routing declaration"
    hint = _router_hint(spec, reading, where=where, node=node_id)
    path_map: dict[str, str] = {}
    seen_labels: set[str] = set()
    for declared_label, target in declared:
        label = _path_map_label(declared_label, workflow=workflow, where=where)
        _refuse_label_collision(label, seen_labels, workflow=workflow, where=where)
        resolved = _path_map_target(
            _routing_target(target, workflow=workflow, where=where),
            reading,
            workflow=workflow,
            location={"node": node_id, "label": label},
            where=where,
            kind=hint.kind,
        )
        if resolved is not None:
            path_map[label] = resolved
    if not path_map:
        return
    _emit_routing(reading, node_id, path_map, hint, condition=None, where=where, codomain=False)


def _declared_destinations(
    ends: object, reading: _Reading, *, node: str, name: str, workflow: object
) -> list[tuple[object, object]]:
    """A node's ``StateNodeSpec.ends``, as ``(label, target)`` pairs read without running it.

    Three shapes reach this member. A **dict** — ``destinations={target: label}`` — is iterated
    as ``dict.items(ends)``, which reads the hash table directly whatever ``dict`` subclass
    holds it, and inverted into ``(label, target)`` pairs. A **sequence of names** — a
    ``destinations=`` tuple, or the tuple a ``Command[Literal[...]]`` hint makes — is iterated
    through its own type's unbound ``__iter__`` (``tuple``, ``list``, ``set`` or
    ``frozenset``), each name paired with itself; repeated names collapse as the substrate's own
    list-to-dict conversion collapses them, and a set's names are sorted, since its iteration
    order is the process's string-hash seed — which is also why a set holding anything but
    strings is refused whole, with ``UNREPRESENTABLE_NODE_ID``, before any member is read as a
    label: which member a label read met first would otherwise decide the refusal's reason, and
    the seed would decide which member came first. **Anything else** — a non-``dict`` mapping, a
    string, a generator — has no reading that would not run its own code, and the substrate
    types the member ``dict | tuple``: it is warned as a known field with an unmappable value
    (§8, the ``retry-policy-unrecognized`` precedent) and declares nothing here.

    Size is never asked of the object and no truthiness test runs on it: an empty declaration is
    an empty list *this* function built.
    """
    if ends is None:
        return []
    kind = type(ends)
    if issubclass(kind, dict):
        return [(label, target) for target, label in dict.items(cast(dict[object, object], ends))]
    members = _sequence_members(ends)
    if members is None:
        reading.warn_unsupported(
            "routing-declaration-unreadable",
            f"the node's routing declaration is a {type_identity(ends)}, which is neither a "
            "dict of target names to labels nor a sequence of target names, so reading it "
            "would run its own code; no routing edge is derived from it",
            location={"node": node},
            ir_partial=True,
            node=node,
        )
        return []
    unordered = issubclass(kind, (set, frozenset))
    if unordered and not all(issubclass(type(member), str) for member in members):
        raise ExtractionError.for_object(
            workflow,
            f"node {name!r}'s routing declaration is a {type_identity(ends)} holding a target "
            "that is not a string; a routing target is a node name or END, so this build "
            "refuses before reading any member (INTROSPECTION-SPEC §6, DEC-38: the admission "
            "of an Enum member is for labels only) — declare the targets by name",
            reason=ExtractionErrorReason.UNREPRESENTABLE_NODE_ID,
            family=ObjectFamily.BUILDER,
        )
    names = _distinct_names(members, unordered=unordered)
    return [(name, name) for name in names]


def _sequence_members(ends: object) -> list[object] | None:
    """The members of a ``tuple``/``list``/``set``/``frozenset``, read through the type's own slot.

    ``tuple.__iter__(ends)`` and its three siblings call the built-in type's C iterator on the
    object, so a subclass that overrides ``__iter__`` (or ``__len__``, or ``__bool__``) is
    never asked. ``None`` for any other type — nothing about it is read.
    """
    kind = type(ends)
    if issubclass(kind, tuple):
        return list(tuple.__iter__(cast(tuple[object, ...], ends)))
    if issubclass(kind, list):
        return list(list.__iter__(cast(list[object], ends)))
    if issubclass(kind, set):
        return list(set.__iter__(cast(set[object], ends)))
    if issubclass(kind, frozenset):
        return list(frozenset.__iter__(cast(frozenset[object], ends)))
    return None


def _distinct_names(members: list[object], *, unordered: bool) -> list[object]:
    """Declared target names with repeats collapsed; a string member projected to a built-in ``str``.

    A string member goes through ``"".join((member,))`` before it is compared with anything, so
    the comparison is ``str.__eq__`` whatever subclass it was. A member that is not a string is
    kept as it is and in place — read as a label it is refused by the label dispatch, or, when
    the dispatch admits it, by the target guard — and nothing here hashes or compares it. An
    unordered container reaches this function holding strings only (the caller refuses it
    otherwise), and its names are sorted.
    """
    names: list[object] = []
    seen: set[str] = set()
    for member in members:
        if not issubclass(type(member), str):
            names.append(member)
            continue
        name = "".join((cast(str, member),))
        if name not in seen:
            seen.add(name)
            names.append(name)
    if unordered and len(seen) == len(names):
        return [*sorted(seen)]
    return names


def _project_retry_policy(
    declared: object,
    node_id: str,
    reading: _Reading,
) -> RetryPolicy | None:
    """``StateNodeSpec.retry_policy`` → the minimal ledger projection (§3; ratified DEC-18).

    Two of the substrate's shapes do not fit the slot, and §3 now states both rules:
    a ``Sequence[RetryPolicy]`` projects its **first** policy (the substrate's first-match
    semantics) with one warning recording the count dropped, and a **callable** ``retry_on``
    — which includes the library default, so it is the commonest shape of all — projects
    ``retry_on: []`` with one warning naming the opaque trigger set.

    The empty ``retry_on`` MUST be read paired with that warning: the substrate's own runtime
    reads a literal empty sequence as "retries on nothing", so the core-IR-only reading is
    the inverse of the fact. §3 states the pairing; this is the emitter half of it.

    The order of the two tests below is load-bearing: the substrate's ``RetryPolicy`` is a
    ``NamedTuple``, so a single policy *is* a ``Sequence`` and would otherwise be read as a
    sequence of its own six fields. The concrete type is asked about first.
    """
    if declared is None:
        return None
    if isinstance(declared, SubstrateRetryPolicy):
        return _project_one_retry_policy(declared, node_id, reading)
    if isinstance(declared, Sequence):
        policies = tuple(declared)
        if not policies:
            # Nothing was attached, so nothing was dropped: the flattening warning below
            # records a *count dropped*, and emitting it here would put a workflow outside
            # the strict-mode bar for a declaration its author did not make.
            return None
        if len(policies) > 1:
            reading.warn_unsupported(
                "retry-policy-sequence-flattened",
                f"{len(policies)} retry policies are attached and ir 1.0 carries one; the "
                "first is projected, matching the substrate's first-match semantics",
                location={"node": node_id},
                ir_partial=True,
                node=node_id,
            )
        if isinstance(policies[0], SubstrateRetryPolicy):
            return _project_one_retry_policy(policies[0], node_id, reading)
        declared = policies[0]
    # Out of the substrate's own contract for the slot, which types it
    # `RetryPolicy | Sequence[RetryPolicy] | None`. §3 requires extraction to tolerate what it
    # does not recognise rather than fail on it, and §8's row covers known node-spec fields
    # carrying unmappable *values* (DEC-18) — so the slot is left absent and the fact is
    # warned, which is also the honest reading: nothing about this policy is known. Reading
    # `max_attempts` off it instead would be a duck-typed call into a foreign object.
    reading.warn_unsupported(
        "retry-policy-unrecognized",
        f"the attached retry policy is a {type_identity(declared)}, which is neither a "
        "substrate retry policy nor a sequence of them, so nothing about it is projectable",
        location={"node": node_id},
        ir_partial=True,
        node=node_id,
    )
    return None


def _project_one_retry_policy(policy: Any, node_id: str, reading: _Reading) -> RetryPolicy:
    """One ``RetryPolicy`` → ``{max_attempts, retry_on}``; the four timing members are dropped.

    The timing members (``initial_interval``, ``backoff_factor``, ``max_interval``,
    ``jitter``) are "deliberately not mirrored — they are timing, not semantics, and carry no
    verification content" (IR-SPEC §3.2), so their absence needs no warning.
    """
    return RetryPolicy(
        max_attempts=policy.max_attempts,
        retry_on=_project_retry_on(policy.retry_on, node_id, reading),
    )


def _project_retry_on(declared: object, node_id: str, reading: _Reading) -> tuple[str, ...]:
    """``retry_on`` → opaque exception-name strings, or ``()`` + a warning when it is opaque.

    The substrate types the member ``type[Exception] | Sequence[type[Exception]] |
    Callable[[Exception], bool]``. Only the first two forms name exceptions; the third is a
    predicate whose trigger set is a body, and bodies are never read (§1). Note the order of
    the tests below: an exception *class* is itself callable, so "is it a class" has to be
    asked first.

    Nothing here is ever ``str()``-ed. A value that is not an exception type is *named* by
    its class identity, which reads two attributes of its type and calls nothing on the value
    itself — the same discipline ``_project_retry_policy`` applies to a foreign policy.

    The name is the class's ``__qualname__`` — the exception's name as Python spells it,
    which is what §3's "opaque exception-name strings" asks for and all a reader needs to
    match it against a traceback. It is deliberately not the ``package:qualname`` class
    identity §7.4 fixes for *digest input*: that spelling answers "which class exactly", a
    question the slot is explicitly opaque about. Two same-named exceptions from different
    modules therefore project to one string; gebra imposes no algebra on these values, so
    nothing here reasons over the collision, but it is a reading a conformance suite should
    pin rather than rediscover.
    """
    if _is_exception_type(declared):
        return (declared.__qualname__,)
    if isinstance(declared, Sequence) and not isinstance(declared, (str, bytes)):
        members = tuple(declared)
        if all(_is_exception_type(item) for item in members):
            # Includes the empty sequence, which projects to `retry_on: []` with **no**
            # warning — and under the DEC-18 pairing rule that is the literal reading, "this
            # policy retries on nothing". Unpaired empty and paired empty are different
            # facts, which is exactly why the rule makes the pairing normative.
            return tuple(item.__qualname__ for item in members)
        # A partly-recognizable sequence is still an opaque trigger set: projecting only the
        # members that *are* exception types would claim the set is exactly those, a stronger
        # statement than the declaration makes. So the whole slot falls to the opaque form.
        return _opaque_retry_on(
            "the retry trigger set holds values that are not exception types "
            f"({', '.join(type_identity(item) for item in members if not _is_exception_type(item))})",
            node_id,
            reading,
        )
    if callable(declared):
        return _opaque_retry_on(
            "the retry trigger set is a callable predicate rather than declared exception "
            "types, so what it triggers on is a body, and bodies are never read",
            node_id,
            reading,
        )
    # Neither an exception type, nor a sequence, nor a predicate — e.g. a `set`, which is a
    # collection the substrate's own type for the member does not admit. Named by its type
    # rather than iterated: iterating it would run its `__iter__`, and `str()`-ing it would
    # run its `__str__` — neither is on §1 rule 3's closed list, and the result would land in
    # `graph_version` (an `object.__repr__` carries a memory address, so the digest would
    # differ between processes for one unchanged builder).
    return _opaque_retry_on(
        f"the retry trigger set is a {type_identity(declared)}, which is neither an "
        "exception type, a sequence of them, nor a predicate",
        node_id,
        reading,
    )


def _opaque_retry_on(why: str, node_id: str, reading: _Reading) -> tuple[str, ...]:
    """Record an opaque trigger set and return the empty projection (ratified DEC-18).

    One emission point for every way a trigger set can be unreadable, so the pairing rule is
    stated once: ``retry_on: []`` **with** this warning means "declared policy, trigger set
    opaque"; without it, it means the literal empty set.
    """
    reading.warn_unsupported(
        "retry-on-opaque",
        f"{why}, so `retry_on: []` records a declared policy with an opaque trigger set — "
        'never "retries on nothing", which is what an unwarned `retry_on: []` means',
        location={"node": node_id},
        ir_partial=True,
        node=node_id,
    )
    return ()


def _read_edges(builder: StateGraph[Any], reading: _Reading, *, workflow: object) -> None:
    """``.edges`` → ``normal`` edges, plus the ``entry``/``finish`` members (§3 row 6).

    "Each ``(a, b)`` with ``a, b ∉ {START, END}`` → ``{from: a, to: b, kind: normal}``;
    ``(START, x)`` pairs derive ``entry``; ``(x, END)`` pairs derive ``finish``."

    One pair is in none of those three cases and §3 does not name it: ``(START, END)``, which
    the substrate accepts. It is a sentinel-to-sentinel incidence, and ir 1.0 has no carrier
    for one — an ``entry`` or ``finish`` member would have to name a reserved segment, which
    §5.1 says the IR never emits. So it is dropped with the warning §8 keeps for exactly this
    ("a supported object contains a construct extraction cannot map"), and the IR is honestly
    partial at that location.
    """
    for source, target in sorted(builder.edges):
        if source == START and target == END:
            reading.warn_unsupported(
                "start-to-end-edge",
                "an edge wires START directly to END; ir 1.0 records sentinel incidences "
                "through `entry`/`finish` node ids, and neither sentinel is a node id",
                location={"edge": {"from": START, "to": END}},
                ir_partial=True,
            )
        elif source == START:
            reading.entry.add(_node_id(target, workflow=workflow, role="entry wiring"))
        elif target == END:
            reading.finish.add(_node_id(source, workflow=workflow, role="finish wiring"))
        else:
            reading.normal_edges.add(
                (
                    _node_id(source, workflow=workflow, role="edge source"),
                    _node_id(target, workflow=workflow, role="edge target"),
                )
            )


def _read_waiting_edges(builder: StateGraph[Any], reading: _Reading, *, workflow: object) -> None:
    """``.waiting_edges`` → one ``normal`` edge per source, plus ``barrier-flattened`` (§3 row 7).

    "Expand per ``_all_edges``: each source in the tuple yields one ``normal`` edge to the
    target." The all-of barrier itself has no ir 1.0 carrier, so one warning per group is
    mandatory, not optional — it is what keeps the P-04/P-09 conservatism visible.

    A group whose target is END contributes each source to ``finish`` instead, for the same
    reason the plain ``(x, END)`` pair does: END is a sentinel, not an edge target.
    """
    for sources, target in sorted(builder.waiting_edges):
        for source in sources:
            source_id = _node_id(source, workflow=workflow, role="waiting-edge source")
            if target == END:
                reading.finish.add(source_id)
            else:
                reading.normal_edges.add(
                    (source_id, _node_id(target, workflow=workflow, role="waiting-edge target"))
                )
        reading.warnings.append(
            ExtractionWarning(
                code=ExtractionWarningCode.BARRIER_FLATTENED,
                message=(
                    f"the all-of barrier on {list(sources)} → {target!r} was expanded to "
                    f"{len(sources)} plain edges"
                ),
                detail={
                    "sources": tuple(sources),
                    "target": target,
                    "edges_expanded": len(sources),
                    "conservatism": (
                        "P-04 path quantification and P-09 concurrency detection over the "
                        "flattened form may over-report, never under-report"
                    ),
                },
            )
        )


def _read_branches(builder: StateGraph[Any], reading: _Reading, *, workflow: object) -> None:
    """``.branches`` → the entry, and one ``conditional`` edge group per declared branch (§3 row 9).

    Two different rows of §3 meet here. ``branches[START]`` "derives the entry": its declared
    ``path_map`` targets *are* the entry set, and when ``ends is None`` the entry is the empty
    form plus the dynamic-entry warning. Every other source is a router, which §3 sends to §6
    as "one ``conditional`` edge group".

    Branch names are unique per source (the substrate refuses duplicates), so ``(from,
    condition)`` identifies a group even under the ``"condition"`` fallback that an unnamed
    callable gets — but consumers must not key on ``condition`` alone, which is why two
    routers on one node stay two edges here.
    """
    for source in sorted(builder.branches):
        for name in sorted(builder.branches[source]):
            spec = builder.branches[source][name]
            if source == START:
                reading.conditional_entry = True
                _read_conditional_entry(spec, name, reading, workflow=workflow)
            else:
                _read_router(spec, source, name, reading, workflow=workflow)


def _read_conditional_entry(
    spec: Any,
    name: str,
    reading: _Reading,
    *,
    workflow: object,
) -> None:
    """``branches[START]`` → the entry members, or the empty form plus its warning.

    §3: "``entry`` = the declared ``path_map`` targets; when ``ends is None``, extraction
    emits the empty-list form ``entry: []`` … plus ``unsupported-construct`` scoped to
    dynamic entry dispatch, carrying the branch name."

    A declared target of END is dropped with its own warning: START-to-END is the same
    unrepresentable sentinel incidence a plain ``(START, END)`` edge is, reached by another
    route.

    This site reads its targets itself rather than through :func:`_path_map_target`, so it
    takes the target guard itself, before the reserved-segment test: a target that is not a
    string is refused there and a string target is read as a built-in ``str``
    (:func:`_routing_target`; DEC-38 §3.5). The labels take the same dispatch as every other
    label, and the ``ends`` mapping is read as the router's is — see :func:`_branch_ends`.
    """
    ends = spec.ends
    if ends is None:
        reading.warn_unsupported(
            "conditional-entry-without-path-map",
            "the entry router declares no targets, so which node runs first is decided at "
            "runtime and no entry wiring is statically knowable",
            location={"branch": name, "source": START},
            ir_partial=True,
        )
        return
    where = f"entry router {name!r}"
    declared = _branch_ends(ends, reading, location={"branch": name, "source": START})
    for declared_label, declared_target in declared:
        label = _path_map_label(declared_label, workflow=workflow, where=where)
        target = _routing_target(declared_target, workflow=workflow, where=where)
        if target in RESERVED_SEGMENTS:
            # Including END: an entry member names a node, and a START→END incidence has no
            # ir 1.0 carrier at all — the same unrepresentable shape a plain `(START, END)`
            # edge is, reached by another route.
            reading.warn_unsupported(
                "reserved-entry-target",
                f"the entry router's {label!r} label targets the reserved sentinel "
                f"{target!r}; `entry` names node ids, and no sentinel is one",
                location={"branch": name, "source": START, "label": label},
                ir_partial=True,
            )
            continue
        reading.entry.add(_node_id(target, workflow=workflow, role="conditional entry target"))


def _read_router(
    spec: Any,
    source: str,
    name: str,
    reading: _Reading,
    *,
    workflow: object,
) -> None:
    """One ``BranchSpec`` → one edge, kind per §6 (§3 row 9 → §6).

    ``condition`` is the declared branch name — the extracted form of the ledger's "declared
    guard/router expression string". The router body is never read and never persisted (§6:
    "Guards are opaque references"); its *declared return-type hint* is, which is the whole
    difference between reading a declaration and reading an implementation.

    A branch that declares no targets is §6's targetless form and emits
    ``{from, kind: dynamic, condition}`` (ratified — DEC-28, 2026-08-09; PD-041), which is
    where a ``Send``-hinted router with no ``path_map`` — the canonical map-reduce — lands too:
    §6 licenses the kind from the hint but still requires declared targets to emit one, and
    there are none. The edge stays in hash scope and the ``unsupported-construct`` §8 keeps for
    dynamic dispatch says what is not known.

    The declared ``ends`` mapping is whatever the substrate's ``path_map.copy()`` returned —
    the author's own ``dict`` subclass, when it overrides ``copy`` — so it is read through
    :func:`_branch_ends` and never through a method of its own. Each label takes §6's
    dispatch, each target the guard (:func:`_routing_target`) before :func:`_path_map_target`
    compares it with anything.
    """
    source_id = _node_id(source, workflow=workflow, role="router source")
    where = f"router {name!r} on node {source!r}"
    hint = _router_hint(spec, reading, where=where, node=source_id)
    ends = spec.ends
    if ends is None:
        reading.conditional_edges.append(
            DynamicEdge(kind="dynamic", **{"from": source_id}, condition=name)
        )
        reading.warn_unsupported(
            "router-without-declared-targets",
            "the router declares no targets — no `path_map`, no `Literal` return hint, no "
            "`destinations=` — so which node runs next is decided at runtime; the edge records "
            "the router and its guard, and says nothing about targets (`kind: dynamic`)",
            location={"branch": name, "source": source_id},
            ir_partial=True,
            node=source_id,
        )
        return
    path_map: dict[str, str] = {}
    seen_labels: set[str] = set()
    for declared_label, target in _branch_ends(
        ends, reading, location={"branch": name, "source": source_id}
    ):
        label = _path_map_label(declared_label, workflow=workflow, where=where)
        _refuse_label_collision(label, seen_labels, workflow=workflow, where=where)
        resolved = _path_map_target(
            _routing_target(target, workflow=workflow, where=where),
            reading,
            workflow=workflow,
            location={"branch": name, "source": source_id, "label": label},
            where=where,
            kind=hint.kind,
        )
        if resolved is not None:
            path_map[label] = resolved
    if not path_map:
        # Every declared label named a target with no ir 1.0 carrier, each already warned. An
        # edge with an empty `path_map` is exactly the shape DEC-18 D4 ruled out in terms, and
        # `kind: dynamic` would be a *stronger* claim than the declaration supports — targets
        # were declared, they just have no carrier — so the group is not emitted at all.
        return
    _emit_routing(reading, source_id, path_map, hint, condition=name, where=where, codomain=True)


def _branch_ends(
    ends: object, reading: _Reading, *, location: Mapping[str, Any]
) -> list[tuple[object, object]]:
    """A ``BranchSpec.ends`` mapping as ``(label, target)`` pairs, read without running it.

    The substrate builds this member as a ``dict`` — a copy of the declared ``path_map``, the
    identity map of a list, or the map of a ``Literal`` hint — and ``copy()`` is the author's
    when the ``path_map`` was a ``dict`` subclass that overrides it. So the mapping is admitted
    by ``issubclass(type(ends), dict)`` and read as ``dict.items(ends)``, which iterates the
    hash table directly: a subclass's own ``items``, ``__iter__``, ``__len__`` or ``__bool__``
    never runs (measured in the re-probe PD-067 records). A member that is not a ``dict`` —
    reachable through a ``path_map`` whose own ``copy()`` returns something else, or a
    ``BranchSpec`` assigned into ``builder.branches`` by hand — is warned as unreadable and
    declares nothing, which leaves the router to the existing all-dropped rule: no edge for a
    group none of whose declared targets this build can carry, the reading the module already
    takes for a group whose every target is the reserved START. Two cases differ in what they
    were before EX-27. A member that is no mapping at all (a tuple) cannot compile, and the
    old bound ``items()`` raised an ``AttributeError`` out of ``extract()``. A mapping that
    is not a ``dict`` compiles and routes — the substrate's ``validate()`` and
    ``BranchSpec.run`` use only its ``values()`` and ``items()`` — and the old read ran its
    own ``items()``, user code the ruled read does not run, and emitted the edge; it is now
    warned and omitted, which moves that graph's ``graph_version`` (the CHANGELOG names it).
    DEC-18 D4 rules ``path_map: {}`` and edge omission out for the *targetless* conditional
    edge; whether omission is the right posture for declared targets held where they cannot
    be read without running the holder's code is not ruled anywhere, so this is recorded as
    the existing posture applied, not generalized.
    """
    if issubclass(type(ends), dict):
        return list(dict.items(cast(dict[object, object], ends)))
    reading.warn_unsupported(
        "routing-declaration-unreadable",
        f"the router's declared targets are held in a {type_identity(ends)}, which is not a "
        "dict, so reading them would run its own code; no routing edge is derived from them",
        location=location,
        ir_partial=True,
    )
    return []


def _router_hint(spec: Any, reading: _Reading, *, where: str, node: str | None) -> RouterHint:
    """§6's declared-return-hint read on one routing declaration, with its degradation warned.

    :mod:`gebra.extraction.routing` is the rule; this is the seam, and the one thing it adds is
    that a hint which *could not be read* does not pass silently. §1 rule 3 requires the
    degradation and says nothing about reporting it, but the two cases are different facts: no
    hint at all is a declaration the author did not make, while an unevaluable hint is one they
    did make and this extraction could not use — and the second changes the edge's kind, which
    is in hash scope. So it takes §8's `unsupported-construct` row, whose four facts it has.
    """
    # No truthiness test on a foreign object (WA-07 pre-review F1, 2026-08-10): `or`
    # would dispatch to a user `__bool__`/`__len__`, which INTROSPECTION §1 rule 3's
    # permitted-operations list does not license. Explicit None checks only.
    routing_callable = getattr(spec, "path", None)
    if routing_callable is None:
        routing_callable = getattr(spec, "runnable", None)
    hint = declared_return_hint(routing_callable)
    if hint.degraded is not None:
        reading.warn_unsupported(
            "router-hint-unevaluable",
            f"{where}: {hint.degraded}, so §6's send/conditional classification ran as the "
            "no-hint case and the edge carries the conservative kind; §1 rule 3 requires the "
            "degradation, and nothing was retried, patched or evaluated in a second namespace",
            location={"router": where, "source": node},
            ir_partial=True,
            node=node,
        )
    return hint


def _emit_routing(
    reading: _Reading,
    source_id: str,
    path_map: dict[str, str],
    hint: RouterHint,
    *,
    condition: str | None,
    where: str,
    codomain: bool,
) -> None:
    """One declared-target routing declaration as edges, kind per §6's classification.

    ``conditional`` keeps the ``path_map`` verbatim — the labels are the declaration, and §6
    has extraction "preserve labels verbatim" and expand nothing. ``codomain`` says whether
    §6's codomain-capture rule applies to the declaration at all, carried explicitly by the
    caller: ``True`` for a ``.branches`` router, ``False`` for a node routing declaration, whose
    hint names goto targets rather than labels (the module docstring).

    ``send`` is a **template**: §6 says "emit one ``{from, to, kind: send}`` edge per declared
    target", and a send edge has no ``path_map``, so the labels have nowhere to ride. Three
    consequences, each handled rather than absorbed:

    * *Targets are deduplicated.* Two labels naming one target declare one template, and two
      identical send edges would be two copies of one fact in hash scope. Emission order is the
      declaration's, so it is deterministic without sorting.
    * *A label that is not its own target is lost, and says so.* A list/tuple declaration
      projects to the identity map (``["book_leg"]`` → ``{"book_leg": "book_leg"}``), where
      nothing is lost and nothing is warned — that is the shape §6's own worked example uses. A
      dict declaration with a *distinct* label (``{"leg": "book_leg"}``) loses the label, which
      is one ``unsupported-construct``, once for the declaration rather than once per label.
    * *The branch name rides as ``condition``.* §3 fixes ``condition`` for every
      ``.branches``-derived edge ("``condition`` = the declared branch name") and §6 decides
      only the kind, so the refinement does not drop it; on ``send`` the member is inert
      declared content (IR-SPEC §2.4) and it keeps ``(from, condition)`` identifying the edge
      group, which two send-hinted routers on one node otherwise would not.
    """
    if hint.kind == "conditional":
        reading.conditional_edges.append(
            ConditionalEdge(
                kind="conditional",
                **{"from": source_id},
                condition=condition,
                path_map=path_map,
            )
        )
        if codomain:
            _record_codomain(reading, source_id, path_map, hint, condition=condition)
        return
    relabelled = sorted(label for label, target in path_map.items() if label != target)
    if relabelled:
        reading.warn_unsupported(
            "send-template-labels-dropped",
            f"{where} is classified `kind: send` by its declared return hint, and a send "
            "template carries a target rather than a label map, so the declared label(s) "
            f"{relabelled} have no ir 1.0 carrier; the targets they named are emitted",
            location={"source": source_id, "labels": tuple(relabelled)},
            ir_partial=True,
            node=source_id,
        )
    emitted: set[str] = set()
    for target in path_map.values():
        if target in emitted:
            continue
        emitted.add(target)
        reading.conditional_edges.append(
            SendEdge(kind="send", **{"from": source_id}, to=target, condition=condition)
        )


def _record_codomain(
    reading: _Reading,
    source_id: str,
    path_map: dict[str, str],
    hint: RouterHint,
    *,
    condition: str | None,
) -> None:
    """§6's codomain-capture rule: a declared codomain distinct from ``path_map``, in provenance.

    Recorded only when the hint's labels differ from the emitted ones as a **set**: where they
    agree the codomain is already in the IR (the substrate fills ``ends`` from a ``Literal``
    hint when no ``path_map`` was declared), and a record would restate the edge. Where they
    differ, this is the P-05(i) scenario §7.3 item 5 names, and ir 1.0 has no carrier for it.

    Nothing is merged into ``path_map`` and nothing is emitted on the edge — §6 forbids the
    first in terms, and the second would put an extractor-side reading inside ``graph_version``.
    """
    if not hint.codomain or set(hint.codomain) == set(path_map):
        return
    reading.router_codomains.append(
        RouterCodomain(
            node=source_id,
            condition=condition,
            labels=hint.codomain,
            path_map_labels=tuple(path_map),
        )
    )


def _warn_missing_wiring(reading: _Reading) -> None:
    """The §2 missing-wiring warning, scoped to genuinely undeclared wiring (ratified DEC-18).

    The scoping is the whole content of the rule. On the finish side the warning fires "iff
    the node set has *no* END incidence at all — neither an (m2) ``finish`` member nor an
    (m3) ``path_map`` label valued ``"END"``", so a workflow that terminates entirely through
    its routers extracts ``finish: []`` **warning-free**: nothing about it is undeclared, and
    a warning there would put every conditionally-terminated workflow permanently outside the
    strict-mode bar for a defect it does not have.

    On the entry side it fires for an unwired START with no conditional entry — a conditional
    entry with no declared targets has already carried its own dynamic-dispatch warning, and
    §2 is explicit that it gets that one "instead, never this one".
    """
    if not reading.entry and not reading.conditional_entry:
        reading.warn_unsupported(
            "missing-start-wiring",
            "no edge wires START to a node and no conditional entry is declared, so no entry "
            "point is statically knowable",
            location={"sentinel": START},
            ir_partial=True,
        )
    if not reading.finish and not reading.end_labelled:
        reading.warn_unsupported(
            "missing-finish-wiring",
            "no node is wired to END and no path_map label targets it, so no terminal wiring "
            "is statically knowable",
            location={"sentinel": END},
            ir_partial=True,
        )


def _path_map_target(
    target: str,
    reading: _Reading,
    *,
    workflow: object,
    location: Mapping[str, Any],
    where: str,
    kind: Literal["send", "conditional"] = "conditional",
) -> str | None:
    """A declared routing target as an edge target, or ``None`` when it has no carrier.

    Three cases, and only the first two are representable. ``END`` becomes the blessed
    ``"END"`` literal — the (m3) incidence, and the forced spelling recorded with DEC-18.
    An ordinary name becomes its escaped node id, whether or not a node by that name exists:
    an unresolvable *reference* is P-01's ``edge-target-undefined`` to report, not
    extraction's to refuse.

    ``START`` is the third case. The substrate accepts ``{"loop": START}`` on an uncompiled
    builder — it only rejects it at ``compile()``, which is never called — and ir 1.0 has no
    carrier for an edge *into* START: §4.2 (m5) gives START no incoming edges, and §5.1
    reserves the segment and says extraction never emits it. So the label is dropped with the
    §8 warning kept for a construct that cannot be mapped, exactly as a ``(START, END)`` edge
    is. Refusing instead would be the one thing this module says it does not do — turn a
    dangling reference into a boundary error and leave P-01 nothing to report.

    ``kind`` is what §6's classification changes about the END case, and only that case: the
    ``"END"`` literal is blessed **for ``path_map`` values only** (IR-SPEC §2.5 as corrected at
    DEC-27), so a ``send`` template — whose target is a ``to``, a plain node id — has no carrier
    for it and drops it with its own warning rather than writing a reference every downstream
    reader would resolve as a node named ``END``. The substrate rejects ``Send(END, …)`` at
    runtime anyway (§6), so nothing is lost that could have run; what would have been lost is
    the honesty of the record.

    ``target`` arrives as a built-in ``str``: every caller runs :func:`_routing_target` on the
    declared object first, so the comparison, the reserved-segment test and the escaping below
    only ever see ``str``'s own methods.
    """
    if target == END:
        if kind == "send":
            reading.warn_unsupported(
                "send-template-targets-end",
                f"{where} is classified `kind: send` and declares END as a target; a send "
                "template's target is a node id and the `END` literal is blessed for path_map "
                "values only, so the declaration has no ir 1.0 carrier and is dropped",
                location=location,
                ir_partial=True,
            )
            return None
        reading.end_labelled = True
        return END_LABEL
    if target in RESERVED_SEGMENTS:
        reading.warn_unsupported(
            "reserved-routing-target",
            f"{where} targets the reserved sentinel {target!r}; ir 1.0 has no carrier for an "
            "edge into it, and the segment is never emitted",
            location=location,
            ir_partial=True,
        )
        return None
    return _node_id(target, workflow=workflow, role="path_map target")


def _is_exception_type(value: object) -> TypeGuard[type[BaseException]]:
    """Whether ``value`` is a declared exception class — the only thing ``retry_on`` names.

    Two ``isinstance``/``issubclass`` checks and nothing else. ``issubclass`` dispatches on
    the *second* argument's metaclass, and ``BaseException``'s is plain ``type``, so no user
    ``__subclasscheck__`` runs here.
    """
    return isinstance(value, type) and issubclass(value, BaseException)


def _path_map_label(label: object, *, workflow: object, where: str) -> str:
    """A declared branch label as an IR ``path_map`` key — read, never coerced.

    The substrate types ``path_map`` keys ``Hashable``, not ``str``, so a label may be an
    enum member, an ``int``, a ``bool``, or any user object. ir 1.0 types the key ``str`` and
    puts it in the NFC identifier role (IR-SPEC §6.3), and INTROSPECTION-SPEC §6 rules the
    spelling by one dispatch, in this order and no other (DEC-32, amended by DEC-38):

    1. a ``str`` instance — ``str`` subclasses and string-mixin enum members included — carries
       its verbatim value;
    2. a plain ``Enum`` member whose stored value is an exact ``str`` carries that stored value
       — so ``AgentDecision.END = "finished"`` is the label ``"finished"``, never ``"END"`` and
       never ``"AgentDecision.END"``, and the plain enum extracts byte-identical to its
       string-mixin twin and to the plain-string graph;
    3. every other key is refused at the object boundary rather than coerced.

    :func:`gebra.extraction.routing.spell_routing_label` is that dispatch, shared with the
    codomain read so a key and its codomain member carry one spelling. It reads the label's
    type slot, the MRO and namespaces of its class and the member's own instance dictionary,
    all through unbound accessors, and nothing else: no ``isinstance`` (which reads
    ``__class__`` through the object's own attribute access when the type check fails), no
    ``str()``, ``repr()``, ``format()``, ``.name``, ``.value`` or ``getattr``.

    Both halves of the refusal matter. Coercing would improvise a digest-affecting spelling:
    the key lands verbatim in ``path_map``, which is in ``graph_version`` hash scope, so
    choosing ``str(label)`` here would silently fix what two conforming extractors must agree
    on (§1.2). And ``str()`` would *call* the label's ``__str__`` — arbitrary user code, which
    §1's closed operation list does not admit and which the never-invokes tripwires exist to
    catch. The refusal names the label's type and why it has no spelling, never a rendering of
    the label.

    Every spelled label is NFC-normalized. The normalization is not optional and not a choice:
    IR-SPEC §6.3 puts ``path_map`` labels in the NFC identifier role, and canonicalization
    *refuses* a label that is not in that form rather than normalizing one. Emitting the
    authored bytes would therefore produce an IR that §2 says must exist and that raises
    ``CanonicalizationError`` the moment anyone asks it for a ``graph_version`` — extraction
    total in name only. §5.1 already applies the same rule one level down, normalizing a
    node-id segment before escaping it.
    """
    spelling = spell_routing_label(label)
    if spelling.label is not None:
        return spelling.label
    raise ExtractionError.for_object(
        workflow,
        f"the {where} declares the non-string routing label of type "
        f"{type_identity(label)}, which ir cannot spell: {spelling.refusal}. A path_map key "
        "is a string, or a plain Enum member whose stored value is a str, spelled as that "
        "value (INTROSPECTION-SPEC §6; DEC-32 as amended by DEC-38); every other key is "
        "refused rather than coerced, because a coerced spelling would land inside "
        "graph_version. Use string labels, or a str-valued Enum (plain or string-mixin), with "
        "the router returning the same members or strings (e.g. 'yes'/'no' instead of "
        "True/False)",
        reason=ExtractionErrorReason.CONSTRUCT_NOT_CARRIED,
        family=ObjectFamily.BUILDER,
    )


def _routing_target(target: object, *, workflow: object, where: str) -> str:
    """A declared routing target as a built-in ``str``, or a refusal before anything touches it.

    INTROSPECTION-SPEC §6 (DEC-38 §3.5): "A ``path_map`` **value** (a routing target) that is
    not a ``str`` instance is likewise refused, before any comparison, hashing or escaping runs
    on it — targets are node names or ``END``, and the admission is for keys only." Two routes
    put a member there: a ``Literal[E.A]`` return hint on a router with no ``path_map``
    (``ends = {E.A: E.A}``), and a node routing declaration naming one. On a member,
    ``target == END`` would run its ``__eq__``, the reserved-segment test would hash it
    (``Enum.__hash__`` reads ``_name_`` through the member's own attribute access), and the
    escaping would fail with a raw ``TypeError`` out of ``extract()`` — so the test here is
    ``issubclass(type(target), str)``, which reads nothing from the object, and it runs at every
    target-reading site, ahead of each of those operations. A target with no name at all has no
    node id, so the reason is ``UNREPRESENTABLE_NODE_ID``.

    A ``str`` target — a ``str`` subclass included — is projected through
    ``"".join((target,))`` first, the C-level read DEC-32 gives a label: a subclass's own
    ``__eq__`` and ``__hash__`` would otherwise run under ``== END`` and the reserved-segment
    test, and NFC hands a subclass object back unchanged on CPython 3.10–3.13.
    """
    if issubclass(type(target), str):
        return "".join((cast(str, target),))
    raise ExtractionError.for_object(
        workflow,
        f"the {where} routes to a target of type {type_identity(target)}; a routing target "
        "is a node name or END, so it has no node id and this build refuses before reading "
        "it (INTROSPECTION-SPEC §6, DEC-38: the admission of an Enum member is for labels "
        "only) — route to the node's name, and keep the enum member for the label",
        reason=ExtractionErrorReason.UNREPRESENTABLE_NODE_ID,
        family=ObjectFamily.BUILDER,
    )


def _refuse_label_collision(
    label: str, seen_labels: set[str], *, workflow: object, where: str
) -> None:
    """Refuse two declared labels that resolve to one ``path_map`` key (DEC-32, DEC-38).

    The check runs over the **projected** labels — what :func:`_path_map_label` made of each
    declared key — so it sees every collision the projection itself produces: distinct authored
    spellings sharing one NFC form (composed vs decomposed accents being the live case), an
    admitted enum member's stored value meeting a string label (``{E.TOOL: …, "tool": …}``,
    which the substrate keeps as two keys), members of two enum classes with one stored value,
    and, on a ``destinations=`` dict, two targets declared under one label. Keeping the last
    writer would silently drop a declared edge from ``graph_version``: a partial IR through the
    back door, which §2's posture forbids. The collision is a fact about the handed object,
    never the build, so the fix is the caller's — rename one label.

    ``label`` and every member of ``seen_labels`` are built-in ``str`` objects (the projection
    returns nothing else), so the membership test runs ``str``'s own hash and comparison only.
    """
    if label in seen_labels:
        raise ExtractionError.for_object(
            workflow,
            f"the {where} declares two routing labels that resolve to the single "
            f"path_map key {label!r} after projection (NFC normalization, or an Enum "
            "member's stored value); a merged key would silently drop a declared edge from "
            "graph_version, so this build refuses — rename one label (a collision is an "
            "error, never a merge; DEC-32, DEC-38)",
            reason=ExtractionErrorReason.LABEL_COLLISION,
            family=ObjectFamily.BUILDER,
        )
    seen_labels.add(label)


def _node_id(name: str, *, workflow: object, role: str) -> str:
    """A source name as an IR node id — NFC-normalized, then percent-escaped (ledger §5).

    The one place a name becomes an id, so node ids and the references that point at them are
    escaped by the same rule and compare by byte equality (§5.1).

    A reference to a name that no node declares is *not* refused here: it is escaped and
    emitted, because "whether a reference resolves" is P-01's verdict (its
    ``edge-target-undefined`` family), not extraction's. What is refused is a name with no
    representable id at all — the substrate admits an empty node name, and ``""`` is not a
    node id under any grammar, so no future build will carry it either.
    """
    try:
        return node_id_from_names([name])
    except NodeIdError as error:
        raise ExtractionError.for_object(
            workflow,
            f"the {role} {name!r} has no representable node id: {error}",
            reason=ExtractionErrorReason.UNREPRESENTABLE_NODE_ID,
            family=ObjectFamily.BUILDER,
        ) from error
