"""The provenance envelope — what ``gebra.extract()`` returns around the core IR.

Normative authority: IR-SPEC §4.1 (the core-IR/envelope split and the envelope's field
names, ``warnings`` and ``disclosures`` among them), INTROSPECTION-SPEC §8 and
ANNOTATION-API-SPEC §4 (warnings ride the envelope, outside hash scope), INTROSPECTION-SPEC §8
again for the disclosures that ride after them (ratified — DEC-36), ANNOTATION-API-SPEC §2
(the sidecar path the envelope must record) and §5 (the (node id, slot) grade lookup the
envelope answers).

**The split, and why it is a wrapper rather than a field.** §4.1: "The **core IR** is
everything specified in §2–§3: it is the hash scope of §6 … The **envelope** is metadata
wrapped *around* the core IR — outside the model, outside the hash scope." So
:class:`ExtractionEnvelope` holds a :class:`~gebra.ir.models.WorkflowIR` rather than adding
members to one, and :meth:`ExtractionEnvelope.graph_version` digests that member alone. A
warning or a disclosure cannot move a digest here because there is no path by which it could.

**What this envelope is not.** §4.1 names five envelope fields — ``version``,
``extracted_from``, ``graph_version``, ``warnings`` and ``disclosures`` (the last two given
their rows at DEC-39) — and gives their semantics to brief D-11 (snapshots and traceability).
Two things it lists are that brief's, not extraction's, and are deliberately absent:

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
from enum import Enum
from itertools import pairwise
from typing import Any

from pydantic import Field, model_validator

from gebra import __version__
from gebra.extraction.base import ExtractionModel, ObjectFamily
from gebra.extraction.disclosures import (
    ExtractionDisclosure,
    ExtractionDisclosureCode,
    disclosure_order,
)
from gebra.extraction.warnings import (
    AnnotationSlot,
    ExtractionWarning,
    ExtractionWarningCode,
    SlotGrade,
    slot_grade,
)
from gebra.ir.canonical import I_JSON_MAX_INT
from gebra.ir.canonical import graph_version as compute_graph_version
from gebra.ir.identity import NodeIdStr
from gebra.ir.models import WorkflowIR

__all__ = [
    "BindingOutcome",
    "CompiledSurfaces",
    "CrossCheck",
    "ExtractedFrom",
    "ExtractionEnvelope",
    "FoldedDefault",
    "RecursionLimitBinding",
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
        condition: The declared branch name the edge carries. The member stays optional in
            the model, which is frozen, but extraction no longer writes ``None`` here: a routing
            declaration with no ``BranchSpec`` behind it — a node's ``destinations=`` or
            ``Command[Literal[...]]`` — records no codomain at all (EX-27), since its hint names
            goto targets rather than labels.
        labels: The ``Literal`` labels the return hint declares, in declaration order, each
            spelled as a ``path_map`` key is (INTROSPECTION-SPEC §6's dispatch, NFC-normalized).
        path_map_labels: The labels the emitted edge actually carries, so the two are readable
            side by side — which is the whole content of "distinct from ``path_map``".
    """

    node: NodeIdStr
    condition: str | None = None
    labels: tuple[str, ...] = ()
    path_map_labels: tuple[str, ...] = ()


class BindingOutcome(str, Enum):
    """What a ``with_config(recursion_limit=…)`` binding did beside the declarations (DEC-36 §3.3).

    The binding is never a declaration, so it never fills ``runtime.recursion_limit``; it has
    exactly three outcomes, and the record names which (ANNOTATION-API-SPEC §3;
    INTROSPECTION-SPEC §4.1).
    """

    CORROBORATES = "corroborates"
    """A declaration resolved, and its value equals the bound one."""

    CONFLICTS = "conflicts"
    """A declaration resolved with a different value: the declaration is kept — it is the
    attested witness, the binding is what one call site configured — and an
    ``annotation-conflict`` names both values and both surfaces."""

    DISCLOSED = "disclosed"
    """No declaration exists on either surface: the slot is absent, and a graph-scoped
    ``recursion-limit-bound-without-justification`` disclosure says so."""


