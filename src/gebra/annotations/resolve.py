"""The per-slot precedence chain — ANNOTATION-API-SPEC §3, ratified as DEC-07.

Four surfaces can say something about one node, and §3 fixes what happens when more than one
of them does: resolution is "**per-slot, strict**", in the order

    Decorator > Tool-carried > Sidecar > Inference

with "set" meaning *not-``None``* — so an explicit ``pure=False`` occupies its slot and blocks
lower-tier fill exactly like a positive value, and only absence leaves a slot open.

Four rules carry the module, and each is enforced here rather than described.

**The chain is per slot, and the winner is the highest tier that set it.** Nothing merges: a
slot has exactly one contributor, recorded in :attr:`Resolution.surfaces` so that §5's grade
lookup and the warning payloads can both name it.

**A losing tier is a conflict only when it says something different.** §3: "A sidecar entry
that sets a slot the decorator already set to a *different* value is a conflict … Identical
values are not a conflict", and identity is decided **structurally**: "two slot values are
identical **iff** their ledger §6 canonicalizations (omit-normalize → RFC 8785 JCS bytes) are
byte-equal". :func:`slot_bytes` is that test, and it asks
:func:`gebra.ir.canonical.canonical_annotations_bytes` — the emitter the digest itself uses —
rather than re-deriving §6.3 here, because a second implementation of the projection would be
a second opinion about a question whose whole point is that there is only one. The consequence
is worth stating: ``reads=["b", "a"]`` and ``reads=["a", "b"]`` are one value, since §6.2
sorts the array before any byte exists.

**A resolved contract is validated across surfaces, warning-grade.** §3: "Per-slot gap-filling
can assemble a contract no single surface authored — e.g. a decorator ``pure=True`` plus a
sidecar ``effects=[...]``: no slot was set twice, so it is not an ``annotation-conflict``, yet
the resolved contract violates decision D-011 exclusivity." So :func:`resolve` runs the four
invariants §3 names over the *resolved* contract and repairs by discarding the
lower-precedence contribution. Never an error — "extraction stays total, for the same reason
the DEC-07 conflict ruling is a warning".

**A resolved slot the canonical form could not carry is discarded, not emitted.** This one is
not in §3's list, and it is not a new rule either: it is the same reading
:mod:`gebra.extraction.builder` records for a ``path_map`` label. IR-SPEC §6.3 puts
``input``/``output`` entries, ``idempotent.key`` and ``variant.key`` in the NFC identifier
role, and canonicalization *refuses* a non-NFC string rather than normalizing one — so a
declared ``reads=["café"]`` spelled decomposed would resolve into an IR that INTROSPECTION §2
requires to exist and that raises the moment anyone asks it for a ``graph_version``. Extraction
total in name only. :func:`carriable` therefore NFC-normalizes the identifier-role members
(normalization, which §5.1 already applies one level down for node-id segments) and discards —
with the §3 repair vocabulary, ``annotation-invalid`` — whatever the canonical form still
refuses. What survives this pass is emittable by construction: every contract this module
returns has canonical bytes.

Nothing here imports langgraph, opens a socket, or executes anything (WA-07). Every value it
handles has already been normalized by :mod:`gebra.annotations.contract` — the one seam both
declaration surfaces share — so this module never reads a raw user value and never renders one.
"""

from __future__ import annotations

import json
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Final

from gebra.annotations.contract import NodeContract
from gebra.annotations.slots import ANNOTATION_SLOTS, AnnotationSlot, SlotGrade
from gebra.ir.canonical import CanonicalizationError, canonical_annotations_bytes
from gebra.ir.models import Annotations, Compensation, IdempotentKey, Variant

__all__ = [
    "IDENTIFIER_SLOTS",
    "PRECEDENCE",
    "TIER_SLOTS",
    "Contribution",
    "IssueKind",
    "Resolution",
    "ResolutionIssue",
    "ResolutionRule",
    "Surface",
    "carriable",
    "resolve",
    "slot_bytes",
    "slot_data",
]


