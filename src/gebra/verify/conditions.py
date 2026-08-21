"""The §0.4 condition-ID registry — the closed diagnostic vocabulary, and the one way to emit.

Normative authority: PROPERTY-CATALOG-SPEC §0.4. Condition IDs are "the frozen, kebab-case
identifiers carried in ``Failure.property_condition`` — the catalog's stable diagnostic
vocabulary and (via §0.5) the SARIF ``rule.id`` namespace". Frozen-verbatim matters beyond
hygiene there: GitHub's alert dedup keys on a result's ``ruleId`` being identical across
analyses, so a renamed ID silently splits one alert into two.

**Three tiers, two questions.** §0.4 tables the registry as RATIFIED / RESERVED / PROPOSED,
and those tiers answer *registration* — which names are spoken for. Emission is the second
question, and §0.4 states its trigger once: "a PROPOSED entry is a **registered name, not an
emittable one** … it ratifies when its dated decision record lands". RESERVED entries "ratify
when their property sections … are merged". So this module derives one rule from the spec's
own wording — :attr:`ConditionEntry.emittable` is true exactly when a dated decision record
has ratified the entry — and the tier is kept as filed, which is why ``orphan-node`` and
``edge-target-undefined`` are both ``proposed``-tier entries that *are* emittable: each has
its own dated record (DEC-11 by name; DEC-12 as the entry's own §0.4 addendum).

**Where each guard lives, and why they are not the same guard.**

* *Unregistered* is refused by the **type**: :data:`~gebra.verify.base.ConditionId` is a
  ``Literal`` over the 21 registered strings, so pydantic rejects an unregistered value
  wherever a :class:`~gebra.verify.report.Failure`, ``CoFailure`` or ``Advisory`` is built or
  loaded — through the constructor, through ``validate_report``, through a fixture. mypy
  covers the other direction: every entry's ``id`` is annotated ``ConditionId``, so a table
  row the Literal does not know is a type error, and the import-time invariant below catches
  a Literal member with no table row.
* *Registered but not emittable* is refused at the **emission constructors**
  (:func:`emit_failure`, :func:`emit_co_failure`, :func:`emit_advisory`) rather than in the
  models, because the models have two duties (PC-6): the vendored corpus carries RESERVED IDs
  inside ``expected:`` blocks — ``mixed/01``, ``mixed/06``, ``mixed/09`` and the P-07/P-09/P-12
  negatives — and a model that refused them would refuse the fixture side of its own contract.
  A report *may record* a held name; a validator may not *emit* one.

The constructors are the sole emission surface for the same reason the registry is a single
table: they take a condition ID and read severity, claim class and the owning property **off
§0.4** instead of letting a caller restate them, so a validator cannot quietly disagree with
the catalog about what grade its own finding carries.

Nothing here imports langgraph, executes anything, or opens a socket (WA-07): this module is
a frozen table plus lookups over it.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Final, Literal, TypeAlias, TypeVar, get_args, overload

from gebra.verify.base import (
    ClaimClass,
    ConditionId,
    PropertyId,
    PropertySlug,
    Severity,
)
from gebra.verify.locations import AnyLocation
from gebra.verify.report import Advisory, CoFailure, Failure

__all__ = [
    "CONDITION_IDS",
    "CONDITION_REGISTRY",
    "EMITTABLE_CONDITION_IDS",
    "PROPOSED_CONDITION_IDS",
    "RATIFIED_CONDITION_IDS",
    "RESERVED_CONDITION_IDS",
    "UNREGISTERED_CORPUS_STRINGS",
    "AdvisoryCarriageError",
    "ConditionEntry",
    "ConditionOwnershipError",
    "ConditionRegistryError",
    "ConditionTier",
    "NonEmittableConditionError",
    "UnregisteredConditionError",
    "condition",
    "conditions_for",
    "emit_advisory",
    "emit_co_failure",
    "emit_failure",
    "emittable_condition",
    "is_emittable",
    "is_registered",
    "property_for_condition",
]


#: The three §0.4 tables an entry can be filed under. The tier is *where the name was filed*,
#: never a shorthand for emittability — see :attr:`ConditionEntry.emittable`.
ConditionTier: TypeAlias = Literal["ratified", "reserved", "proposed"]


class ConditionRegistryError(ValueError):
    """A condition ID was used in a way the §0.4 registry does not license."""


class UnregisteredConditionError(ConditionRegistryError):
    """The string is not a member of the §0.4 registry.

    "Validators may never emit a string absent from the registry" (§0.4 registry
    discipline). Adding one is a spec addendum — a dated decision record plus an edit to the
    §0.4 table — never a local patch.
    """


class NonEmittableConditionError(ConditionRegistryError):
    """The ID is registered, but no dated decision record has ratified it yet.

    RESERVED entries ratify when their property sections merge; a PROPOSED entry ratifies
    when its own addendum lands (§0.4). Until then the name is held, not emittable — a
    fixture may record it, a validator may not produce it.
    """


class ConditionOwnershipError(ConditionRegistryError):
    """The emitting property does not own this condition ID.

    §0.4 holds each name "for their properties" and forbids reuse, so a finding attributed to
    one property may not carry another's condition ID.
    """


class AdvisoryCarriageError(ConditionRegistryError):
    """A property tried to ride its own finding on its own report as an advisory.

    §0.3's packaging rule is one sentence with two halves: ``advisories`` carries
    **cross-property** WARNING-class side findings only, and same-property findings "are never
    dropped and never re-packaged as self-referential advisories" — they ride ``co_failures``
    (ratified envelope-wide at walkthrough #2; DEC-11).
    """


@dataclass(frozen=True)
class ConditionEntry:
    """One row of the §0.4 registry.

    Attributes:
        id: The frozen kebab-case identifier, byte-exact as §0.4 spells it.
        property_slug: The catalog slug the name is held for.
        property_id: That property's ``P-nn`` id.
        tier: The §0.4 table this entry is filed under.
        severity: The §0.2 grade §0.4 pins for this condition, when it pins one. The RESERVED
            table carries no severity column — those grades arrive with the section merge —
            so this is ``None`` there rather than a guess.
        claim_class: The §0.1 class §0.4 pins, on the same terms as ``severity``.
        ratified_by: The dated decision record that ratified the entry, if one has. This is
            the whole of the emittability test (§0.4's ratification trigger); ``None`` means
            the name is held and nothing more.
        precedent: The in-corpus precedent §0.4 cites for the string.
        note: Anything else §0.4 says about the entry that a caller may need.
    """

    id: ConditionId
    property_slug: PropertySlug
    property_id: PropertyId
    tier: ConditionTier
    severity: Severity | None = None
    claim_class: ClaimClass | None = None
    ratified_by: str | None = None
    precedent: str | None = None
    note: str | None = None

    def __post_init__(self) -> None:
        if self.emittable and (self.severity is None or self.claim_class is None):
            raise ConditionRegistryError(
                f"{self.id!r} is ratified for emission but pins no severity/claim class; "
                "§0.1 requires every emitted record to classify its own claim."
            )

    @property
    def emittable(self) -> bool:
        """Whether a validator may emit this ID (§0.4's ratification trigger, stated once)."""
        return self.ratified_by is not None


#: The registry, in §0.4 table order. Every fact here is the spec's; nothing is inferred.
#: The severity/claim-class columns of the RATIFIED tier are also attested by the corpus —
#: ``tests/verify/test_conditions.py`` checks every ``expected:`` block that states a grade
#: against this table, so a divergence surfaces as a failing test rather than as a report
#: that disagrees with the catalog.
_ENTRIES: Final[tuple[ConditionEntry, ...]] = (
    # ── RATIFIED — "fixed by the reviewed fixture corpus … frozen as of this spec" ──
    ConditionEntry(
        id="node-unreachable-from-start",
        property_slug="graph-well-formed",
        property_id="P-01",
        tier="ratified",
        severity="fatal",
        claim_class="defensible",
        ratified_by="PROPERTY-CATALOG-SPEC §0.4 RATIFIED (DEC-05)",
        precedent="graph-well-formed/negative-01; mixed/04",
        note=(
            "P-01 owns unreachable code entirely (DEC-05 D2): a downstream dataflow gap "
            "under an unreachable node is subsumed here, never double-blamed."
        ),
    ),
    ConditionEntry(
        id="dead-end-node-not-wired-to-end",
        property_slug="graph-well-formed",
        property_id="P-01",
        tier="ratified",
        severity="fatal",
        claim_class="defensible",
        ratified_by="PROPERTY-CATALOG-SPEC §0.4 RATIFIED (DEC-05)",
        precedent="graph-well-formed/negative-02",
    ),
    ConditionEntry(
        id="path-map-target-undefined",
        property_slug="graph-well-formed",
        property_id="P-01",
        tier="ratified",
        severity="fatal",
        claim_class="defensible",
        ratified_by="PROPERTY-CATALOG-SPEC §0.4 RATIFIED (DEC-05)",
        precedent="graph-well-formed/negative-03; mixed/04",
    ),
    ConditionEntry(
        id="cycle-without-termination-witness",
        property_slug="termination-witness",
        property_id="P-02",
        tier="ratified",
        severity="fatal",
        claim_class="defensible",
        ratified_by="PROPERTY-CATALOG-SPEC §0.4 RATIFIED (DEC-05)",
        precedent="termination-witness/negative-01/-02/-04; mixed/02/05/08",
        note=(
            "The strict profile mints no new condition ID: TERMINATION-WITNESS-SPEC §2.4 and "
            "§6.1 (ratified — walkthrough #2, 2026-07-18; DEC-11) have S_b-excluded SCCs "
            "reuse this ID with the structured field `blanket_only: true` on the location. "
            "Read it with the catalog: §2.4's pseudocode takes no strict parameter and §0.2 "
            "has promotion change the gate, never the record, so this is the gate layer's "
            "projection of a pass-with-note — see P02SccLocation, which also disposes of "
            "§6.1's `blanket_only: false`."
        ),
    ),
    ConditionEntry(
        id="counter-guard-without-exit-edge",
        property_slug="termination-witness",
        property_id="P-02",
        tier="ratified",
        severity="fatal",
        claim_class="defensible",
        ratified_by="PROPERTY-CATALOG-SPEC §0.4 RATIFIED (DEC-05)",
        precedent="termination-witness/negative-03",
        note=(
            "Distinct ID per DEC-05 D4's granularity rule: a diagnostically distinct "
            "failure gets its own ID, never an overloaded one."
        ),
    ),
    ConditionEntry(
        id="read-key-never-written-on-path",
        property_slug="dataflow-completeness",
        property_id="P-04",
        tier="ratified",
        severity="fatal",
        claim_class="defensible-a",
        ratified_by="PROPERTY-CATALOG-SPEC §0.4 RATIFIED (DEC-05)",
        precedent="dataflow-completeness/negative-01..03; mixed/02/04/05/08",
    ),
    ConditionEntry(
        id="unprotected-effect-in-cycle",
        property_slug="effect-safety",
        property_id="P-06",
        tier="ratified",
        severity="error",
        claim_class="defensible-a",
        ratified_by="PROPERTY-CATALOG-SPEC §0.4 RATIFIED (DEC-05)",
        precedent="effect-safety/negative-02",
    ),
    ConditionEntry(
        id="unprotected-effect-in-retry-region",
        property_slug="effect-safety",
        property_id="P-06",
        tier="ratified",
        severity="error",
        claim_class="defensible-a",
        ratified_by="PROPERTY-CATALOG-SPEC §0.4 RATIFIED (DEC-05)",
        precedent="effect-safety/negative-01; mixed/01/06/09",
    ),
    ConditionEntry(
        id="irreversible-with-keyless-idempotent",
        property_slug="effect-safety",
        property_id="P-06",
        tier="ratified",
        severity="fatal",
        claim_class="defensible-a",
        ratified_by="PROPERTY-CATALOG-SPEC §0.4 RATIFIED (DEC-05)",
        precedent="effect-safety/negative-03",
        note="The D-012 forbidden combination; FATAL and cycle-independent.",
    ),
    ConditionEntry(
        id="deterministic-llm-seed-unpinned",
        property_slug="determinism-replay",
        property_id="P-08",
        tier="ratified",
        severity="warning",
        claim_class="heuristic",
        ratified_by="PROPERTY-CATALOG-SPEC §0.4 RATIFIED (DEC-05)",
        precedent="determinism-replay/negative-01; mixed/03",
        note=(
            "Promotable to a gate failure under --gebra-strict; promotion changes the gate, "
            "never the record (§0.2)."
        ),
    ),
    ConditionEntry(
        id="deterministic-llm-temperature-unpinned",
        property_slug="determinism-replay",
        property_id="P-08",
        tier="ratified",
        severity="warning",
        claim_class="heuristic",
        ratified_by="PROPERTY-CATALOG-SPEC §0.4 RATIFIED (DEC-05)",
        precedent="determinism-replay/negative-02 (schema v2.1, DEC-05 D5)",
    ),
    # ── RESERVED — "held for their properties … MUST NOT be reused for anything else" ──
    ConditionEntry(
        id="reentrant-node-neither-pure-nor-idempotent",
        property_slug="retry-coherence",
        property_id="P-07",
        tier="reserved",
        precedent="retry-coherence/negative-01; mixed/01/09",
    ),
    ConditionEntry(
        id="idempotency-key-not-in-declared-reads",
        property_slug="retry-coherence",
        property_id="P-07",
        tier="reserved",
        precedent="retry-coherence/negative-02; mixed/06",
    ),
    ConditionEntry(
        id="concurrent-writers-without-reducer",
        property_slug="parallel-safety",
        property_id="P-09",
        tier="reserved",
        precedent="parallel-safety/negative-01; mixed/03/07",
    ),
    ConditionEntry(
        id="send-fanout-writer-without-reducer",
        property_slug="parallel-safety",
        property_id="P-09",
        tier="reserved",
        precedent="parallel-safety/negative-02",
    ),
    ConditionEntry(
        id="fanout-retry-duplicate-accumulation",
        property_slug="parallel-safety",
        property_id="P-09",
        tier="reserved",
        precedent="mixed/09",
    ),
    ConditionEntry(
        id="read-key-removed",
        property_slug="evolution-safety",
        property_id="P-12",
        tier="reserved",
        precedent="evolution-safety/negative-01",
        note="Breaking class: read-key removal/retype. P-12 IDs exist for breaking classes "
        "only — a safe classification is a pass carrying a structured diff witness.",
    ),
    ConditionEntry(
        id="termination-witness-removed",
        property_slug="evolution-safety",
        property_id="P-12",
        tier="reserved",
        precedent="evolution-safety/negative-02; mixed/05",
        note="Breaking class: witness removal.",
    ),
    ConditionEntry(
        id="sole-writer-severed",
        property_slug="evolution-safety",
        property_id="P-12",
        tier="reserved",
        precedent="evolution-safety/negative-03; mixed/05",
        note="Fourth breaking class, DEC-05 D8. The effect-class-escalation breaking class "
        "has no corpus string yet; its ID is assigned by the §P-12 merge.",
    ),
    # ── PROPOSED — filed 2026-07-18 at the §P-01 merge, per §P-01.7 open item 7 ──
    ConditionEntry(
        id="orphan-node",
        property_slug="graph-well-formed",
        property_id="P-01",
        tier="proposed",
        severity="fatal",
        claim_class="defensible",
        ratified_by="DEC-11 (walkthrough #2, 2026-07-18)",
        precedent=None,
        note=(
            "Filed PROPOSED, ratified by name in DEC-11 once the orphan reading it waited "
            "on was fixed (Reading A, §P-01.3) — §0.4 says of this entry 'now emittable'. "
            "No corpus precedent yet: the condition-(iii) negative fixture is DEC-16 "
            "gap-fixture work (card TE-14) — the DEC-17 reconciliation pass landed "
            "without it (rerouted at the DEC-26 marker lift)."
        ),
    ),
    ConditionEntry(
        id="edge-target-undefined",
        property_slug="graph-well-formed",
        property_id="P-01",
        tier="proposed",
        severity="fatal",
        claim_class="defensible",
        ratified_by="DEC-12 (edge-target-undefined ratification, 2026-07-31)",
        precedent="mixed/04 (co-failure; expected block revised by the same record)",
        note=(
            "Ratified by its own §0.4 addendum, filed per the PD-007 (VAL-D1) ruling: "
            "DEC-12 landed in the vault's R-05 decisions (commit 9093972) and the §0.4 "
            "table was edited in the same commit, so the vendored spec this table mirrors "
            "now reads RATIFIED/emittable. Scope is condition (iv) for unresolved `entry` "
            "ids, `finish` ids, edge `from` fields, and normal/`send` edge `to` fields; "
            "§1.4 Step 1 emits on an unresolved reference and inserts nothing (no phantom "
            "auto-vivification), with the F_iv leading ordering key keeping "
            "resolvable-anchor findings ahead of unresolved-source ones."
        ),
    ),
)

#: The registry keyed by ID — the lookup surface. Read-only: the set of names is closed, and
#: adding one at runtime would be the local patch §0.4 forbids.
CONDITION_REGISTRY: Final[Mapping[ConditionId, ConditionEntry]] = MappingProxyType(
    {entry.id: entry for entry in _ENTRIES}
)

#: The same table keyed by plain ``str``, for asking about a string that may not be a member
#: at all — which is the whole point of the guards below. Private because the *public*
#: question "is this a condition ID" is :func:`is_registered`'s to answer.
_BY_STRING: Final[Mapping[str, ConditionEntry]] = MappingProxyType(
    {entry.id: entry for entry in _ENTRIES}
)

#: Every registered ID, in §0.4 table order.
CONDITION_IDS: Final[tuple[ConditionId, ...]] = tuple(CONDITION_REGISTRY)

#: The RATIFIED tier — the wedge-five conditions frozen with the spec.
RATIFIED_CONDITION_IDS: Final[tuple[ConditionId, ...]] = tuple(
    entry.id for entry in _ENTRIES if entry.tier == "ratified"
)

#: The RESERVED tier — held for P-07/P-09/P-12, ratifying at their section merges.
RESERVED_CONDITION_IDS: Final[tuple[ConditionId, ...]] = tuple(
    entry.id for entry in _ENTRIES if entry.tier == "reserved"
)

#: The PROPOSED tier — names filed 2026-07-18, ratified one dated record at a time.
#: Membership here does not answer emittability, and neither does absence from it: the tier is
#: where a name was filed, and ``orphan-node`` is a member that DEC-11 has since ratified. Ask
#: :data:`EMITTABLE_CONDITION_IDS` or :func:`is_emittable`.
PROPOSED_CONDITION_IDS: Final[tuple[ConditionId, ...]] = tuple(
    entry.id for entry in _ENTRIES if entry.tier == "proposed"
)

#: The IDs a validator may emit today — the RATIFIED tier plus the two record-ratified
#: PROPOSED-tier entries: DEC-11's ``orphan-node`` and DEC-12's ``edge-target-undefined``.
EMITTABLE_CONDITION_IDS: Final[tuple[ConditionId, ...]] = tuple(
    entry.id for entry in _ENTRIES if entry.emittable
)

#: Strings that are in the vendored corpus and **deliberately not** in the registry: §0.4
#: holds P-03's three back, because DEC-05 D6 marks the P-03 ``args_schema`` fixture shapes
#: forward-looking pending the R-06 IR field, so "these strings enter the registry with
#: §P-03, not before". Listed here so the boundary is visible and testable — being named
#: here registers nothing.
#:
#: For the harness (D-10): four fixtures carry these strings and therefore do not validate
#: into the envelope — ``signature-soundness/negative-01/-02/-03`` and ``mixed/07``, whose
#: primary is ``write-key-not-in-state-schema``. That is the faithful outcome of a frozen
#: §0.3 ``ConditionId`` defined as "a member of the §0.4 registry", and it belongs in the
#: fidelity matrix with this citation — never as a fixture edit (WA-04) and never by
#: reopening the type.
UNREGISTERED_CORPUS_STRINGS: Final[frozenset[str]] = frozenset(
    {
        "read-key-not-in-state-schema",
        "write-key-not-in-state-schema",
        "args-schema-type-mismatch",
    }
)


def _check_registry_is_closed() -> None:
    """The two spellings of the closed set agree: the Literal's members and the table's rows.

    mypy already refuses a table row whose ``id`` the Literal does not know. This catches the
    other direction — a Literal member with no row, which would otherwise surface as a
    ``KeyError`` from :func:`condition` at the moment a validator needed it.
    """
    declared = frozenset(get_args(ConditionId))
    tabled = frozenset(CONDITION_REGISTRY)
    if declared != tabled:
        raise ConditionRegistryError(
            "the §0.4 registry and the ConditionId Literal disagree: "
            f"only in the Literal {sorted(declared - tabled)}, only in the table "
            f"{sorted(tabled - declared)}"
        )


_check_registry_is_closed()


# ── Lookups ──────────────────────────────────────────────────────────────────────────────


def is_registered(condition_id: str) -> bool:
    """Whether ``condition_id`` is a member of the §0.4 registry, in any tier."""
    return condition_id in _BY_STRING


def is_emittable(condition_id: str) -> bool:
    """Whether a validator may emit ``condition_id`` today.

    False for an unregistered string and for a registered name no dated decision record has
    ratified yet — the two are distinguished by :func:`condition` and by the two error types.
    """
    entry = _BY_STRING.get(condition_id)
    return entry is not None and entry.emittable


def condition(condition_id: str) -> ConditionEntry:
    """The registry entry for ``condition_id``.

    Raises:
        UnregisteredConditionError: if the string is not in the §0.4 registry.
    """
    entry = _BY_STRING.get(condition_id)
    if entry is None:
        raise UnregisteredConditionError(
            f"{condition_id!r} is not a member of the PROPERTY-CATALOG-SPEC §0.4 registry. "
            "The registry is closed: a new ID is a spec addendum (a dated decision record "
            "plus an edit to the §0.4 table), never a local patch."
        )
    return entry


def emittable_condition(condition_id: str) -> ConditionEntry:
    """The registry entry for ``condition_id``, refusing anything not emittable.

    This is the check every emission goes through.

    Raises:
        UnregisteredConditionError: if the string is not in the §0.4 registry.
        NonEmittableConditionError: if it is registered but not yet ratified for emission.
    """
    entry = condition(condition_id)
    if not entry.emittable:
        raise NonEmittableConditionError(
            f"{entry.id!r} is registered in the §0.4 {entry.tier.upper()} tier but is not "
            "emittable: no dated decision record has ratified it. A report may record the "
            "name; a validator may not emit it."
        )
    return entry


def property_for_condition(condition_id: str) -> PropertySlug:
    """The catalog slug §0.4 holds ``condition_id`` for.

    Raises:
        UnregisteredConditionError: if the string is not in the §0.4 registry.
    """
    return condition(condition_id).property_slug


def conditions_for(property_slug: PropertySlug) -> tuple[ConditionEntry, ...]:
    """Every registered condition held for ``property_slug``, in §0.4 table order.

    The property registry (:mod:`gebra.verify.registry`) reads its condition lists from here
    rather than restating them, so the two tables cannot disagree about who owns a name.
    """
    return tuple(entry for entry in _ENTRIES if entry.property_slug == property_slug)


# ── Emission: the one surface a validator builds findings through ────────────────────────


FailureT = TypeVar("FailureT", bound=Failure)


def _pinned(entry: ConditionEntry) -> tuple[Severity, ClaimClass]:
    """The §0.4-pinned grades of an emittable entry, narrowed for the constructors."""
    if entry.severity is None or entry.claim_class is None:  # pragma: no cover - invariant
        raise ConditionRegistryError(f"{entry.id!r} is emittable but pins no severity/claim class")
    return entry.severity, entry.claim_class


def _check_advisory_carriage(property_slug: PropertySlug, advisories: object) -> None:
    """Refuse a self-referential advisory on ``property_slug``'s own report (§0.3).

    Only the carriage rule is checked; whether the value is an advisory at all is the model's
    business, so a non-``Advisory`` member falls through to pydantic's own error.
    """
    if not isinstance(advisories, (tuple, list)):
        return
    offenders = [
        item.property_condition
        for item in advisories
        if isinstance(item, Advisory) and item.property == property_slug
    ]
    if offenders:
        raise AdvisoryCarriageError(
            f"{property_slug!r} may not ride its own findings ({', '.join(offenders)}) on its "
            "own report as advisories: §0.3 carries cross-property WARNING-class side findings "
            "there, and a same-property finding rides `co_failures`."
        )


def _owned(property_slug: PropertySlug, condition_id: str) -> ConditionEntry:
    """Resolve ``condition_id``, refusing a name another property holds."""
    entry = emittable_condition(condition_id)
    if entry.property_slug != property_slug:
        raise ConditionOwnershipError(
            f"{entry.id!r} is held for {entry.property_slug!r} ({entry.property_id}) in the "
            f"§0.4 registry; {property_slug!r} may not emit it. Condition IDs are never "
            "reused across properties."
        )
    return entry


@overload
def emit_failure(
    property_slug: PropertySlug,
    condition_id: str,
    location: AnyLocation,
    *,
    model: type[FailureT],
    **fields: Any,
) -> FailureT: ...


@overload
def emit_failure(
    property_slug: PropertySlug, condition_id: str, location: AnyLocation, **fields: Any
) -> Failure: ...


def emit_failure(
    property_slug: PropertySlug,
    condition_id: str,
    location: AnyLocation,
    *,
    model: type[Failure] = Failure,
    **fields: Any,
) -> Failure:
    """Build the primary :class:`~gebra.verify.report.Failure` for a §0.4 condition.

    ``severity`` and ``claim_class`` are read off the registry, never passed in: §0.4 pins one
    grade per condition, and a validator that restated them could disagree with the catalog
    about its own finding. Everything else a section's contract adds — ``remediation``,
    ``co_failures``, ``advisories``, ``subsumed_by``, and a subtype's own members — passes
    through ``fields``; ``model`` selects a concrete subtype such as
    :class:`~gebra.verify.report.P04Failure`.

    One packaging rule is enforced here rather than left to review: an ``advisories`` entry
    from the emitting property itself is refused. §0.3 carries **cross-property** WARNING-class
    side findings there, and same-property findings ride ``co_failures`` — they are "never
    dropped and never re-packaged as self-referential advisories".

    Args:
        property_slug: The property making the finding. Checked against the registry: a
            property may not emit a name held for another.
        condition_id: A §0.4 registry member that has been ratified for emission.
        location: The structural anchor, already in report-side spelling (§0.3 sentinels).
        model: The failure class to build; defaults to the base :class:`Failure`.
        **fields: Further members of ``model``.

    Raises:
        UnregisteredConditionError: if ``condition_id`` is not in the §0.4 registry.
        NonEmittableConditionError: if it is registered but not ratified for emission.
        ConditionOwnershipError: if another property holds it.
        AdvisoryCarriageError: if an advisory rides its own property's report.
        pydantic.ValidationError: if the remaining fields do not satisfy ``model``.
    """
    entry = _owned(property_slug, condition_id)
    severity, claim_class = _pinned(entry)
    _check_advisory_carriage(property_slug, fields.get("advisories"))
    return model(
        property_condition=entry.id,
        location=location,
        severity=severity,
        claim_class=claim_class,
        **fields,
    )


def emit_co_failure(
    property_slug: PropertySlug,
    condition_id: str,
    location: AnyLocation,
    *,
    subsumed_by: PropertyId | None = None,
    note: str | None = None,
) -> CoFailure:
    """Build a :class:`~gebra.verify.report.CoFailure` for a §0.4 condition.

    ``property``, ``severity`` and ``claim_class`` all come off the registry (§0.1: every
    record in the envelope classifies its own claim, not only the primary). ``subsumed_by``
    names the property that owns the root cause when one does (DEC-05 D2).

    Raises:
        UnregisteredConditionError: if ``condition_id`` is not in the §0.4 registry.
        NonEmittableConditionError: if it is registered but not ratified for emission.
        ConditionOwnershipError: if another property holds it.
    """
    entry = _owned(property_slug, condition_id)
    severity, claim_class = _pinned(entry)
    return CoFailure(
        property=entry.property_slug,
        property_condition=entry.id,
        location=location,
        severity=severity,
        claim_class=claim_class,
        subsumed_by=subsumed_by,
        note=note,
    )


def emit_advisory(
    property_slug: PropertySlug, condition_id: str, location: AnyLocation
) -> Advisory:
    """Build a cross-property :class:`~gebra.verify.report.Advisory` for a §0.4 condition.

    §0.3 admits only WARNING-class side findings as advisories — an ERROR- or FATAL-grade
    finding of its own is that property's report to make — so a condition §0.4 grades above
    WARNING is refused here rather than silently downgraded.

    Raises:
        UnregisteredConditionError: if ``condition_id`` is not in the §0.4 registry.
        NonEmittableConditionError: if it is registered but not ratified for emission.
        ConditionOwnershipError: if another property holds it.
        ConditionRegistryError: if §0.4 grades the condition above WARNING.
    """
    entry = _owned(property_slug, condition_id)
    severity, claim_class = _pinned(entry)
    if severity != "warning":
        raise ConditionRegistryError(
            f"{entry.id!r} is graded {severity!r} in the §0.4 registry; §0.3 carries only "
            "WARNING-class side findings as advisories."
        )
    return Advisory(
        property=entry.property_slug,
        property_condition=entry.id,
        severity=severity,
        claim_class=claim_class,
        location=location,
    )