class RecursionLimitBinding(ExtractionModel):
    """A usable ``with_config(recursion_limit=…)`` binding on the compiled object (DEC-36 §3.3).

    Provenance, outside hash scope: a binding is a compiled-level fact, read from the compiled
    object's own instance dictionary (its ``config`` mapping), and it never enters the slot — so
    the builder-level and compiled-level documents of one declared source carry the same
    ``runtime.recursion_limit`` (ANNOTATION-API-SPEC §6's parity). Recorded only when the bound
    value is usable — an ``int`` that is not a ``bool``, at least ``1`` and within ±(2⁵³−1); any
    other bound value is an ``unsupported-construct`` warning and no binding. LangGraph's default
    limit, and a limit passed when the graph is run, are not on the object and are never read:
    with no binding there is no record, never a default.

    Attributes:
        value: The bound limit.
        outcome: What the binding did beside the declarations — corroborated one, conflicted
            with one, or was disclosed because there was none.
    """

    value: int = Field(ge=1, le=I_JSON_MAX_INT)
    outcome: BindingOutcome


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
    folded-defaults resolution — and records the parents subgraph discovery found, whose
    children ir 1.0/1.1 does not emit (see :mod:`gebra.extraction.compiled` for why). A
    ``with_config`` recursion-limit binding is provenance too (DEC-36 §3.3): it never fills
    ``runtime.recursion_limit``, so it is recorded here, with what it did beside the
    declarations.
    Everything §4 knows and the IR cannot carry is collected here rather than spread across
    :class:`ExtractedFrom`, so a consumer asking "what did the compiled level add?" reads one
    object.

    Attributes:
        subgraphs: The node ids under which ``get_subgraphs()`` (§4.1) reports a subgraph, in
            node-id order (the ledger §6 comparator, UTF-16 code units) — the compiled getter's
            provenance record, which DEC-36 keeps where DEC-19 put it, and empty when the
            getter is missing or could not be read. It is **not** the disclosure: ir 1.0/1.1
            carries each subgraph as its parent node only, and every parent read as one node
            is disclosed by a ``subgraph-read-as-one-node`` record in
            :attr:`ExtractionEnvelope.disclosures` (DEC-19 Ruling 1 as amended by DEC-36), over
            the union of this tuple and the builder's direct-mount read — a node whose bound
            object is a compiled graph. The getter reaches a subgraph a node holds through a
            sequence, a lambda's ``deps`` or a closure, and skips any subgraph compiled with
            ``checkpointer=False``; the direct-mount read still sees such a subgraph when it is
            a node's own bound object. **This tuple is a lower bound, never a census, and so is
            the union**: a
            subgraph compiled with ``checkpointer=False`` and reached only from inside a node
            body is invisible to both reads, and on the compiled-only path, where no builder
            exists to read, every ``checkpointer=False`` child is. Nothing can disclose what no
            read can see.
        folded_defaults: The graph-level defaults ``compile()`` folded into node specs.
        error_handlers: ``node_error_handler_map`` — node id → its error-handler node id.
        cross_check: The §4.2 cross-check record, or ``None`` on a path that has no builder to
            check against.
        recursion_limit_binding: The compiled object's ``with_config(recursion_limit=…)``
            binding and what it did beside the declarations (:class:`RecursionLimitBinding`),
            or ``None`` when the object binds no usable limit (DEC-36 §3.3). Never a default:
            "the provenance record is empty when no binding exists, not 25" (DEC-36 §3.4) — nor
            10007, the default LangGraph's own loop applies at the pins (INTROSPECTION-SPEC §4.1,
            correcting A1-D36's citation at A1-D39).
    """

    subgraphs: tuple[NodeIdStr, ...] = ()
    folded_defaults: tuple[FoldedDefault, ...] = ()
    error_handlers: dict[str, str] = Field(default_factory=dict)
    cross_check: CrossCheck | None = None
    recursion_limit_binding: RecursionLimitBinding | None = None


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
    """The core IR plus its provenance, warnings and disclosures — what ``extract()`` returns.

    Attributes:
        ir: The core IR (IR-SPEC §2–§3). The whole hash scope, and the only member
            :meth:`graph_version` reads.
        extracted_from: Where this IR came from.
        warnings: The extraction warnings, in emission order — structured records from the
            one closed taxonomy (INTROSPECTION §8; ANNOTATION §4). §8: warnings "are never
            silently droppable", and a warning-free extraction is part of the strict-mode
            bar, so they are carried in the return value rather than raised through
            :mod:`warnings` where a filter could drop them.
        disclosures: The extraction disclosures (INTROSPECTION §8, ratified — DEC-36): records
            of a fact about what this complete, conforming document does not contain, from
            the closed vocabulary of :mod:`gebra.extraction.disclosures` — in this build, one
            ``subgraph-read-as-one-node`` record per node that the §3 direct-mount read or
            §4.1's ``get_subgraphs()`` finds mounting or reaching a compiled subgraph the
            document carries as that one node, and one graph-scoped
            ``recursion-limit-bound-without-justification`` record when a compiled graph binds
            a recursion limit through ``with_config`` and no surface declares one, so
            ``runtime.recursion_limit`` is absent (§4.1). **Not warnings**: no disclosure is
            a row of the §8 warning table, counts against the warning-free strict-mode bar,
            moves an exit code or is promoted by a strict flag — and none is droppable either,
            which is why they ride the return value too. They come after the warnings, in the
            §8 order — graph-scoped records first, then node-scoped ones in node-id order (the
            ledger §6 comparator) and, within one node, by code — checked when the envelope is
            built, one record per node and code. Outside hash scope: :meth:`graph_version`
            never reads them. The set of
            nodes disclosed as subgraph-bearing is a **lower bound, never a census**: a subgraph
            compiled with ``checkpointer=False`` and reached only from inside a node body is
            invisible to every read, and on the compiled-only path every ``checkpointer=False``
            child is.
    """

    ir: WorkflowIR
    extracted_from: ExtractedFrom
    warnings: tuple[ExtractionWarning, ...] = ()
    disclosures: tuple[ExtractionDisclosure, ...] = ()

    @model_validator(mode="after")
    def _disclosures_in_the_ruled_order(self) -> ExtractionEnvelope:
        """INTROSPECTION §8's order, strictly — which is also one record per node and code."""
        for earlier, later in pairwise(self.disclosures):
            if not disclosure_order(earlier) < disclosure_order(later):
                raise ValueError(
                    f"disclosure {later.code.value!r} on {later.node!r} follows "
                    f"{earlier.code.value!r} on {earlier.node!r}: disclosures come graph-scoped "
                    "first, then by node id, then by code, one record per node and code "
                    "(INTROSPECTION-SPEC §8)"
                )
        return self

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

    def disclosures_for(self, node: str) -> tuple[ExtractionDisclosure, ...]:
        """Every disclosure naming ``node``, in the §8 order."""
        return tuple(disclosure for disclosure in self.disclosures if disclosure.node == node)

    def disclosures_of(self, code: ExtractionDisclosureCode) -> tuple[ExtractionDisclosure, ...]:
        """Every disclosure carrying ``code``, in the §8 order."""
        return tuple(disclosure for disclosure in self.disclosures if disclosure.code is code)

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
