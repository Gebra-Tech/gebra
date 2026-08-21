"""The thirteen-slug property registry — one table, and the dispatch it drives.

Brief D-09 Deliverable 2 asks for exactly one of these: "slug → callable → claim class →
severity → derivation reference, generated from one table so [the catalog] and the code
cannot drift silently". :data:`PROPERTY_REGISTRY` is that table. It restates no condition
IDs: :func:`gebra.verify.conditions.conditions_for` reads those off the §0.4 registry, so the
two tables cannot disagree about which property holds a name.

**The eight non-wedge properties are not silent passes.** Phase-0 ships the wedge five
(P-01, P-02, P-04, P-06, P-08); SOW §8 puts the other eight out of scope, and the Phase-0
plan's scope statement makes the registry carry them as "structured not-implemented markers,
never silent passes". Brief D-09's Definition of Done spells out the shape: "a distinct
structured status — neither pass nor fail — with a human message", "never a silent pass,
never an unstructured exception".
:class:`NotImplementedMarker` is that status, and it is deliberately **not** a
:class:`~gebra.verify.report.PropertyReport`: §0.3 fixes ``result`` to ``"pass" | "fail"``
and the envelope is frozen, so a third verdict cannot be smuggled into it. Dispatch returns
``PropertyReport | NotImplementedMarker`` instead, and a consumer that forgets the second
member gets a type error rather than a report it can mistake for a verdict.

Two statuses, because the two absences mean different things: ``deferred-to-phase-1`` is the
scope statement for the eight (D-09 in-scope item 7), and ``not-yet-implemented`` is the
build-order statement for a wedge property whose validator has not been wired yet. Neither
is a pass.

**Wiring a validator is a registration, not a table edit.** The table is frozen data; the
implementations live beside it in a mapping each wedge validator adds itself to. Registration
is refused for the eight non-wedge slugs, so a Phase-1 validator cannot appear without an
edit here that says so.

Nothing in this module imports langgraph, executes a workflow node, or opens a network
connection (WA-07). Dispatch calls whatever a validator registered — validators are hermetic
functions over serialized IR (D-09: "Gebra never executes workflows").
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, Literal, Protocol, TypeAlias

from gebra.ir import WorkflowIR
from gebra.verify.base import ClaimClass, PropertyId, PropertySlug, ReportModel, Severity
from gebra.verify.report import PropertyReport

__all__ = [
    "NON_WEDGE_SLUGS",
    "PROPERTY_REGISTRY",
    "PROPERTY_SLUGS",
    "WEDGE_SLUGS",
    "NotImplementedMarker",
    "NotImplementedStatus",
    "PropertyArity",
    "PropertyEntry",
    "PropertyRegistryError",
    "PropertyScope",
    "Validator",
    "is_implemented",
    "not_implemented",
    "property_entry",
    "register_validator",
    "run_property",
    "unregister_validator",
    "validator_for",
]


#: Whether a property is in the Phase-0 wedge or out of scope for it (SOW §1/§8).
PropertyScope: TypeAlias = Literal["phase-0-wedge", "deferred-to-phase-1"]

#: How many IR snapshots a validator reads. P-12 alone is a two-snapshot classifier
#: (``validate(ir_before, ir_after)``, brief D-09 in-scope item 5).
PropertyArity: TypeAlias = Literal["one-snapshot", "two-snapshot"]

#: Why no verdict was produced. ``deferred-to-phase-1`` is D-09's own vocabulary for its
#: stub discipline; ``not-yet-implemented`` is the wedge property whose card has not landed.
NotImplementedStatus: TypeAlias = Literal["deferred-to-phase-1", "not-yet-implemented"]


class PropertyRegistryError(ValueError):
    """A property slug was used in a way the registry does not license."""


@dataclass(frozen=True)
class PropertyEntry:
    """One row of the property registry.

    Attributes:
        slug: The catalog slug (Verification-Properties §1.3), as serialized.
        property_id: The ``P-nn`` id the envelope's ``subsumed_by`` carries.
        claim_classes: Every §0.1 class this property's findings can carry, in the order the
            catalog states them. More than one where the catalog splits a property across
            sub-checks (P-05, P-09) — the per-finding class is always the §0.4 registry's,
            never this field's.
        severities: Every §0.2 grade this property's findings can carry, on the same terms.
        derivation: What the property is derived *from*, as the catalog states it — the
            derivation reference D-09 Deliverable 2 asks this table to carry.
        spec_ref: Where its contract lives.
        scope: Phase-0 wedge, or out of scope for Phase-0 (SOW §8).
        arity: How many IR snapshots the validator reads.
    """

    slug: PropertySlug
    property_id: PropertyId
    claim_classes: tuple[ClaimClass, ...]
    severities: tuple[Severity, ...]
    derivation: str
    spec_ref: str
    scope: PropertyScope
    arity: PropertyArity = "one-snapshot"

    @property
    def wedge(self) -> bool:
        """Whether this property is one of the Phase-0 wedge five."""
        return self.scope == "phase-0-wedge"


#: The registry, in catalog order (P-01…P-13). Claim classes, severities and derivations are
#: the catalog's own — for the wedge five from their drafted sections, for the other eight
#: from the catalog pointers PROPERTY-CATALOG-SPEC carries at each stub.
_ENTRIES: Final[tuple[PropertyEntry, ...]] = (
    PropertyEntry(
        slug="graph-well-formed",
        property_id="P-01",
        claim_classes=("defensible",),
        severities=("fatal",),
        derivation=(
            "Pure graph theory — forward reachability, sink detection and reference "
            "resolution over the sentinel-augmented digraph G* (§1.1). No axiom is invoked, "
            "so no Skavantzos & Link citation is owed (D-019); the direct ancestor is the "
            "C-S3/C-S4 structural check of Formal-Model §7.1.1, lifted to the cyclic agent "
            "graph admitted by D-016."
        ),
        spec_ref="PROPERTY-CATALOG-SPEC §1",
        scope="phase-0-wedge",
    ),
    PropertyEntry(
        slug="termination-witness",
        property_id="P-02",
        claim_classes=("defensible",),
        severities=("fatal",),
        derivation=(
            "Decision-derived (§2.1): D-016 admits cyclic sequence graphs, inverting the "
            "DAG-only rule of Formal-Model §5.3 into a per-simple-cycle witness obligation. "
            "Witness semantics — the three forms, the guard grammar, the discharge "
            "predicates, the coverage lemma — are TERMINATION-WITNESS-SPEC §§2–5's. The "
            "claim is witness *presence*; semantic termination is never claimed."
        ),
        spec_ref="PROPERTY-CATALOG-SPEC §2; TERMINATION-WITNESS-SPEC",
        scope="phase-0-wedge",
    ),
    PropertyEntry(
        slug="signature-soundness",
        property_id="P-03",
        claim_classes=("defensible-a",),
        severities=("error",),
        derivation="D-010 (declared reads/writes and args_schema consistency).",
        spec_ref="PROPERTY-CATALOG-SPEC §P-03 (stub; Verification-Properties §2 authoritative)",
        scope="deferred-to-phase-1",
    ),
    PropertyEntry(
        slug="dataflow-completeness",
        property_id="P-04",
        claim_classes=("defensible-a",),
        severities=("fatal",),
        derivation=(
            "Axiom T (transitivity), Skavantzos & Link (2023), PVLDB 16(11):3031–3043, "
            "cited directly per D-019 — the transitive closure of write-before-read "
            "dependencies, i.e. the Sequence Dependency Rule of Formal-Model §5.2 lifted to "
            "START-paths (§4.1)."
        ),
        spec_ref="PROPERTY-CATALOG-SPEC §4",
        scope="phase-0-wedge",
    ),
    PropertyEntry(
        slug="guard-exhaustiveness",
        property_id="P-05",
        claim_classes=("defensible", "heuristic"),
        severities=("error", "warning"),
        derivation=(
            "Pure graph/codomain analysis — DEFENSIBLE over a declared path_map, HEURISTIC "
            "in the fallback where no codomain is declared."
        ),
        spec_ref="PROPERTY-CATALOG-SPEC §P-05 (stub; Verification-Properties §2 authoritative)",
        scope="deferred-to-phase-1",
    ),
    PropertyEntry(
        slug="effect-safety",
        property_id="P-06",
        claim_classes=("defensible-a",),
        severities=("fatal", "error"),
        derivation=(
            "Decision-derived (§6.1): D-011 supplies the effect-tag vocabulary and D-012 the "
            "idempotency forms plus the forbidden irreversible + keyless-idempotent "
            "combination, evaluated over the cyclic structure D-016 admits. Cycle regions "
            "are Tarjan (1972) SCCs; the two protection mechanisms trace to Garcia-Molina & "
            "Salem (1987) on sagas and Helland (2012) on keyed idempotence."
        ),
        spec_ref="PROPERTY-CATALOG-SPEC §6",
        scope="phase-0-wedge",
    ),
    PropertyEntry(
        slug="retry-coherence",
        property_id="P-07",
        claim_classes=("defensible-a",),
        severities=("error",),
        derivation="D-012 (retry safety: pure or idempotent, with keys among declared reads).",
        spec_ref="PROPERTY-CATALOG-SPEC §P-07 (stub; Verification-Properties §2 authoritative)",
        scope="deferred-to-phase-1",
    ),
    PropertyEntry(
        slug="determinism-replay",
        property_id="P-08",
        claim_classes=("heuristic",),
        severities=("warning",),
        derivation=(
            "Decisional, not axiom-derived — stated explicitly per D-019 (§8.1): D-013 fixes "
            "the @DETERMINISTIC contract (seed, memoisation and replay as licensed uses, "
            "divergence logged and never silently accepted), and P-08 checks that contract's "
            "*coherence* only. Determinism of an external provider is a claim about the "
            "world, not the graph; DEC-05 D5 makes both halves of the pinning contract "
            "IR-decidable, and Appendix B is non-normative support."
        ),
        spec_ref="PROPERTY-CATALOG-SPEC §8 + Appendix B",
        scope="phase-0-wedge",
    ),
    PropertyEntry(
        slug="parallel-safety",
        property_id="P-09",
        claim_classes=("defensible", "heuristic"),
        severities=("error", "warning"),
        derivation=(
            "Axiom A (Skavantzos & Link 2023) + D-011 — DEFENSIBLE for reducer conflicts, "
            "HEURISTIC for declared-tag effect commutativity; send-template severity per "
            "DEC-05."
        ),
        spec_ref="PROPERTY-CATALOG-SPEC §P-09 (stub; Verification-Properties §2 authoritative)",
        scope="deferred-to-phase-1",
    ),
    PropertyEntry(
        slug="subgraph-consistency",
        property_id="P-10",
        claim_classes=("defensible-a",),
        severities=("error",),
        derivation="Axiom W (Skavantzos & Link 2023) + layer homomorphism (Formal-Model).",
        spec_ref="PROPERTY-CATALOG-SPEC §P-10 (stub; Verification-Properties §2 authoritative)",
        scope="deferred-to-phase-1",
    ),
    PropertyEntry(
        slug="join-key-soundness",
        property_id="P-11",
        claim_classes=("defensible-a",),
        severities=("error", "warning"),
        derivation=(
            "Axiom P (Skavantzos & Link 2023); fibre-product semantics per Formal-Model §6."
        ),
        spec_ref="PROPERTY-CATALOG-SPEC §P-11 (stub; Verification-Properties §2 authoritative)",
        scope="deferred-to-phase-1",
    ),
    PropertyEntry(
        slug="evolution-safety",
        property_id="P-12",
        claim_classes=("defensible",),
        severities=("error",),
        derivation=(
            "Axioms E + A (Skavantzos & Link 2023); the fourth breaking class per DEC-05 D8. "
            "Condition IDs exist for breaking classes only — a safe classification is a pass "
            "carrying a structured diff witness."
        ),
        spec_ref="PROPERTY-CATALOG-SPEC §P-12 (stub; Verification-Properties §2 authoritative)",
        scope="deferred-to-phase-1",
        arity="two-snapshot",
    ),
    PropertyEntry(
        slug="interrupt-gate-coverage",
        property_id="P-13",
        claim_classes=("defensible",),
        severities=("error",),
        derivation=(
            "Dominator analysis (Cooper–Harvey–Kennedy) — pure graph theory, no axiom; "
            "D-011 supplies the gated effect tags. ERROR when the policy pack is enabled."
        ),
        spec_ref="PROPERTY-CATALOG-SPEC §P-13 (stub; Verification-Properties §2 authoritative)",
        scope="deferred-to-phase-1",
    ),
)

#: The registry keyed by slug. Read-only: the thirteen are the catalog's, and adding a
#: fourteenth is a catalog change, not a runtime one.
PROPERTY_REGISTRY: Final[Mapping[PropertySlug, PropertyEntry]] = MappingProxyType(
    {entry.slug: entry for entry in _ENTRIES}
)

#: The thirteen slugs, in catalog order.
PROPERTY_SLUGS: Final[tuple[PropertySlug, ...]] = tuple(PROPERTY_REGISTRY)

#: The Phase-0 wedge five (SOW §1).
WEDGE_SLUGS: Final[tuple[PropertySlug, ...]] = tuple(
    entry.slug for entry in _ENTRIES if entry.wedge
)

#: The eight properties out of Phase-0 scope (SOW §8) — markers, never silent passes.
NON_WEDGE_SLUGS: Final[tuple[PropertySlug, ...]] = tuple(
    entry.slug for entry in _ENTRIES if not entry.wedge
)

_BY_STRING: Final[Mapping[str, PropertyEntry]] = MappingProxyType(
    {entry.slug: entry for entry in _ENTRIES}
)


class NotImplementedMarker(ReportModel):
    """No verdict was produced, and why — neither a pass nor a fail.

    D-09's stub discipline, in the shape its Definition of Done fixes: a distinct structured
    status carrying a human-readable pointer, so a consumer renders "not checked" rather than
    inheriting a silent pass. ``detail`` is display-only prose, like ``Failure.remediation``;
    everything a consumer branches on is ``status``, ``property`` and ``property_id``.
    """

    kind: Literal["not-implemented"]
    property: PropertySlug
    property_id: PropertyId
    status: NotImplementedStatus
    #: Display-only prose; never parsed.
    detail: str


class Validator(Protocol):
    """What a registered wedge validator is: serialized IR in, one report out.

    Hermetic by construction (D-09, D-018): the argument is a validated
    :class:`~gebra.ir.WorkflowIR`, never a langgraph object, and a validator neither executes
    a node nor calls a model. P-12's two-snapshot classifier does not fit this shape and is
    not registrable here — it is ``deferred-to-phase-1`` in the table above.
    """

    def __call__(self, ir: WorkflowIR, /) -> PropertyReport: ...


_IMPLEMENTATIONS: Final[dict[PropertySlug, Validator]] = {}


# ── Lookups over the table ───────────────────────────────────────────────────────────────


def property_entry(property_slug: str) -> PropertyEntry:
    """The registry entry for ``property_slug``.

    Raises:
        PropertyRegistryError: if the string is not one of the thirteen catalog slugs.
    """
    entry = _BY_STRING.get(property_slug)
    if entry is None:
        raise PropertyRegistryError(
            f"{property_slug!r} is not one of the thirteen catalog slugs "
            f"(Verification-Properties §1.3): {', '.join(PROPERTY_SLUGS)}."
        )
    return entry


# ── Dispatch ─────────────────────────────────────────────────────────────────────────────


def register_validator(property_slug: PropertySlug, implementation: Validator) -> None:
    """Wire ``implementation`` in as the validator for ``property_slug``.

    Refused for the eight properties the table marks ``deferred-to-phase-1``: SOW §8 puts
    them out of Phase-0 scope, and the registry is what says so, so one appearing at runtime
    would be a scope change nobody recorded.

    Raises:
        PropertyRegistryError: if the slug is unknown, is out of Phase-0 scope, or already
            has an implementation. Re-wiring is :func:`unregister_validator` first — silently
            replacing a validator is how two of them end up shipping.
    """
    entry = property_entry(property_slug)
    if not entry.wedge:
        raise PropertyRegistryError(
            f"{property_slug!r} ({entry.property_id}) is out of Phase-0 scope (SOW §8); the "
            "registry answers for it with a structured not-implemented marker. Registering "
            "an implementation means editing this table first."
        )
    if property_slug in _IMPLEMENTATIONS:
        raise PropertyRegistryError(
            f"{property_slug!r} already has a registered validator; unregister it first."
        )
    _IMPLEMENTATIONS[property_slug] = implementation


def unregister_validator(property_slug: PropertySlug) -> None:
    """Drop the registered validator for ``property_slug``, if any.

    For tests and for re-wiring; a shipped validator registers once, at import.
    """
    _IMPLEMENTATIONS.pop(property_slug, None)


def validator_for(property_slug: PropertySlug) -> Validator | None:
    """The registered validator for ``property_slug``, or ``None`` if none is wired yet."""
    property_entry(property_slug)
    return _IMPLEMENTATIONS.get(property_slug)


def is_implemented(property_slug: PropertySlug) -> bool:
    """Whether ``property_slug`` has a registered validator."""
    return validator_for(property_slug) is not None


def not_implemented(property_slug: PropertySlug) -> NotImplementedMarker:
    """The structured marker this registry answers with when no validator ran.

    The status distinguishes the two absences: a property SOW §8 puts out of Phase-0 scope
    is ``deferred-to-phase-1``; a wedge property whose validator has not been wired yet is
    ``not-yet-implemented``. Neither is a pass, and neither is a
    :class:`~gebra.verify.report.PropertyReport`.
    """
    entry = property_entry(property_slug)
    if entry.wedge:
        return NotImplementedMarker(
            kind="not-implemented",
            property=entry.slug,
            property_id=entry.property_id,
            status="not-yet-implemented",
            detail=(
                f"{entry.property_id} {entry.slug} is one of the Phase-0 wedge five, but no "
                f"validator is registered for it in this build. Its contract is "
                f"{entry.spec_ref}. No verdict was reached — this is not a pass."
            ),
        )
    return NotImplementedMarker(
        kind="not-implemented",
        property=entry.slug,
        property_id=entry.property_id,
        status="deferred-to-phase-1",
        detail=(
            f"{entry.property_id} {entry.slug} is outside the Phase-0 wedge (SOW §8) and has "
            f"no validator in this release; the catalog contract is {entry.spec_ref}. No "
            f"verdict was reached — this is not a pass."
        ),
    )


def run_property(
    property_slug: PropertySlug, ir: WorkflowIR
) -> PropertyReport | NotImplementedMarker:
    """Run the validator registered for ``property_slug`` over ``ir``.

    This is the registry-driven dispatch: the table decides what answers for a slug, and a
    slug with no validator answers with :func:`not_implemented` rather than with silence or a
    pass. Aggregating the thirteen answers into a run — the severity ladder, exit codes and
    strict promotion of §0.2 — is ``verify()``'s job, not this function's.

    Two things ``verify()`` should not inherit from here. Registration happens at import, so a
    wedge validator whose module was never imported dispatches to ``not-yet-implemented``: a
    marker is the honest answer to *this* call, but a run that silently checked four of the
    wedge five is a weakened gate, so the aggregation should require every
    :data:`WEDGE_SLUGS` member to be registered before deriving an exit code. And
    ``PropertyEntry.claim_classes``/``severities`` are property-level unions for display and
    documentation — the §0.2 input is always the per-record ``severity`` on the finding.

    Raises:
        PropertyRegistryError: if the slug is unknown, or if a registered validator returns a
            report for a different property.
    """
    entry = property_entry(property_slug)
    implementation = _IMPLEMENTATIONS.get(entry.slug)
    if implementation is None:
        return not_implemented(entry.slug)
    report = implementation(ir)
    if report.property != entry.slug:
        raise PropertyRegistryError(
            f"the validator registered for {entry.slug!r} returned a report for "
            f"{report.property!r}; one property, one report (§0.3)."
        )
    return report
