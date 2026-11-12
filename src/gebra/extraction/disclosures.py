"""The extraction-disclosure vocabulary — beside the warnings taxonomy, never inside it.

Normative authority: INTROSPECTION-SPEC §8, "Extraction disclosures" (ratified — DEC-36,
2026-10-28), for the record and its order; §3 row (iv) and §4.1 for the one record this build
emits; DEC-19 Ruling 1 as DEC-36 §3.7 amends it; IR-SPEC §4.1's ``disclosures`` row and the
ledger's §6 comparator for what "node-id order" means.

**What a disclosure is.** §8: a structured record "of a fact about what a *complete,
conforming* document does not contain". It is **not a warning**: it is not a row of the §8
warning table, so it is no :class:`~gebra.extraction.warnings.ExtractionWarningCode` and cannot
become one; it does not count against the warning-free strict-mode bar; it moves no exit code
and no strict flag promotes it (PROPERTY-CATALOG-SPEC §0.6 item 8: a note is never a finding).
It is not silently droppable either, which is why it rides the value ``gebra.extract()``
returns — :attr:`~gebra.extraction.envelope.ExtractionEnvelope.disclosures`, after the
warnings, outside hash scope, where nothing can carry it into a ``graph_version``.

**The vocabulary is closed** and grows only by an R-06 decision record. DEC-36 admits two
codes and DEC-40 a third, and each joins :class:`ExtractionDisclosureCode` with the change that
emits it; this build emits one, ``subgraph-read-as-one-node``.

**One record per node and code, in the §8 order** — graph-scoped records first, then
node-scoped ones in node-id order and, within one node, by code. Node-id order is the ledger §6
comparator, UTF-16 code units — the order of ``nodes[]`` in canonical form (IR-SPEC §6.2), which
is not Python's string order wherever an id mixes characters beyond U+FFFF with ones in
U+E000–U+FFFF. Graph-scoped records, for which §8 fixes no order among themselves, are kept by
code. :func:`disclosure_order` is that key, and the envelope refuses a sequence that is not
strictly increasing under it, so the order holds by construction rather than by each emitter's
care.

**Structured, never a bare string** (§8): a record carries ``code``, a display-only
``message``, an optional ``node`` and a JSON-shaped ``detail``, held to the same reportable-data
discipline a warning's ``detail`` is. :data:`DISCLOSURE_RULES` is the §8 table's "what it
carries" column in the form the model validator checks.

**The subgraph record, and why its set is a lower bound.** In ``ir_version`` 1.0/1.1 output a
compiled subgraph is carried as its parent node only (DEC-19 Ruling 1), and every parent read as
one node is disclosed (DEC-36 §3.7). Two reads find such a parent, and the disclosed set is their
union: the §3 direct-mount read — a node whose bound object is a ``langgraph.pregel.Pregel``
instance — and §4.1's ``get_subgraphs()``, which also reaches a subgraph a node holds through a
sequence, a lambda's ``deps`` or a closure, and which skips any subgraph compiled with
``checkpointer=False``. So the set is a **lower bound, never a census**: a subgraph compiled with
``checkpointer=False`` and reached only from inside a node body is seen by neither read, on the
compiled-only path every ``checkpointer=False`` child is invisible, and wherever
``get_subgraphs()`` was not read — an uncompiled builder offers none — so is every subgraph that
is not itself a node's bound object. Every record carries the ruled lower-bound sentence and the
reads its extraction ran; a record made without the getter also says, in its message, what that
leaves unseen.

Nothing here imports langgraph, reads a workflow object, opens a socket, or executes anything
(WA-07). The reads that find a subgraph live with the paths that own them — the direct-mount read
in :mod:`gebra.extraction.builder`, ``get_subgraphs()`` in :mod:`gebra.extraction.compiled` — and
hand this module node ids.
"""

from __future__ import annotations

from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any, Final

from pydantic import Field, field_validator, model_validator

from gebra.extraction.base import ExtractionModel
from gebra.extraction.warnings import _reportable
from gebra.ir.identity import NodeIdStr

__all__ = [
    "DISCLOSURE_RULES",
    "DisclosureRule",
    "ExtractionDisclosure",
    "ExtractionDisclosureCode",
    "disclosure_rule",
]


