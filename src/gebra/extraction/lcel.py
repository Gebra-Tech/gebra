"""LCEL fragment stitching — the INTROSPECTION-SPEC §5 rule set.

Normative authority: INTROSPECTION-SPEC §5 (the five stitching rules), §2 (the family-3
dispatch row, the degenerate-input rule, the termination rule and the error posture), §8 (the
warnings taxonomy), and IR-SPEC §5.2 (the closed synthetic-token vocabulary) — all under the
§1 never-invokes discipline.

**What a synthetic segment names.** §5 rule 3 keys a stitched node by ``"%" kind "["
selector "]"`` with ``kind`` from the closed IR-SPEC §5.2 vocabulary and ``selector`` "= source
key when one exists else the zero-based structural index". The reading this module implements
is the one rule 3's own ordering clause forces: **``kind`` is the containing composite's kind
and ``selector`` places the child inside it.** Rule 3 enumerates a "per-kind child order" over
containers — ``RunnableSequence`` children in ``.steps`` order, ``RunnableParallel`` children
in its mapping's insertion order with the source key preferred, a ``RunnableBranch``'s bodies in
declaration order then its default (conditions are §6 guards, never children), a
``RunnableLambda``'s captured runnables in the derived static order :func:`_deps` states, and
fallbacks and bind wrappers in definition order — and then says "this ordering determines the
``%kind[selector]`` indices". (The branch and deps clauses are DEC-20's, 2026-08-03; the rest is
as first drafted.) So the spec's three examples read off directly: ``%seq[0]`` is
member 0 of a sequence, ``%map[docs]`` is the ``docs`` branch of a parallel, ``%lambda[1]`` is
dep 1 of a lambda. This ordering is digest-critical — it fixes ``node_id``s, hence
``graph_version`` — and "two conforming extractors MUST produce identical indices".

**The frame, and who carries it.** §5 rule 4 mounts a fragment extracted from node ``n`` as
``n/%seq[0]``: the composite itself contributes **no segment** and its children hang off the
carrier's path, while "``n`` itself persists in ``nodes[]`` as the fragment's parent and
remains the carrier of the node-level contract annotations". Applied to the §2 family-3 path,
where the whole object *is* the fragment, the root composite likewise contributes no segment —
"the root graph contributes no segment" (IR-SPEC §5.1) — so its children are top-level ids.
Fragment-internal edges are emitted "between the ``n/…`` children only" and "parent↔fragment
linkage is structural path containment", which is the (H3) clause of IR-SPEC §7; nothing is
ever re-pointed at a fragment's heads or tails, so multi-head composites need no
edge-inheritance rule and a child edge points at the child node whatever that child contains.

**The degenerate one-fragment case.** §2 sends any other ``Runnable`` to "§5: fragment
extraction of the whole object as a degenerate one-fragment topology". A runnable with no
readable children has no containing composite, so it stands as the sole member of its own
kind's frame and takes selector ``0`` — a bare ``RunnableLambda`` extracts to the single node
``%lambda[0]``. A runnable that is neither one of the seven kinds nor composes anything has no
ir 1.0 segment at all, and is refused at the object boundary rather than given an invented one:
adding a token to the closed vocabulary is a minor-version change (IR-SPEC §8). §2's family-3
row and error posture state that refusal in terms (ratified — DEC-20, 2026-08-03), with a 1.x
register for the kinds it would take to admit such an object. This only ever reaches the
whole-object case — a leaf *inside* a frame is named by its frame, so any runnable at all can be
a fragment child.

**Never-invokes, and the one hazard this path has.** Composition is read from attributes and
``isinstance`` checks (§1 rule 3); ``get_graph()`` is never called here, so the fresh
``uuid4`` ids §5 rule 2 forbids are never even constructed, and the schema-placeholder nodes
rule 1 trims are never built. One surface is different: ``RunnableLambda.deps`` is a
``cached_property`` that runs ``get_function_nonlocals``, which resolves **dotted** nonlocal
names by walking ``getattr`` chains over the closure's and module's values — a user object with
a property on such a chain would execute inside ``gebra.extract()``. DEC-19 made a
provenance-verified hazard gate the required posture in front of a surface like this, and
:func:`_deps_hazard` is that gate here: it reads the callable's own definition, takes the
attribute chains the substrate's own visitor would resolve — :class:`_OutsideNames` is a
transcription of it, so the set is the same one and not an approximation of it — and admits the
read only when every object a chain would reach is stock substrate. A hazard
**declines** the read — the lambda stays a leaf and one ``unsupported-construct`` records it,
which is a fact about that object rather than about this build, so it does not over-fire.

The same posture covers the composites: a kind is recognised by **exact type**, so the
*composition* members — ``first``/``middle``/``last``, ``steps__``, ``branches``/``default``,
``deps``, ``runnable``/``fallbacks``, ``bound`` — are read only off the stock classes, and a
subclass that overrode one is kept opaque and warned instead. One set of subclasses is named and
admitted: the stock langchain-core ``RunnableBinding`` subclasses A1-D21 enumerates
(``_ChatModelBinding`` at the pin), which INTROSPECTION §7.4 (a) as amended by DEC-21 admits *by
exact type* so that a tool-bound chat model is reached at all —
:mod:`gebra.extraction.stock` is that enumeration and the reasoning behind it. Everything
outside the enumeration, subclasses of it included, stays declined. **What that does not cover, said
plainly:** every stitched node, foreign ones included, still goes through ANNOTATION §6's
wrapper walk (:func:`gebra.extraction.contracts.walk`), which reads ``__wrapped__``, ``func``,
``afunc``, ``coroutine`` and ``bound`` by name. §6 *requires* that walk — it is how a contract
is located at all — so it is not this path's to gate; the claim here is about which members
decide the node set and the ids, not about every attribute anything reads.

**What this module does not do.** It stitches a fragment handed to ``gebra.extract()``. Wiring
§5 discovery into §3's ``StateNodeSpec.runnable`` row — a chain bound as a StateGraph node —
is not part of this path; :func:`stitch_fragment` takes the rule-4 ``carrier`` prefix so the
seam exists and is tested, but no builder-level extraction calls it yet.
"""

from __future__ import annotations

import ast
import itertools
import types
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Final

from langchain_core.runnables import (
    Runnable,
    RunnableBranch,
    RunnableLambda,
    RunnableParallel,
    RunnableSequence,
)
from langchain_core.runnables.base import RunnableBinding, RunnableBindingBase
from langchain_core.runnables.fallbacks import RunnableWithFallbacks
from langchain_core.runnables.retry import RunnableRetry