class Surface(str, Enum):
    """A §3 precedence tier — where one slot value came from.

    The four spellings are §3's own, and the first three are also the ``annotation-conflict``
    registry row's "both surfaces (``decorator``/``tool``/``sidecar``)" vocabulary (§4), so a
    warning payload names a surface with the same string the chain is written in.
    """

    DECORATOR = "decorator"
    """§3 tier 1 (highest) — ``@gebra.contract`` and the shorthands (§1)."""

    TOOL = "tool"
    """§3 tier 2 — a LangChain ``BaseTool``'s author-written pydantic ``args_schema`` (§1).

    "``args_schema`` is the sole slot with a tool-carried source in ir 1.0."
    """

    SIDECAR = "sidecar"
    """§3 tier 3 — ``gebra.toml`` entries, which "fill slots the higher tiers left unset"."""

    INFERENCE = "inference"
    """§3 tier 4 (lowest) — the §4 shallow patterns and the D-011 defaults, "always warned"."""


#: The chain, highest first. §3's order is normative and DEC-07 is the ruling behind the
#: decorator/sidecar edge; the tool-carried tier sits between them "by DEC-07's own rationale:
#: the schema lives on the tool class and moves with the code, while a TOML file drifts".
PRECEDENCE: Final[tuple[Surface, ...]] = (
    Surface.DECORATOR,
    Surface.TOOL,
    Surface.SIDECAR,
    Surface.INFERENCE,
)

#: Which slots each tier is *able* to speak about, where the spec closes the set. The
#: decorator and the sidecar share the whole §1 nine "byte-for-byte"; the tool-carried tier is
#: one slot by §3's own sentence; inference is §4's two patterns plus the two D-011 default
#: slots, and its closure is the NEVER-SILENT-UPGRADE rule
#: (:data:`gebra.annotations.inference.INFERENCE_SLOTS` is the producer side of the same set).
#:
#: This table does not *filter* — a contribution is taken as it comes, so an out-of-tier slot
#: would still resolve. It is here because the precedence matrix is a claim about which cells
#: exist, and a test quantified over the table is how that claim stays checkable.
TIER_SLOTS: Final[Mapping[Surface, frozenset[AnnotationSlot]]] = {
    Surface.DECORATOR: frozenset(ANNOTATION_SLOTS),
    Surface.TOOL: frozenset({"args_schema"}),
    Surface.SIDECAR: frozenset(ANNOTATION_SLOTS),
    Surface.INFERENCE: frozenset({"input", "output", "effect", "pure"}),
}

#: The slots whose value carries identifier-role strings (IR-SPEC §6.3: ``input``/``output``
#: entries, ``idempotent.key``, ``variant.key``). :func:`carriable` NFC-normalizes exactly
#: these; ``compensation.hook`` is node-id-role and is normalized through the same rule at one
#: remove, since §5.1 normalizes a segment before escaping it.
IDENTIFIER_SLOTS: Final[frozenset[AnnotationSlot]] = frozenset(
    {"input", "output", "idempotent", "variant"}
)


class IssueKind(str, Enum):
    """Which §4 registry row a finding of this module belongs to.

    Two, and the split is §3's own: a *disagreement between tiers* is
    ``annotation-conflict`` (DEC-07's ruling), while a resolved contract that violates a §1
    invariant — or a value the IR could not carry — is ``annotation-invalid`` (§3's
    resolved-contract pass). :mod:`gebra.extraction.contracts` maps the two to their codes;
    keeping the mapping there is what lets this package stay free of the extractor.
    """

    CONFLICT = "annotation-conflict"
    INVALID = "annotation-invalid"


