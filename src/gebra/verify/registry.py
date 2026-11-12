"""The thirteen-slug property registry — one table, and the dispatch it drives.

Brief D-09 Deliverable 2 asks for exactly one of these: "slug → callable → claim class →
severity → derivation reference, generated from one table so [the catalog] and the code
cannot drift silently". :data:`PROPERTY_REGISTRY` is that table. It restates no condition
IDs: :func:`gebra.verify.conditions.conditions_for` reads those off the §0.4 registry, so the
two tables cannot disagree about which property holds a name.

**Every row carries one of three scopes** — the vocabulary of DEC-35 §3.1, the Phase-1
catalog charter, with the deferred scope defined as DEC-42 §3.2 restated it
(PROPERTY-CATALOG-SPEC §0.6 item 1):

- ``phase-0-wedge`` — P-01, P-02, P-04, P-06 and P-08, the five SOW §1 put in Phase-0 scope.
- ``catalog`` — a property whose §P-nn section is ratified and whose validator ships. A row
  moves ``deferred-to-phase-1`` → ``catalog`` only in the build that registers its validator,
  and only once (i) its section is ratified and re-vendored, (ii) its reference fixtures are in
  the vendored corpus, and (iii) every condition ID the section ratifies is emittable with its
  Appendix C rule copy. No row carries it in this build.
- ``deferred-to-phase-1`` — a property for which no validator ships, whether or not its §P-nn
  section is ratified. Ratifying a section moves no row; only the build that registers the
  validator does. The token is read as "no validator in this release": its name is brief
  D-09's historical word for the stubs it deferred, kept verbatim on the wire, and no schedule
  is read from it (DEC-42 §3.3). SOW §8 is the reason the ``deferred-to-phase-1`` token exists:
  it put the eight non-wedge properties (P-03, P-05, P-07, P-09…P-13) out of Phase-0 scope.
  DEC-35 §3.1 moved that citation out of user-facing copy and into this docstring and the
  governance records; PD-072 §1 reads the acceptance checklist's C2 clause (3) — "citing
  SOW §8" — against this citation and its three siblings in the governance records
  (owner-re-signed, 2026-11-11).

The first two are the **shipped** scopes. "Not wedge" and "deferred" stopped being the same
fact the day the charter ruled, so every reader that means *not live* asks
:attr:`PropertyEntry.deferred` (or :func:`deferred_slugs`), never ``not wedge``.

**A property with no verdict is never a silent pass.** Brief D-09's Definition of Done spells
out the shape: "a distinct structured status — neither pass nor fail — with a human message",
"never a silent pass, never an unstructured exception". :class:`NotImplementedMarker` is that
status, and it is deliberately **not** a :class:`~gebra.verify.report.PropertyReport`: §0.3
fixes ``result`` to ``"pass" | "fail"`` and the envelope is frozen, so a third verdict cannot
be smuggled into it. Dispatch returns ``PropertyReport | NotImplementedMarker`` instead, and a
consumer that forgets the second member gets a type error rather than a report it can mistake
for a verdict.

Two statuses, because the two absences mean different things: ``deferred-to-phase-1`` is the
scope statement — no validator for the property in this release — and ``not-yet-implemented``
is the build-order statement for a shipped property whose validator is not wired into this
build. Neither is a pass. The wire token ``deferred-to-phase-1`` stays verbatim (renaming it is
a REPORT-FORMAT-SPEC §1.6 MAJOR); the copy beside it on every surface that renders a marker is
:data:`DEFERRED_READING`, the words DEC-42 §3.1 rules, plus :data:`NO_VERDICT`, the sentence
DEC-35 §3.1 keeps verbatim.

**Wiring a validator is a registration, not a table edit.** The table is frozen data; the
implementations live beside it in a mapping each shipped validator adds itself to.
Registration is refused for a ``deferred-to-phase-1`` row, so a validator cannot appear
without the edit here that moves its row to ``catalog``; and a run that finds a shipped row
with no registered validator is a ``dispatch`` tool error, never a thinner gate
(:func:`gebra.verify.verify`, REPORT-FORMAT-SPEC §1.4 rule 2 read over both shipped scopes).
A property that registers gates from its landing release like any other (DEC-35 §3.2):
nothing here, and nothing in ``verify()``, reads a release to decide whether it gates.

**Counts are derived here, never stated.** :func:`registry_counts` is the one place a property
count comes from (DEC-35 §3.5 (c)), read off the table and the registrations at call time, so a
landing that moves a row moves every count that reads it.

Nothing in this module imports langgraph, executes a workflow node, or opens a network
connection (WA-07). Dispatch calls whatever a validator registered — validators are hermetic
functions over serialized IR (D-09: "Gebra never executes workflows").
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, Literal, Protocol, TypeAlias, cast

from gebra.ir import WorkflowIR
from gebra.verify.base import ClaimClass, PropertyId, PropertySlug, ReportModel, Severity
from gebra.verify.report import PropertyReport

__all__ = [
    "DEFERRED_READING",
    "MARKER_REASONS",
    "NON_WEDGE_SLUGS",
    "NO_VERDICT",
    "PROPERTY_REGISTRY",
    "PROPERTY_SLUGS",
    "SHIPPED_SCOPES",
    "WEDGE_SLUGS",
    "NotImplementedMarker",
    "NotImplementedStatus",
    "PropertyArity",
    "PropertyEntry",
    "PropertyRegistryError",
    "PropertyScope",
    "RegistryCounts",
    "Validator",
    "deferred_slugs",
    "is_implemented",
    "not_implemented",
    "property_entry",
    "register_validator",
    "registry_counts",
    "run_property",
    "shipped_slugs",
    "unregister_validator",
    "validator_for",
]


#: Where a property stands in the catalog (DEC-35 §3.1, the deferred scope as DEC-42 §3.2
#: restated it; PROPERTY-CATALOG-SPEC §0.6 item 1): one of the Phase-0 wedge five, a property
#: whose ratified section's validator ships, or a property for which no validator ships,
#: whether or not its section is ratified.
PropertyScope: TypeAlias = Literal["phase-0-wedge", "catalog", "deferred-to-phase-1"]

#: The two scopes whose properties have a validator in this release. Registration accepts
#: either; a run that finds either with no registered validator is a ``dispatch`` tool error.
SHIPPED_SCOPES: Final[tuple[PropertyScope, ...]] = ("phase-0-wedge", "catalog")

#: How many IR snapshots a validator reads. P-12 alone is a two-snapshot classifier
#: (``validate(ir_before, ir_after)``, brief D-09 in-scope item 5).
PropertyArity: TypeAlias = Literal["one-snapshot", "two-snapshot"]

#: Why no verdict was produced. ``deferred-to-phase-1`` is D-09's historical word for its stub
#: discipline, kept verbatim on the wire and read since DEC-42 §3.3 as "no validator in this
#: release" — no schedule is read from it; ``not-yet-implemented`` is a shipped property whose
#: validator is not wired into this build.
NotImplementedStatus: TypeAlias = Literal["deferred-to-phase-1", "not-yet-implemented"]

#: What a ``deferred-to-phase-1`` marker says about its property, on every surface that renders
#: one — PROPERTY-CATALOG-SPEC §0.6 item 1's words, verbatim (DEC-42 §3.1). A marker with this
#: status answers only for a row its producing build holds deferred, so the words state a fact
#: of that build, true whenever the marker is read. A surface lays the words out as it needs;
#: it does not reword them.
DEFERRED_READING: Final = "has no validator in this release"

#: The sentence every marker surface keeps verbatim (DEC-35 §3.1; §0.6 item 1).
NO_VERDICT: Final = "No verdict was reached — this is not a pass."

#: Why a marker of each wire status answered where a report would have — the reason every
#: surface that renders a marker states beside its status (DEC-35 §3.1), written to follow
#: the property's name. One entry per :data:`NotImplementedStatus`, held in lockstep with it
#: by the registry's tests: a status a later landing admits (``not-enabled``,
#: ``two-snapshot-only``) cannot reach a surface without its entry here, and no surface falls
#: back to another status's words. The words for those two are already fixed —
#: PROPERTY-CATALOG-SPEC §0.6 items 6 and 7; the charter owns both statuses' copy and a
#: section's landing admits the token, never the words (DEC-35 §3.7, §4).
MARKER_REASONS: Final[Mapping[NotImplementedStatus, str]] = MappingProxyType(
    {
        "deferred-to-phase-1": DEFERRED_READING,
        "not-yet-implemented": (
            "has a validator in this release, but none is registered for it in this build"
        ),
    }
)


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
        spec_ref: Where the specifications state the property: for a shipped row, what its
            validator is written against; for a ``deferred-to-phase-1`` row, the property's
            catalog section, named with no statement of its standing (DEC-42 §3.4).
        scope: Where the property stands in the catalog (:data:`PropertyScope`).
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
        """Whether this property is one of the Phase-0 wedge five.

        A fact about Phase-0's scope, and nothing more: a ``catalog`` row is not wedge and is
        live all the same. A reader asking whether a property is *live* reads
        :attr:`deferred` instead.
        """
        return self.scope == "phase-0-wedge"

    @property
    def deferred(self) -> bool:
        """Whether no validator for this property ships in this release (``deferred-to-phase-1``).

        The one predicate every deferral reader keys on — the harness's deferral outcome, the
        corpus-green accounting, the plugin's refusal — so a property that lands is read as
        live everywhere at once (DEC-35 §3.5 (b)).
        """
        return self.scope == "deferred-to-phase-1"

    @property
    def shipped(self) -> bool:
        """Whether a validator for this property ships in this release (:data:`SHIPPED_SCOPES`)."""
        return self.scope in SHIPPED_SCOPES

    @property
    def reports_on_one_snapshot(self) -> bool:
        """Whether a run over one IR that reaches a verdict answers this property with a report.

        True for a shipped row whose validator reads one snapshot. A two-snapshot classifier
        (P-12) has nothing to classify in a run over one IR, so no such run ever answers it with
        a report: DEC-35 §3.6 rules the marker it answers with once its two-snapshot shape is
        registered, which is P-12's own landing — before that, a shipped two-snapshot row is a
        ``dispatch`` tool error (:func:`gebra.verify.verify`), and P-12's row is not shipped.
        """
        return self.shipped and self.arity == "one-snapshot"


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
        spec_ref="PROPERTY-CATALOG-SPEC §P-03",
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
        spec_ref="PROPERTY-CATALOG-SPEC §P-05",
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
        spec_ref="PROPERTY-CATALOG-SPEC §P-07",
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
        spec_ref="PROPERTY-CATALOG-SPEC §P-09",
        scope="deferred-to-phase-1",
    ),
    PropertyEntry(
        slug="subgraph-consistency",
        property_id="P-10",
        claim_classes=("defensible-a",),
        severities=("error",),
        derivation="Axiom W (Skavantzos & Link 2023) + layer homomorphism (Formal-Model).",
        spec_ref="PROPERTY-CATALOG-SPEC §P-10",
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
        spec_ref="PROPERTY-CATALOG-SPEC §P-11",
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
        spec_ref="PROPERTY-CATALOG-SPEC §P-12",
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
        spec_ref="PROPERTY-CATALOG-SPEC §P-13",
        scope="deferred-to-phase-1",
    ),
)

#: The one table every lookup reads, keyed by slug. Private and never written by this
#: package: the two read-only views below wrap this same dict, so the table has one source.
_TABLE: Final[dict[PropertySlug, PropertyEntry]] = {entry.slug: entry for entry in _ENTRIES}

#: The registry keyed by slug. Read-only: the thirteen are the catalog's, and adding a
#: fourteenth is a catalog change, not a runtime one.
PROPERTY_REGISTRY: Final[Mapping[PropertySlug, PropertyEntry]] = MappingProxyType(_TABLE)

#: The thirteen slugs, in catalog order.
PROPERTY_SLUGS: Final[tuple[PropertySlug, ...]] = tuple(PROPERTY_REGISTRY)

#: The Phase-0 wedge five (SOW §1).
WEDGE_SLUGS: Final[tuple[PropertySlug, ...]] = tuple(
    entry.slug for entry in _ENTRIES if entry.wedge
)

#: The eight properties outside the wedge five (SOW §8 put them out of Phase-0 scope). A fact
#: about Phase-0's scope, fixed with the table: a non-wedge property that lands stays in this
#: tuple and is live all the same. Which properties have no validator in this release is
#: :func:`deferred_slugs`' question, not this one's.
NON_WEDGE_SLUGS: Final[tuple[PropertySlug, ...]] = tuple(
    entry.slug for entry in _ENTRIES if not entry.wedge
)

#: :data:`PROPERTY_REGISTRY` for a lookup by an arbitrary string — the same table, typed for
#: the caller who has not yet established that the string is a slug.
_BY_STRING: Final[Mapping[str, PropertyEntry]] = MappingProxyType(
    cast("dict[str, PropertyEntry]", _TABLE)
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
    """What a registered validator is: serialized IR in, one report out.

    Hermetic by construction (D-09, D-018): the argument is a validated
    :class:`~gebra.ir.WorkflowIR`, never a langgraph object, and a validator neither executes
    a node nor calls a model. P-12's two-snapshot classifier does not fit this shape, and
    :func:`register_validator` refuses a two-snapshot row through it whatever the row's scope:
    the two-snapshot registration shape is P-12's own landing's to add (DEC-35 §3.6).
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