from gebra.annotations.inference import SourceCache, read_node_source
from gebra.annotations.sidecar import SidecarReading
from gebra.annotations.slots import SlotGrade
from gebra.extraction.base import ObjectFamily, type_identity
from gebra.extraction.contracts import resolve_node, walk
from gebra.extraction.digests import NodeDigests, digests_for
from gebra.extraction.envelope import ExtractedFrom, ExtractionEnvelope
from gebra.extraction.errors import ExtractionError, ExtractionErrorReason
from gebra.extraction.sidecar import sidecar_warnings, unknown_node_warnings
from gebra.extraction.stock import is_binding
from gebra.extraction.warnings import ExtractionWarning, ExtractionWarningCode
from gebra.ir.identity import SYNTHETIC_KINDS, join_node_id, synthetic_segment
from gebra.ir.models import Annotations, Node, NormalEdge, WorkflowIR, lowest_ir_version

if TYPE_CHECKING:
    from gebra.annotations.contract import NodeContract
    from gebra.extraction.dispatch import Dispatch
    from gebra.ir.models import Edge

__all__ = [
    "FRAGMENT_CLASSES",
    "FragmentKind",
    "FragmentReading",
    "extract_lcel_fragment",
    "kind_of",
    "stitch_fragment",
]


class FragmentKind(str, Enum):
    """The closed ir 1.0 synthetic-kind vocabulary, as LCEL composition classes (§5.2).

    Seven tokens, fixed at the 1.0 freeze; adding one is a minor-version change (IR-SPEC §8),
    so this enum is the vocabulary rather than a view of it. Each member names the *composite*
    whose children the token indexes — :data:`FRAGMENT_CLASSES` is that correspondence, and
    :func:`kind_of` is the lookup.
    """

    SEQ = "seq"
    """``RunnableSequence`` — its steps, in ``.steps`` list order."""
    MAP = "map"
    """``RunnableParallel`` — its branches, keyed by the source-level dict key."""
    BRANCH = "branch"
    """``RunnableBranch`` — its declared branches, then its default."""
    LAMBDA = "lambda"
    """``RunnableLambda`` — the runnables captured in its function's closure (``deps``)."""
    RETRY = "retry"
    """``RunnableRetry`` — the single runnable it retries."""
    FALLBACK = "fallback"
    """``RunnableWithFallbacks`` — the primary runnable, then its alternatives."""
    BIND = "bind"
    """``RunnableBinding`` — the single runnable a ``.bind()``/``.with_config()`` wraps."""


#: kind → the stock langchain-core class it names, in match order.
#:
#: **Exact type, not ``isinstance``**, and the order matters for one pair: ``RunnableRetry`` is
#: a ``RunnableBindingBase`` subclass, so an ``isinstance`` table would have to be read in this
#: order anyway. Exact matching is also this path's WA-07 gate — a subclass could override
#: ``steps``/``deps``/``bound`` with a property of its own, and reading it would run user code
#: inside ``gebra.extract()``. A subclass is therefore kept opaque and warned (§8), which is the
#: conservative direction: structure is under-reported and said to be, never invented.
#:
#: The ``bind`` row has a second, *enumerated* half — :data:`gebra.extraction.stock.
#: STOCK_BINDING_SUBCLASSES`, which §7.4 (a) as amended by DEC-21 admits by exact type. It is
#: kept out of this table because this one is the kind → **stock class** correspondence the
#: ``%kind[selector]`` grammar is written against, one class per token; the admission is a
#: widening of the gate, not a second class for the token.
FRAGMENT_CLASSES: Final[tuple[tuple[FragmentKind, type], ...]] = (
    (FragmentKind.SEQ, RunnableSequence),
    (FragmentKind.MAP, RunnableParallel),
    (FragmentKind.BRANCH, RunnableBranch),
    (FragmentKind.LAMBDA, RunnableLambda),
    (FragmentKind.RETRY, RunnableRetry),
    (FragmentKind.FALLBACK, RunnableWithFallbacks),
    (FragmentKind.BIND, RunnableBinding),
)

#: The base classes that really do hold composition, for the one warning :func:`kind_of`'s
#: exact matching owes: an object that *is* a composite but is not the stock class carries
#: children this path declines to read, and saying so is the difference between "no
#: composition" and "composition not read". ``RunnableBindingBase`` rather than
#: ``RunnableBinding`` because it is the base every wrapper of that family shares — a
#: ``RunnableWithMessageHistory`` holds a ``bound`` exactly as a ``.bind()`` result does.
_COMPOSITE_BASES: Final[tuple[tuple[FragmentKind, type], ...]] = (
    (FragmentKind.SEQ, RunnableSequence),
    (FragmentKind.MAP, RunnableParallel),
    (FragmentKind.BRANCH, RunnableBranch),
    (FragmentKind.LAMBDA, RunnableLambda),
    (FragmentKind.RETRY, RunnableRetry),
    (FragmentKind.FALLBACK, RunnableWithFallbacks),
    (FragmentKind.BIND, RunnableBindingBase),
)

#: How deep the §5 walk descends before it stops and says so. A bound rather than a policy: a
#: composition this deep is either generated or cyclic in a way the identity guard of §2's
#: termination rule did not catch, and a recorded stop is a better answer than a
#: ``RecursionError`` out of ``gebra.extract()``.
_MAX_DEPTH: Final = 32

#: The packages whose objects the §5 deps gate treats as substrate rather than as user code.
#: The same line DEC-19 drew for the drawing gate: LangChain's and LangGraph's own attribute
#: access on their own objects is library work, and this path states that residue rather than
#: denying it; anything else on a ``getattr`` chain declines the read.
_STOCK_ROOTS: Final[frozenset[str]] = frozenset({"langchain_core", "langgraph", "builtins"})


def kind_of(runnable: object) -> FragmentKind | None:
    """The §5.2 kind ``runnable`` names, or ``None`` when no token in the closed set does.

    Exact-type matching — see :data:`FRAGMENT_CLASSES` for why that is the never-invokes gate
    and not merely a lookup strategy — over the seven stock classes **and** the enumerated stock
    ``RunnableBinding`` subclasses of :mod:`gebra.extraction.stock`, which §7.4 (a) as amended by
    DEC-21 admits by exact type so that a model inside ``model.bind(tools=…)`` is reached.
    ``is`` throughout: a subclass of an admitted class is not admitted.
    """
    holder = type(runnable)
    for kind, stock in FRAGMENT_CLASSES:
        if holder is stock:
            return kind
    return FragmentKind.BIND if is_binding(holder) else None


