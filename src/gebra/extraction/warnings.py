"""The extraction-warnings taxonomy — one closed vocabulary, structured records.

Normative authority: INTROSPECTION-SPEC §8 (the seven extraction rows) together with
ANNOTATION-API-SPEC §4's warning registry (the five annotation-surface rows, two of which
are the same warnings under their ratified names). §4 states the relationship outright —
"the annotation-surface warnings are part of the single extraction-warnings taxonomy of
INTROSPECTION-SPEC §8" — so this module carries **one** enumeration of ten codes, not two.

Three properties of a warning are load-bearing, and each is enforced rather than documented:

* **Ratified spellings.** ``contract-inferred`` is the DEC-08 spelling; INTROSPECTION §8's
  prose notes that its own draft ``inferred-contract`` "name the same warning" and that the
  taxonomy consolidates on the ratified names. :class:`ExtractionWarningCode` carries the
  ratified set and nothing else, so the un-ratified spelling is not constructible.
* **Structured, never a bare string.** ANNOTATION §2 says ``annotation-invalid`` "carries
  scope (file / node id), slot(s), value(s), and the violated rule — structured fields,
  never a bare string", and §4 repeats it for the whole registry. So a record carries a
  code, an optional node id, the slots it names, and a JSON-shaped ``detail`` mapping;
  :attr:`ExtractionWarning.message` is display-only and never the carrier of a fact.
* **(node id, slot).** ANNOTATION §5 makes the pair normative: "a slot on node *n* is
  declared-grade **iff** no ``contract-inferred``/``contract-defaulted`` warning in the
  extraction envelope names the (node id, slot) pair; otherwise it is heuristic-grade …
  This lookup is normative for the P-01…P-13 validators — and is why the §4 registry's
  warnings are structured records with node-id and slot fields, never strings."
  :func:`slot_grade` is that lookup, and :data:`WARNING_RULES` is what makes the fields it
  reads mandatory on the codes whose registry rows name them.

:data:`~gebra.annotations.slots.AnnotationSlot` and its members, and
:class:`~gebra.annotations.slots.SlotGrade`, are re-exported here rather than defined here.
The nine-slot set is ANNOTATION §1's, shared "byte-for-byte" by the decorator and sidecar
surfaces, and the §5 lookup below is quantified over exactly it; the grade is §5's own
declared-vs-heuristic line, which :mod:`gebra.annotations.inference` produces and this module
reads back off the envelope. Both therefore have one definition, in
:mod:`gebra.annotations.slots`, which this module reads and the declaration surfaces enforce.

**Outside hash scope, by construction.** §8: warnings "ride in the provenance envelope,
outside hash scope"; §4 repeats it (DEC-10). Nothing here is an IR model and nothing here
reaches :func:`gebra.ir.canonical.graph_version`, which digests
:attr:`~gebra.extraction.envelope.ExtractionEnvelope.ir` alone — so a warning can never
perturb a ``graph_version``.

Nothing here imports langgraph, opens a socket, or executes anything (WA-07).
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any, Final

from pydantic import Field, field_validator, model_validator

from gebra.annotations.slots import ANNOTATION_SLOTS, AnnotationSlot, SlotGrade
from gebra.extraction.base import ExtractionModel, type_identity
from gebra.ir.identity import NodeIdStr

__all__ = [
    "ANNOTATION_SLOTS",
    "HEURISTIC_GRADE_CODES",
    "WARNING_RULES",
    "AnnotationSlot",
    "ExtractionWarning",
    "ExtractionWarningCode",
    "SlotGrade",
    "WarningRule",
    "slot_grade",
    "warning_rule",
]


class ExtractionWarningCode(str, Enum):
    """The closed warning vocabulary ``gebra.extract()`` emits (INTROSPECTION §8; ANNOTATION §4).

    Closed: a construct extraction cannot map is reported with one of these ten codes or it
    is not reported at all, and "warnings are never silently droppable — ``gebra verify``
    MUST surface them, and a warning-free extraction is part of the strict-mode bar" (§8).
    Adding a code is a spec change, not a code change.
    """

    # ── INTROSPECTION-SPEC §8 ────────────────────────────────────────────────────────────
    CONTRACT_INFERRED = "contract-inferred"
    CONTRACT_DEFAULTED = "contract-defaulted"
    OPAQUE_LAMBDA = "opaque-lambda"
    BUILDER_COMPILED_DIVERGENCE = "builder-compiled-divergence"
    COMPILED_ONLY_EXTRACTION = "compiled-only-extraction"
    BARRIER_FLATTENED = "barrier-flattened"
    UNSUPPORTED_CONSTRUCT = "unsupported-construct"
    # ── ANNOTATION-API-SPEC §4 registry (the annotation-surface half of the same taxonomy) ─
    ANNOTATION_CONFLICT = "annotation-conflict"
    ANNOTATION_UNKNOWN_NODE = "annotation-unknown-node"
    ANNOTATION_INVALID = "annotation-invalid"


#: How deep a ``detail`` value may nest. Set far above anything a registry row asks for; it
#: exists so that a self-referential mapping is refused with a message rather than a
#: :class:`RecursionError`.
_MAX_DETAIL_DEPTH: Final = 20


@dataclass(frozen=True)
class WarningRule:
    """What one taxonomy row requires of the records that carry its code.

    The registry tables state what each warning "carries"; this is that column, in the form
    the model validator can check. Only the requirements the tables state are encoded — a
    row that does not name a node id does not get ``node_required``, so nothing here is
    stricter than INTROSPECTION §8 / ANNOTATION §4 are.

    Attributes:
        origin: The registry row this rule reads, cited so the requirement is traceable.
        carries: The row's "what it carries" column, condensed — what an emitter is expected
            to put in ``detail`` beyond the fields the model names.
        node_required: The row names a node id as the first thing it carries.
        slots_required: The row names the slot(s) it concerns.
        licensed_slots: The slots the row's own semantics admit, when the specs close the
            set; ``None`` where they do not, in which case the whole §1 annotatable set is
            admitted.
    """

    origin: str
    carries: str
    node_required: bool = False
    slots_required: bool = False
    licensed_slots: frozenset[str] | None = None


#: The ten rows, each with the requirement its registry entry states.
#:
#: ``contract-inferred`` is the one row whose slot set is closed here: DEC-08 is the
#: write-inference ruling and ANNOTATION §4's licensed-pattern table has exactly two slot
#: rows, ``input`` and ``output`` (INTROSPECTION §7.1 maps the same pair to it). That closure
#: is the structural half of the §4 NEVER-SILENT-UPGRADE rule — a record claiming
#: ``deterministic`` was *inferred* cannot be built. ``contract-defaulted`` is deliberately
#: left open: the D-011 defaults are ``effect``/``pure``, but §7.1 states the row over a
#: four-slot grouping, and encoding a closure the spec does not state is not this module's
#: call.
WARNING_RULES: Final[Mapping[ExtractionWarningCode, WarningRule]] = {
    ExtractionWarningCode.CONTRACT_INFERRED: WarningRule(
        origin="INTROSPECTION §8; ANNOTATION §4 (ratified — DEC-08)",
        carries="the licensing pattern per key; claims-not-upgraded reminder",
        node_required=True,
        slots_required=True,
        licensed_slots=frozenset({"input", "output"}),
    ),
    ExtractionWarningCode.CONTRACT_DEFAULTED: WarningRule(
        # §8/§4 word the row as "the applied D-011 default" rather than "slot"; §5 is what
        # makes the (node id, slot) pair normative for this code — "that is why the §4
        # registry's warnings are structured records with node-id and slot fields".
        origin="INTROSPECTION §8; ANNOTATION §4 (ratified — DEC-08), §5",
        carries="the applied D-011 default; why no pattern applied; declaration surfaces",
        node_required=True,
        slots_required=True,
    ),
    ExtractionWarningCode.OPAQUE_LAMBDA: WarningRule(
        origin="INTROSPECTION §8 (§5 rule 5)",
        carries="the applied D-011 default; pointer to the attachment options",
        node_required=True,
    ),
    ExtractionWarningCode.BUILDER_COMPILED_DIVERGENCE: WarningRule(
        origin="INTROSPECTION §8 (§4.3 rule 3)",
        carries="both readings, builder kept authoritative; the xray level used",
    ),
    ExtractionWarningCode.COMPILED_ONLY_EXTRACTION: WarningRule(
        origin="INTROSPECTION §8 (§4.3 rule 4); emitted once per extraction",
        carries="object type; extraction level; the one-class knowability downgrade",
    ),
    ExtractionWarningCode.BARRIER_FLATTENED: WarningRule(
        origin="INTROSPECTION §8 (§3 waiting_edges); one per waiting-edge group",
        carries="the source tuple and target; edges expanded; the P-04/P-09 caveat",
    ),
    ExtractionWarningCode.UNSUPPORTED_CONSTRUCT: WarningRule(
        origin="INTROSPECTION §8 (§2, §3, §6, §7.4)",
        carries="construct kind; location; why unmappable; whether the IR is partial there",
    ),
    ExtractionWarningCode.ANNOTATION_CONFLICT: WarningRule(
        origin="ANNOTATION §4 (ratified — DEC-07); §3",
        carries="both values; both surfaces (decorator/tool/sidecar)",
        node_required=True,
        slots_required=True,
    ),
    ExtractionWarningCode.ANNOTATION_UNKNOWN_NODE: WarningRule(
        origin="ANNOTATION §4 (ratified — DEC-07); §2",
        carries="the sidecar path; the unmatched entry key",
    ),
    ExtractionWarningCode.ANNOTATION_INVALID: WarningRule(
        origin="ANNOTATION §4 (this spec, §2/§3/§6)",
        carries="scope (file / node id); surface(s); value(s); the violated rule",
    ),
}

#: The two codes ANNOTATION §5's grade lookup reads, and only those two. The "iff" is the
#: spec's own: widening it here would be improvising semantics. Worth knowing while reading
#: :func:`slot_grade`: INTROSPECTION §8's ``contract-defaulted`` row sends *stitched lambdas*
#: to ``opaque-lambda`` "instead", and ``opaque-lambda`` is not one of the two codes §5 names
#: — so a defaulted slot on a stitched lambda reads as declared-grade under the lookup as
#: written. The §5 stitching path — the only one that can produce a stitched lambda — therefore
#: emits ``opaque-lambda`` **and** keeps the ``contract-defaulted`` record, so the lookup below
#: keeps its footing while §5 rule 5 is satisfied in terms. That is a co-emission where §8 words
#: the substitution as a replacement; it is the conservative direction (over-warning, never
#: under-grading). **Ratified — DEC-20, 2026-08-03:** §8's `contract-defaulted` row now reads
#: "`opaque-lambda` is emitted **in addition** and the default rides on this row", so both
#: codes name the (node, slot) pair and the lookup below stays sound by the spec's own words
#: rather than by this build's caution.
HEURISTIC_GRADE_CODES: Final[tuple[ExtractionWarningCode, ...]] = (
    ExtractionWarningCode.CONTRACT_INFERRED,
    ExtractionWarningCode.CONTRACT_DEFAULTED,
)


def warning_rule(code: ExtractionWarningCode) -> WarningRule:
    """The registry rule for ``code``. Total over the enum, so it never returns ``None``."""
    return WARNING_RULES[code]


class ExtractionWarning(ExtractionModel):
    """One structured warning record, riding the provenance envelope (§8; ANNOTATION §4).

    Attributes:
        code: The taxonomy code — the whole vocabulary is :class:`ExtractionWarningCode`.
        message: A one-line human summary. **Display-only**: every fact a consumer branches
            on lives in the fields below, never in this string (§4 "structured fields, never
            a bare string").
        node: The node id the warning is about, in the escaped IR-SPEC §5 form, or ``None``
            for a warning about the graph or about a file. Required for the codes whose
            registry row names a node id.
        slots: The annotation slots the warning names, as IR slot names. Required for the
            codes whose registry row names slots; together with :attr:`node` these are the
            (node id, slot) pairs of the §5 lookup.
        detail: The rest of the row's "what it carries" column, as JSON data — strings,
            numbers, booleans, ``None``, sequences and string-keyed mappings, and nothing
            else (checked, not assumed). Held as a plain JSON object the way
            :attr:`gebra.ir.models.Annotations.args_schema` is, because what a row carries
            differs per code and 1.0 imposes no algebra on it. Keys are the emitter's to
            choose; :attr:`WarningRule.carries` records what the registry expects to find
            there. A warning is *reported* — by ``gebra verify``, by the CLI, by the plugin
            — so a value that could not be serialized could not be reported.
    """

    code: ExtractionWarningCode
    message: str = Field(min_length=1)
    node: NodeIdStr | None = None
    slots: tuple[AnnotationSlot, ...] = ()
    detail: dict[str, Any] = Field(default_factory=dict)

    @field_validator("detail", mode="before")
    @classmethod
    def _detail_is_reportable_data(cls, detail: object) -> object:
        """Refuse what a report could not carry, and give sequences one representation.

        Two jobs, one walk. The refusal is the same discipline
        :mod:`gebra.ir.serialization` applies to documents — a value that cannot cross the
        boundary is named where it was introduced, and nothing is silently coerced on the way
        out (a non-string mapping key is refused rather than stringified, which is what
        ``json.dumps`` would do). The normalization is what makes an envelope reload equal to
        itself: JSON has one sequence type, so an authored tuple and a loaded array become
        the same value here instead of comparing unequal later.
        """
        if not isinstance(detail, dict):
            return detail  # not a mapping: let strict validation report it
        return {
            key: _reportable(value, path=f"detail[{key!r}]", depth=0)
            for key, value in detail.items()
        }

    @model_validator(mode="after")
    def _carries_what_its_registry_row_names(self) -> ExtractionWarning:
        """Hold the record to :data:`WARNING_RULES` — the taxonomy's own "carries" column."""
        rule = warning_rule(self.code)
        if rule.node_required and self.node is None:
            raise ValueError(
                f"{self.code.value!r} carries a node id ({rule.origin}); this record has none"
            )
        if rule.slots_required and not self.slots:
            raise ValueError(
                f"{self.code.value!r} carries the slot(s) it concerns ({rule.origin}); "
                "this record names none"
            )
        if rule.licensed_slots is not None:
            outside = tuple(slot for slot in self.slots if slot not in rule.licensed_slots)
            if outside:
                raise ValueError(
                    f"{self.code.value!r} is licensed for "
                    f"{sorted(rule.licensed_slots)} only ({rule.origin}); got {list(outside)}"
                )
        return self

    def targets(self) -> tuple[tuple[str, AnnotationSlot], ...]:
        """The (node id, slot) pairs this record names — the §5 lookup key, enumerated.

        Empty when the warning names no node (a file- or graph-scoped one) or no slot.
        """
        if self.node is None:
            return ()
        return tuple((self.node, slot) for slot in self.slots)


def _reportable(value: object, *, path: str, depth: int) -> Any:
    """``value`` as reportable JSON data, with sequences as tuples; raise if it is not.

    Total over JSON data and nothing else. The depth bound is what turns a self-referential
    mapping into a message rather than a :class:`RecursionError`.
    """
    if depth > _MAX_DETAIL_DEPTH:
        raise ValueError(
            f"{path} nests deeper than {_MAX_DETAIL_DEPTH} levels; a warning's detail is a "
            "record of what extraction found, not a data structure"
        )
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{path} is {value!r}; JSON has no form for it")
        return value
    if isinstance(value, (tuple, list)):
        return tuple(
            _reportable(item, path=f"{path}[{index}]", depth=depth + 1)
            for index, item in enumerate(value)
        )
    if isinstance(value, dict):
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                # ValueError, not TypeError (TRY004): pydantic converts a ValueError raised
                # in a validator into a ValidationError, and lets a TypeError escape as itself.
                raise ValueError(  # noqa: TRY004
                    f"{path} has the non-string key {key!r}; JSON keys are strings"
                )
            normalized[key] = _reportable(item, path=f"{path}[{key!r}]", depth=depth + 1)
        return normalized
    raise ValueError(
        f"{path} holds a {type_identity(value)}, which is not JSON data; a warning carries "
        "what extraction found, in a form it can be reported in"
    )


def slot_grade(
    warnings: Iterable[ExtractionWarning],
    node: str,
    slot: AnnotationSlot,
) -> SlotGrade:
    """The ANNOTATION §5 grade of ``slot`` on ``node``, read off the envelope's warnings.

    §5, normatively: "a slot on node *n* is declared-grade **iff** no
    ``contract-inferred``/``contract-defaulted`` warning in the extraction envelope names the
    (node id, slot) pair; otherwise it is heuristic-grade". The serialized IR carries no
    per-slot provenance (ledger §6 keeps the hash scope behavioral), so this lookup is how a
    validator learns whether a value it is about to reason from was declared by an author or
    produced by inference — which P-06/P-07's declared-only ``pure`` ⟹ idempotent gate and
    P-08's determinism reads both depend on.

    A pair named by both codes — which the §4 patterns cannot produce, since a slot either
    matched a pattern or fell to the default — reads as :attr:`SlotGrade.INFERRED`: a
    pattern licensed it, so the default did not apply.

    Comparison is byte equality of the escaped node id (IR-SPEC §5.1), the same comparison
    the ids themselves are compared under.
    """
    grade = SlotGrade.DECLARED
    for warning in warnings:
        if warning.node != node or slot not in warning.slots:
            continue
        if warning.code is ExtractionWarningCode.CONTRACT_INFERRED:
            return SlotGrade.INFERRED
        if warning.code is ExtractionWarningCode.CONTRACT_DEFAULTED:
            grade = SlotGrade.DEFAULTED
    return grade