def deferred_slugs() -> tuple[PropertySlug, ...]:
    """The properties with no validator in this release, in catalog order.

    Every row whose scope is ``deferred-to-phase-1``, read off the table when called rather than
    frozen at import, so it is the same answer :attr:`PropertyEntry.deferred` gives slug by slug.
    """
    return tuple(slug for slug in PROPERTY_SLUGS if property_entry(slug).deferred)


def shipped_slugs() -> tuple[PropertySlug, ...]:
    """The properties whose validator ships in this release, in catalog order.

    Every row in a shipped scope (:data:`SHIPPED_SCOPES`), read off the table when called.
    """
    return tuple(slug for slug in PROPERTY_SLUGS if property_entry(slug).shipped)


@dataclass(frozen=True)
class RegistryCounts:
    """Every property count the registry derives — the one source a count is read from.

    DEC-35 §3.5 (c): counts derive from the registry, so a property's landing moves no literal.
    Each field is a count of table rows or registrations, taken when :func:`registry_counts` is
    called; nothing here is stated, so nothing here can go stale.

    Attributes:
        total: Rows in the table — the catalog's size.
        wedge: Rows in scope ``phase-0-wedge``.
        catalog: Rows in scope ``catalog``.
        deferred: Rows in scope ``deferred-to-phase-1`` — each answered with a marker.
        registered: Rows with a validator registered in this build.
        reported: How many properties a run over one IR that reaches a verdict answers with a
            report: the shipped rows whose validator reads one snapshot
            (:attr:`PropertyEntry.reports_on_one_snapshot`).
    """

    total: int
    wedge: int
    catalog: int
    deferred: int
    registered: int
    reported: int

    @property
    def shipped(self) -> int:
        """Rows in either shipped scope — a validator for each ships in this release."""
        return self.wedge + self.catalog

    @property
    def not_checked(self) -> int:
        """How many properties such a run answers with a marker: the rest of the catalog."""
        return self.total - self.reported