def extract_lcel_fragment(
    dispatch: Dispatch, /, *, sidecar: SidecarReading | None = None
) -> ExtractionEnvelope:
    """Extract an LCEL ``Runnable`` into the core IR and its provenance envelope (§5).

    The §2 family-3 path: "fragment extraction of the whole object as a degenerate one-fragment
    topology". Compiled-level and builder-level surfaces have no source here at all, so
    ``state``, ``runtime`` and ``extracted_from.compiled`` are absent rather than guessed
    (§0's never-guess discipline).

    Args:
        dispatch: The §2 classification decision; its ``workflow`` is the runnable §5 applies
            to and is what any boundary refusal names.
        sidecar: The ANNOTATION §2 sidecar reading for this extraction — already discovered,
            parsed and validated by the entry point. Its entries are keyed by node id, which on
            this path means a synthetic token (``"%seq[0]"``), and they are the §3 tier-3
            contribution to each stitched node's resolved contract.

    Returns:
        The envelope: the core IR, its provenance, and the structured warnings, in source
        order — the sidecar's own file-level findings, then the §5 reading's, then the
        unmatched-key findings.

    Raises:
        ExtractionError: at the object boundary only (§2) — a runnable that composes nothing
            and that no ir 1.0 synthetic kind names, or a fragment whose children collide on
            one node id.
    """
    annotations = SidecarReading() if sidecar is None else sidecar
    reading = stitch_fragment(dispatch.workflow, sidecar=annotations)
    ir = reading.ir()
    return ExtractionEnvelope(
        ir=ir,
        extracted_from=ExtractedFrom(
            source=type_identity(dispatch.workflow),
            family=ObjectFamily.LCEL,
            sidecar=None if annotations.path is None else str(annotations.path),
        ),
        warnings=(
            *sidecar_warnings(annotations),
            *reading.warnings,
            *unknown_node_warnings(annotations, (node.id for node in ir.nodes)),
        ),
    )


def stitch_fragment(
    runnable: object,
    *,
    carrier: Sequence[str] = (),
    sidecar: SidecarReading | None = None,
) -> FragmentReading:
    """Walk ``runnable``'s composition into stitched nodes and edges (§5 rules 1–5).

    Args:
        runnable: The fragment's root. It is read, never invoked (§1).
        carrier: The rule-4 mount path — the already-escaped segments of the enclosing node
            ``n``, so that fragment ids come out as ``n/%seq[0]``. Empty for the §2 family-3
            path, where the fragment *is* the whole object and the root contributes no segment
            (IR-SPEC §5.1).
        sidecar: The reading whose entries are looked up per stitched node id.

    Returns:
        The :class:`FragmentReading` collector — nodes, edges, the frame's head/tail ids, and the
        warnings, ready to be assembled or mounted.

    Raises:
        ExtractionError: on the two shapes §2 puts at the object boundary — a root with no
            representable id, and two children that would occupy one.
    """
    reading = FragmentReading(
        workflow=runnable,
        carrier=tuple(carrier),
        sidecar=SidecarReading() if sidecar is None else sidecar,
    )
    heads = _emit_frame(runnable, tuple(carrier), reading, depth=0, path=(id(runnable),))
    if heads:
        reading.entry = _heads(runnable, heads)
        reading.finish = _tails(runnable, heads)
        _warn_uncarried_root_contract(runnable, reading)
    else:
        node_id = _degenerate_id(runnable, reading)
        reading.add(node_id, runnable)
        reading.entry = (node_id,)
        reading.finish = (node_id,)
    return reading


# ── the collector ────────────────────────────────────────────────────────────────────────