class ResolutionRule(str, Enum):
    """The §3 rule a :class:`ResolutionIssue` reports — a stable code to branch on.

    Attributes:
        LOWER_TIER_DIFFERS: §3/DEC-07 — a lower tier set a slot a higher tier had already
            set, to a value whose canonicalization differs. The higher tier's value stands.
        PURE_EFFECT_EXCLUSIVE: §3's own worked example — a resolved ``pure: true`` beside a
            non-empty ``effect`` (decision D-011 exclusivity).
        IDEMPOTENT_KEY_NOT_IN_INPUT: §1 — ``idempotent={"key": k}`` "requires ``k`` to appear
            in the node's resolved ``input`` set". Advisory when the resolved ``input`` is
            heuristic-grade (§1: "a heuristic-grade input set cannot ground a hard verdict
            against a declared key; the warning records both grades").
        IRREVERSIBLE_IDEMPOTENT: §1/decision D-012 — ``effects`` containing ``irreversible``
            together with ``idempotent=True`` "is rejected as a design error".
        SLOT_NOT_CARRIABLE: The resolved value has no canonical form, so a node emitting it
            would have no ``graph_version``. Not one of §3's four; see the module docstring
            for why the §3 repair vocabulary is the right home for it.

    §3's fourth named invariant — "the ``deterministic`` object shape (ledger §3)" — has no
    code here on purpose, and the absence is a claim rather than an omission: the seedless
    object form cannot reach a resolved contract at all. It is refused where it is written on
    both declaration surfaces (an import-time ``GebraContractError`` on the decorator, §1; an
    ``annotation-invalid`` with the slot left unset on the sidecar, §2 bullet 5), and the
    carrier both surfaces produce — :class:`~gebra.ir.models.DeterministicSpec` — types
    ``seed`` required. A branch here would be code no input could reach, which is a worse
    record of the invariant than a test that shows all three refusals.
    """

    LOWER_TIER_DIFFERS = "lower-tier-differs"
    PURE_EFFECT_EXCLUSIVE = "pure-effect-exclusive"
    IDEMPOTENT_KEY_NOT_IN_INPUT = "idempotent-key-not-in-input"
    IRREVERSIBLE_IDEMPOTENT = "irreversible-idempotent"
    SLOT_NOT_CARRIABLE = "slot-not-carriable"


#: The effect tag decision D-012 refuses to see beside ``idempotent: true``.
_IRREVERSIBLE: Final = "irreversible"


@dataclass(frozen=True)
class Contribution:
    """What one §3 tier says about one node.

    A whole :class:`~gebra.annotations.contract.NodeContract` rather than a slot at a time,
    because that is the shape all four tiers already produce — the decorator attaches one, the
    sidecar loader parses one per entry, the tool tier builds one holding ``args_schema``, and
    :class:`gebra.annotations.inference.Inference` carries one. "Set" is the model's own test
    (:meth:`~gebra.annotations.contract.NodeContract.declared_slots`), so the chain never needs
    a second record of which slots a tier meant.

    Attributes:
        surface: The tier.
        contract: What it declared. An empty contract is a tier that said nothing, which is
            the ordinary case for three of the four on most nodes.
    """

    surface: Surface
    contract: NodeContract


@dataclass(frozen=True)
class ResolutionIssue:
    """One warning-grade §3 finding, in the shape its §4 registry row asks for.

    A neutral record rather than an :class:`~gebra.extraction.warnings.ExtractionWarning`,
    for the reason :class:`~gebra.annotations.sidecar.SidecarIssue` is one: this package must
    not import :mod:`gebra.extraction`, which reads the substrate's classes.

    Attributes:
        kind: Which registry row — :class:`IssueKind`.
        rule: The violated §3 rule.
        message: A one-line human summary. Display-only; the facts are the fields.
        slots: The IR slot names the finding concerns — the ``annotation-conflict`` row's
            "slot" and the ``annotation-invalid`` row's "slot(s)".
        detail: The rest of the row's "carries" column as JSON data: the surfaces, the
            values, the violated rule, and (for the advisory case) the §5 grades.
    """

    kind: IssueKind
    rule: ResolutionRule
    message: str
    slots: tuple[AnnotationSlot, ...]
    detail: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Resolution:
    """The resolved contract for one node, and everything §3 had to say about getting there.

    Attributes:
        contract: The winner per slot, after the carriability pass and the resolved-contract
            repair. Every slot in it has canonical bytes, so a node carrying it has a
            ``graph_version``.
        surfaces: Which tier each surviving slot came from — the record §5's grade lookup and
            the conflict payloads are both written against. A slot absent from
            :attr:`contract` is absent here.
        issues: Every finding, in the order the chain produced them: conflicts per slot in
            :data:`~gebra.annotations.slots.ANNOTATION_SLOTS` order, then the carriability
            discards, then the resolved-contract repairs.
    """

    contract: NodeContract
    surfaces: Mapping[AnnotationSlot, Surface] = field(default_factory=dict)
    issues: tuple[ResolutionIssue, ...] = ()

    def declared(self) -> tuple[AnnotationSlot, ...]:
        """The slots filled by a *declaration* tier — everything but inference.

        §5's grade lookup stays normative and runs off the envelope's warnings; this is the
        producer side of the same line, available here because the tier is still known. The
        two agree by construction, since :mod:`gebra.extraction.contracts` emits one §4
        record for every slot the inference tier filled and none for any other.
        """
        return tuple(
            slot
            for slot in ANNOTATION_SLOTS
            if slot in self.surfaces and self.surfaces[slot] is not Surface.INFERENCE
        )