class ExtractionDisclosureCode(str, Enum):
    """The closed disclosure vocabulary ``gebra.extract()`` emits (INTROSPECTION §8; DEC-36).

    A second enumeration rather than members of
    :class:`~gebra.extraction.warnings.ExtractionWarningCode`, because DEC-36 §3.6 rules the
    disclosure "beside the §8 warning taxonomy, and deliberately outside it": a code here can
    never be read as a warning, and the warning vocabulary keeps its ten codes. Adding a code is
    a decision record, not a code change.
    """

    SUBGRAPH_READ_AS_ONE_NODE = "subgraph-read-as-one-node"


@dataclass(frozen=True)
class DisclosureRule:
    """What one disclosure row requires of the records that carry its code.

    The §8 table's "what it carries" column in the form the model validator can check — the
    shape :class:`~gebra.extraction.warnings.WarningRule` gives the warning rows, and like it no
    stricter than the row states.

    Attributes:
        origin: The table row and the decision record it reads, cited so the requirement is
            traceable.
        carries: The row's "what it carries" column, condensed.
        node_required: The row names a node id: the record is node-scoped.
        detail_required: The ``detail`` members the row names, under the keys the emitter
            writes them with.
    """

    origin: str
    carries: str
    node_required: bool = False
    detail_required: frozenset[str] = frozenset()


#: The one row this build emits, with the requirement the ruling states for it in 1.0/1.1
#: output (DEC-36 §3.6, which INTROSPECTION-SPEC §4.1 keeps standing for that output). ``reason``
#: — why a mount was left unexpanded — is absent: §8 states it is absent in 1.0/1.1 output,
#: where every mount is left unexpanded.
DISCLOSURE_RULES: Final[Mapping[ExtractionDisclosureCode, DisclosureRule]] = {
    ExtractionDisclosureCode.SUBGRAPH_READ_AS_ONE_NODE: DisclosureRule(
        origin="INTROSPECTION §8 (§3 row (iv), §4.1); DEC-19 Ruling 1 as amended by DEC-36",
        carries=(
            "the node id; which read(s) saw it; that its interior was not read; that the "
            "disclosed set is a lower bound, never a census; that child expansion is the named "
            "ir 1.x feature"
        ),
        node_required=True,
        detail_required=frozenset(
            {"seen_by", "interior_not_read", "lower_bound", "child_expansion"}
        ),
    ),
}


def disclosure_rule(code: ExtractionDisclosureCode) -> DisclosureRule:
    """The registry rule for ``code``. Total over the enum, so it never returns ``None``."""
    return DISCLOSURE_RULES[code]


class ExtractionDisclosure(ExtractionModel):
    """One structured disclosure record, riding the provenance envelope (INTROSPECTION §8).

    Attributes:
        code: The disclosure code — the whole vocabulary is :class:`ExtractionDisclosureCode`.
        message: The disclosure in words, within the wording §8 rules for its code.
            **Display-only**: every fact a consumer branches on lives in the fields below,
            never in this string.
        node: The node id the disclosure is about, in the escaped IR-SPEC §5 form, or ``None``
            for a graph-scoped one. Required for the codes whose row names a node id.
        detail: The rest of the row's "what it carries" column, as JSON data — checked the way
            a warning's ``detail`` is, and required to hold the members the code's
            :class:`DisclosureRule` names. For ``subgraph-read-as-one-node``: ``seen_by`` (the
            reads that saw this node — ``direct-mount``, ``get-subgraphs`` or both),
            ``reads_performed`` (the reads this extraction ran, which is what the lower bound
            rests on), ``interior_not_read`` (the child's ``nodes``, ``edges``, ``entry``,
            ``finish`` and ``state``), ``lower_bound`` (the ruled sentence that the set of such
            nodes is a lower bound, not a census) and ``child_expansion`` (that child expansion
            is the named ir 1.x feature of DEC-19's design register, not performed in
            ``ir_version`` 1.0/1.1 output).
    """

    code: ExtractionDisclosureCode
    message: str = Field(min_length=1)
    node: NodeIdStr | None = None
    detail: dict[str, Any] = Field(default_factory=dict)

    @field_validator("detail", mode="before")
    @classmethod
    def _detail_is_reportable_data(cls, detail: object) -> object:
        """Refuse what a report could not carry, and give sequences one representation."""
        if not isinstance(detail, dict):
            return detail  # not a mapping: let strict validation report it
        return {
            key: _reportable(value, path=f"detail[{key!r}]", depth=0, record="disclosure")
            for key, value in detail.items()
        }

    @model_validator(mode="after")
    def _carries_what_its_row_names(self) -> ExtractionDisclosure:
        """Hold the record to :data:`DISCLOSURE_RULES` — the table's own "carries" column."""
        rule = disclosure_rule(self.code)
        if rule.node_required and self.node is None:
            raise ValueError(
                f"{self.code.value!r} names a node id ({rule.origin}); this record has none"
            )
        missing = sorted(rule.detail_required.difference(self.detail))
        if missing:
            raise ValueError(
                f"{self.code.value!r} carries {sorted(rule.detail_required)} in its detail "
                f"({rule.origin}); this record lacks {missing}"
            )
        return self