@dataclass
class FragmentReading:
    """What one §5 walk has stitched so far.

    A mutable collector for the same reason the §3 pass has one: the node set, the edge set and
    the frame's head/tail ids are produced at different depths of one recursion, and threading
    them through return values would bury the rule each function transcribes.

    Attributes:
        workflow: The object handed in — what a boundary refusal names (§2).
        carrier: The rule-4 mount path this fragment hangs under.
        sidecar: The reading whose entries are the §3 tier-3 contribution per node.
        nodes: Node id → its resolved contract, in emission order (which is §5 rule 3's child
            order, depth first).
        digests: Node id → what §7.4 had to say about it. Only the carriers get an entry, and
            most fragments have none.
        edges: The fragment-internal ``normal`` edges — only a sequence frame produces any.
        entry: The frame's head ids; ``finish`` its tail ids (see :func:`_heads`).
        warnings: The §8 records, in emission order.
    """

    workflow: object
    carrier: tuple[str, ...] = ()
    sidecar: SidecarReading = field(default_factory=SidecarReading)
    nodes: dict[str, NodeContract | None] = field(default_factory=dict)
    digests: dict[str, NodeDigests] = field(default_factory=dict)
    edges: list[Edge] = field(default_factory=list)
    entry: tuple[str, ...] = ()
    finish: tuple[str, ...] = ()
    warnings: list[ExtractionWarning] = field(default_factory=list)
    cache: SourceCache = field(default_factory=SourceCache)

    def add(self, node_id: str, runnable: object, bindings: tuple[object, ...] = ()) -> None:
        """Emit one stitched node: its §3-resolved contract, its §5 rule-5 warning, its digests.

        Two ids that collide would silently merge two fragment children into one node — and
        would break the (m5) uniqueness IR-SPEC §4.2 takes after normalization — so a collision
        is a boundary refusal rather than a last-write-wins.

        ``bindings`` is the enclosing ``RunnableBinding`` chain, outermost first: §7.4 (a) puts
        ``config_digest`` on the node carrying the *model*, and (c) builds its ``"bound"``
        member out of the wrappers between that node and the composition around it. Every other
        node passes ``()`` and every non-carrier gets no entry at all, so this is where §7.4's
        "computed for exactly the nodes whose own bound object is …" is applied, once.
        """
        if node_id in self.nodes:
            raise ExtractionError.for_object(
                self.workflow,
                f"two fragment children occupy the node id {node_id!r}; ir 1.0 node ids are "
                "unique after NFC normalization (IR-SPEC §5.1/§4.2), and merging them would "
                "delete one child from the IR",
                reason=ExtractionErrorReason.CONSTRUCT_NOT_CARRIED,
                family=ObjectFamily.LCEL,
            )
        self.nodes[node_id] = self._contract(node_id, runnable)
        digests = digests_for(node_id, runnable, bindings=bindings)
        self.warnings.extend(digests.warnings)
        if digests:
            self.digests[node_id] = digests

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
        """Assemble the core IR from what was stitched (IR-SPEC §2.1).

        ``nodes[]`` is emitted **sorted by id**, as §6.2 orders it, so that an extraction
        compares equal to another *as a model* and not only after canonicalization — which is
        what a test, a golden or a cache compares. The comparator is Python's own code-point
        order rather than the UTF-16 code-unit order §6.2 fixes for canonical form; the two
        differ only between supplementary-plane characters and U+E000–U+FFFF, and
        canonicalization re-sorts before any byte is hashed, so they can never disagree about a
        digest. ``edges`` keeps emission order, which is the §5 rule-3 child order and is
        equally deterministic.
        """
        nodes = tuple(
            Node(id=node_id, annotations=_annotations(contract, self.digests.get(node_id)))
            for node_id, contract in sorted(self.nodes.items())
        )
        edges = tuple(self.edges)
        return WorkflowIR(
            # IR-SPEC §8's minimal stamping through the one helper (see the builder path): a
            # fragment carries no router, so this is "1.0" by the policy rather than by a
            # literal that would have to be found again if that ever changed.
            ir_version=lowest_ir_version(edges),
            entry=_collapse(self.entry),
            finish=_collapse(self.finish),
            state=None,
            nodes=nodes,
            edges=edges,
            runtime=None,
        )

    def _contract(self, node_id: str, runnable: object) -> NodeContract | None:
        """The node's contract through the §3 chain, plus §5 rule 5's ``opaque-lambda``.

        §5 rule 5: "A stitched lambda node MUST carry a decorator or sidecar contract, or
        extraction applies the D-011 conservative default … and emits ``opaque-lambda``". So
        the rule fires exactly when the node's chain reaches a ``RunnableLambda`` *and* a slot
        fell to a default rather than to a declaration.

        **The one place this build emits two codes where §8 words it as one, recorded rather
        than hidden.** §8's ``contract-defaulted`` row says that for stitched lambdas
        ``opaque-lambda`` "is emitted instead and carries the default". Taken literally, the
        defaulted slots on a stitched lambda would be named by ``opaque-lambda`` alone — and
        ANNOTATION §5's grade lookup is an **iff** over ``contract-inferred``/
        ``contract-defaulted`` only, so those slots would read back as *declared*-grade and
        unlock the ``pure`` ⟹ idempotent implication §4's NEVER-SILENT-UPGRADE corollary
        forbids. This build therefore emits ``opaque-lambda`` (rule 5, satisfied in terms) and
        keeps the ``contract-defaulted`` records (§5's lookup, kept sound). Over-warning costs a
        workflow the strict-mode bar it had already lost to ``opaque-lambda``; under-grading
        would cost a validator its footing. **Ratified — DEC-20, 2026-08-03**, which replaced
        §8's "instead" with "**in addition**" and states the reason in terms: both codes name
        the (node, slot) pair, so ANNOTATION §5's declared-grade *iff* stays sound. What was
        the conservative branch is now the conforming one.
        """
        resolved = resolve_node(
            node_id,
            runnable,
            sidecar_entry=self.sidecar.entries.get(node_id),
            state_schema=None,
            cache=self.cache,
        )
        self.warnings.extend(resolved.warnings)
        defaulted = (
            ()
            if resolved.inference is None
            else tuple(
                finding
                for finding in resolved.inference.findings
                if finding.grade is SlotGrade.DEFAULTED
            )
        )
        if defaulted and resolved.opaque:
            slots = sorted({slot for finding in defaulted for slot in finding.slots})
            self.warnings.append(
                ExtractionWarning(
                    code=ExtractionWarningCode.OPAQUE_LAMBDA,
                    message=(
                        f"the stitched lambda {node_id!r} declares no contract, so the "
                        f"conservative D-011 default applies to {slots}"
                    ),
                    node=node_id,
                    detail={
                        "defaults": {
                            slot: finding.message for finding in defaulted for slot in finding.slots
                        },
                        "attachment_options": (
                            "declare the contract with @gebra.contract on the wrapped function, "
                            "or key a gebra.toml [nodes.…] entry by this node id "
                            "(ANNOTATION-API-SPEC §1/§2)"
                        ),
                    },
                )
            )
        return resolved.contract


def _annotations(contract: NodeContract | None, digests: NodeDigests | None) -> Annotations | None:
    """A stitched node's ``annotations`` — the resolved contract, the digests, or nothing.

    The two sources cannot collide: ANNOTATION §1 puts ``prompt_digest``/``config_digest``
    "computed, never annotated" outside the closed annotatable-slot set, so no declaration tier
    can reach either, and §7.4 is the only path that writes them.

    ``retry_policy`` has no source here: §3 projects it from a ``StateNodeSpec``, and a
    fragment child has none. A ``RunnableRetry``'s own settings are deliberately *not* read
    across into the slot — IR-SPEC §3.2's projection is specified over the substrate's
    ``RetryPolicy``, which is a LangGraph type, and inventing the mapping from LCEL's
    ``max_attempt_number``/``retry_exception_types`` pair would land a made-up value inside
    ``graph_version``. The composition is carried by the ``%retry[…]`` token instead.
    """
    members: dict[str, object] = (
        {}
        if contract is None
        else {slot: contract.slot_value(slot) for slot in contract.declared_slots()}
    )
    if digests is not None:
        if digests.prompt is not None:
            members["prompt_digest"] = digests.prompt
        if digests.config is not None:
            members["config_digest"] = digests.config
    if not members:
        return None
    return Annotations.model_validate(members)


def _collapse(wired: tuple[str, ...]) -> str | tuple[str, ...]:
    """A wired sentinel set in its canonical representation (IR-SPEC §6.3).

    Scalar iff singleton, list otherwise — emitted directly, as §6.3 requires of
    ``gebra.extract()``, so an extracted model already carries the one canonical form.
    """
    if len(wired) == 1:
        return wired[0]
    return tuple(sorted(set(wired)))


# ── the walk (§5 rules 1, 3, 4 and §2's termination rule) ─────────────────────────────────


