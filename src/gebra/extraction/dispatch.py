"""``gebra.extract()`` — the single entry point and its object-family dispatch.

Normative authority: INTROSPECTION-SPEC §2, whose pseudocode this module implements branch
for branch, under the §1 never-invokes discipline.

**What dispatch is allowed to do.** §1 rule 3 fixes the permitted operations: "attribute
reads, ``isinstance`` checks, ``typing.get_type_hints()``, pydantic model/JSON-schema
introspection, and the read-only getters named in §3–§5". Classification here uses the first
two and nothing else — no ``get_graph()`` call, no ``compile()`` (§1 rule 2 forbids it
outright: compilation "changes the object under inspection"), no duck-typed probing that
would call a method to find out whether it exists. ``callable(getattr(obj, "get_graph",
None))`` reads the attribute and asks whether it *is* callable; it never calls it.

**The four routes, three families.** §2 dispatches in order — a ``CompiledStateGraph`` or any
Pregel-protocol object with a ``.builder`` backreference takes §4 (builder-primary via the
backreference, plus compiled-only surfaces); an uncompiled ``StateGraph`` takes §3; a Pregel
with no backreference takes the §4.3 rule-4 compiled-only downgrade; any other ``Runnable``
takes §5. The first and third are one *family* under two sub-rules, which is why
:class:`Dispatch` carries :attr:`~Dispatch.compiled_only` rather than a fourth family: the §4
handler needs to know which sub-rule applies, and every consumer downstream of it — the
warning taxonomy included — treats both as compiled-level extraction.

**Errors are the boundary, warnings are the inside.** §2: an unsupported object "MUST raise a
typed ``ExtractionError`` naming the object type — never return a silent partial IR", while a
supported object carrying unmappable constructs extracts with warnings. This module owns the
boundary; :mod:`gebra.extraction.warnings` owns the inside.

**Where the per-family extraction paths are.** The three rule sets are separate task cards
(builder §3, compiled §4, LCEL §5), and each registers itself here through
:func:`register_extractor`. Until a family's path is registered, ``extract()`` refuses that
family with :data:`~gebra.extraction.errors.ExtractionErrorReason.EXTRACTOR_NOT_REGISTERED`
— which is the same discipline §2 states for an unsupported object, applied to a build that
does not carry the path yet: a refusal, never a partial IR.

**The first-extract version check (VERSION-COMPAT §4).** Every call runs
:func:`~gebra.extraction.compat.check_version_once`, which classifies the installed
substrate once per process. An in-range-but-untested pairing warns
:class:`~gebra.extraction.compat.GebraVersionWarning` on the first ``extract()`` call only;
an out-of-range one carries no Python warning but attaches an ``unsupported-construct``
extraction warning to every envelope produced while the install stays out of range, since an
envelope is a record of one extraction and the fact is true of each one. A bare ``import
gebra`` never reaches any of this — see :mod:`gebra.extraction.compat` for the full
rationale, including the one thing that *does* run at that module's own import and why.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

from langchain_core.runnables import Runnable
from langgraph.graph.state import CompiledStateGraph, StateGraph
from langgraph.pregel.protocol import PregelProtocol

from gebra.extraction.base import ObjectFamily
from gebra.extraction.compat import CompatClass, check_version_once, out_of_range_warning
from gebra.extraction.envelope import ExtractionEnvelope
from gebra.extraction.errors import ExtractionError, ExtractionErrorReason
from gebra.extraction.sidecar import load_sidecar

if TYPE_CHECKING:
    import os

    from gebra.annotations.sidecar import SidecarReading

__all__ = [
    "Dispatch",
    "Extractor",
    "classify",
    "extract",
    "extractor_for",
    "register_extractor",
    "unregister_extractor",
]


@dataclass(frozen=True)
class Dispatch:
    """The classification decision for one object: which rules apply, and to what.

    Attributes:
        family: The rule set (INTROSPECTION §2).
        workflow: The object handed to :func:`extract`, unchanged.
        builder: The ``StateGraph`` §3 applies to — ``workflow`` itself for
            :data:`~gebra.extraction.base.ObjectFamily.BUILDER`, the ``.builder``
            backreference for a compiled object that has a reachable one, and ``None``
            otherwise. "Builder-authoritative-when-available" (§4.3 rule 1) is exactly the
            statement that this member, when set, defines topology, state schema and
            per-node declarations.
        compiled_only: The §4.3 rule-4 downgrade: a compiled-level object with no reachable
            builder, "with every §3-derived field downgraded one knowability class". The
            handler that takes this path owes one ``compiled-only-extraction`` warning per
            extraction (§8).
    """

    family: ObjectFamily
    workflow: object
    builder: StateGraph[Any] | None = None
    compiled_only: bool = False


class Extractor(Protocol):
    """What a family's extraction path is, as seen from here.

    Takes a classified object and the sidecar reading for this extraction (ANNOTATION §2 —
    already discovered, parsed and validated, because "exactly **one** sidecar file per
    extraction" is a property of the entry point rather than of each path), and returns the
    provenance envelope. It never returns a partial IR and never ``None``: a failure inside a
    supported object is a warning on the envelope, and a failure at the boundary is an
    :class:`~gebra.extraction.errors.ExtractionError`.
    """

    def __call__(self, dispatch: Dispatch, /, *, sidecar: SidecarReading) -> ExtractionEnvelope: ...


#: The registered path per family. Empty at import; each family's card registers its own.
_EXTRACTORS: dict[ObjectFamily, Extractor] = {}


def register_extractor(family: ObjectFamily, implementation: Extractor) -> None:
    """Wire ``implementation`` in as the extraction path for ``family``.

    Raises:
        ValueError: if ``family`` already has a registered path. Re-wiring goes through
            :func:`unregister_extractor` first — silently replacing an extraction path is
            how two of them come to disagree about what a workflow means.
    """
    if family in _EXTRACTORS:
        raise ValueError(
            f"the {family.value!r} object family already has a registered extraction path; "
            "unregister it first"
        )
    _EXTRACTORS[family] = implementation


def unregister_extractor(family: ObjectFamily) -> None:
    """Drop the registered path for ``family``, if any. For tests and for re-wiring."""
    _EXTRACTORS.pop(family, None)


def extractor_for(family: ObjectFamily) -> Extractor | None:
    """The registered extraction path for ``family``, or ``None`` if none is wired yet."""
    return _EXTRACTORS.get(family)


def classify(workflow: object) -> Dispatch:
    """Decide which rule set applies to ``workflow`` — the §2 dispatch, isinstance-only.

    The branches are §2's, in §2's order. Two of them read one attribute, and both reads are
    what the spec's own pseudocode performs:

    * ``.builder`` — the backreference §4.3 rule 1 routes topology through. It is taken as
      *reachable* only when it is a ``StateGraph``, since §3 is the only thing that can be
      applied to it; a Pregel-protocol object carrying something else there takes the rule-4
      compiled-only downgrade, which is the conservative direction — the path that announces
      the reduced knowability rather than the one that would silently apply §3 rules to an
      object they were not written for.
    * ``get_graph`` — §2's "no usable surface at all" test for a builderless Pregel. Asked as
      ``callable(...)``; never called here (§1 rule 3, and §4.2 demotes it to cross-check
      even where it is called).

    Returns:
        The :class:`Dispatch` decision. Classification alone never touches the object's
        content, so a degenerate-but-supported object classifies normally and is refused, if
        at all, by :func:`extract`'s boundary check.

    Raises:
        ExtractionError: with reason ``unsupported-object`` when ``workflow`` is none of the
            three families, or ``no-extractable-surface`` when it is a Pregel-protocol object
            with neither a reachable ``.builder`` nor a callable ``get_graph``. §2 states both
            under one posture: name the object type, never return a silent partial IR.
    """
    if isinstance(workflow, (CompiledStateGraph, PregelProtocol)):
        builder = _builder_backreference(workflow)
        if builder is not None:
            return Dispatch(family=ObjectFamily.COMPILED, workflow=workflow, builder=builder)
        if not callable(getattr(workflow, "get_graph", None)):
            raise ExtractionError.for_object(
                workflow,
                "this object implements the Pregel protocol but exposes neither a `.builder` "
                "backreference nor a callable `get_graph()`, so there is no surface to "
                "extract from (INTROSPECTION-SPEC §2)",
                reason=ExtractionErrorReason.NO_EXTRACTABLE_SURFACE,
            )
        return Dispatch(family=ObjectFamily.COMPILED, workflow=workflow, compiled_only=True)
    if isinstance(workflow, StateGraph):
        return Dispatch(family=ObjectFamily.BUILDER, workflow=workflow, builder=workflow)
    if isinstance(workflow, Runnable):
        return Dispatch(family=ObjectFamily.LCEL, workflow=workflow)
    raise ExtractionError.for_object(
        workflow,
        "gebra.extract() takes a LangGraph StateGraph, a compiled graph, or an LCEL "
        "Runnable (INTROSPECTION-SPEC §2); this object is none of those",
        reason=ExtractionErrorReason.UNSUPPORTED_OBJECT,
    )


def extract(
    workflow: object,
    *,
    sidecar: str | os.PathLike[str] | None = None,
) -> ExtractionEnvelope:
    """Extract ``workflow`` into the Gebra IR 1.0 and its provenance envelope.

    The single entry point of INTROSPECTION-SPEC §2: it classifies the object, applies the
    one content check §2 puts at the object boundary, and hands the decision to the rule set
    for that family. It imports and inspects; it never invokes (§1) — no node function,
    router or tool is called, no LLM is contacted, no network connection is opened, and
    ``compile()`` is never called on a builder handed in.

    **One scoped exception, stated rather than implied.** §1 rule 3 licenses ``get_graph()``,
    and the §4 compiled path calls it. On langgraph 1.2.10 that call runs the Pregel loop
    symbolically, which performs LangGraph's own ``ChannelWrite.invoke`` and asks LangGraph's
    own channels for their values — library code, not the workflow's. Every surface through
    which a *user-authored* body could be reached that way is gated by
    :func:`gebra.extraction.compiled._drawing_hazard`, which names the six routes and either
    declines the call (where it is the SHOULD-grade cross-check) or refuses at the boundary
    (where it is the only extraction surface, including the ``RemoteGraph`` shape whose getter
    would open a connection).

    **The §5 path has one surface of the same kind, gated the same way.** Finding the runnables
    a ``RunnableLambda`` captured means resolving the dotted names its body loads, and resolving
    one walks ``getattr`` from a module global or a closure cell — where a ``property`` of yours,
    or a module ``__getattr__``, would be your code running here. ``gebra.extraction.lcel``
    admits that walk only while every object on it is stock substrate and otherwise declines the
    whole read, recording it. That path calls ``get_graph()`` nowhere at all.

    Args:
        workflow: A ``StateGraph`` builder, a ``CompiledStateGraph`` (or other Pregel-protocol
            object), or any other LCEL ``Runnable``.
        sidecar: An explicit ``gebra.toml`` path, which ANNOTATION §2's discovery rule 1
            ranks above the directory walk; ``None`` runs the rule-2 walk from the current
            working directory to the repository root. Either way the file is resolved, read
            and validated **here**, once, and the reading is handed to the family's path —
            which is what makes "exactly one sidecar file per extraction, never merged across
            directories" true of every family at once. A sidecar that cannot be read or does
            not validate never raises: §2 puts the whole surface at warning grade, so the
            findings ride the returned envelope and extraction stays total.

    Returns:
        The :class:`~gebra.extraction.envelope.ExtractionEnvelope`: the core IR, its
        provenance, and the structured warnings. Reading a ``graph_version`` off it is
        :meth:`~gebra.extraction.envelope.ExtractionEnvelope.graph_version`; the warnings
        never reach that digest (IR-SPEC §6.4). If the installed substrate is outside
        gebra's supported version range, the warnings carry an ``unsupported-construct``
        record naming it (VERSION-COMPAT §4) — see :mod:`gebra.extraction.compat`.

    Raises:
        ExtractionError: at the object boundary, never inside it — an unsupported object, a
            Pregel-protocol object with no usable surface, a builder with an empty ``.nodes``
            dict, or a supported family whose extraction path this build does not carry.
            Extraction never returns a silent partial IR (§2).
    """
    version_check = check_version_once()
    dispatch = classify(workflow)
    _refuse_empty_node_set(dispatch)
    extractor = extractor_for(dispatch.family)
    if extractor is None:
        raise ExtractionError.for_object(
            workflow,
            f"no extraction path is registered for the {dispatch.family.value!r} object "
            "family, so this build of gebra cannot extract this object; it refuses rather "
            "than returning a partial IR (INTROSPECTION-SPEC §2)",
            reason=ExtractionErrorReason.EXTRACTOR_NOT_REGISTERED,
            family=dispatch.family,
        )
    envelope = extractor(dispatch, sidecar=load_sidecar(sidecar))
    if version_check.compat is CompatClass.OUT_OF_RANGE:
        # Rebuilt through the constructor rather than `model_copy` (A6 PC-6's reasoning,
        # extended): validation runs on this envelope exactly as it does on any extraction
        # path's own output, rather than trusting an unvalidated `update` mapping.
        envelope = ExtractionEnvelope(
            ir=envelope.ir,
            extracted_from=envelope.extracted_from,
            warnings=(*envelope.warnings, out_of_range_warning(version_check.versions)),
        )
    return envelope


def _builder_backreference(workflow: object) -> StateGraph[Any] | None:
    """The ``.builder`` backreference of a compiled object, when §3 can be applied to it.

    One attribute read (§2's own ``getattr(workflow, "builder", None)``), narrowed to the
    class §3 is written against.
    """
    backreference = getattr(workflow, "builder", None)
    return backreference if isinstance(backreference, StateGraph) else None


def _refuse_empty_node_set(dispatch: Dispatch) -> None:
    """The §2 degenerate-input rule's one boundary exception.

    §2 is emphatic that degeneracy is *not* an error: "extraction is total over supported
    objects and emits the IR exactly as declared" — an unwired ``START`` gives ``entry: []``
    with a warning, a graph with no END wiring of either kind gives ``finish: []`` with one
    (a graph that reaches END only through its routers gives ``finish: []`` and no warning at
    all, per the DEC-18 scoping), and well-formedness verdicts belong to P-01, never to
    ``extract()``. The single exception is stated in the same paragraph: "a
    builder with an empty ``.nodes`` dict has no extractable content and cannot satisfy the
    IR's ``nodes`` minItems 1 (IR-SPEC §2.1) — it raises ``ExtractionError`` at the object
    boundary."

    The check therefore runs exactly where a builder is reachable — the §3 family, and the §4
    family whose topology routes through its backreference. A compiled-only object has no
    builder to read, and §5 extracts a fragment as "a degenerate one-fragment topology" of the
    object itself, so neither is in scope. A ``.nodes`` that is not a mapping is left alone:
    this is the empty-content check, not a type check on the substrate.
    """
    if dispatch.builder is None:
        return
    nodes = getattr(dispatch.builder, "nodes", None)
    if isinstance(nodes, Mapping) and len(nodes) == 0:
        raise ExtractionError.for_object(
            dispatch.workflow,
            "this graph has no nodes, so there is nothing to extract: the IR requires at "
            "least one node (IR-SPEC §2.1, INTROSPECTION-SPEC §2)",
            reason=ExtractionErrorReason.EMPTY_NODE_SET,
            family=dispatch.family,
        )