def node_id_order(node: str) -> bytes:
    """The ledger §6 comparator for node ids: UTF-16 code units, as sortable bytes.

    "Compared as UTF-16 code units — the same comparator as JCS member sorting" (IR-SPEC §6.2's
    ``nodes[]`` row), which is the order the ids have in a canonical document. Big-endian UTF-16
    compares bytewise exactly as code units do. It differs from Python's code-point order where
    an id holds a character beyond U+FFFF — a surrogate pair, which sorts *below* U+E000–U+FFFF.
    """
    return node.encode("utf-16-be")


def disclosure_order(disclosure: ExtractionDisclosure) -> tuple[bool, bytes, str]:
    """The §8 order's key: graph-scoped first, then by node id, then by code within a node."""
    node = disclosure.node
    return (node is not None, b"" if node is None else node_id_order(node), disclosure.code.value)


def in_disclosure_order(
    disclosures: Iterable[ExtractionDisclosure],
) -> tuple[ExtractionDisclosure, ...]:
    """``disclosures`` sorted into the §8 order."""
    return tuple(sorted(disclosures, key=disclosure_order))


# ── The subgraph record ──────────────────────────────────────────────────────────────────

#: INTROSPECTION-SPEC §3 row (iv)'s read on ``StateNodeSpec.runnable`` — a node whose bound
#: object is a ``langgraph.pregel.Pregel`` instance (DEC-36 §3.6) — as a record names it.
DIRECT_MOUNT_READ: Final = "direct-mount"

#: §4.1's compiled-level discovery, ``get_subgraphs()``, as a record names it.
GET_SUBGRAPHS_READ: Final = "get-subgraphs"

#: The two reads in the order a record lists them, which is the order §8 names them in.
SUBGRAPH_READS: Final = (DIRECT_MOUNT_READ, GET_SUBGRAPHS_READ)

#: What a node read as one node leaves unread, by the IR member names of the graph it mounts.
INTERIOR_NOT_READ: Final = ("nodes", "edges", "entry", "finish", "state")

#: The lower-bound sentence INTROSPECTION-SPEC §8 rules for ``subgraph-read-as-one-node``,
#: carried verbatim in every record's ``detail`` and message.
LOWER_BOUND: Final = (
    "The set of mounts this document knows of is a lower bound, not a census: a subgraph "
    "compiled with `checkpointer=False` and reached only from inside a node body is "
    "invisible, and on the compiled-only path (INTROSPECTION-SPEC §4.3 rule 4), where no "
    "builder-level direct-mount read exists, every `checkpointer=False` child is."
)

#: DEC-36 §3.6's last field for the record, as ``detail`` carries it: a pointer to the design
#: register, never a statement that the expansion is available.
CHILD_EXPANSION: Final = (
    "the named ir 1.x feature of DEC-19's design register; not performed in ir_version 1.0/1.1 "
    "output"
)

#: Appended to the message on an uncompiled builder, which has no ``get_subgraphs()`` to read.
NO_GETTER_ON_A_BUILDER: Final = (
    "On an uncompiled builder no `get_subgraphs()` read exists, so a subgraph that is not "
    "itself a node's bound object is invisible here whatever its checkpointer."
)

#: Appended to the message on a compiled graph whose ``get_subgraphs()`` is missing or failed.
GETTER_UNREADABLE: Final = (
    "This graph's `get_subgraphs()` could not be read, so a subgraph that is not itself a "
    "node's bound object is invisible here whatever its checkpointer."
)