def _emit_frame(
    runnable: object,
    carrier: tuple[str, ...],
    reading: FragmentReading,
    *,
    depth: int,
    path: tuple[int, ...],
    bindings: tuple[object, ...] = (),
) -> tuple[str, ...]:
    """Emit ``runnable``'s children under ``carrier`` and return their ids in §5 rule-3 order.

    The composite itself contributes no segment: rule 4 mounts children on the *carrier*'s
    path, and the carrier is the enclosing node ``n`` (or, on the family-3 path, nothing at
    all). Returns ``()`` when ``runnable`` is not a frame — no kind, no readable children, or
    a hazard that declined the read — which is what makes the caller's degenerate branch the
    honest one rather than a fallback.

    ``bindings`` is the contiguous chain of ``RunnableBinding`` frames enclosing this one,
    outermost first — §7.4 (a)'s "any chain of ``RunnableBinding`` wrappers", accumulated on
    the way down because a model node's ``config_digest`` needs the wrappers *above* it and a
    child never sees its ancestors otherwise. A frame of any other kind resets the chain to
    empty: (c) reads the overlay an invocation would pass straight into the model, and an
    intervening sequence or parallel is not that.
    """
    kind = kind_of(runnable)
    if kind is None:
        _warn_foreign_composite(runnable, carrier, reading)
        return ()
    if depth >= _MAX_DEPTH:
        reading.warn_unsupported(
            "lcel-fragment-too-deep",
            f"the composition nests deeper than {_MAX_DEPTH} levels, so this fragment is not "
            "expanded further and is carried as one opaque node",
            location={"parent": _location(carrier), "kind": kind.value},
            ir_partial=True,
        )
        return ()
    children = _children(runnable, kind, carrier, reading)
    if not children:
        return ()

    inherited = (*bindings, runnable) if kind is FragmentKind.BIND else ()
    ids: list[str] = []
    for selector, child in children:
        segment = synthetic_segment(kind.value, selector)
        node_id = join_node_id((*carrier, segment))
        if id(child) in path:
            # §2's termination rule: "an object already on the current walk path is never
            # re-expanded — it is kept as a single opaque node and `unsupported-construct`
            # (self-referential composition) is emitted".
            reading.warn_unsupported(
                "self-referential-composition",
                "this child is already on the current composition path, so it is carried as "
                "one opaque node rather than expanded again",
                location={"node": node_id},
                ir_partial=True,
                node=node_id,
            )
            reading.add(node_id, child, inherited)
        else:
            reading.add(node_id, child, inherited)
            _emit_frame(
                child,
                (*carrier, segment),
                reading,
                depth=depth + 1,
                path=(*path, id(child)),
                bindings=inherited,
            )
        ids.append(node_id)

    if kind is FragmentKind.SEQ:
        # §5 rule 1: a sequence "concatenat[es] step graphs … adding an edge from each step's
        # last node to the next step's first node". Rule 4 forbids re-pointing anything at a
        # fragment's heads or tails, so the edge is between the *child nodes*, whatever each
        # child turns out to contain — which is also why a multi-head child needs no rule.
        reading.edges.extend(
            NormalEdge(kind="normal", **{"from": source}, to=target)
            for source, target in itertools.pairwise(ids)
        )
    return tuple(ids)


def _children(
    runnable: object,
    kind: FragmentKind,
    carrier: tuple[str, ...],
    reading: FragmentReading,
) -> tuple[tuple[str | int, object], ...]:
    """One frame's children as ``(selector, child)`` pairs, in §5 rule 3's canonical order.

    Rule 3 fixes the order per kind, and this function is that clause transcribed. Every read
    is a plain attribute read of a pydantic model field on a stock class — with the single
    exception ``deps`` is, which goes through :func:`_deps_hazard` first.

    A ``RunnableBranch``'s *conditions* are not children: §6 makes a guard "an opaque
    reference", never evaluated and never persisted, and a condition callable is not part of
    the composition the ``%branch[…]`` tokens index.
    """
    if kind is FragmentKind.SEQ:
        middle = getattr(runnable, "middle", None)
        steps = (
            getattr(runnable, "first", None),
            *(middle if isinstance(middle, (list, tuple)) else ()),
            getattr(runnable, "last", None),
        )
        return tuple(enumerate(step for step in steps if step is not None))
    if kind is FragmentKind.MAP:
        return _map_children(runnable, carrier, reading)
    if kind is FragmentKind.BRANCH:
        branches = getattr(runnable, "branches", ())
        declared = tuple(
            pair[-1] for pair in branches if isinstance(pair, tuple) and len(pair) == 2
        )
        default = getattr(runnable, "default", None)
        return tuple(enumerate((*declared, *(() if default is None else (default,)))))
    if kind is FragmentKind.LAMBDA:
        return tuple(enumerate(_deps(runnable, carrier, reading)))
    if kind is FragmentKind.FALLBACK:
        fallbacks = getattr(runnable, "fallbacks", ())
        primary = getattr(runnable, "runnable", None)
        alternatives = tuple(fallbacks) if isinstance(fallbacks, (list, tuple)) else ()
        return tuple(enumerate((*(() if primary is None else (primary,)), *alternatives)))
    bound = getattr(runnable, "bound", None)
    return () if bound is None else ((0, bound),)


def _map_children(
    runnable: object,
    carrier: tuple[str, ...],
    reading: FragmentReading,
) -> tuple[tuple[str | int, object], ...]:
    """``RunnableParallel`` children, keyed by source key where the keys can carry it (§5 r3).

    Rule 3: children come "in the dict insertion order of its ``.steps`` mapping (the
    source-key selector is **preferred** when keys exist; the same order still fixes indices
    for unkeyed siblings)". Preference, not requirement — so a key the ir 1.0 grammar cannot
    carry sends the *whole frame* to indices rather than producing a half-keyed one, which
    keeps a frame's selectors one kind of thing and keeps the choice deterministic.

    Two keys can fail that test. A non-``str`` key has no specified spelling and is never
    ``str()``-ed here, for the reason ``builder.py`` gives for a ``path_map`` label: the value
    lands inside ``graph_version``, and calling ``__str__`` would run the key's own code (§1).
    And two keys that differ only below NFC normalize to one segment (IR-SPEC §5.1), which
    would collide.
    """
    steps = getattr(runnable, "steps__", None)
    if not isinstance(steps, dict):
        return ()
    keys = tuple(steps)
    usable = all(isinstance(key, str) for key in keys)
    if usable:
        normalized = [unicodedata.normalize("NFC", key) for key in keys]
        usable = len(set(normalized)) == len(normalized)
    if not usable:
        reading.warn_unsupported(
            "lcel-map-key-not-carried",
            "a parallel branch key is not a string or collides with another under NFC "
            "normalization, so this frame's children are keyed by structural index instead "
            "of by source key",
            location={"parent": _location(carrier)},
            ir_partial=False,
        )
        return tuple(enumerate(steps.values()))
    return tuple((key, steps[key]) for key in keys)