def _one_slot(slot: AnnotationSlot, value: object) -> Annotations:
    """An ``annotations`` object carrying ``slot`` and nothing else.

    The projection both §3 questions are asked through: value identity is byte-equality of
    the ledger §6 canonicalization of a slot, and a warning payload carries the slot's IR
    shape. Building the real model for one slot is what makes both answers the IR's own
    rather than this module's rendering of it.
    """
    return Annotations.model_validate({slot: value})


def slot_data(slot: AnnotationSlot, value: object) -> Any:
    """One slot value as JSON data — what a warning payload carries.

    Routed through :class:`~gebra.ir.models.Annotations` rather than rendered, so the shape a
    reader sees in an ``annotation-conflict`` is the shape the IR would have carried, and so
    that a sub-model (``{"key": …}``, ``{"seed": …}``) becomes an object instead of a repr.
    """
    dumped: dict[str, Any] = _one_slot(slot, value).model_dump(mode="json", exclude_none=True)
    return dumped.get(slot)


def slot_bytes(slot: AnnotationSlot, value: object) -> bytes:
    """The ledger §6 canonicalization of one slot value — §3's value-identity test.

    Raises:
        CanonicalizationError: if the value has no canonical form. Callers compare through
            :func:`_identical`, which reads a refusal as "not identical" rather than letting
            it escape; :func:`carriable` is what turns the refusal into a finding.
    """
    return canonical_annotations_bytes(_one_slot(slot, value))


def carriable(slot: AnnotationSlot, value: object) -> object | None:
    """``value`` in the form the IR carries it, or ``None`` if the canonical form refuses it.

    Two steps, in this order. The identifier-role members are NFC-normalized (IR-SPEC §6.3
    puts them in that role and §5.1 already normalizes node-id segments the same way, so this
    is the established reading rather than a new rule), and then the whole slot is
    canonicalized as the acceptance test. A value that survives is one the emitter has already
    accepted, which is what makes "every contract :func:`resolve` returns has canonical bytes"
    a property rather than a hope.
    """
    normalized = _normalized(slot, value)
    try:
        slot_bytes(slot, normalized)
    except CanonicalizationError:
        return None
    return normalized


def resolve(contributions: Iterable[Contribution]) -> Resolution:
    """Run the §3 chain over one node's contributions and validate what it assembled.

    Args:
        contributions: One per tier that has something to say, in any order — the chain
            sorts by :data:`PRECEDENCE`, so a caller cannot change the outcome by changing
            the order it collects them in. This is the "source-order independent" half of the
            §6 parity requirement, made structural: two tiers at the same precedence are not
            representable, and a repeated surface is resolved in the order given (the caller
            that builds two contributions for one tier has already merged them, or has a bug
            this module cannot see).

    Returns:
        The :class:`Resolution` — the resolved contract, the surface per slot, and every
        warning-grade finding, all of it total: nothing here raises.
    """
    ordered = sorted(contributions, key=lambda item: PRECEDENCE.index(item.surface))
    won: dict[AnnotationSlot, object] = {}
    surfaces: dict[AnnotationSlot, Surface] = {}
    issues: list[ResolutionIssue] = []

    _elect(ordered, won, surfaces, issues)
    _discard_uncarriable(won, surfaces, issues)
    _validate_resolved(won, surfaces, issues)

    return Resolution(
        # Validated rather than constructed positionally, for the reason
        # `contract._attach` records: `model_validate` is the path that keeps
        # `extra="forbid"` meaningful over a slot-name-keyed mapping.
        contract=NodeContract.model_validate(dict(won)),
        surfaces=dict(surfaces),
        issues=tuple(issues),
    )