def subgraph_disclosures(
    *,
    direct: Iterable[str] = (),
    discovered: Iterable[str] = (),
    reads_performed: Collection[str],
    unseen: str | None = None,
) -> tuple[ExtractionDisclosure, ...]:
    """One ``subgraph-read-as-one-node`` record per node either read saw, in node-id order.

    The union DEC-36 §3.6 rules: a node is disclosed when the direct-mount read or
    ``get_subgraphs()`` saw it, and its record names which. The message is §8's ruled wording
    with its ``(<reason>)`` clause absent — §8 states that clause is absent in 1.0/1.1 output,
    where every mount is left unexpanded — the pointer to child expansion DEC-36 §3.6 asks for,
    and, when the caller names one, the sentence saying what this extraction's reads could not
    see beyond the ruled remainder.

    Args:
        direct: The node ids whose bound object the direct-mount read found to be a compiled
            graph.
        discovered: The node ids ``get_subgraphs()`` reported a subgraph under.
        reads_performed: The reads this extraction ran, from :data:`SUBGRAPH_READS`. Recorded
            on every record, because the lower bound rests on them: an empty record list means
            "these reads saw nothing", never "there is nothing".
        unseen: The sentence naming what a missing read leaves unseen —
            :data:`NO_GETTER_ON_A_BUILDER` or :data:`GETTER_UNREADABLE` — appended to the
            message only; ``detail`` keeps the ruled sentence alone, and ``reads_performed`` is
            the structured fact.

    Returns:
        The records, in node-id order; empty when neither read saw a node.

    Raises:
        ValueError: if a node is attributed to a read that ``reads_performed`` does not name,
            or ``reads_performed`` names a read that is not one of :data:`SUBGRAPH_READS` — an
            emitter's inconsistency, never a property of the workflow.
    """
    unknown = sorted(set(reads_performed).difference(SUBGRAPH_READS))
    if unknown:
        raise ValueError(f"no subgraph read is named {unknown}; the reads are {SUBGRAPH_READS}")
    seen: dict[str, frozenset[str]] = {
        DIRECT_MOUNT_READ: frozenset(direct),
        GET_SUBGRAPHS_READ: frozenset(discovered),
    }
    unperformed = sorted(read for read, ids in seen.items() if ids and read not in reads_performed)
    if unperformed:
        raise ValueError(
            f"nodes are attributed to {unperformed}, a read this extraction did not run"
        )
    performed = tuple(read for read in SUBGRAPH_READS if read in reads_performed)
    tail = LOWER_BOUND if unseen is None else f"{LOWER_BOUND} {unseen}"
    return tuple(
        ExtractionDisclosure(
            code=ExtractionDisclosureCode.SUBGRAPH_READ_AS_ONE_NODE,
            message=(
                f"node `{node}` mounts or reaches a compiled subgraph that this document "
                "carries as one node; its interior (child nodes, edges, entry, finish and "
                "state) was not read — child expansion is the named ir 1.x feature of "
                "DEC-19's design register, not performed in ir_version 1.0/1.1 output. "
                f"{tail}"
            ),
            node=node,
            detail={
                "seen_by": tuple(read for read in SUBGRAPH_READS if node in seen[read]),
                "reads_performed": performed,
                "interior_not_read": INTERIOR_NOT_READ,
                "lower_bound": LOWER_BOUND,
                "child_expansion": CHILD_EXPANSION,
            },
        )
        for node in sorted(seen[DIRECT_MOUNT_READ] | seen[GET_SUBGRAPHS_READ], key=node_id_order)
    )


def split_subgraph_disclosures(
    disclosures: Iterable[ExtractionDisclosure],
) -> tuple[tuple[str, ...], tuple[ExtractionDisclosure, ...]]:
    """The node ids of the ``subgraph-read-as-one-node`` records, and every other record.

    What the compiled path needs from the builder reading it layers on: the nodes the builder's
    direct-mount read disclosed, to union with ``get_subgraphs()``'s, and the records of any
    other code, carried through unchanged.
    """
    parents: list[str] = []
    others: list[ExtractionDisclosure] = []
    for disclosure in disclosures:
        # Compared by value: with one member in the vocabulary today, mypy reads a member test as
        # always true. The test is what keeps another code's records out of the union.
        if (
            disclosure.code.value == ExtractionDisclosureCode.SUBGRAPH_READ_AS_ONE_NODE.value
            and disclosure.node is not None
        ):
            parents.append(disclosure.node)
        else:
            others.append(disclosure)
    return tuple(parents), tuple(others)