def _deps(
    runnable: object,
    carrier: tuple[str, ...],
    reading: FragmentReading,
) -> tuple[object, ...]:
    """A ``RunnableLambda``'s captured runnables, in a deterministic order (§5 rule 1/3).

    §5 rule 1: "``RunnableLambda`` with ``deps`` draws like Parallel"; rule 3 orders them "in
    definition order", and that order fixes ``%lambda[i]`` indices, hence ``node_id``s, hence
    ``graph_version``.

    **Why the substrate's ``deps`` member is not what this returns.** ``RunnableLambda.deps``
    resolves its candidates through ``inspect.getclosurevars``, whose global-name loop iterates
    a ``set``: at CPython 3.13 the resulting order varies with ``PYTHONHASHSEED``, so a lambda
    capturing two runnables answers ``deps`` in a **different order in different processes**.
    Reading it would put a process-dependent index inside a digest, which IR-SPEC §5.3 ("stable
    within ``graph_version``: re-extracting unchanged source yields byte-identical ids") and
    §1.2 conformance both forbid. So this derives the same set from the same two sources — the
    code object's global names and the closure's free variables — in the code object's own
    first-reference order, which is deterministic and is what "definition order" can mean
    statically. Set-equality with the substrate's own answer is asserted in the tests; only the
    *order* is this build's.

    The gate is :func:`_deps_hazard`, and it is all-or-nothing: a partly-resolved dependency
    list would renumber the siblings that were resolved, so a hazard declines the whole read.
    The lambda then stays a leaf and the decline is recorded, because "this object's
    dependencies were not read" is a fact about the object rather than about the build.
    """
    if not isinstance(runnable, RunnableLambda):
        return ()
    function = _closure_source(_wrapped_callable(runnable))
    body = _read_body(function, reading.cache)
    if body is None:
        return ()
    candidates = _closure_candidates(function)
    hazard = _deps_hazard(body, candidates)
    if hazard is not None:
        reading.warn_unsupported(
            "lcel-deps-not-read",
            f"{hazard}, so any runnable captured in this lambda's closure is not stitched and "
            "the lambda is carried as one opaque node",
            location={"parent": _location(carrier)},
            ir_partial=True,
        )
        return ()
    return _captured_runnables(body, candidates)


# ── the frame's heads and tails ──────────────────────────────────────────────────────────


def _heads(runnable: object, children: tuple[str, ...]) -> tuple[str, ...]:
    """Which children the frame's input reaches — the fragment's ``entry`` (IR-SPEC §4.2).

    A sequence has one head, its first step. Every other frame hands its input to all of its
    children at once — a parallel fans out, a branch and a fallback chain choose one of theirs
    at runtime, a retry and a binding wrap exactly one — so all of them are heads. Choosing
    "all" for the alternative-shaped frames is the conservative direction: it over-reports
    reachability rather than claiming a static choice extraction cannot make (§6, "guards are
    opaque references").
    """
    if kind_of(runnable) is FragmentKind.SEQ:
        return children[:1]
    return children


def _tails(runnable: object, children: tuple[str, ...]) -> tuple[str, ...]:
    """Which children produce the frame's output — the fragment's ``finish`` (IR-SPEC §4.2)."""
    if kind_of(runnable) is FragmentKind.SEQ:
        return children[-1:]
    return children


def _degenerate_id(runnable: object, reading: FragmentReading) -> str:
    """The node id for §2's degenerate one-fragment case.

    §2 dispatches any other ``Runnable`` to "§5: fragment extraction of the whole object as a
    degenerate **one-fragment** topology". With nothing composed there is no containing frame
    to name the object, so it stands as the sole member of its own kind's frame and takes the
    zero-based structural index rule 3 gives an unkeyed sibling: a bare ``RunnableLambda``
    extracts to ``%lambda[0]``.

    Raises:
        ExtractionError: when no token in the closed §5.2 vocabulary names the object. That is
            §2's boundary posture applied to the shape it was written for — an object with "no
            extractable content [that] cannot satisfy the IR's ``nodes`` minItems 1" — and the
            alternative is not available to a 1.0 build: adding a synthetic kind is a
            minor-version change (IR-SPEC §8), never an extractor's improvisation.
    """
    kind = kind_of(runnable) or _base_kind(runnable)
    if kind is None:
        raise ExtractionError.for_object(
            reading.workflow,
            "this Runnable composes nothing that ir 1.0 can name: the synthetic-kind "
            f"vocabulary is closed at {sorted(SYNTHETIC_KINDS)} (IR-SPEC §5.2) and none of "
            "those tokens names this object, so it has no node id and there is nothing to "
            "extract (INTROSPECTION-SPEC §2)",
            reason=ExtractionErrorReason.CONSTRUCT_NOT_CARRIED,
            family=ObjectFamily.LCEL,
        )
    return join_node_id((*reading.carrier, synthetic_segment(kind.value, 0)))


def _base_kind(runnable: object) -> FragmentKind | None:
    """The kind a *subclass* of a composite answers to, for naming only.

    Exact-type matching decides whether this path reads an object's **children**; it is not
    the right question for what to *call* the object. A ``RunnableLambda`` subclass is still a
    lambda, and naming it ``%lambda[0]`` says the true thing while its unread composition is
    carried by the ``lcel-composition-not-stock`` warning :func:`_warn_foreign_composite`
    already emitted.
    """
    for kind, stock in _COMPOSITE_BASES:
        if isinstance(runnable, stock):
            return kind
    return None


def _warn_uncarried_root_contract(runnable: object, reading: FragmentReading) -> None:
    """A frame root's own declared contract has no carrier on the family-3 path (§5 rule 4).

    Rule 4 gives the carrier role to the enclosing node ``n``: "``n`` itself persists in
    ``nodes[]`` … and remains the carrier of the node-level contract annotations". The §2
    family-3 path has no ``n`` — the root contributes no segment (IR-SPEC §5.1) — so a contract
    declared on a root that *is* a frame lands nowhere. It is warned rather than dropped
    quietly, and only when a declaration tier actually spoke: the D-011 default every node
    would otherwise take says nothing about this object that its absence does not.

    The two tiers asked are the two a root can have. The sidecar tier cannot reach it by
    construction — ANNOTATION §2 keys entries by node id, and this object has none — which is
    the same reason the warning is about the *root* rather than about the sidecar.
    """
    if reading.carrier:
        return
    declarations = walk(runnable)
    if declarations.contract is None and declarations.tool is None:
        return
    reading.warn_unsupported(
        "fragment-root-contract-not-carried",
        "a contract is declared on the fragment's root, and the root of a whole-object "
        "extraction contributes no node to carry it — §5 rule 4 gives that role to the "
        "enclosing node, which this path has none of",
        location={"root": type_identity(runnable)},
        ir_partial=True,
    )


