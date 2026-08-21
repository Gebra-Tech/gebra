"""The provenance envelope — what ``gebra.extract()`` returns around the core IR.

Normative authority: IR-SPEC §4.1 (the core-IR/envelope split and the envelope's field
names), INTROSPECTION-SPEC §8 and ANNOTATION-API-SPEC §4 (warnings ride the envelope,
outside hash scope), ANNOTATION-API-SPEC §2 (the sidecar path the envelope must record) and
§5 (the (node id, slot) grade lookup the envelope answers).

**The split, and why it is a wrapper rather than a field.** §4.1: "The **core IR** is
everything specified in §2–§3: it is the hash scope of §6 … The **envelope** is metadata
wrapped *around* the core IR — outside the model, outside the hash scope." So
:class:`ExtractionEnvelope` holds a :class:`~gebra.ir.models.WorkflowIR` rather than adding
members to one, and :meth:`ExtractionEnvelope.graph_version` digests that member alone. A
warning cannot move a digest here because there is no path by which it could.

**What this envelope is not.** §4.1 names three envelope fields and gives their semantics to
brief D-11 (snapshots and traceability). Two of them are that brief's, not extraction's, and
are deliberately absent:

* ``version`` — the V.S.F.E label — is "derived *from* diffs of the digested content", which
  needs two snapshots; one extraction cannot compute it.
* the extraction **timestamp** §4.1 lists under ``extracted_from`` is left to the snapshot
  layer that records "how/when it was made". It could not move a digest — nothing in the
  envelope can (§6.4) — but it would make two extractions of one unchanged object compare
  unequal *as envelopes*, and value-equality of an extraction is what a test, a golden or a
  cache can otherwise rely on. Wall-clock content belongs where something is being dated.

What is here is what extraction itself knows: what was extracted, by which rule set, with
which extractor, against which sidecar (ANNOTATION §2: the envelope's ``extracted_from``
"MUST record the absolute sidecar path used (or its absence) so digest divergence is
diagnosable").

Nothing here imports langgraph, opens a socket, or executes anything (WA-07).
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import Field

from gebra import __version__
from gebra.extraction.base import ExtractionModel, ObjectFamily
from gebra.extraction.warnings import (
    AnnotationSlot,
    ExtractionWarning,
    ExtractionWarningCode,
    SlotGrade,
    slot_grade,
)
from gebra.ir.canonical import graph_version as compute_graph_version
from gebra.ir.identity import NodeIdStr
from gebra.ir.models import WorkflowIR

__all__ = [
    "CompiledSurfaces",
    "CrossCheck",
    "ExtractedFrom",
    "ExtractionEnvelope",
    "FoldedDefault",
    "RouterCodomain",
    "to_data",
    "to_json",
]


class FoldedDefault(ExtractionModel):
    """One node-spec member whose value came from the graph-level ``set_node_defaults``.

    INTROSPECTION §4.1 lists "folded ``set_node_defaults``" among the facts the compiled level
    contributes, and puts the *resolution* of those defaults in provenance: "``node_error_handler_map``
    and folded-defaults resolution still land in provenance only — no ir 1.0 slot; candidate 1.x
    extensions". The folded **value** is not lost — ``compile()`` writes it into the builder's own
    node specs, so §3 reads it like any authored one — but which nodes *declared* it and which
    inherited it is exactly what has no carrier, and this is where that lands.

    Attributes:
        node: The node id whose spec member was filled from the graph-level default.
        member: The ``StateNodeSpec`` member name (``retry_policy``, ``cache_policy``, …).
    """

    node: NodeIdStr
    member: str


class RouterCodomain(ExtractionModel):
    """A router's declared codomain, where ir 1.0 has no slot for it (INTROSPECTION §6).

    §6's codomain-capture rule: "``BranchSpec.from_path`` gives ``path_map`` precedence — a
    coexisting ``Literal[...]`` return hint never reaches ``BranchSpec.ends``. Extraction MUST
    still read that hint via ``typing.get_type_hints()`` (§1) and record it in provenance as
    Inferred-warned router-codomain evidence, **never merged into ``path_map``**." §7.3 item 5
    is the gap this fills the honest half of: ir 1.0 has no ``codomain`` carrier, so a codomain
    declared *independently* of ``path_map`` — the exact P-05(i) scenario — can only be recorded
    beside the IR, and a future carrier is what would promote it.

    Recorded only when the hint's label set **differs** from the edge's ``path_map`` labels: when
    the two agree the hint is already in the IR (the substrate itself fills ``ends`` from a
    ``Literal`` hint when no ``path_map`` was declared), and a record would be a restatement.

    **No warning rides this** — a deliberate reading, recorded rather than assumed. §6 files
    the evidence under the Inferred-warned class, whose §0 definition is "a §8 warning always
    accompanies it", and §8's vocabulary is closed with no row for a router codomain. Borrowing
    ``unsupported-construct`` would put every workflow that annotates a router with its own
    return type outside the strict-mode bar for declaring *more* than the IR can carry, which
    inverts the incentive the class exists to create. This is the same disposition
    :attr:`ExtractedFrom.managed_state_keys` already took for the same shape of gap, and the
    tension is filed rather than resolved locally (PD-045).

    Attributes:
        node: The router's source node id.
        condition: The declared branch name the edge carries, or ``None`` for a routing
            declaration with no ``BranchSpec`` behind it.
        labels: The ``Literal`` labels the return hint declares, in declaration order.
        path_map_labels: The labels the emitted edge actually carries, so the two are readable
            side by side — which is the whole content of "distinct from ``path_map``".
    """

    node: NodeIdStr
    condition: str | None = None
    labels: tuple[str, ...] = ()
    path_map_labels: tuple[str, ...] = ()


class CrossCheck(ExtractionModel):
    """Whether the §4.2 compiled-level cross-check ran, and at what level.

    §4.3 rule 2 grades the cross-check **SHOULD**, so "it did not run" is a conforming outcome
    and has to be legible: an extraction with no ``builder-compiled-divergence`` warning means
    "no divergence found" only when this record says the comparison happened.

    Attributes:
        performed: Whether the drawn edge set was derived and compared.
        xray: The ``xray`` level passed to ``get_graph()`` — the §8 row's "xray level used",
            recorded here as well so it is present even when nothing diverged.
        declined: Why the cross-check did not run, when it did not. ``None`` iff
            :attr:`performed`.
    """

    performed: bool
    xray: bool = True
    declined: str | None = None


class CompiledSurfaces(ExtractionModel):
    """The §4.1 compiled-level facts that ir 1.0 has no slot for, plus the cross-check record.

    §4.1 names two facts outright as provenance-only — ``node_error_handler_map`` and
    folded-defaults resolution — and gives subgraph discovery an id rule but no boundary-wiring
    rule (see :mod:`gebra.extraction.compiled` for why the children are therefore not emitted).
    Everything §4 knows and the IR cannot carry is collected here rather than spread across
    :class:`ExtractedFrom`, so a consumer asking "what did the compiled level add?" reads one
    object.

    Attributes:
        subgraphs: The node ids whose bound object is itself a Pregel graph, as discovered by
            ``get_subgraphs()`` (§4.1), in node-id order. **This member is the conforming
            disclosure**, not a consolation for one: ir 1.0 carries a discovered subgraph as
            its parent node only, and §4.1 (ratified — DEC-19) makes that document *complete*
            — it carries no warning for the unexpansion and reaches the §8 strict-mode bar.
            Child expansion is the named first 1.x feature. Subgraphs compiled with
            ``checkpointer=False`` are invisible to discovery (§4.1) — a documented blind spot,
            so this tuple is a lower bound, never a census, and nothing can warn about what it
            cannot see.
        folded_defaults: The graph-level defaults ``compile()`` folded into node specs.
        error_handlers: ``node_error_handler_map`` — node id → its error-handler node id.
        cross_check: The §4.2 cross-check record, or ``None`` on a path that has no builder to
            check against.
    """

    subgraphs: tuple[NodeIdStr, ...] = ()
    folded_defaults: tuple[FoldedDefault, ...] = ()
    error_handlers: dict[str, str] = Field(default_factory=dict)
    cross_check: CrossCheck | None = None


class ExtractedFrom(ExtractionModel):
    """Provenance: what was extracted, by what, against which sidecar (IR-SPEC §4.1).

    Attributes:
        source: The extracted object's type, as ``"<top-level package>:<qualname>"``.
            Extraction takes a live object rather than a file, so the source *reference* is
            that object's identity; the sidecar below is the one filesystem path an
            extraction has.
        family: The rule set that produced the IR (INTROSPECTION §2) — which is also the
            honest record of how much was knowable, since a builder-level extraction records
            the compiled-only surfaces absent and a compiled-only one downgrades every
            §3-derived field by one knowability class (§4.3 rule 4).
        extractor_version: The version of ``gebra`` that extracted it.
        sidecar: The ``gebra.toml`` the extraction used, or ``None`` when none was. Recorded
            because sidecar-filled annotations sit *inside* the hash scope while the discovery
            walk is CWD-dependent, so this is what makes a moved digest diagnosable.
            ANNOTATION §2 requires the **absolute** path; resolving to one is the sidecar
            loader's step, and this field is the carrier that step writes to — the constraint
            is not enforced here, where there is nothing yet to resolve it against.
        managed_state_keys: The managed-value state keys the source declared
            (``RemainingSteps`` and its kind), in declaration order, under the names the
            schema gave them. INTROSPECTION §3 puts them exactly here: "ir 1.0 has no managed
            marker slot — extraction records presence in provenance as P-02 corroborating
            evidence only", which §7.3 item 4 restates as "lands only in provenance, not the
            core IR". A **provenance** field rather than a warning because §8's vocabulary is
            closed and carries no row for a managed value: borrowing one would put every
            graph that declares ``RemainingSteps`` outside the strict-mode bar for using a
            construct the substrate supports and the IR simply does not mirror.
        router_codomains: The router codomains INTROSPECTION §6 has extraction read and record
            here rather than merge into ``path_map`` (:class:`RouterCodomain`), in emission
            order. Empty on every workflow whose routers declare no codomain distinct from
            their declared targets, which is most of them.
        compiled: The §4.1 compiled-level facts with no ir 1.0 carrier, and the §4.2
            cross-check record — ``None`` for a builder-level or LCEL extraction, which have
            no compiled level to read.
    """

    source: str
    family: ObjectFamily
    extractor_version: str = __version__
    sidecar: str | None = None
    managed_state_keys: tuple[str, ...] = ()
    router_codomains: tuple[RouterCodomain, ...] = ()
    compiled: CompiledSurfaces | None = None


class ExtractionEnvelope(ExtractionModel):
    """The core IR plus its provenance and warnings — what ``extract()`` returns.

    Attributes:
        ir: The core IR (IR-SPEC §2–§3). The whole hash scope, and the only member
            :meth:`graph_version` reads.
        extracted_from: Where this IR came from.
        warnings: The extraction warnings, in emission order — structured records from the
            one closed taxonomy (INTROSPECTION §8; ANNOTATION §4). §8: warnings "are never
            silently droppable", and a warning-free extraction is part of the strict-mode
            bar, so they are carried in the return value rather than raised through
            :mod:`warnings` where a filter could drop them.
    """

    ir: WorkflowIR
    extracted_from: ExtractedFrom
    warnings: tuple[ExtractionWarning, ...] = ()

    def graph_version(self) -> str:
        """The IR-SPEC §6 content digest of :attr:`ir`, as ``"sha256:<hex>"``.

        §4.1's ``graph_version`` envelope field, computed rather than stored — one source of
        truth, and no way for the two to disagree. Nothing else in the envelope reaches the
        digest, which is the §6.4 exclusion rule holding by construction.

        Raises:
            CanonicalizationError: if the IR carries a value the canonical form refuses (a
                non-finite number, an out-of-I-JSON-range integer, a non-NFC identifier).
        """
        return compute_graph_version(self.ir)

    def warnings_for(self, node: str) -> tuple[ExtractionWarning, ...]:
        """Every warning naming ``node``, in emission order."""
        return tuple(warning for warning in self.warnings if warning.node == node)

    def warnings_of(self, code: ExtractionWarningCode) -> tuple[ExtractionWarning, ...]:
        """Every warning carrying ``code``, in emission order."""
        return tuple(warning for warning in self.warnings if warning.code is code)

    def slot_grade(self, node: str, slot: AnnotationSlot) -> SlotGrade:
        """The ANNOTATION §5 grade of ``slot`` on ``node`` — declared, inferred or defaulted.

        The envelope-side spelling of :func:`~gebra.extraction.warnings.slot_grade`; §5 makes
        this lookup normative for the P-01…P-13 validators, and the envelope is where §5 says
        to run it.
        """
        return slot_grade(self.warnings, node, slot)


def to_data(model: ExtractionModel) -> dict[str, Any]:
    """Serialize an envelope model as JSON data: members in definition order, nulls dropped.

    Dropping ``None`` is what makes absence round-trip — an omitted ``sidecar`` and a
    warning that names no node serialize the same way they were authored (A6 PC-4, the
    profile :func:`gebra.verify.base.to_data` uses for the result envelope). Tuples become
    arrays and enums become their values, so the result is data a report or a snapshot can
    carry; it is **not** canonical form, and nothing here is ever hashed (§6.4).

    ``by_alias=True`` for the same reason :func:`gebra.ir.serialization.dump_json` uses it
    (A6 PC-4): the envelope carries a core IR, and an IR field has one spelling wherever it
    is written — ``edges[].from``, the ledger's name for it, never the ``from_`` the Python
    keyword forces on the model. §2.5 note 2 states the obligation for canonical output; two
    repo-authored surfaces disagreeing about a field name would be a bug in either.
    """
    return model.model_dump(mode="json", by_alias=True, exclude_none=True)


def to_json(model: ExtractionModel, *, indent: int | None = 2) -> str:
    """Serialize an envelope model as JSON text, in the :func:`to_data` profile.

    Two-space indentation matching ``.editorconfig``; ``indent=None`` gives the compact
    single-line form. Non-ASCII characters are kept as themselves, and no trailing newline
    is added.
    """
    return json.dumps(to_data(model), indent=indent, ensure_ascii=False)