# ── The chain ────────────────────────────────────────────────────────────────────────────


def _elect(
    ordered: Sequence[Contribution],
    won: dict[AnnotationSlot, object],
    surfaces: dict[AnnotationSlot, Surface],
    issues: list[ResolutionIssue],
) -> None:
    """§3's per-slot election: the highest tier that set a slot keeps it.

    A lower tier that sets the same slot is *kept out* (DEC-07: the sidecar "fills gaps
    only") and reported — unless the two values canonicalize to the same bytes, which §3 says
    "are not a conflict" and which this build takes literally enough to emit nothing at all.
    """
    for slot in ANNOTATION_SLOTS:
        for contribution in ordered:
            declared = contribution.contract.slot_value(slot)
            if declared is None:
                continue
            # Normalized *before* the comparison, and the order is the whole point: an NFD
            # `reads=["café"]` and an NFC one are the same state key — §6.3 says so by putting
            # both in one normal form — so comparing the authored spellings would report a
            # conflict about a file's encoding, and then normalize the two into one key anyway.
            value = _normalized(slot, declared)
            if slot not in won:
                won[slot] = value
                surfaces[slot] = contribution.surface
                continue
            if _identical(slot, won[slot], value):
                continue
            kept = surfaces[slot]
            issues.append(
                ResolutionIssue(
                    kind=IssueKind.CONFLICT,
                    rule=ResolutionRule.LOWER_TIER_DIFFERS,
                    message=(
                        f"the {contribution.surface.value} declares {slot!r} differently from "
                        f"the {kept.value}, which takes precedence (ANNOTATION-API-SPEC §3; "
                        f"ratified DEC-07); the {kept.value} value is kept"
                    ),
                    slots=(slot,),
                    detail={
                        "rule": ResolutionRule.LOWER_TIER_DIFFERS.value,
                        "slot": slot,
                        "surfaces": {"kept": kept.value, "discarded": contribution.surface.value},
                        "values": {
                            "kept": slot_data(slot, won[slot]),
                            "discarded": slot_data(slot, value),
                        },
                    },
                )
            )


def _identical(slot: AnnotationSlot, kept: object, offered: object) -> bool:
    """§3's structural value identity, with a refusal read as "not identical".

    A value with no canonical form cannot be shown identical to anything, and reporting the
    disagreement is the conservative direction: the losing value is discarded either way, and
    :func:`_discard_uncarriable` is what answers for the winner.
    """
    try:
        return slot_bytes(slot, kept) == slot_bytes(slot, offered)
    except CanonicalizationError:
        return False


def _discard_uncarriable(
    won: dict[AnnotationSlot, object],
    surfaces: dict[AnnotationSlot, Surface],
    issues: list[ResolutionIssue],
) -> None:
    """Normalize the identifier-role members and drop what the canonical form still refuses."""
    for slot in ANNOTATION_SLOTS:
        if slot not in won:
            continue
        carried = carriable(slot, won[slot])
        if carried is not None:
            won[slot] = carried
            continue
        surface = surfaces.pop(slot)
        value = won.pop(slot)
        issues.append(
            ResolutionIssue(
                kind=IssueKind.INVALID,
                rule=ResolutionRule.SLOT_NOT_CARRIABLE,
                message=(
                    f"the {surface.value}'s {slot!r} has no canonical form, so a node carrying "
                    "it would have no graph_version (IR-SPEC §6.3); the slot is dropped and "
                    "extraction stays total (ANNOTATION-API-SPEC §3)"
                ),
                slots=(slot,),
                detail={
                    "rule": ResolutionRule.SLOT_NOT_CARRIABLE.value,
                    "slot": slot,
                    "surfaces": {"discarded": surface.value},
                    "values": {"discarded": _describe(slot, value)},
                },
            )
        )