def _warn_foreign_composite(
    runnable: object, carrier: tuple[str, ...], reading: FragmentReading
) -> None:
    """A subclass of a composite kind is kept opaque, and says so (§8).

    Only a genuine *subclass* is warned. A stock runnable that composes nothing —
    ``RunnablePassthrough``, a chat model, a tool — is a leaf and there is nothing to report
    about it; a subclass of one of the seven kinds, on the other hand, really does hold
    composition this path declines to read, because reading it would call whatever the subclass
    put in ``steps``/``deps``/``bound`` (§1 rule 3's list admits no such call).

    The enumerated stock binding subclasses never reach here: :func:`kind_of` admits them, so
    their composition *is* read and there is nothing unread to report (§7.4 (a) as amended by
    DEC-21). What still reaches here is every other subclass, which is DEC-20's stockness
    discipline intact.
    """
    for kind, stock in _COMPOSITE_BASES:
        if isinstance(runnable, stock):
            reading.warn_unsupported(
                "lcel-composition-not-stock",
                f"this object is a {type_identity(runnable)} rather than the stock "
                f"{stock.__qualname__} the {kind.value!r} token names, so its composition is "
                "not read — a subclass can answer the composition members with code of its "
                "own, which extraction never runs",
                location={"parent": _location(carrier)},
                ir_partial=True,
            )
            return


def _location(carrier: tuple[str, ...]) -> str:
    """Where in the fragment something was found — the carrier path, or the root."""
    return join_node_id(carrier) if carrier else "<fragment root>"


# ── reading a lambda's captured runnables, and the gate in front of it ───────────────────


@dataclass(frozen=True)
class _Body:
    """What one lambda body loads from outside itself, read from its source (§5 rule 1).

    Attributes:
        names: The plain names the body loads — the undotted half of the substrate's own
            ``loads - stores`` nonlocal set.
        chains: The dotted attribute loads, as name paths from the rooting name, in source
            order. Nested chains contribute their prefixes too, which only widens what the
            gate checks.
    """

    names: frozenset[str]
    chains: tuple[tuple[str, ...], ...]


class _OutsideNames(ast.NodeVisitor):
    """The substrate's own nonlocal-name visitor, with the dotted names kept **ordered**.

    A transcription of ``langchain_core.runnables.utils.NonLocals``, deliberately including the
    two behaviours that are easy to miss and that both change the answer:

    * ``visit_Attribute`` does **not** descend into the attribute's own value, so a name that
      appears only under an attribute load is never seen as a plain name — and the root of a
      dotted chain is explicitly *discarded* from the plain set. A body spelling
      ``CHAIN.no_such_member`` therefore captures nothing, while one spelling ``CHAIN``
      captures it.
    * A chain rooted at a **call** contributes too (``f().attr`` records ``f``;
      ``obj.method().attr`` records ``obj.method``), which is why this is a transcription
      rather than a simplification: leaving it out would make the derived set a strict subset
      of the substrate's, and a missing dependency renumbers every sibling after it.

    The one deliberate difference is the point of the exercise: the substrate keeps its result
    in a ``set``, and this keeps the dotted chains in traversal order (see :func:`_deps`).
    """

    def __init__(self) -> None:
        self.loads: set[str] = set()
        self.stores: set[str] = set()
        self.chains: list[tuple[str, ...]] = []

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, ast.Load):
            self.loads.add(node.id)
        elif isinstance(node.ctx, ast.Store):
            self.stores.add(node.id)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if not isinstance(node.ctx, ast.Load):
            return
        parts, parent = _attribute_path(node)
        if isinstance(parent, ast.Name):
            self.chains.append((parent.id, *parts))
            self.loads.discard(parent.id)
        elif isinstance(parent, ast.Call):
            if isinstance(parent.func, ast.Name):
                self.loads.add(parent.func.id)
            else:
                inner, root = _attribute_path(parent.func)
                if isinstance(root, ast.Name) and inner:
                    self.chains.append((root.id, *inner))

    def body(self) -> _Body:
        """The (plain names, dotted chains) split, with the substrate's ``loads - stores``."""
        return _Body(
            names=frozenset(self.loads - self.stores),
            chains=tuple(self.chains),
        )


def _attribute_path(node: ast.expr) -> tuple[tuple[str, ...], ast.expr]:
    """Unwind an attribute chain into its parts (outermost last) and whatever roots it."""
    parts: list[str] = []
    current = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    return tuple(reversed(parts)), current


def _read_body(function: Any, cache: SourceCache | None = None) -> _Body | None:
    """``function``'s own definition, as the names it loads from outside itself; else ``None``.

    The source is located by :func:`gebra.annotations.inference.read_node_source`, **not** by
    :func:`inspect.getsource`. That is the ratified route for this repo and the reason is
    WA-07: ``inspect``'s lookup falls back through :mod:`linecache` to a module's own
    ``__loader__.get_source()`` and sweeps ``sys.modules`` through ``inspect.getmodule`` — both
    user code running inside what is supposed to be a read — and ``getsourcelines`` additionally
    reads ``__wrapped__`` off the caller's object. The engine's reader names the file from the
    code object, reads it as bytes and locates the definition by name and line, which is why
    the ANNOTATION §4 tripwire can arm ``inspect.getsource`` outright. Sharing that path also
    shares its cache: a fragment's lambdas usually live in one file.

    Where there is no definition to read — a callable object, a builtin, a file that is gone —
    the answer is ``None``, which is the substrate's "no dependencies" by another route.
    """
    if function is None:
        return None
    source = read_node_source(function, cache=cache)
    if source.definition is None:
        return None
    visitor = _OutsideNames()
    visitor.visit(source.definition)
    return visitor.body()


def _deps_hazard(body: _Body, candidates: Mapping[str, object]) -> str | None:
    """Why a lambda's dependencies must not be resolved, or ``None`` when they may be.

    Resolving a **dotted** captured name means walking ``getattr`` from the closure or module
    value it roots at — and a user object with a ``property``, or a module with a PEP 562
    ``__getattr__``, anywhere on such a chain runs its own code inside ``gebra.extract()``. It
    is the same shape as the six routes DEC-19 ruled on for ``get_graph()``, and it takes the
    same answer: a provenance-verified gate, admitting only stock-substrate objects at every
    level of the walk.

    The gate is a *superset* check — it quantifies over every attribute chain in the body, not
    only over the ones that will turn out to name a runnable — and it is all-or-nothing, since
    a partly-resolved dependency list would renumber the siblings that did resolve.

    What it lets through is stated rather than denied: LangChain's and LangGraph's own attribute
    access on their own objects, which is library work and is what makes the read possible at
    all.
    """
    for chain in body.chains:
        root, *parts = chain
        if root not in candidates:
            continue
        subject: object = candidates[root]
        for part in parts:
            if not _is_stock(subject):
                return (
                    f"reading this lambda's dependencies would resolve {'.'.join(chain)!r} "
                    f"through a {type_identity(subject)}, which is not substrate — the "
                    "attribute access could run its code"
                )
            resolved = _read_attribute(subject, part)
            if resolved is _UNRESOLVED:
                break
            subject = resolved
    return None