def registry_counts() -> RegistryCounts:
    """The registry's counts as they stand now — the table's rows and this build's registrations."""
    entries = tuple(property_entry(slug) for slug in PROPERTY_SLUGS)
    return RegistryCounts(
        total=len(entries),
        wedge=sum(1 for entry in entries if entry.scope == "phase-0-wedge"),
        catalog=sum(1 for entry in entries if entry.scope == "catalog"),
        deferred=sum(1 for entry in entries if entry.deferred),
        registered=sum(1 for entry in entries if entry.slug in _IMPLEMENTATIONS),
        reported=sum(1 for entry in entries if entry.reports_on_one_snapshot),
    )


# ── Dispatch ─────────────────────────────────────────────────────────────────────────────


def register_validator(property_slug: PropertySlug, implementation: Validator) -> None:
    """Wire ``implementation`` in as the validator for ``property_slug``.

    The ruled path (DEC-35 §3.1): a row in either shipped scope — ``phase-0-wedge`` or
    ``catalog`` — accepts one validator. Two kinds of row refuse:

    - a ``deferred-to-phase-1`` row — no validator for it ships in this release, whether or
      not its section is ratified. A validator for it cannot appear at runtime; the build that
      lands one moves the row to ``catalog`` in the table above first, and only once the
      section is ratified and re-vendored, its reference fixtures are vendored and every
      condition ID it ratifies is emittable with its rule copy.
    - a two-snapshot row (P-12), whatever its scope. :class:`Validator` reads one IR, and a
      two-snapshot classifier registers through the shape its own landing adds (DEC-35 §3.6).

    Raises:
        PropertyRegistryError: if the slug is unknown, its row is ``deferred-to-phase-1``, its
            row reads two snapshots, or it already has an implementation. Re-wiring is
            :func:`unregister_validator` first — silently replacing a validator is how two of
            them end up shipping.
    """
    entry = property_entry(property_slug)
    if entry.deferred:
        raise PropertyRegistryError(
            f"{property_slug!r} ({entry.property_id}) {DEFERRED_READING}, so the registry "
            "answers for it with a structured not-implemented marker. A validator registers "
            "only for a shipped row: its build moves the row to `catalog` in the property "
            "table first (DEC-35 §3.1)."
        )
    if entry.arity != "one-snapshot":
        raise PropertyRegistryError(
            f"{property_slug!r} ({entry.property_id}) reads two snapshots; a Validator reads "
            "one, so a two-snapshot classifier cannot register through this path "
            "(DEC-35 §3.6)."
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

    The status distinguishes the two absences: a ``deferred-to-phase-1`` row has no validator
    in this release, and its marker carries the charter's words (:data:`DEFERRED_READING`,
    DEC-42 §3.1) and names the property's catalog section without stating its standing
    (DEC-42 §3.4); a shipped row whose validator has not been wired into this build is
    ``not-yet-implemented``, and its marker names what that validator is written against.
    Both keep :data:`NO_VERDICT` verbatim (DEC-35 §3.1). Neither is a pass, and neither is a
    :class:`~gebra.verify.report.PropertyReport`.
    """
    entry = property_entry(property_slug)
    if entry.deferred:
        return NotImplementedMarker(
            kind="not-implemented",
            property=entry.slug,
            property_id=entry.property_id,
            status="deferred-to-phase-1",
            detail=(
                f"{entry.property_id} {entry.slug} {MARKER_REASONS['deferred-to-phase-1']}. "
                f"Its catalog section is {entry.spec_ref}. {NO_VERDICT}"
            ),
        )
    return NotImplementedMarker(
        kind="not-implemented",
        property=entry.slug,
        property_id=entry.property_id,
        status="not-yet-implemented",
        detail=(
            f"{entry.property_id} {entry.slug} {MARKER_REASONS['not-yet-implemented']}. "
            f"Its contract is {entry.spec_ref}. {NO_VERDICT}"
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
    shipped validator whose module was never imported dispatches to ``not-yet-implemented``: a
    marker is the honest answer to *this* call, but a run that silently checked four of the
    five is a weakened gate, so the aggregation requires every shipped row to be registered
    before deriving an exit code. And ``PropertyEntry.claim_classes``/``severities``
    are property-level unions for display and documentation — the §0.2 input is always the
    per-record ``severity`` on the finding.

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