def _normalized(slot: AnnotationSlot, value: object) -> object:
    """The identifier-role strings inside ``value`` in NFC; everything else untouched."""
    if slot in ("input", "output") and isinstance(value, tuple):
        return tuple(_nfc(member) for member in value)
    if slot == "idempotent" and isinstance(value, IdempotentKey):
        return IdempotentKey(key=_nfc(value.key))
    if slot == "variant" and isinstance(value, Variant):
        return Variant(key=_nfc(value.key), measure=value.measure)
    if slot == "compensation" and isinstance(value, Compensation):
        return Compensation(hook=_nfc(value.hook))
    return value


def _nfc(value: object) -> Any:
    """One identifier-role string in NFC. A non-string is returned unchanged, for the model
    to refuse where the type is declared."""
    return unicodedata.normalize("NFC", value) if isinstance(value, str) else value


def _describe(slot: AnnotationSlot, value: object) -> Any:
    """A discarded value as JSON data, or its type name when that cannot be reported.

    The fallback is load-bearing rather than defensive: this function exists for values the
    canonical form *refused*, and one way to be refused is to hold a lone surrogate — which
    :class:`~gebra.extraction.warnings.ExtractionWarning` also cannot carry, since a warning
    is reported and a surrogate has no UTF-8 encoding. Degrading to a type name is what keeps
    the warning that reports an unreportable value from being unreportable itself.

    The test is the report's own: serialize the value the way a report would and see whether
    the bytes exist. Asking that question directly, rather than re-deriving which shapes a
    warning admits, is what keeps this function from being a second opinion about it.
    """
    data = slot_data(slot, value)
    try:
        json.dumps(data, ensure_ascii=False).encode("utf-8")
    except (UnicodeEncodeError, TypeError, ValueError):
        return type(value).__name__
    return data


# ── The resolved-contract pass (§3) ──────────────────────────────────────────────────────


def _validate_resolved(
    won: dict[AnnotationSlot, object],
    surfaces: dict[AnnotationSlot, Surface],
    issues: list[ResolutionIssue],
) -> None:
    """§3's resolved-contract validation, with its lower-precedence-discard repair.

    Run to a fixed point over the three invariants that can fire, because a repair changes
    the contract the next invariant sees — discarding a sidecar ``effect`` to settle D-011
    exclusivity is exactly what can leave a D-012 pair behind.
    """
    for _ in range(len(ANNOTATION_SLOTS)):
        issue = _first_violation(won, surfaces)
        if issue is None:
            return
        finding, repairable = issue
        issues.append(finding)
        if not repairable:
            return
        for slot in _lowest_tier_slots(finding.slots, surfaces):
            won.pop(slot, None)
            surfaces.pop(slot, None)