def _captured_runnables(body: _Body, candidates: Mapping[str, object]) -> tuple[object, ...]:
    """The runnables a lambda body captures, in the code object's first-reference order.

    The membership rule is the substrate's: a captured value counts when it *is* a ``Runnable``,
    and a captured **bound method** counts for its ``__self__`` — which is what makes the
    ``CHAIN.invoke(state)`` idiom a dependency on ``CHAIN``. The order is
    :func:`_closure_candidates`'s, which is the code object's own, because the substrate's is
    not reproducible across processes (see :func:`_deps`).

    De-duplicated by identity: a body that names one chain both bare and dotted captures it
    once, and one node per captured runnable is what the ``%lambda[i]`` indices count.

    **The stock check is repeated here rather than inherited from the gate**, at both places
    this function reads an attribute. :func:`_deps_hazard` has already quantified over the same
    chains, so nothing new is refused — but the ``__self__`` probe below is a read the gate does
    *not* cover: a stock attribute may return an arbitrary value, and asking a foreign object
    for ``__self__`` would run its ``__getattr__``. Keeping the invariant local is what makes
    "no attribute of a non-substrate object is read" a property of this function rather than of
    the order two functions happen to be called in. A bound method's own type is ``builtins``,
    so the ``CHAIN.invoke`` idiom the substrate's rule targets is admitted unchanged.
    """
    found: list[object] = []
    seen: set[int] = set()

    def consider(value: object) -> None:
        target = value
        if not isinstance(target, Runnable):
            if not _is_stock(target):
                return
            owner = getattr(target, "__self__", None)
            if not isinstance(owner, Runnable):
                return
            target = owner
        if id(target) not in seen:
            seen.add(id(target))
            found.append(target)

    for name, value in candidates.items():
        if name in body.names:
            consider(value)
        for chain in body.chains:
            if chain[0] != name:
                continue
            subject: object = value
            for part in chain[1:]:
                if not _is_stock(subject):
                    break
                subject = _read_attribute(subject, part)
                if subject is _UNRESOLVED:
                    break
            else:
                consider(subject)
    return tuple(found)


#: What :func:`_read_attribute` answers when the attribute is not there. A sentinel rather than
#: ``None``, because ``None`` is a value a captured name can legitimately hold.
_UNRESOLVED: Final = object()


def _read_attribute(subject: object, name: str) -> Any:
    """One step of a dotted capture, or :data:`_UNRESOLVED`.

    Only ever called on a subject :func:`_is_stock` has admitted, so the read is substrate
    attribute access. ``AttributeError`` is the miss the substrate's own walk tolerates; nothing
    wider is caught, so a sentinel raised here still fails the run rather than reading as a miss.
    """
    try:
        return getattr(subject, name)
    except AttributeError:
        return _UNRESOLVED


def _wrapped_callable(runnable: object) -> Any:
    """The function a ``RunnableLambda`` holds, as ``deps`` itself selects it.

    ``deps`` prefers ``func`` and falls back to ``afunc``, and it selects by **presence**
    (``hasattr``), never by truthiness. The distinction is not stylistic: ``func or afunc``
    would evaluate ``bool(func)``, and a ``RunnableLambda`` accepts any callable — including a
    class instance whose ``__bool__``/``__len__`` is the caller's code. That is not on §1 rule
    3's list of permitted operations, and it is the same implicit-protocol call
    :func:`gebra.ir.identity.synthetic_segment` refuses when it invokes ``str.__str__``
    unbound.
    """
    if not isinstance(runnable, RunnableLambda):
        return None
    function = getattr(runnable, "func", None)
    return function if function is not None else getattr(runnable, "afunc", None)


def _closure_source(function: Any) -> Any:
    """Whose closure and body the captured names come from, when a decorator moved them.

    ``functools.wraps`` leaves the *wrapper* in ``func`` while the author's captures live one
    level in, so a chain-following decorator would otherwise contribute the decorator's own
    closure and the decorator's own body. Both halves are taken from the same object here —
    which is also what the substrate ends up reading, since ``inspect.getsource`` follows
    ``__wrapped__`` and ``get_function_nonlocals`` reads that object's closure.

    ``callable`` is an ``isinstance``-grade check on the type, not a call.
    """
    wrapped = getattr(function, "__wrapped__", None)
    return wrapped if callable(wrapped) else function


def _closure_candidates(function: Any) -> dict[str, object]:
    """The module globals and free variables a captured name can resolve against.

    The substrate reaches these through ``inspect.getclosurevars``; this reads the same two
    sources directly — the code object's name list against the function's own ``__globals__``
    mapping, then its free variables out of the closure cells — because the ordering is the
    whole point (see :func:`_deps`): a code object's name list is fixed at compile time, while
    ``getclosurevars`` rebuilds its globals from a ``set``. Reading a cell's contents is a
    read; an unbound cell has no value to read and is skipped.
    """
    code = getattr(function, "__code__", None)
    if code is None:
        return {}
    candidates: dict[str, object] = {}
    module_globals = getattr(function, "__globals__", None)
    if isinstance(module_globals, dict):
        for name in code.co_names:
            if name in module_globals:
                candidates[name] = module_globals[name]
    closure = getattr(function, "__closure__", None) or ()
    for name, cell in zip(code.co_freevars, closure, strict=False):
        try:
            candidates[name] = cell.cell_contents
        except ValueError:  # pragma: no cover - an unbound cell cannot be reached from here
            continue
    return candidates


def _is_stock(value: object) -> bool:
    """Whether an attribute access on ``value`` runs substrate code rather than user code.

    Three subjects can appear on a chain and each is asked about its own provenance rather than
    its type's: a **module**, whose PEP 562 ``__getattr__`` would be user code; a **class**,
    whose metaclass or class-level descriptor would be; and an **instance**, whose type's
    ``property`` would be. Everything else is judged by the package its type comes from.
    """
    if isinstance(value, types.ModuleType):
        name = getattr(value, "__name__", "")
        return isinstance(name, str) and name.partition(".")[0] in _STOCK_ROOTS
    holder = value if isinstance(value, type) else type(value)
    module = getattr(holder, "__module__", "")
    return isinstance(module, str) and module.partition(".")[0] in _STOCK_ROOTS


#: **The residual this gate has, named rather than implied** — the same one
#: :func:`gebra.naming.type_identity` and ``compiled.py``'s level scan record. Deciding that an
#: object is *not* substrate takes one attribute read of its type (or of the module's
#: ``__name__``), so a sufficiently exotic metaclass — one overriding ``__getattribute__``, or
#: answering ``__module__`` from a descriptor — observes the question being asked before it is
#: answered "no". Nothing is read *of the value*, the answer is still "decline", and no further
#: attribute of it is touched; what cannot be avoided is that the refusal is observable.
_STOCK_PROBE_RESIDUAL = __doc__