def _first_violation(
    won: Mapping[AnnotationSlot, object],
    surfaces: Mapping[AnnotationSlot, Surface],
) -> tuple[ResolutionIssue, bool] | None:
    """The first §3 invariant the resolved contract violates, and whether it can be repaired.

    "Repairable" is the §3 repair rule's own precondition: it says "the contribution from the
    **lower-precedence** tier is discarded, the higher tier's slots stand", which presupposes
    two tiers. When every participating slot came from one tier there is no lower contribution
    to discard, and §1 puts both decision D-012 checks at warning grade precisely because they
    "need the *resolved* contract" — so the finding is reported and the contract is left as the
    author wrote it, for P-06/P-07 to judge. The idempotency-key check has its own reason to
    report without repairing, and §1 states it in terms: against an inference-grade ``input``
    the check is "advisory only".
    """
    pure = won.get("pure")
    effect = won.get("effect")
    idempotent = won.get("idempotent")

    if pure is True and isinstance(effect, tuple) and effect:
        return (
            _invalid(
                ResolutionRule.PURE_EFFECT_EXCLUSIVE,
                (
                    "the resolved contract declares pure=true together with the effects "
                    f"{list(effect)!r}; decision D-011 makes the two mutually exclusive "
                    "(ANNOTATION-API-SPEC §1/§3)"
                ),
                ("pure", "effect"),
                won,
                surfaces,
            ),
            _spans_two_tiers(("pure", "effect"), surfaces),
        )

    if idempotent is True and isinstance(effect, tuple) and _IRREVERSIBLE in effect:
        return (
            _invalid(
                ResolutionRule.IRREVERSIBLE_IDEMPOTENT,
                (
                    "the resolved contract declares idempotent=true on a node whose effects "
                    "include 'irreversible'; decision D-012 rejects that pair as a design "
                    "error (ANNOTATION-API-SPEC §1/§3)"
                ),
                ("idempotent", "effect"),
                won,
                surfaces,
            ),
            _spans_two_tiers(("idempotent", "effect"), surfaces),
        )

    if isinstance(idempotent, IdempotentKey):
        declared_input = won.get("input")
        if isinstance(declared_input, tuple) and idempotent.key not in declared_input:
            heuristic = surfaces.get("input") is Surface.INFERENCE
            return (
                _invalid(
                    ResolutionRule.IDEMPOTENT_KEY_NOT_IN_INPUT,
                    (
                        f"the idempotency key {idempotent.key!r} is not a member of the "
                        f"resolved input {list(declared_input)!r}; §1 requires it to appear "
                        "there"
                        + (
                            " — advisory only here, because the resolved input is "
                            "heuristic-grade and cannot ground a hard verdict against a "
                            "declared key"
                            if heuristic
                            else ""
                        )
                    ),
                    ("idempotent", "input"),
                    won,
                    surfaces,
                    extra={
                        "advisory": heuristic,
                        "grades": {
                            "idempotent": _grade(surfaces.get("idempotent")),
                            "input": _grade(surfaces.get("input")),
                        },
                    },
                ),
                not heuristic and _spans_two_tiers(("idempotent", "input"), surfaces),
            )

    return None


def _invalid(
    rule: ResolutionRule,
    message: str,
    slots: tuple[AnnotationSlot, ...],
    won: Mapping[AnnotationSlot, object],
    surfaces: Mapping[AnnotationSlot, Surface],
    *,
    extra: Mapping[str, Any] | None = None,
) -> ResolutionIssue:
    """One resolved-contract finding, carrying §3's "node id, slot(s), surfaces, both values,
    and the violated invariant" — the node id is added by the extraction seam, which is the
    layer that knows it."""
    detail: dict[str, Any] = {
        "rule": rule.value,
        "slots": list(slots),
        "surfaces": {slot: _surface_name(surfaces.get(slot)) for slot in slots},
        "values": {slot: slot_data(slot, won[slot]) for slot in slots if slot in won},
    }
    if extra is not None:
        detail.update(extra)
    return ResolutionIssue(
        kind=IssueKind.INVALID,
        rule=rule,
        message=message,
        slots=slots,
        detail=detail,
    )


def _spans_two_tiers(
    slots: tuple[AnnotationSlot, ...], surfaces: Mapping[AnnotationSlot, Surface]
) -> bool:
    """Whether the participating slots came from more than one tier — §3's repair precondition."""
    return len({surfaces[slot] for slot in slots if slot in surfaces}) > 1


def _lowest_tier_slots(
    slots: tuple[AnnotationSlot, ...], surfaces: Mapping[AnnotationSlot, Surface]
) -> tuple[AnnotationSlot, ...]:
    """The participating slots contributed by the lowest tier — what §3's repair discards."""
    present = [slot for slot in slots if slot in surfaces]
    if not present:  # pragma: no cover - a violation names slots that were resolved
        return ()
    lowest = max(PRECEDENCE.index(surfaces[slot]) for slot in present)
    return tuple(slot for slot in present if PRECEDENCE.index(surfaces[slot]) == lowest)


def _surface_name(surface: Surface | None) -> str | None:
    """A surface as its §4 payload spelling, or ``None`` for a slot that is not set."""
    return None if surface is None else str(surface.value)


def _grade(surface: Surface | None) -> str:
    """The §5 grade a slot filled from ``surface`` reads back as."""
    grade = SlotGrade.DECLARED if surface is not Surface.INFERENCE else SlotGrade.INFERRED
    return str(grade.value)
