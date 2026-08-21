"""The gebra pytest plugin — brief D-10 In-Scope 2, deliverable 2.

``pytest`` is the front door to gebra verification: a team adds one dependency, marks the
function that builds their LangGraph agent, and CI reports one test item per checked property,
each passing or carrying that property's findings. This module is the ``pytest11`` entry point
that does it. Two surfaces, and each does exactly one thing. A passing *item* still renders
nothing — an item is a verdict, not a report — but the run does not end silent: the closing
``gebra`` section carries REPORT-FORMAT-SPEC §5.1's obligations and §4's fact sets onto a
pytest run, and it is where the witness summaries, the notes and the eight not-checked
properties are (D-10's Definition of Done line 1 asks for the witnesses beside the verdicts).
It is not `gebra verify`'s human profile and does not claim to be: that surface is CLI-03's,
and the one bound worth naming here is that the §4.3 witness rows are rendered as **summaries**
— every witness in full is on ``gebra_verification.report``.

**The marker — one item per target × enabled property.** ``@pytest.mark.gebra`` marks a
*graph-producing* function: the plugin calls it, extracts what it returns, runs
:func:`gebra.verify.verify` over the IR, and reports the item for one property::

    @pytest.mark.gebra(name="travel_agent")
    def test_gebra():
        return build_travel_booking_agent()      # a StateGraph, a compiled graph, or a WorkflowIR

    # $ pytest -q
    # test_gebra[travel_agent-graph-well-formed]      PASSED
    # test_gebra[travel_agent-termination-witness]    PASSED
    # test_gebra[travel_agent-dataflow-completeness]  PASSED
    # test_gebra[travel_agent-effect-safety]          PASSED
    # test_gebra[travel_agent-determinism-replay]     PASSED

The marked function may request fixtures like any other test; the plugin fills them the way
pytest would. What it returns is the target, and returning nothing is a usage error rather
than a pass — a marked function that verified nothing must not look like a green check.

``@pytest.mark.gebra`` takes one more keyword, ``sidecar=``, naming an explicit ``gebra.toml``
for the extraction (ANNOTATION-API-SPEC §2 discovery rule 1). Without it the rule-2 walk starts
at the pytest process's working directory, and that is worth a thought on a CI surface of all
places: sidecar-filled annotations sit inside the ``graph_version`` hash scope and they move
P-04 and P-06 *verdicts*, not only the digest — which is why the same section says
reproducible/CI extraction SHOULD pass one explicitly. Whichever file was used is recorded on
``subject.sidecar``.

**The fixture — the extracted IR, for plain assertions.** Override ``gebra_workflow`` in
``conftest.py`` (the "conftest.py factory" of D-10 In-Scope 2) and ``gebra_graph`` is that
workflow's :class:`~gebra.ir.WorkflowIR`, with ``gebra_verification`` the whole
:class:`TargetVerification` over it (``.report`` is the
:class:`~gebra.verify.RunReport`)::

    # conftest.py
    @pytest.fixture
    def gebra_workflow():
        return build_travel_booking_agent()

    # test_topology.py
    def test_the_release_path_is_wired(gebra_graph):
        assert "release_hotel_hold" in {node.id for node in gebra_graph.nodes}

Override ``gebra_sidecar`` beside it for the same explicit-``gebra.toml`` control the marker's
``sidecar=`` gives.

**Which level you hand it is your declaration.** A ``StateGraph`` and the same graph compiled
are *different documents by design* (PD-023 D4): ``runtime.checkpointer`` and
``runtime.interrupts`` are read only off a compiled object, so the compiled extraction carries
a ``runtime`` block the builder extraction does not and therefore a different
``graph_version``. Neither is more correct and the plugin chooses neither; a suite that
compares an item against a stored snapshot needs the two to be the same level.

**Which properties get an item.** Every catalog property this build can actually answer, in
PROPERTY-CATALOG-SPEC order — the wedge five in Phase-0 (:func:`enabled_properties` reads the
registry rather than restating a list, so a validator that lands gets an item without an edit
here). The eight properties SOW §8 defers get **no item**, and that is a deliberate distinction
rather than a silence: :func:`gebra.verify.run_property` answers for them with a structured
:class:`~gebra.verify.NotImplementedMarker`, never a pass, and a run that minted a green item
out of one would be exactly the silent pass the registry exists to refuse. They are visible
where they are honest — ``gebra_verification``'s ``properties`` carries all thirteen outcomes,
markers included.

**What fails an item.** The D-10 In-Scope 2 default mapping: a FATAL or ERROR **finding**
owned by that property fails its item; a WARNING-grade finding is noted, never a failure.
Ownership is REPORT-FORMAT-SPEC §2.3's reach table, not the host report's — a co-failure or
advisory owned by P-06 riding P-04's report fails P-06's item, which is the one attribution
rule that is easy to get wrong and the reason :func:`findings_for` walks all three carriers.

Two run-level facts ride into the items rather than being dropped. A tool error — exit 2, "no
verdict was reached" (§2.4) — fails every item of that target with its stage and detail,
because a run that could not be assembled is not a pass. And where P-01 found something FATAL,
PROPERTY-CATALOG-SPEC §0.3 makes the other topology properties' results best-effort
diagnostics rather than contract-bearing verdicts; ``RunReport.best_effort`` says which, and
the item's own text says so too.

**The three gate flags.** ``--gebra-strict`` is PROPERTY-CATALOG-SPEC §0.2's, in both its
forms: bare promotes every WARNING in the run, ``--gebra-strict=<slug>[,<slug>…]`` promotes
only the named properties'. A promotion fails its property's item — and changes **nothing**
about the record, which keeps ``severity: warning`` and its claim class exactly where it
stands. The plugin does not implement promotion: it hands the policy to
:func:`gebra.verify.verify` and reads ``gate.promotions``, so §2.3's reach — including the
advisory row, and including WARNING-grade **witness notes**, which no finding walk can see —
is implemented once. Rendering a promotion is where the care goes, because §4.6 rule 8 makes
the promoted-item identity a name and not a grade: P-02's promoted note is reported under
``cycle-without-termination-witness``, an id §0.4 registers FATAL, while the record is a
WARNING-grade note. :func:`promoted_records` performs rule 8's own join back to the record so
the grade shown is the record's.

``--gebra-select`` and ``--gebra-skip`` subset which properties get an item —
``enabled ∩ select \\ skip``, computed in :func:`enabled_properties`. Neither reaches
``verify()``: the run always answers the whole catalog, so ``gebra_verification`` still
carries all thirteen outcomes and a skipped property is un-*itemized*, never unchecked.

The live strict case worth knowing about is P-02's ``scc-covered-only-by-recursion-limit``:
TERMINATION-WITNESS-SPEC §2.4 has a justified form-(b) blanket alone pass "with a
WARNING-grade note", §6.1 fixes the identity the promoted item is reported under, and that
note rides a *witness* rather than a finding — which is why :class:`ItemOutcome` carries
``witness_notes`` beside ``findings`` rather than folding the two together. A note is not a
finding (§P-02.3: "structured, display-adjacent, never gate-bearing"; §2.1: notes "never fail
a gate on their own"), so it never fails an item on its own and it carries no claim class; it
fails one only by being promoted, and then it is the promotion that failed it.

**The freshness marker — has the store kept up with the definition?** ``@pytest.mark.
gebra_freshness`` marks a graph-producing function the same way, and its one item fails when
the workflow it returns is not the snapshot the store currently holds (brief D-11 In-Scope 7:
"fail CI if the workflow definition changed but no ``gebra snapshot`` was taken")::

    @pytest.mark.gebra_freshness(name="travel_agent")
    def test_snapshot_is_current():
        return build_travel_booking_agent()

    # $ pytest -q
    # test_snapshot_is_current                        PASSED

``store=`` names the ``.gebra/`` directory, relative to pytest's rootdir and defaulting to
``.gebra``; ``name=`` and ``sidecar=`` are the ``gebra`` marker's. It is a check on the
**store**, not a fourteenth property: it never runs a validator, it never writes — recording is
:func:`gebra.snapshot.snapshot`'s and a check that fixed itself would be a gate that always
passes — and it says the content moved and which of S/F/E moved with it, never whether the
change is safe (P-12 ``evolution-safety`` is deferred; SOW §8). :func:`check_freshness` is the
same question programmatically, for a suite that would rather assert on the outcome.

**Never-invokes (WA-07).** *gebra* runs nothing on this path. It calls the function you
marked — which is your code, called exactly as pytest would call any test function, and the
marker asks you to make it a graph *producer* rather than enforcing that it is one — and hands
what that returns to :func:`gebra.extract`, which imports and inspects but never invokes
(INTROSPECTION-SPEC §1). From there on: no node body, router or tool is called, no model is
contacted, no connection is opened, and a builder handed in is never compiled. Three tripwires,
because the claim has two halves that one guard cannot hold both of, and two live-object
surfaces.
``tests/plugin/test_plugin.py`` covers the **live-object** half for the ``gebra`` marker: it
runs inner pytest sessions over the sentinel-guarded travel-booking agent — whose nine node
bodies and two routers record themselves and raise — and reads that ledger afterwards.
``tests/audit/test_freshness_gate.py`` does the same for the ``gebra_freshness`` marker, where
every target is a live workflow object.
``tests/plugin/test_hermeticity.py`` covers the **import** half: a fresh interpreter where
every substrate import, socket construction and name resolution raises, running a whole inner
session in fixture-only mode over that agent's already-extracted IR. The substrate is
unimportable there, so nothing in that child can build or compile a graph — which is why the
live-object half is the other files' and not this one's.

**Nothing heavy is imported until something is marked.** A ``pytest11`` entry point is imported
at the start of *every* pytest session in any environment where gebra is installed, so this
module's import closure is ``pytest`` and the standard library — nothing else. ``gebra.ir``
(~90 ms) and ``gebra.verify`` (~190 ms) are resolved inside the functions that need them, and
:func:`gebra.extract` inside the one branch that needs the substrate. That last split is what
makes **fixture-only mode** a fact rather than a wish: hand the marker or ``gebra_workflow`` a
:class:`~gebra.ir.WorkflowIR` — one loaded from a property fixture, an IR document, or a stored
snapshot — and no langgraph import happens on any path, which
``tests/plugin/test_hermeticity.py`` proves in an interpreter where importing the substrate
raises.

Nothing here **classifies** the object you hand it by reading attributes off it. The
classification is one ``isinstance`` and the rest is :func:`gebra.extract`'s job: a
``property`` on a user object is user code, and a plugin that probed for ``.ir`` or ``.nodes``
to "helpfully" accept more shapes would run it. The one place an attribute *is* asked for is
:func:`_call_target`'s awaitable guard — two ``hasattr`` calls for ``__await__`` and
``__aiter__``, which a pathological ``__getattr__`` could observe. That is the plugin's own
refusal rather than a classification, and it is on the return value of a function pytest had
already called; extraction still receives the object without having touched it. The same
discipline decides how the marked function is *called* — see
:func:`_call_target`, which reads the fixture names pytest already resolved rather than asking
``inspect.signature`` for them, because from Python 3.14 that call evaluates the function's
annotations.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final, Literal

import pytest

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from gebra.audit.models import FreshnessOutcome
    from gebra.ir import WorkflowIR
    from gebra.verify import (
        Advisory,
        AnyLocation,
        ClaimClass,
        CoFailure,
        ConditionId,
        DeterminismClaim,
        Failure,
        P06EffectRecord,
        Promotion,
        PromotionOrigin,
        PropertyOutcome,
        PropertyReport,
        PropertySlug,
        RunReport,
        Severity,
        StrictPolicy,
        Witness,
        WitnessNote,
        WitnessNoteKind,
    )

__all__ = [
    "BLOCKING_SEVERITIES",
    "CHECK_PARAM",
    "FRESHNESS_MARKER",
    "MARKER",
    "NOTES_KEY",
    "REPORT_KEY",
    "SELECT_OPTION",
    "SKIP_OPTION",
    "STRICT_OPTION",
    "WORKFLOW_FIXTURE",
    "ExtractionNote",
    "FreshnessCheck",
    "GatePolicy",
    "GebraCheck",
    "GebraTargetError",
    "ItemOutcome",
    "OwnedFinding",
    "PromotedRecord",
    "Resolution",
    "TargetVerification",
    "check_freshness",
    "enabled_properties",
    "enabled_properties_for",
    "findings_for",
    "gate_policy",
    "item_outcome",
    "notes_for",
    "owned_findings",
    "promoted_records",
    "promotions_for",
    "resolve_ir",
    "run_promotions",
    "verify_target",
]

#: The marker name. ``@pytest.mark.gebra`` — namespaced, as D-10's plugin-conflict mitigation
#: asks of every name this plugin adds to a user's session.
MARKER: Final = "gebra"

#: The snapshot-freshness marker. ``@pytest.mark.gebra_freshness`` — brief D-11 In-Scope 7's
#: "fail CI if the workflow definition changed but no ``gebra snapshot`` was taken", as one
#: pytest item. Deliberately its **own** marker rather than an extra item on
#: :data:`MARKER`'s parametrization: that parametrization is one item per catalog *property*,
#: it carries the property slug in the item id and in the public ``gebra_check`` fixture, and
#: freshness is not a property — it is a question about the store. Putting it in that position
#: would read as a fourteenth property to every reader of a CI log.
FRESHNESS_MARKER: Final = "gebra_freshness"

#: The parametrization argname, and the name of the fixture carrying it. A marked function
#: need not request it; one that does receives the :class:`GebraCheck` for its item.
CHECK_PARAM: Final = "gebra_check"

#: The fixture a user overrides in ``conftest.py`` to declare the workflow ``gebra_graph`` and
#: ``gebra_verification`` are about.
WORKFLOW_FIXTURE: Final = "gebra_workflow"

#: The severities that fail an item under the default mapping (D-10 In-Scope 2). WARNING is a
#: note, and promotion under ``--gebra-strict`` never touches this set: a promoted record keeps
#: ``severity: warning`` (§0.2), so what fails its item is the *promotion*, not a re-grade.
BLOCKING_SEVERITIES: Final[frozenset[str]] = frozenset({"fatal", "error"})

_REPORT_SECTION: Final = "gebra"

#: ``--gebra-strict`` — PROPERTY-CATALOG-SPEC §0.2's two forms, in one option.
STRICT_OPTION: Final = "--gebra-strict"

#: What argparse stores for the **bare** ``--gebra-strict``. An object rather than a string,
#: because the alternative reading of an empty string — ``--gebra-strict=`` with nothing after
#: the ``=`` — is a malformed per-property list, and an empty list widening into
#: promote-everything is the opposite of what every other refusal here does. A sentinel makes
#: the two distinguishable, which a shared ``""`` const would not.
_BARE_STRICT: Final = object()
#: ``--gebra-select`` — D-10 In-Scope 2's property-selection option.
SELECT_OPTION: Final = "--gebra-select"
#: ``--gebra-skip`` — its complement.
SKIP_OPTION: Final = "--gebra-skip"

#: The run's collected notes, keyed off the ``Config`` rather than a module global — D-10's
#: plugin-conflict mitigation asks for no global state, and a module global would also leak
#: between the nested sessions ``pytester`` runs in-process.
NOTES_KEY: Final[pytest.StashKey[list[tuple[str, str]]]] = pytest.StashKey()

#: The run's verified targets, in first-seen order, for the closing report. Keyed by the item
#: reference with the gebra parametrization stripped, so the five items of one target
#: contribute one block rather than five copies of it.
REPORT_KEY: Final[pytest.StashKey[dict[str, _Block]]] = pytest.StashKey()

#: The parsed gate policy for this session, or absent when no gebra flag was given.
POLICY_KEY: Final[pytest.StashKey[GatePolicy]] = pytest.StashKey()


class GebraTargetError(Exception):
    """A declared target could not be turned into IR to verify.

    Raised by :func:`resolve_ir` rather than letting the underlying
    :class:`gebra.ExtractionError` out, for one reason that is about this module's import
    closure and not about tidiness: catching the extractor's own exception type would mean
    importing it, and importing it imports the substrate — on the *fixture-only* path too,
    where the whole point is that nothing does. The original is always the ``__cause__``.
    """


@dataclass(frozen=True)
class GebraCheck:
    """One item's parametrization: the target it is about and the property it checks.

    This is what the ``gebra_check`` fixture yields and what the item id is built from
    (``<target>-<property-slug>``, D-10's ``test_gebra[travel_agent-termination-witness]``).
    It carries the *declaration*, never a result: it is resolved while pytest is filling
    fixtures, which is before the plugin has called the target factory.

    ``sidecar`` is the marker's ``sidecar=`` if it named one — the ANNOTATION-API-SPEC §2
    rule-1 path, whose absence leaves the rule-2 walk to start from the pytest process's
    working directory.
    """

    target: str
    property: PropertySlug
    sidecar: str | None = None


@dataclass(frozen=True)
class ExtractionNote:
    """One INTROSPECTION-SPEC §8 extraction warning, flattened to plain strings.

    Flattened rather than carried as the
    :class:`~gebra.extraction.warnings.ExtractionWarning` model itself, and the reason is the
    same one that keeps the extractor out of this module's import closure: this shape is
    annotated and constructed on the fixture-only path too, where the extraction models are
    not importable without the substrate. Flattened to **strings**, not to prose — ``code`` is
    the §8 taxonomy member verbatim (``compiled-only-extraction``, not the Python enum's
    ``repr``), so a consumer or a CI grep keyed on the vocabulary finds it, and TE-07's strict
    bar has a field to match on rather than a message to parse.
    """

    code: str
    message: str
    node: str | None = None
    slots: tuple[str, ...] = ()
    #: The rest of the §8 row's "what it carries" column, flattened to ``key=value`` strings in
    #: the order the warning wrote them. Carried rather than dropped because the column names
    #: facts a reader of a *pytest* run has no other way to reach — ``ir_partial`` above all,
    #: which is whether the IR is partial at that location, and which a run that reached no
    #: verdict is exactly the run that needs.
    detail: tuple[str, ...] = ()

    def render(self) -> str:
        """One line, code first — how the note reads on an item and in the summary."""
        where = f" at {self.node}" if self.node is not None else ""
        slots = f" ({', '.join(self.slots)})" if self.slots else ""
        detail = f" [{', '.join(self.detail)}]" if self.detail else ""
        return f"extraction warning [{self.code}]{where}{slots}{detail} {self.message}"


@dataclass(frozen=True)
class TargetVerification:
    """One target, resolved to IR and verified — the whole per-target answer, once.

    Attributes:
        target: The declared target name.
        report: The :class:`~gebra.verify.RunReport` of the run, carrying all thirteen
            catalog outcomes, the §2.2 gate, and ``best_effort``.
        extraction_notes: The INTROSPECTION-SPEC §8 warnings this extraction raised, when the
            target was a live workflow. Empty on the fixture-only path, where nothing was
            extracted.
    """

    target: str
    report: RunReport
    extraction_notes: tuple[ExtractionNote, ...] = ()


@dataclass(frozen=True)
class OwnedFinding:
    """One emitted record, attributed to the property that **owns** it (§2.1/§2.3).

    The same six members ``verify()``'s own gate derivation reads, for the same reason: an
    advisory riding a host report is still its own property's finding, and an item gate that
    read the host's slug would fail the wrong item.
    """

    owner: PropertySlug
    origin: Literal["failure", "co-failure", "advisory"]
    severity: Severity
    claim_class: ClaimClass
    property_condition: ConditionId
    location: AnyLocation

    @property
    def blocking(self) -> bool:
        """Whether this record fails its property's item under the default mapping."""
        return self.severity in BLOCKING_SEVERITIES


@dataclass(frozen=True)
class PromotedRecord:
    """One :class:`~gebra.verify.Promotion`, joined back to the record it names.

    The join is REPORT-FORMAT-SPEC §4.6 rule 8 taken literally, and it is the reason this
    class exists rather than the item rendering reading a ``Promotion`` directly. A promotion
    "is not a finding, and its condition id is not a grade": ``property_condition`` there
    names the *item* the promotion is reported under, and for P-02's one promotable note that
    id — ``cycle-without-termination-witness`` — is registered **FATAL** in §0.4 while the
    record it points at is a WARNING-grade note. Rendering the promotion with the id's
    registered severity "would invert §0.2's whole rule", so the grade is taken from the
    record: rule 8's own join is the identity tuple ``(property, property_condition,
    location)``, "with ``note_kind`` standing in for the condition on a ``witness-note``
    origin", which is exactly :func:`promoted_records`' lookup.

    Attributes:
        promotion: The run-level record ``verify()`` produced, verbatim.
        severity: The **promoted record's own** grade — always ``warning``, because §2.3's
            reach selects nothing else.
        claim_class: The record's own claim class on a finding origin; ``None`` for a witness
            note, which has none by design (§2.3: notes are "deliberately **not** §0.4
            condition IDs").
        label: What the promoted record calls itself — its condition ID, or its note kind.
        joined: Whether a record was actually found. ``False`` is a drift signal rather than a
            rendering choice: the severity above is then §2.3's guarantee rather than an
            observation, and the item says so.
    """

    promotion: Promotion
    severity: Severity
    claim_class: ClaimClass | None
    label: str
    joined: bool = True

    @property
    def origin(self) -> PromotionOrigin:
        """Where the promoted record was carried — ``failure``/``co-failure``/``advisory``/note."""
        return self.promotion.origin

    @property
    def reported_under(self) -> ConditionId | None:
        """The §0.4 id the promoted *item* is named by, where its property's spec fixes one.

        Never a grade (§4.6 rule 8) and never an input to ``gate.counts``; absent on a
        witness-note origin whose property fixes no identity, because minting one would breach
        §0.4's closed registry.
        """
        return self.promotion.property_condition


@dataclass(frozen=True)
class ItemOutcome:
    """What one ``<target>-<property>`` item reports.

    Attributes:
        check: The item's declaration.
        findings: Every record owned by this property anywhere in the run, in the order
            ``verify()`` carries them.
        best_effort: Whether §0.3's P-01-clean precondition failed for this property, making
            its result a diagnostic rather than a contract-bearing verdict.
        tool_error: The §2.4 stage and detail when the run reached no verdict at all, else
            ``None``. A tool error fails every item of the target.
        promotions: The §2.3 promotions this property owns — what ``--gebra-strict`` selected.
            Empty under the default policy, and empty on every property the policy does not
            name. These fail the item; the records they name are unchanged in ``properties``.
        witness_notes: The structured :class:`~gebra.verify.WitnessNote`\\ s this property's
            own report carries, on either result path. A note is not a finding and never fails
            an item on its own (§P-02.3, §2.1); it fails one only by being promoted, in which
            case it also appears in ``promotions``.
    """

    check: GebraCheck
    findings: tuple[OwnedFinding, ...]
    best_effort: bool = False
    tool_error: str | None = None
    promotions: tuple[Promotion, ...] = ()
    witness_notes: tuple[WitnessNote, ...] = ()

    @property
    def blocking(self) -> tuple[OwnedFinding, ...]:
        """The FATAL/ERROR findings — what fails the item under the default mapping."""
        return tuple(finding for finding in self.findings if finding.blocking)

    @property
    def notes(self) -> tuple[OwnedFinding, ...]:
        """The WARNING-grade **findings** — noted on the item, never a failure of their own."""
        return tuple(finding for finding in self.findings if not finding.blocking)

    @property
    def failed(self) -> bool:
        """Whether this item fails.

        Three ways, and the third is a gate rather than a grade: a tool error (§2.4, no verdict
        was reached), a finding this property owns at FATAL/ERROR (the D-10 default mapping),
        or a record a ``--gebra-strict`` policy naming this property promoted (§0.2). Nothing
        about the third rewrites the second: the promoted record is still WARNING in the
        envelope, and ``blocking`` still names only what the ladder blocks on.
        """
        return self.tool_error is not None or bool(self.blocking) or bool(self.promotions)


# ── The gate policy: what the three flags say ────────────────────────────────────────────


@dataclass(frozen=True)
class GatePolicy:
    """What this session's gebra flags asked for — parsed once, at ``pytest_configure``.

    Parsed once so that a mistyped slug fails the session where a reader is looking, rather
    than once per collected item; and parsed *only* when a gebra flag is actually present, so
    that a session with none still imports nothing of gebra. That last is measured — by a
    subprocess in ``tests/plugin/test_gating.py``, which pins ``sys.modules`` at the end of a
    plain session, and not by ``tests/plugin/test_hermeticity.py``, whose ``after_import``
    measurement is taken before any session is configured.

    Attributes:
        strict: The §0.2 strict-mode request, in the envelope's own model — handed to
            ``verify()`` unchanged, so §2.3's reach stays implemented once, there.
        select: The properties ``--gebra-select`` named, or ``None`` for "every enabled one".
            An intersection, never an addition: selecting a property no validator answers is
            refused at parse time rather than silently yielding no item.
        skip: The properties ``--gebra-skip`` named — subtracted after ``select``.
    """

    strict: StrictPolicy
    select: tuple[PropertySlug, ...] | None = None
    skip: tuple[PropertySlug, ...] = ()


def pytest_addoption(parser: pytest.Parser) -> None:
    """Declare the three D-10 In-Scope 2 gate flags.

    ``--gebra-strict`` takes an **optional** value because §0.2 specifies two forms under one
    spelling: bare promotes every WARNING in the run, ``=<slug>[,<slug>…]`` promotes only the
    named properties'. That is ``nargs="?"``, and it carries one hazard worth naming rather
    than discovering: argparse will happily consume the *next* token as the value, so
    ``pytest --gebra-strict tests/`` would read ``tests/`` as a property slug and lose the
    path. It cannot be prevented at the parser — but it can be made loud, and it is: the value
    is checked against the closed thirteen-slug catalog vocabulary at ``pytest_configure``,
    and the refusal names the ``=`` form. Nothing is guessed and nothing is dropped.
    """
    group = parser.getgroup("gebra", "gebra — design-time verification gating")
    group.addoption(
        STRICT_OPTION,
        nargs="?",
        const=_BARE_STRICT,
        default=None,
        metavar="SLUG[,SLUG...]",
        help=(
            "Promote WARNING-grade records to gate failures (PROPERTY-CATALOG-SPEC §0.2). "
            "Bare promotes every WARNING in the run; "
            f"`{STRICT_OPTION}=determinism-replay` promotes only the named properties'. "
            "The promoted record is unchanged — it keeps `severity: warning` and its claim "
            "class; only the gate moves."
        ),
    )
    group.addoption(
        SELECT_OPTION,
        action="append",
        default=None,
        metavar="SLUG[,SLUG...]",
        help=(
            "Generate items only for these properties. Repeatable, comma-separated. "
            "An intersection with the properties this build can answer."
        ),
    )
    group.addoption(
        SKIP_OPTION,
        action="append",
        default=None,
        metavar="SLUG[,SLUG...]",
        help=(
            f"Generate no item for these properties. Repeatable, comma-separated. Applied "
            f"after {SELECT_OPTION}."
        ),
    )


def _requested_slugs(values: list[str], option: str) -> tuple[PropertySlug, ...]:
    """The catalog slugs one repeatable, comma-separated option named, in catalog order.

    Deduplicated and ordered by construction, because the result is built by filtering
    ``PROPERTY_SLUGS`` rather than by echoing what was typed — so ``--gebra-skip=b,a --
    gebra-skip=a`` is the same request as ``--gebra-skip=a,b``.

    Raises:
        pytest.UsageError: on an empty member or on any string outside the thirteen catalog
            slugs. A typo is refused rather than ignored: a silently-dropped
            ``--gebra-skip`` slug gates on a property the user asked to leave out, and a
            silently-dropped ``--gebra-strict`` slug is a gate that quietly did not tighten.
    """
    from gebra.verify import PROPERTY_SLUGS

    requested: list[str] = []
    for value in values:
        for member in value.split(","):
            slug = member.strip()
            if not slug:
                raise pytest.UsageError(
                    f"{option} was given an empty property slug in {value!r}. "
                    f"Write {option}=<slug>[,<slug>…] with the catalog slugs."
                )
            requested.append(slug)
    unknown = [slug for slug in requested if slug not in PROPERTY_SLUGS]
    if unknown:
        raise pytest.UsageError(
            f"{option} names {unknown!r}, which is not a property slug. The catalog has "
            f"exactly thirteen: {', '.join(PROPERTY_SLUGS)}. "
            f"(If you meant a path or another option, note that {option} takes its value "
            f"joined with `=`.)"
        )
    return tuple(slug for slug in PROPERTY_SLUGS if slug in requested)


def _parse_policy(config: pytest.Config) -> GatePolicy | None:
    """This session's :class:`GatePolicy`, or ``None`` when no gebra flag was given.

    ``None`` rather than a default-valued policy, and that is the whole reason this function
    returns an option type: building the default would import ``gebra.verify``, and a
    ``pytest11`` entry point runs in every session in every environment where gebra is
    installed — including sessions with nothing gebra-related in them.
    """
    raw_strict: object = config.getoption("gebra_strict", default=None)
    raw_select: list[str] | None = config.getoption("gebra_select", default=None)
    raw_skip: list[str] | None = config.getoption("gebra_skip", default=None)
    if raw_strict is None and not raw_select and not raw_skip:
        return None

    from gebra.verify import STRICT_ALL, STRICT_OFF, StrictPolicy, is_implemented

    strict = STRICT_OFF
    if raw_strict is _BARE_STRICT:
        strict = STRICT_ALL
    elif isinstance(raw_strict, str):
        # `--gebra-strict=` with nothing after the `=` lands here rather than on the bare arm,
        # and `_requested_slugs` refuses it as an empty slug — an empty per-property list is a
        # malformed request, and reading it as "promote everything" would widen a gate the user
        # did not ask to widen.
        strict = StrictPolicy(
            mode="per-property", properties=_requested_slugs([raw_strict], STRICT_OPTION)
        )

    select: tuple[PropertySlug, ...] | None = None
    if raw_select:
        select = _requested_slugs(raw_select, SELECT_OPTION)
        deferred = [slug for slug in select if not is_implemented(slug)]
        if deferred:
            raise pytest.UsageError(
                f"{SELECT_OPTION} names {deferred!r}, which no validator in this build "
                "answers (SOW §8 defers them to Phase 1). Selecting one could only produce "
                "an item that asserts nothing, so it is refused rather than silently "
                f"dropped — those properties are visible as not-implemented markers on "
                "`gebra_verification.report.properties`."
            )
    skip = _requested_slugs(raw_skip, SKIP_OPTION) if raw_skip else ()
    return GatePolicy(strict=strict, select=select, skip=skip)


def gate_policy(config: pytest.Config | None = None) -> GatePolicy:
    """The policy in force — this session's flags, or the default when there were none."""
    if config is not None:
        stored = config.stash.get(POLICY_KEY, None)
        if stored is not None:
            return stored
    from gebra.verify import STRICT_OFF

    return GatePolicy(strict=STRICT_OFF)


# ── The programmatic path: target → IR → run report → item outcomes ──────────────────────


def enabled_properties(config: pytest.Config | None = None) -> tuple[PropertySlug, ...]:
    """The catalog properties this run generates an item for, in catalog order.

    The base set is read off the registry rather than listed here, so it is whatever
    :func:`gebra.verify.register_validator` actually accepted: the wedge five in Phase-0,
    and a later validator without an edit to this module. The eight properties SOW §8 defers
    are absent by construction, since registration refuses them — and their absence is not a
    verdict about them (see this module's docstring).

    ``--gebra-select`` and ``--gebra-skip`` subset exactly that set, in that order:
    ``enabled ∩ select \\ skip``. Overlap between the two flags is a subtraction and not a
    contradiction — the later operation wins, deterministically — which is what lets a broad
    ``addopts`` selection compose with a narrow command-line skip. Neither flag reaches
    ``verify()``: the run always answers the whole catalog, so ``gebra_verification`` still
    carries all thirteen outcomes and a skipped property is un-*itemized*, never unchecked.
    """
    return enabled_properties_for(gate_policy(config))


def enabled_properties_for(policy: GatePolicy) -> tuple[PropertySlug, ...]:
    """:func:`enabled_properties`, for a policy already in hand rather than a ``Config``."""
    from gebra.verify import PROPERTY_SLUGS, is_implemented

    return tuple(
        slug
        for slug in PROPERTY_SLUGS
        if is_implemented(slug)
        and (policy.select is None or slug in policy.select)
        and slug not in policy.skip
    )


@dataclass(frozen=True)
class Resolution:
    """A target reduced to IR, with the REPORT-FORMAT-SPEC §1.3 provenance a subject wants.

    Attributes:
        ir: The workflow IR to verify.
        input_mode: ``"ir-document"`` when the target already was one — nothing was
            extracted and nothing imported the substrate — and ``"extracted"`` otherwise.
            ``ir-document`` is the only admissible value of the three for a target that
            arrived as IR: ``extracted`` would owe an ``extractor_version`` nothing produced,
            and ``snapshot`` would owe a V.S.F.E label there is none of. What it rests on is
            §1.3's headline rule — ``subject.source`` is a **label**, not a locator — rather
            than that bullet's "the IR document path", because an in-memory ``WorkflowIR``
            has no path and the plugin will not invent one.
        extractor_version: What produced the IR; present iff ``input_mode == "extracted"``.
        sidecar: The ``gebra.toml`` path extraction resolved, when there was one — so a digest
            that moved because a different sidecar was in reach is diagnosable
            (ANNOTATION-API-SPEC §2).
        notes: The INTROSPECTION-SPEC §8 warnings the extraction raised, if any.
    """

    ir: WorkflowIR
    input_mode: Literal["extracted", "ir-document"]
    extractor_version: str | None = None
    sidecar: str | None = None
    notes: tuple[ExtractionNote, ...] = ()


def resolve_ir(target: object, *, sidecar: str | None = None) -> Resolution:
    """Reduce ``target`` to a :class:`~gebra.ir.WorkflowIR`, extracting only if it must.

    Two branches and no probing. A ``WorkflowIR`` is used as it stands — that is fixture-only
    mode, and on that branch nothing imports the substrate. Anything else is handed to
    :func:`gebra.extract`, which is the one component licensed to classify a live object
    (INTROSPECTION-SPEC §2) and does it with ``isinstance`` rather than by calling anything.

    There is deliberately no third branch for "an object that looks like it has IR on it":
    reading an attribute off a foreign object can run a ``property``, which is user code
    executing inside a verification path (WA-07). A caller holding an
    :class:`~gebra.extraction.envelope.ExtractionEnvelope` passes ``envelope.ir`` — and gives
    up ``extractor_version`` and ``sidecar`` on the subject by doing so, since the plugin can
    no longer tell the IR was extracted.

    Args:
        target: The workflow object, or a ``WorkflowIR`` already in hand.
        sidecar: An explicit ``gebra.toml`` path — ANNOTATION-API-SPEC §2 discovery rule 1,
            which the same section's "reproducible/CI extraction SHOULD pass ``sidecar=``
            explicitly" asks a CI surface to offer. ``None`` leaves extraction to the rule-2
            walk **from the pytest process's current working directory**, which is what makes
            that recommendation matter: sidecar-filled annotations sit inside the
            ``graph_version`` hash scope, and they move P-04 and P-06 verdicts as well as the
            digest.

    Raises:
        GebraTargetError: if extraction refused the object, naming the object type and the
            §2 refusal reason, with the :class:`gebra.ExtractionError` as ``__cause__``.
    """
    from gebra.ir import WorkflowIR

    if isinstance(target, WorkflowIR):
        return Resolution(ir=target, input_mode="ir-document")

    from gebra import ExtractionError, extract

    try:
        envelope = extract(target, sidecar=sidecar)
    except ExtractionError as error:
        # The type and the reason are what INTROSPECTION-SPEC §2 makes the refusal carry, and
        # `pytest.fail(pytrace=False)` drops the `__cause__` chain the exception object holds
        # them on — so they are lifted into the message here or they never reach the reader.
        raise GebraTargetError(
            f"{error} [object_type={error.object_type}, reason={error.reason.value}]"
        ) from error
    return Resolution(
        ir=envelope.ir,
        input_mode="extracted",
        extractor_version=envelope.extracted_from.extractor_version,
        sidecar=envelope.extracted_from.sidecar,
        notes=tuple(
            ExtractionNote(
                code=warning.code.value,
                message=warning.message,
                node=warning.node,
                slots=tuple(str(slot) for slot in warning.slots),
                detail=tuple(f"{key}={value}" for key, value in warning.detail.items()),
            )
            for warning in envelope.warnings
        ),
    )


def verify_target(
    target: object,
    *,
    name: str,
    source: str,
    sidecar: str | None = None,
    strict: StrictPolicy | None = None,
) -> TargetVerification:
    """Resolve ``target`` to IR and run :func:`gebra.verify.verify` over it, once.

    Args:
        target: The workflow object or :class:`~gebra.ir.WorkflowIR` to verify.
        name: The declared target name, carried into the result for reporting.
        source: The §1.3 ``subject.source`` label — a label the caller names, never a
            locator the report invents. The plugin passes the item's own reference.
        sidecar: An explicit ``gebra.toml`` path for the extraction, per :func:`resolve_ir`.
        strict: The PROPERTY-CATALOG-SPEC §0.2 strict-mode request, handed to ``verify()``
            unchanged; ``None`` is strict off. What ``--gebra-strict`` fills, and the reason
            §2.3's promotion reach is implemented once — inside ``verify()`` — instead of a
            second time here.

    Returns:
        The :class:`TargetVerification`: the run report plus any extraction warnings.

    Raises:
        GebraTargetError: if the target could not be reduced to IR.
    """
    from gebra.verify import STRICT_OFF, RunPolicy, SubjectRef, verify

    resolution = resolve_ir(target, sidecar=sidecar)
    reference = SubjectRef(
        source=source,
        input_mode=resolution.input_mode,
        extractor_version=resolution.extractor_version,
        sidecar=resolution.sidecar,
    )
    policy = RunPolicy(strict=strict if strict is not None else STRICT_OFF, subject=reference)
    report = verify(resolution.ir, policy)
    return TargetVerification(target=name, report=report, extraction_notes=resolution.notes)


def owned_findings(report: PropertyReport) -> tuple[OwnedFinding, ...]:
    """Every record one property's report carries, attributed to the property that owns it.

    Three carriers, because REPORT-FORMAT-SPEC §2.1 has three: the report's own ``failure``,
    the ``co_failures`` riding it, and the ``advisories`` riding it. The owner is the
    record's own ``property`` wherever the record carries one, which is §2.3's rule and the
    one thing here that is easy to get wrong: a co-failure or advisory riding a *host*
    report is still its own property's finding, so an item gate that read the host's slug
    would fail the wrong item and leave the right one green.

    Held to ``verify()``'s own derivation by test rather than by inheritance: this walk's
    severity tally over a whole run must equal ``report.gate.counts``, which
    ``tests/plugin/test_plugin.py`` asserts over every vendored fixture. A record carrier
    added to the envelope that this walk misses would move the two apart.
    """
    failure = report.failure
    if failure is None:
        return ()
    records = [
        OwnedFinding(
            owner=report.property,
            origin="failure",
            severity=failure.severity,
            claim_class=failure.claim_class,
            property_condition=failure.property_condition,
            location=failure.location,
        )
    ]
    records.extend(
        OwnedFinding(
            owner=co_failure.property,
            origin="co-failure",
            severity=co_failure.severity,
            claim_class=co_failure.claim_class,
            property_condition=co_failure.property_condition,
            location=co_failure.location,
        )
        for co_failure in failure.co_failures or ()
    )
    records.extend(
        OwnedFinding(
            owner=advisory.property,
            origin="advisory",
            severity=advisory.severity,
            claim_class=advisory.claim_class,
            property_condition=advisory.property_condition,
            location=advisory.location,
        )
        for advisory in failure.advisories or ()
    )
    return tuple(records)


def _records(report: RunReport) -> Iterator[OwnedFinding]:
    """Every emitted record of the whole run, in the order the run carries its properties."""
    from gebra.verify import PropertyReport

    for outcome in report.properties:
        # A NotImplementedMarker emits nothing: never a pass, and never a finding either.
        if isinstance(outcome, PropertyReport):
            yield from owned_findings(outcome)


def findings_for(report: RunReport, property_slug: PropertySlug) -> tuple[OwnedFinding, ...]:
    """Every record ``property_slug`` owns in this run, wherever it was carried."""
    return tuple(record for record in _records(report) if record.owner == property_slug)


def notes_for(report: RunReport, property_slug: PropertySlug) -> tuple[WitnessNote, ...]:
    """Every structured :class:`~gebra.verify.WitnessNote` ``property_slug``'s report carries.

    Its **own** report and no other, which is the one place note ownership differs from
    finding ownership: REPORT-FORMAT-SPEC §2.3's reach table gives a ``WitnessNote``'s owning
    property as "the report's own ``property``", while a co-failure or advisory carries its
    own. A note does not travel between reports, so there is nothing here to attribute.

    Both carriage paths, because DEC-23 gave notes two: a passing report's witness, and —
    unconditionally, so a failing property never silently drops one — ``Failure.notes`` and
    ``CoFailure.notes``. Held to ``verify()``'s own walk by test rather than by inheritance:
    the WARNING-grade subset of this must equal the witness-note promotions a ``mode="all"``
    run produces, which ``tests/plugin/test_gating.py`` asserts over the whole corpus.
    """
    from gebra.verify import PropertyReport

    for outcome in report.properties:
        if not isinstance(outcome, PropertyReport) or outcome.property != property_slug:
            continue
        notes: list[WitnessNote] = list(_witness_notes(outcome.witness))
        failure = outcome.failure
        if failure is not None:
            notes.extend(failure.notes or ())
            for co_failure in failure.co_failures or ():
                notes.extend(co_failure.notes or ())
        return tuple(notes)
    return ()


def _witness_notes(witness: Witness | None) -> tuple[WitnessNote, ...]:
    """The notes a witness carries, asked of the model rather than of a hard-coded kind."""
    if witness is None or "notes" not in type(witness).model_fields:
        return ()
    notes: tuple[WitnessNote, ...] = getattr(witness, "notes", ())
    return notes


def promotions_for(report: RunReport, property_slug: PropertySlug) -> tuple[Promotion, ...]:
    """What the run's strict policy promoted that ``property_slug`` owns (§2.3).

    Read off ``gate.promotions`` rather than re-derived. That is the seam TE-06 left on
    purpose: §2.3's reach — including the advisory row, where the owner is the advisory's own
    property and not the host report's — is implemented once, inside ``verify()``, and a
    second implementation here would be a second thing to keep in step with the envelope.
    """
    return tuple(
        promotion for promotion in report.gate.promotions if promotion.property == property_slug
    )


def promoted_records(outcome: ItemOutcome) -> tuple[PromotedRecord, ...]:
    """Join this item's promotions back to the records they name — §4.6 rule 8's own join.

    Rule 8 is explicit both about the hazard and about the remedy. The hazard: a promotion's
    ``property_condition`` "names the item, and the §0.4 severity registered for that id is
    **not** the promoted record's". P-02 is the live case — its promoted note is reported
    under ``cycle-without-termination-witness``, which §0.4 registers FATAL, while the record
    is a WARNING-grade note. The remedy: "a rendering that wants the grade joins back to the
    record", on the identity tuple ``(property, property_condition, location)``, "with
    ``note_kind`` standing in for the condition on a ``witness-note`` origin".

    A promotion that joins to nothing is not silently dropped and not silently graded: it is
    carried with ``joined=False`` and §2.3's guarantee (only WARNING-grade records are
    promotable) standing in for the observation, and the rendering says which it had.
    """
    joined: list[PromotedRecord] = []
    for promotion in outcome.promotions:
        if promotion.origin == "witness-note":
            joined.append(_join_note(promotion, outcome.witness_notes))
            continue
        joined.append(_join_finding(promotion, outcome.findings))
    return tuple(joined)


def run_promotions(report: RunReport) -> tuple[PromotedRecord, ...]:
    """:func:`promoted_records` for a whole run — every promotion, in ``gate.promotions`` order.

    The same join, over each promotion's **owning** property's records rather than one item's,
    which is what the closing report needs: §5.1 obligation 6 asks a run's summary for "the
    strict policy in force with what it promoted", and a count is not a *what*.
    """
    return tuple(
        _join_note(promotion, notes_for(report, promotion.property))
        if promotion.origin == "witness-note"
        else _join_finding(promotion, findings_for(report, promotion.property))
        for promotion in report.gate.promotions
    )


def _join_note(promotion: Promotion, notes: tuple[WitnessNote, ...]) -> PromotedRecord:
    """The ``witness-note`` arm of rule 8's join: ``note_kind`` stands in for the condition."""
    kind: WitnessNoteKind | None = promotion.note_kind
    for note in notes:
        if note.kind != kind:
            continue
        locations = note.locations or ()
        if promotion.location is not None and locations and promotion.location not in locations:
            continue
        if note.severity is None:
            # A note with no grade is not promotable at all (§2.3 selects on severity), so a
            # promotion naming one is drift rather than a note to grade. `joined=False` says
            # the grade below is the rule and not a reading, which is the honest answer —
            # inventing `warning` here would fabricate the one field that decides gating.
            break
        return PromotedRecord(
            promotion=promotion,
            severity=note.severity,
            claim_class=None,  # a note has none by design (§2.3)
            label=note.kind,
        )
    return PromotedRecord(
        promotion=promotion,
        severity="warning",
        claim_class=None,
        label=kind or "witness note",
        joined=False,
    )


def _join_finding(promotion: Promotion, findings: tuple[OwnedFinding, ...]) -> PromotedRecord:
    """The finding arm of rule 8's join: ``(property, property_condition, location)``."""
    for finding in findings:
        if (
            finding.origin == promotion.origin
            and finding.property_condition == promotion.property_condition
            and finding.location == promotion.location
        ):
            return PromotedRecord(
                promotion=promotion,
                severity=finding.severity,
                claim_class=finding.claim_class,
                label=finding.property_condition,
            )
    return PromotedRecord(
        promotion=promotion,
        severity="warning",
        claim_class=None,
        label=promotion.property_condition or "record",
        joined=False,
    )


def item_outcome(verification: TargetVerification, property_slug: PropertySlug) -> ItemOutcome:
    """What the ``<target>-<property_slug>`` item reports for this run."""
    report = verification.report
    error = report.error
    return ItemOutcome(
        check=GebraCheck(target=verification.target, property=property_slug),
        findings=findings_for(report, property_slug),
        best_effort=property_slug in report.best_effort,
        tool_error=f"{error.stage}: {error.detail}" if error is not None else None,
        # Both are empty on a tool-error run by the envelope's own invariants — a run that
        # reached no verdict carries no outcome to note and promoted nothing (§2.4) — so
        # neither needs a guard here, and adding one would state the rule a second time.
        promotions=promotions_for(report, property_slug),
        witness_notes=notes_for(report, property_slug),
    )


# ── Rendering: the item message, and the human profile of REPORT-FORMAT-SPEC §5 ──────────


def _render_location(location: AnyLocation) -> str:
    """One record's anchor, compactly — ``kind field=value, …`` in PC-4 spelling.

    A member whose name repeats the discriminator drops the name (``node 'escalate'`` rather
    than ``node node='escalate'``); everything else keeps it, because an anchor read out of
    context has to say which member is which. §5.1 obligation 2 defers the anchor spelling to
    §4.5; this is the one-line form an item message and a terminal block can both carry.
    """
    from gebra.verify import to_data

    data = to_data(location)
    kind = str(data.pop("kind", location.kind))
    members = ", ".join(
        f"{value!r}" if name == kind else f"{name}={value!r}" for name, value in data.items()
    )
    return f"{kind} {members}" if members else kind


def _render_finding(finding: OwnedFinding) -> str:
    """One record, with its claim class — WA-06 requires a finding to carry its own grade.

    The severity word is the envelope's own (§5.1 obligation 3): FATAL is never collapsed
    into "error" here, because only SARIF is forced to collapse it.
    """
    origin = "" if finding.origin == "failure" else f" ({finding.origin})"
    return (
        f"  {finding.severity.upper()}{origin} {finding.property_condition} "
        f"[{finding.claim_class}]\n"
        f"    at {_render_location(finding.location)}"
    )


def _render_witness_note(note: WitnessNote, *, owner: PropertySlug, promoted: bool) -> list[str]:
    """One structured note, under §5.1 obligation 3's fourth label — which is not a severity.

    The grade is stated in words (``warning-grade``) rather than as a severity word, because a
    note is not a finding: §P-02.3 makes note kinds "structured, display-adjacent, never
    gate-bearing" and §2.1 says notes "never fail a gate on their own".

    What a strict policy did or could do with it is on the same line, because that is the fact
    a reader of a pass-with-notes run needs — and the two are kept apart. §4.3's row for
    ``scc-covered-only-by-recursion-limit`` says "promotable under a strict flag **naming
    P-02**", so the per-property form is named rather than the bare flag standing in for both;
    and on a run where the note *was* promoted the subjunctive would be simply false, so it
    says so instead.

    A note carrying no ``severity`` is reported as carrying none. §2.3 makes an absent grade
    meaningful — such a note is not promotable at all — and defaulting it to ``warning`` would
    be inventing the one fact that decides whether it can gate.
    """
    if note.severity is None:
        grade = "no grade carried"
    elif promoted:
        grade = f"warning-grade, promoted by {STRICT_OPTION}"
    else:
        grade = f"warning-grade, promotable under {STRICT_OPTION}={owner}"
    lines = [f"  note: witness note {note.kind} ({grade})"]
    lines.extend(f"    at {_render_location(location)}" for location in note.locations or ())
    return lines


def _strict_flag(policy: StrictPolicy) -> str:
    """The command line that produced ``policy``, as one string — §5.1 obligation 6's "policy".

    Written once because it is shown twice, on the item and in the closing report, and two
    spellings of one policy would be two things to keep in step. The ``off`` arm is named
    rather than left to fall through an empty join: a promotion cannot arise under it, and a
    rendering that said ``--gebra-strict=`` where nothing was passed would be a claim about a
    command line the user did not type.
    """
    if policy.mode == "all":
        return STRICT_OPTION
    if policy.mode == "per-property":
        return f"{STRICT_OPTION}={','.join(policy.properties)}"
    return "no strict policy"


def _render_promoted(record: PromotedRecord, policy: StrictPolicy) -> list[str]:
    """One promoted record — §4.6 rule 8's rendering, with the grade joined back to it.

    Three things this must not do, each of which rule 8 names: show the promotion's
    ``property_condition`` as a grade (it names the *item*; for P-02's note that id is
    registered FATAL while the record is a WARNING-grade note), show a HEURISTIC record with a
    DEFENSIBLE finding's weight (rule 6, "the gate changed; the finding did not"), or imply
    the envelope was rewritten. So the record's own grade leads, the promoted-item identity
    follows as an identity, and the policy that selected it is beside it.
    """
    flag = _strict_flag(policy)
    if record.origin == "witness-note":
        # The grade is the joined record's, not a constant: a promotion that found no record
        # says so through `joined` below rather than by asserting a grade it did not read.
        head = f"  promoted by {flag}: witness note {record.label} ({record.severity}-grade)"
    else:
        grade = f" [{record.claim_class}]" if record.claim_class is not None else ""
        origin = "" if record.origin == "failure" else f" ({record.origin})"
        head = f"  promoted by {flag}: {record.severity.upper()}{origin} {record.label}{grade}"
    lines = [head]
    if record.reported_under is not None:
        lines.append(
            f"    reported under {record.reported_under} — the promoted item's identity, "
            "not a grade\n      (REPORT-FORMAT-SPEC §4.6 rule 8)"
        )
    if record.promotion.location is not None:
        lines.append(f"    at {_render_location(record.promotion.location)}")
    if not record.joined:
        lines.append(
            "    the record this promotion names was not found beside it; the grade shown is "
            "§2.3's\n      rule that only WARNING-grade records are promotable, not a reading "
            "of the record"
        )
    lines.append(
        "    the record is unchanged — it keeps `severity: warning` and its claim class; "
        "only the\n      gate moved (PROPERTY-CATALOG-SPEC §0.2)"
    )
    return lines


def _render_failure(outcome: ItemOutcome, verification: TargetVerification) -> str:
    """The message a failing item carries. Facts only — findings, anchors, claim classes."""
    check = outcome.check
    lines = [f"gebra · {check.target} · {check.property}"]
    if outcome.tool_error is not None:
        lines.append(
            f"  no verdict was reached — {outcome.tool_error}\n"
            "    exit 2 is never a verification result (REPORT-FORMAT-SPEC §2.4)."
        )
    lines.extend(_render_finding(finding) for finding in outcome.blocking)
    policy = verification.report.gate.strict
    for record in promoted_records(outcome):
        lines.extend(_render_promoted(record, policy))
    lines.extend(_render_notes(outcome, verification))
    subject = verification.report.subject
    if subject is not None:
        lines.append(
            f"  subject: {subject.graph_version} ({subject.input_mode}, ir {subject.ir_version})"
        )
    return "\n".join(lines)


def _promoted_identities(outcome: ItemOutcome) -> tuple[set[object], set[object]]:
    """Which of this item's findings and notes were promoted, so nothing is printed twice."""
    findings: set[object] = {
        (promotion.origin, promotion.property_condition, promotion.location)
        for promotion in outcome.promotions
        if promotion.origin != "witness-note"
    }
    # Kind is a sufficient key for the note side: a strict policy matches on the owning
    # property, and `verify()` selects every WARNING-grade note of a named property or none of
    # them — so one kind is never half-promoted within one item.
    notes: set[object] = {
        promotion.note_kind
        for promotion in outcome.promotions
        if promotion.origin == "witness-note"
    }
    return (findings, notes)


def _render_notes(outcome: ItemOutcome, verification: TargetVerification) -> list[str]:
    """Everything the item records without failing on it.

    Four kinds now. A WARNING-grade **finding** this property owns. A structured
    :class:`~gebra.verify.WitnessNote` its report carries — the channel TE-06 left unbuilt,
    and the one ``--gebra-strict`` reaches that no finding walk can see. An
    INTROSPECTION-SPEC §8 extraction warning about how the IR was obtained at all. And —
    attached to a **passing** item as much as to a failing one — the §0.3 qualifier, because a
    P-04 pass on an ill-formed topology is a qualified pass and dropping the qualifier is what
    would turn a diagnostic into a verdict (§5.1 obligation 7).

    A record the strict policy promoted is omitted here: it is rendered in the promotion block
    instead, where its grade and the identity it is reported under are kept apart. Printing it
    in both places would be the same record twice under two labels.

    Where these end up: on the item's own report section, which pytest prints for a failing
    item and, for a passing one, only under ``-rA``/``-rP`` — and, so that a default
    ``pytest`` run cannot swallow them, in the run's closing gebra report
    (:func:`pytest_terminal_summary`). §8's "warnings are never silently droppable" is what
    makes the extraction warning an obligation rather than a nicety.
    """
    promoted_findings, promoted_notes = _promoted_identities(outcome)
    # A WARNING-grade **finding** renders as a finding, with the envelope's own severity word
    # (§5.1 obligation 3) — not under the `note` label, which that same obligation reserves for
    # witness notes and which §2.1 keeps categorically apart from findings. That it did not
    # fail the item is said in words rather than by relabelling the record.
    lines = [
        f"{_render_finding(finding)}\n    advisory under the default mapping — a WARNING-grade "
        f"finding is reported, not gated (D-10 In-Scope 2)"
        for finding in outcome.notes
        if (finding.origin, finding.property_condition, finding.location) not in promoted_findings
    ]
    for note in outcome.witness_notes:
        if note.kind not in promoted_notes:
            lines.extend(_render_witness_note(note, owner=outcome.check.property, promoted=False))
    lines.extend(f"  note: {note.render()}" for note in verification.extraction_notes)
    if outcome.best_effort:
        lines.append(
            "  note: P-01 found the topology ill-formed, so this property's result on this "
            "run is\n    a best-effort diagnostic, not a contract-bearing verdict "
            "(PROPERTY-CATALOG-SPEC §0.3)."
        )
    return lines


# ── The pytest surface: hooks ────────────────────────────────────────────────────────────


def pytest_configure(config: pytest.Config) -> None:
    """Register the marker, parse the gate flags, and arm the run's collectors.

    The flags are parsed here rather than at first use so that a mistyped slug ends the
    session at configure time with one message, instead of surfacing as a collection error on
    every marked function in the tree.
    """
    config.addinivalue_line(
        "markers",
        f"{MARKER}(name=..., sidecar=...): verify the workflow this function returns — one "
        "test item per gebra property. `name` labels the target in the item id, defaulting "
        "to the function name without its `test_` prefix; `sidecar` is an explicit "
        "`gebra.toml` path for the extraction.",
    )
    config.addinivalue_line(
        "markers",
        f"{FRESHNESS_MARKER}(name=..., store=..., sidecar=...): fail if the workflow this "
        "function returns is not the snapshot the store currently holds (brief D-11 In-Scope "
        "7). `store` is the `.gebra/` directory, relative to rootdir, defaulting to "
        "`.gebra`; `name` and `sidecar` are as the `gebra` marker's. Nothing is written.",
    )
    config.stash[NOTES_KEY] = []
    config.stash[REPORT_KEY] = {}
    policy = _parse_policy(config)
    if policy is not None:
        config.stash[POLICY_KEY] = policy


def _record_notes(config: pytest.Config, where: str, notes: list[str]) -> None:
    """Put notes with no report block behind them where a default run will still show them.

    The `gebra_graph` surface is the one that needs this: it hands back the IR and never
    verifies, so nothing else in the closing report would speak for its extraction warnings.
    A verified target's notes ride its own report block instead, once per target rather than
    once per item.
    """
    collected = config.stash.get(NOTES_KEY, None)
    if collected is None:  # a Config this plugin never configured (a bare hook call)
        return
    collected.extend((where, note.strip()) for note in notes)


@dataclass(frozen=True)
class _Block:
    """One entry of the closing report: a verified target, and which surface produced it.

    ``itemized`` is what keeps the ``--gebra-select``/``--gebra-skip`` line off a block it
    would misdescribe: those flags subset *marker items*, and the ``gebra_verification``
    surface has none, so a line about which properties got an item is a statement about a
    different surface.
    """

    verification: TargetVerification
    itemized: bool


def _record_verification(
    config: pytest.Config, where: str, result: TargetVerification, *, itemized: bool
) -> None:
    """Remember one verified target for the closing report, first sighting wins.

    First wins because the five items of a target each re-verify it (there is deliberately no
    cross-item cache) and produce equal reports; keeping the first is what makes the closing
    report one block per target instead of five copies of one.
    """
    collected = config.stash.get(REPORT_KEY, None)
    if collected is None:
        return
    collected.setdefault(where, _Block(verification=result, itemized=itemized))


def _target_key(nodeid: str, property_slug: PropertySlug) -> str:
    """One item's nodeid with the gebra parametrization removed — the target's own reference.

    ``pytest_generate_tests`` builds the id as ``<target>-<slug>`` and runs ``trylast``, so in
    the ordinary case the gebra component is the tail of the last bracket group. It is not
    *guaranteed* to be: pytest's own duplicate-id disambiguation appends an index
    (``[…-graph-well-formed0]``), and another ``trylast`` plugin could parametrize after this
    one. Both land on the second branch, which keys by the whole nodeid — one block per *item*
    rather than one per target. That is the safe direction, and the reason this is a fallback
    rather than a refusal: the report gets more verbose and nothing is dropped.

    What the key cannot do is *merge* two different targets, which is the direction that would
    report one graph's verdicts under another's name. The target label is a marker keyword,
    constant per function definition, so within one function only the user's own
    parametrizations vary and pytest has already made those ids unique; across functions the
    nodeid prefix differs.
    """
    suffix = f"-{property_slug}]"
    return f"{nodeid.removesuffix(suffix)}]" if nodeid.endswith(suffix) else nodeid


def _witness_summary(witness: Witness | None) -> str:
    """One line of what a passing property actually checked — §5.1 obligation 4.

    "A property that passed appears with its claim class and a witness summary; a reader can
    see what was checked, not merely that nothing was said." Counts and shapes only, in
    witness-presence wording (§4.6 rule 2): P-02's line says every simple cycle carries a
    *declared bound* and that the certificate is re-checkable, and it says nothing about what
    the workflow does when it runs, which is not observed by anything here.
    """
    from gebra.verify import (
        DataflowWitness,
        EffectSafetyWitness,
        TerminationWitness,
        WellFormednessWitness,
    )

    if witness is None:
        return "no witness"
    if isinstance(witness, WellFormednessWitness):
        return (
            f"{len(witness.reachable_from_start)} nodes reachable from START · "
            f"{len(witness.terminal_nodes)} terminal · {len(witness.orphan_nodes)} orphans · "
            f"{len(witness.unresolved_targets)} unresolved targets"
        )
    if isinstance(witness, TerminationWitness):
        forms = "/".join(sorted({entry.form for entry in witness.inventory}))
        forms = f" (form {forms})" if forms else ""
        if witness.cycles is None:
            # §4.3: an aborted census is "never rendered as 'no cycles'". Whether one was
            # aborted is the `cycle-census-capped` note's to say, and it is rendered as a note.
            census = " · no census carried"
        else:
            census = f" · census exhaustive under the cap: {len(witness.cycles.cycles)} cycles"
        return (
            f"{len(witness.inventory)} declared-bound entries{forms} · re-checkable "
            f"certificate over {len(witness.certificate)} vertices{census}"
        )
    if isinstance(witness, DataflowWitness):
        return f"{len(witness.coverage)} (reader, key) obligations covered"
    if isinstance(witness, EffectSafetyWitness):
        records = " · ".join(_render_effect_record(record) for record in witness.effects)
        head = f"{len(witness.cycles)} non-trivial SCCs · {len(witness.effects)} effect records"
        return f"{head} · {records}" if records else head
    # The §0.3 witness union has exactly these five members, so the last needs no guard —
    # and a member added to it lands here as a type error rather than as a silent fallthrough.
    # §4.3 asks for "the `claim_class: heuristic` it carries in-band", and the caller has
    # already put P-08's catalog class on this line. The two are the same closed literal by
    # construction — `DeterminismWitness.claim_class` is `Literal["heuristic"]` and the
    # registry row is `("heuristic",)` — so one rendering discharges both, and printing it
    # twice would only read as two different facts.
    if not witness.claims:
        # §4.3: "never 'all deterministic'" — a vacuous pass says what it did not check.
        return "no node declared determinism, so nothing was checked"
    # §4.3: the caveat renders "verbatim and adjacent to the claims it qualifies, never in a
    # footnote a reader can miss" — so it leads, rather than trailing a list of node names.
    caveat = "" if witness.caveat is None else f"{witness.caveat} · "
    claims = " · ".join(_render_determinism_claim(claim) for claim in witness.claims)
    return f"{len(witness.claims)} declared claims · {caveat}{claims}"


def _render_effect_record(record: P06EffectRecord) -> str:
    """One P-06 record — §4.3's per-region fact set, with the protection's own evidence.

    ``none_required`` says why rather than reading as "protected", which §4.3 forbids in terms;
    the two binding protections name what satisfied them, which is what makes them evidence.
    """
    where = f"in {record.region}" + ("" if record.cycle is None else f" {list(record.cycle)}")
    if record.protection == "idempotency_key":
        how = f"protected by idempotency key {record.key!r}"
    elif record.protection == "compensation_hook":
        how = f"protected by compensation hook {record.hook!r}"
    else:
        how = f"no obligation arose ({record.region} region)"
    return f"{record.node} [{', '.join(record.effect)}] {where}: {how}"


def _render_determinism_claim(claim: DeterminismClaim) -> str:
    """One P-08 claim — §4.3's two rows, by the ``llm_backed`` split the model already carries."""
    if not claim.llm_backed:
        return f"{claim.node} ({claim.basis}, no pinning required)"
    echo = "" if claim.divergence_handling is None else f", divergence {claim.divergence_handling}"
    return f"{claim.node} (llm-backed, seed={claim.seed}, temperature={claim.temperature}{echo})"


def _elide_digest(graph_version: str, *, keep: int = 16) -> str:
    """A ``sha256:…`` digest, shortened for a terminal line — §5.1 obligation 1's allowance.

    "Elided for length is fine; a digest prefix must be recognizable as a prefix", so the
    algorithm label is kept and the ellipsis is the marker that this is not the whole thing.
    The full digest is on ``gebra_verification.report.subject.graph_version``, which is what a
    suite comparing against a stored snapshot reads.
    """
    algorithm, separator, value = graph_version.partition(":")
    if not separator or len(value) <= keep:
        return graph_version
    return f"{algorithm}:{value[:keep]}…"


def _render_property_line(outcome: PropertyOutcome, report: RunReport) -> list[str]:
    """One property's block in the closing report — a verdict, or the statement that there is none.

    §4.2's three report-level rows, each with the facts that row names: the property **id** and
    slug on every one; on a pass, the claim class read from the catalog (a pass carries no
    per-record grade — §4.6 rule 1) and a §4.3 witness summary; on a fail, the primary finding
    per §4.4 and **every** co-failure and advisory rendered too, "never summarized away"; on a
    marker, *not checked*, that it is outside the Phase-0 wedge, and explicitly not a pass.
    """
    from gebra.verify import PropertyReport, property_entry

    slug = outcome.property
    entry = property_entry(slug)
    name = f"{entry.property_id} {slug}"
    if not isinstance(outcome, PropertyReport):
        # §5.1 obligation 5 and §4.6 rule 5: shown, never as a pass, never omitted.
        return [f"  not checked  {name} [{outcome.status}]", f"      {outcome.detail}"]
    lines: list[str] = []
    # Keyed on the record rather than on `result`, which the §0.3 model makes equivalent
    # (`result == "fail"` iff a failure is carried) and which needs no assertion to read.
    failure = outcome.failure
    if failure is not None:
        records = 1 + len(failure.co_failures or ()) + len(failure.advisories or ())
        lines.append(f"  fail         {name} — {records} record(s)")
        lines.extend(_render_record(failure, host=slug))
        for co_failure in failure.co_failures or ():
            lines.extend(_render_record(co_failure, origin="co-failure", host=slug))
        for advisory in failure.advisories or ():
            lines.extend(_render_record(advisory, origin="advisory", host=slug))
    else:
        # §4.6 rule 1: a pass carries no per-record grade, so its class is the catalog's.
        classes = "/".join(entry.claim_classes)
        lines.append(f"  pass         {name} [{classes}] {_witness_summary(outcome.witness)}")
    if slug in report.best_effort:
        # §5.1 obligation 7: stated where its report is, not only in the summary.
        lines.append(
            "      answered on topology P-01 found ill-formed — a diagnostic, not a "
            "contract-bearing verdict"
        )
    return lines


def _render_record(
    record: Failure | CoFailure | Advisory, *, host: PropertySlug, origin: str = "primary"
) -> list[str]:
    """One failure-side record — §4.4's fact set, with §4.5's anchor.

    The severity word is the envelope's own and the claim class is the **record's**, never the
    property's catalog union: §4.6 rule 1 splits those two cases and this is the one that
    carries its own.

    A rider whose own ``property`` is not the report it rides names that property, "which is
    not the host report's" (§2.3) — the attribution that decides which *item* it failed, and
    the one thing about this rendering worth getting right. It is shown only when the two
    differ, so a same-property co-failure does not repeat its host on every line.
    """
    where = "" if origin == "primary" else f" ({origin})"
    owner = getattr(record, "property", None)
    belongs = f" owned by {owner}" if owner is not None and owner != host else ""
    head = (
        f"      {record.severity} {record.property_condition} [{record.claim_class}]"
        f"{where}{belongs}"
    )
    lines = [head, f"        at {_render_location(record.location)}"]
    for name in ("writers_on_other_paths", "downstream_writers"):
        # §4.4's two P04Failure diagnostics: "what makes the finding legible rather than
        # baffling". Read by name because they exist only on that subclass.
        extra = getattr(record, name, None)
        if extra:
            lines.append(f"        {name.replace('_', ' ')}: {', '.join(extra)}")
    subsumed = getattr(record, "subsumed_by", None)
    if subsumed is not None:
        lines.append(f"        owned upstream by {subsumed} — context, not a second charge")
    note = getattr(record, "note", None)
    if note is not None:
        lines.append(f"        {note}")
    remediation = getattr(record, "remediation", None)
    if remediation is not None:
        # §4.4: display-only guidance, clearly separate from the finding, parsed by nothing.
        lines.append(f"        remediation (guidance only): {remediation}")
    return lines


def _render_run(
    where: str,
    verification: TargetVerification,
    itemized: tuple[PropertySlug, ...] | None = None,
) -> list[str]:
    """One verified target, carrying REPORT-FORMAT-SPEC §5.1's obligations onto a pytest run.

    The obligations, in order: a subject line (1); one block per property carrying its property
    id and slug, with every failure-side record rendered per §4.4 and anchored per §4.5 (2), a
    §4.3 witness summary and the catalog claim class on a pass (4), and the marker's status on
    a not-checked (5); the notes under their own label (3); the best-effort qualifier beside
    the reports it qualifies (7); and a closing summary with the counts, the exit code and its
    reason, snapshot eligibility when it is ``false``, and the strict policy together with each
    record it promoted (6).

    **What this is not**, said here because the difference is easy to elide: `gebra verify`'s
    own human profile, which is CLI-03's surface and PD-031's framework. The bound that follows
    is on §4.3 — the witness rows are rendered as *summaries* (counts, forms, and the per-record
    lines §4.3 names as facts), not as the full witness, which stays on
    ``gebra_verification.report`` for a suite that wants it.

    ``itemized`` adds lines the spec does not ask for, because the spec's subject is a CLI run
    with no such flag: when ``--gebra-select``/``--gebra-skip`` narrowed the *items* of **this**
    block's surface, the block says which properties got one and what the run gated on that no
    item could fail. Without them a subset run reads as though all five verdicts below gated
    CI, and only two did — which is the one way this rendering could mislead a reader about
    what the gate actually was. It is ``None`` on a block those flags did not itemize (the
    ``gebra_verification`` surface has no items at all), where the lines would describe
    something else.

    What this is **not** is a machine format. PD-015 (the CLI-D1 ruling) puts the native JSON
    envelope and the SARIF projection on ``gebra verify --format`` — one emitter, owned by
    CLI-01/CLI-03 — and a second serialization invented in a pytest plugin would be a second
    schema for that ruling to reconcile. The whole run is on ``gebra_verification.report`` for
    a suite that wants to write its own.
    """
    report = verification.report
    lines = [where]
    subject = report.subject
    if subject is not None:
        version = "" if subject.version is None else f" · {subject.version}"
        extractor = (
            "" if subject.extractor_version is None else f" · extractor {subject.extractor_version}"
        )
        sidecar = "" if subject.sidecar is None else f" · sidecar {subject.sidecar}"
        lines.append(
            f"  {subject.source} · {_elide_digest(subject.graph_version)} · "
            f"ir {subject.ir_version} · {subject.input_mode}{version}{extractor}{sidecar}"
        )
    error = report.error
    if error is not None:
        # The §8 warnings come **before** the §2.4 early return, not after it. A run that
        # reached no verdict is exactly the run whose extraction warnings are the most
        # diagnostic thing it has — a hintless conditional router warns `unsupported-construct`
        # and stamps `ir_version 1.1`, which `verify()` then refuses as an ir-validation tool
        # error, so "warned and reached no verdict" is that path's normal outcome. §8's
        # "warnings are never silently droppable" has no exception for it.
        lines.extend(_render_run_notes(verification))
        lines.append(f"  no verdict was reached — {error.stage}: {error.detail}")
        lines.append("  exit 2 — a tool error is never a verification result (§2.4).")
        return lines
    for outcome in report.properties:
        lines.extend(_render_property_line(outcome, report))
    lines.extend(_render_run_notes(verification))
    if itemized is not None:
        names = ", ".join(itemized) or "nothing"
        lines.append(
            f"  {SELECT_OPTION}/{SKIP_OPTION} generated an item for: {names} — the run carried "
            "all thirteen outcomes either way, and the exit code below is the **run's**, not "
            "this pytest session's"
        )
        lines.extend(_render_ungated(report, itemized))
    lines.extend(_render_gate(report))
    return lines


def _render_ungated(report: RunReport, itemized: tuple[PropertySlug, ...]) -> list[str]:
    """What the run gated on that no item could fail — the cost of subsetting, said out loud.

    ``--gebra-select``/``--gebra-skip`` narrow the items while ``verify()`` still gates over
    the whole catalog, so a blocking finding or a strict promotion owned by a property with no
    item moves ``gate.exit_code`` and leaves every pytest item green. That is the user's
    explicit request and it is not refused — but §2.2 makes ``exit_code`` the contract, and a
    gate the user was owed must not go missing in silence, so the block counts what fell
    outside the subset and names the properties.
    """
    blocking = [
        record for record in _records(report) if record.blocking and record.owner not in itemized
    ]
    promoted = [
        promotion for promotion in report.gate.promotions if promotion.property not in itemized
    ]
    if not blocking and not promoted:
        return []
    owners = sorted({record.owner for record in blocking} | {p.property for p in promoted})
    head = (
        f"      {len(blocking)} blocking finding(s) and {len(promoted)} promotion(s) fall "
        f"outside that subset — {', '.join(owners)}. No item could fail on them;"
    )
    return [head, "      the run's own exit code did."]


def _render_run_notes(verification: TargetVerification) -> list[str]:
    """The run's notes, once per target: the §8 extraction warnings and every witness note."""
    from gebra.verify import PropertyReport

    report = verification.report
    lines = [f"  note: {note.render()}" for note in verification.extraction_notes]
    promoted = {
        (promotion.property, promotion.note_kind)
        for promotion in report.gate.promotions
        if promotion.origin == "witness-note"
    }
    for outcome in report.properties:
        if not isinstance(outcome, PropertyReport):
            continue
        for note in notes_for(report, outcome.property):
            lines.extend(
                _render_witness_note(
                    note,
                    owner=outcome.property,
                    promoted=(outcome.property, note.kind) in promoted,
                )
            )
    return lines


def _render_gate(report: RunReport) -> list[str]:
    """§5.1 obligation 6's closing summary — counts, exit code and reason, policy, promotions.

    Deliberately no "checks passed" tally: §4.6 rule 5 keeps a not-implemented marker out of
    one and rule 9 keeps a best-effort report out of one, and the honest number is how many
    properties reported at all beside how many did not.
    """
    from gebra.verify import PropertyReport

    gate = report.gate
    reported = sum(1 for outcome in report.properties if isinstance(outcome, PropertyReport))
    counts = gate.counts
    qualified = f" · {len(report.best_effort)} best-effort" if report.best_effort else ""
    policy = gate.strict
    strict = "strict off" if policy.mode == "off" else f"strict {_strict_flag(policy)}"
    promoted = f"; {len(gate.promotions)} promoted" if gate.promotions else ""
    tally = (
        f"  {reported} properties reported · {len(report.properties) - reported} not checked · "
        f"{counts.fatal} fatal · {counts.error} error · {counts.warning} warning{qualified}"
    )
    lines = [tally, f"  exit {gate.exit_code} — {gate.outcome}; {strict}{promoted}"]
    records = run_promotions(report)
    if records:
        lines.append(
            f"  promoted by {_strict_flag(gate.strict)} — the gate moved, the records did "
            "not (§0.2):"
        )
        for record in records:
            lines.extend(_render_promotion_line(record))
    if not gate.snapshot_eligible:
        lines.append("  no snapshot is recorded for this run — a FATAL finding is present (§0.2).")
    return lines


def _render_promotion_line(record: PromotedRecord) -> list[str]:
    """One promoted record in the closing summary — compact, and still not a grade.

    The verbose form, with the §0.2 sentence and the anchor, is the failing item's
    (:func:`_render_promoted`); here the rule is stated once above the list, so what each entry
    owes is the owning property, the record's own grade, and — kept visibly separate — the
    identity the promoted item is reported under.
    """
    if record.origin == "witness-note":
        label = f"witness note {record.label} (warning-grade)"
    else:
        grade = f" [{record.claim_class}]" if record.claim_class is not None else ""
        label = f"{record.severity.upper()} {record.label}{grade}"
    lines = [f"    {record.promotion.property}: {label}"]
    if record.reported_under is not None:
        lines.append(
            f"      reported under {record.reported_under} — an item identity, not a grade"
        )
    return lines


def pytest_terminal_summary(terminalreporter: Any) -> None:
    """Print the closing gebra report — the human profile of REPORT-FORMAT-SPEC §5.

    One block per verified target, plus any notes from a surface that produced no report of
    its own. Printed with no flag, because that is what makes §5.1's obligations and
    INTROSPECTION-SPEC §8's "warnings are never silently droppable" hold for the primary
    adoption path: a marker-only adopter never touches ``gebra_verification``, so without this
    the passing witnesses and the eight not-checked properties would be invisible and a
    default ``pytest`` run would show five green items and nothing else.

    One bound on the claim, stated rather than left to be found: the blocks are assembled in
    the process that ran the items, off that process's ``Config`` stash. Under a plugin that
    distributes items to worker processes (``pytest-xdist``, named in D-10's own risk table)
    the controller's summary hook has its own ``Config``, so this section is not expected
    there. That has not been measured in this environment — no distributing plugin is
    installed — so it is a statement about how the collection is keyed, not a tested result.
    What survives distribution either way is the per-item report section, which pytest
    serializes back to the controller with the report.
    """
    config = terminalreporter.config
    verified: dict[str, _Block] = config.stash.get(REPORT_KEY, {})
    collected: list[tuple[str, str]] = config.stash.get(NOTES_KEY, [])
    if not verified and not collected:
        return
    policy = config.stash.get(POLICY_KEY, None)
    subsetting = policy is not None and (policy.select is not None or policy.skip)
    itemized = enabled_properties_for(policy) if subsetting and policy is not None else None
    terminalreporter.write_sep("=", "gebra")
    for where, block in verified.items():
        for line in _render_run(where, block.verification, itemized if block.itemized else None):
            terminalreporter.write_line(line)
    previous = None
    for where, note in collected:
        if where != previous:
            terminalreporter.write_line(where)
            previous = where
        terminalreporter.write_line(f"  {note}")


def _marker_argument(marker: pytest.Mark, key: str) -> str | None:
    """One optional string keyword off the marker, refused at collection if unreadable."""
    value = marker.kwargs.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise pytest.UsageError(
            f"@pytest.mark.{MARKER}({key}=...) takes a non-empty string; got {value!r}."
        )
    return value


def _read_marker(marker: pytest.Mark, function_name: str) -> tuple[str, str | None]:
    """The declaration: the target's label in the item id, and its explicit sidecar if any.

    Raises:
        pytest.UsageError: on a positional argument, an unknown keyword, or a non-string
            value. A declaration the plugin cannot read is a usage error at collection, never
            a silently differently-named item or a silently discarded sidecar.
    """
    if marker.args:
        raise pytest.UsageError(
            f"@pytest.mark.{MARKER} takes no positional arguments; got {marker.args!r}. "
            f"Use @pytest.mark.{MARKER}(name='my_agent') and return the workflow from the "
            "function body."
        )
    unknown = set(marker.kwargs) - {"name", "sidecar"}
    if unknown:
        raise pytest.UsageError(
            f"@pytest.mark.{MARKER} takes only `name` and `sidecar`; got {sorted(unknown)!r}."
        )
    name = _marker_argument(marker, "name")
    sidecar = _marker_argument(marker, "sidecar")
    return (name or function_name.removeprefix("test_") or function_name, sidecar)


@pytest.hookimpl(trylast=True)
def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    """Parametrize a marked function into one item per enabled property.

    One :meth:`~pytest.Metafunc.parametrize` call with explicit ids, which is what produces
    D-10's ``test_gebra[travel_agent-termination-witness]`` spelling. The argname is a fixture
    this plugin defines and is pushed onto the closure first, so a marked function that does
    not request ``gebra_check`` — the ordinary case, since the function's job is to return a
    graph — is still parametrizable; one that *does* request it gets its :class:`GebraCheck`.

    ``trylast`` so that the user's own ``@pytest.mark.parametrize`` is applied first and the
    gebra component lands at the **end** of the id: ``test_gebra[express-travel_agent-
    termination-witness]`` reads outward-in, and the plain case — no other parametrization —
    is unaffected either way. Each combination is verified on its own; nothing is reused
    across them.
    """
    marker = metafunc.definition.get_closest_marker(MARKER)
    if marker is None:
        return
    if metafunc.definition.get_closest_marker(FRESHNESS_MARKER) is not None:
        # Refused rather than resolved, because either resolution is a silent drop: this hook
        # parametrizes the function into property items and `pytest_pyfunc_call` then takes the
        # `gebra` branch, so the freshness declaration would simply never run. The two markers
        # ask different questions of the same function and want two functions.
        raise pytest.UsageError(
            f"@pytest.mark.{MARKER} and @pytest.mark.{FRESHNESS_MARKER} are both on "
            f"{metafunc.function.__name__!r}. They are different checks — one verifies the "
            "workflow's properties, the other compares it against the store — so put them on "
            "two functions rather than have one of them silently not run."
        )
    target, sidecar = _read_marker(marker, metafunc.function.__name__)
    slugs = enabled_properties(metafunc.config)
    if not slugs:
        policy = gate_policy(metafunc.config)
        reason = (
            "no validator is registered"
            if policy.select is None and not policy.skip
            else (
                f"{SELECT_OPTION}/{SKIP_OPTION} left nothing to check "
                f"(select={policy.select}, skip={policy.skip})"
            )
        )
        raise pytest.UsageError(
            f"@pytest.mark.{MARKER} has no property to check: {reason}. "
            "A gebra run that checked nothing must not report a green item."
        )
    if CHECK_PARAM not in metafunc.fixturenames:
        metafunc.fixturenames.append(CHECK_PARAM)
    metafunc.parametrize(
        CHECK_PARAM,
        [GebraCheck(target=target, property=slug, sidecar=sidecar) for slug in slugs],
        ids=[f"{target}-{slug}" for slug in slugs],
        indirect=True,
    )


def _check_for(item: pytest.Function) -> GebraCheck | None:
    """This item's :class:`GebraCheck`, or ``None`` if the item is not one of ours."""
    callspec = getattr(item, "callspec", None)
    if callspec is None:
        return None
    check = callspec.params.get(CHECK_PARAM)
    return check if isinstance(check, GebraCheck) else None


def _call_target(item: pytest.Function) -> object:
    """Call the marked function with its fixtures, the way pytest's own runner would.

    Literally the way: the argument names come from ``item._fixtureinfo.argnames``, which is
    the same list ``_pytest.python.pytest_pyfunc_call`` builds its ``testargs`` from. That is
    a private attribute, and it is chosen **over** the public ``inspect.signature`` on
    never-invokes grounds rather than despite them. Under PEP 649 (Python 3.14),
    ``inspect.signature`` reads ``__annotations__`` at ``Format.VALUE`` and therefore
    *evaluates* the marked function's parameter annotations — arbitrary user expressions
    running inside a verification path, which is INTROSPECTION-SPEC §1 rule 3's hazard class.
    pytest refuses that on the same objects for the same reason (``_pytest.compat.signature``,
    "return signature without evaluating annotations"). Reading a list pytest already computed
    touches no annotation on any version, so this removes the hazard instead of version-gating
    it, and it cannot disagree with pytest about which fixtures a function takes.

    An ``async def`` never reaches the call: pytest's own guard lives in the implementation
    this hook displaces, so the refusal has to be re-stated here or an un-awaited coroutine
    would travel on to the extractor and be refused as "not a LangGraph object", which is a
    true statement and a useless one.
    """
    function = item.obj
    # Both surfaces call this, so the refusal names the marker the user actually wrote rather
    # than the one this function was written for.
    marker = MARKER if item.get_closest_marker(MARKER) is not None else FRESHNESS_MARKER
    if inspect.iscoroutinefunction(function) or inspect.isasyncgenfunction(function):
        raise GebraTargetError(
            f"@pytest.mark.{marker} function {item.originalname!r} is async. gebra verifies "
            "a workflow *definition* and never runs anything, so its target factory has "
            "nothing to await — declare it with `def`, and build the graph synchronously."
        )
    kwargs = {name: item.funcargs[name] for name in item._fixtureinfo.argnames}
    result: object = function(**kwargs)
    if hasattr(result, "__await__") or hasattr(result, "__aiter__"):
        raise GebraTargetError(
            f"@pytest.mark.{marker} function {item.originalname!r} returned an awaitable. "
            "Return the workflow itself; gebra never runs anything and will not await it."
        )
    return result


def _verification_for(item: pytest.Function, check: GebraCheck) -> TargetVerification:
    """Call the target factory and verify what it returned, for this one item.

    Deliberately **not** cached across the items of a target. A cache key would have to
    exclude this plugin's own parameter and include every other parametrization of the same
    function, and there is no public spelling of that key whose collisions are impossible —
    a false hit is a wrong verdict, which is a worse failure than a repeated extraction. It
    would also buy nothing under ``pytest-xdist``, where sibling items run in different
    processes. The cost is one extraction and one ``verify()`` per property; the benefit is
    that each item is independent, so ``-k``, ``-x``, reruns and distribution all behave.
    """
    target = _call_target(item)
    if target is None:
        raise GebraTargetError(
            f"@pytest.mark.{MARKER} function {item.originalname!r} returned None. The "
            "function body must return the workflow to verify — a StateGraph, a compiled "
            "graph, an LCEL Runnable, or a gebra WorkflowIR."
        )
    source = f"{item.location[0]}::{item.originalname}#{check.target}"
    return verify_target(
        target,
        name=check.target,
        source=source,
        sidecar=check.sidecar,
        strict=gate_policy(item.config).strict,
    )


# ── The snapshot-freshness gate (brief D-11 In-Scope 7) ──────────────────────────────────


@dataclass(frozen=True)
class FreshnessCheck:
    """One ``@pytest.mark.gebra_freshness`` declaration: a target, and the store it is about.

    Attributes:
        target: The declared target name — what the item's message calls the workflow.
        store: The ``.gebra/`` directory to check against, already resolved to an absolute
            path. A relative ``store=`` is resolved against pytest's ``rootdir``, not the
            process's working directory: a CI check whose meaning depended on where ``pytest``
            was invoked from would pass and fail for reasons nobody could see in the log.
        sidecar: An explicit ``gebra.toml`` for the extraction, as the ``gebra`` marker's.
    """

    target: str
    store: Path
    sidecar: str | None = None


def _read_freshness_marker(
    marker: pytest.Mark, function_name: str, rootpath: Path
) -> FreshnessCheck:
    """The freshness declaration, refused at call time if it cannot be read.

    Raises:
        pytest.UsageError: on a positional argument, an unknown keyword, or a non-string
            value — the same discipline :func:`_read_marker` applies, for the same reason.
    """
    if marker.args:
        raise pytest.UsageError(
            f"@pytest.mark.{FRESHNESS_MARKER} takes no positional arguments; got "
            f"{marker.args!r}. Use @pytest.mark.{FRESHNESS_MARKER}(name='my_agent') and return "
            "the workflow from the function body."
        )
    unknown = set(marker.kwargs) - {"name", "sidecar", "store"}
    if unknown:
        raise pytest.UsageError(
            f"@pytest.mark.{FRESHNESS_MARKER} takes only `name`, `sidecar` and `store`; got "
            f"{sorted(unknown)!r}."
        )
    from gebra.store import STORE_DIRNAME

    name = _marker_argument(marker, "name")
    store = _marker_argument(marker, "store")
    return FreshnessCheck(
        # `rootpath / absolute` is `absolute` — pathlib's join rule, which is exactly the
        # "relative to rootdir, absolute as given" reading this wants, without a branch.
        target=name or function_name.removeprefix("test_") or function_name,
        store=rootpath / (store if store is not None else STORE_DIRNAME),
        sidecar=_marker_argument(marker, "sidecar"),
    )


def check_freshness(target: object, *, store: Path, sidecar: str | None = None) -> FreshnessOutcome:
    """Resolve ``target`` to IR and ask :func:`gebra.audit.freshness` about it.

    The programmatic half of the marker, for a suite that would rather hold the outcome than
    have an item fail on it. Extraction is :func:`resolve_ir`'s, so a ``WorkflowIR`` handed in
    is used as it stands and nothing imports the substrate on that path.

    Args:
        target: The workflow object, or a :class:`~gebra.ir.WorkflowIR` already in hand.
        store: The ``.gebra/`` directory to check against. Nothing is created and nothing is
            written: a store that does not exist reads as an empty one, which is the
            ``unsnapshotted`` outcome rather than an error.
        sidecar: An explicit ``gebra.toml`` path, per :func:`resolve_ir`.

    Returns:
        The :class:`~gebra.audit.models.FreshnessOutcome`.

    Raises:
        GebraTargetError: if the target could not be reduced to IR.
        ValueError: if the check could not be made over an IR that was — a document repeating a
            node id (IR-SPEC §2.1, DEC-22), or a store whose index or current snapshot is not
            readable (:class:`~gebra.store.store.StoreError`).
        gebra.ir.DynamicEdgeUnsupportedError: if the target's IR, or the store's current
            snapshot, carries a ``dynamic`` edge — the ir 1.1 decline
            :func:`gebra.audit.freshness` makes (DEC-28). On the marker surface it is rendered
            as "the freshness check could not be made", beside the two above; the item is
            neither fresh nor stale, because no comparison was made.
    """
    from gebra.audit import freshness
    from gebra.store import SnapshotStore

    return freshness(resolve_ir(target, sidecar=sidecar).ir, store=SnapshotStore(store))


def _freshness_state_is_unsnapshotted(outcome: FreshnessOutcome) -> bool:
    """Whether the store held nothing — read through the engine's own enum, not a string."""
    from gebra.audit import Freshness

    return outcome.state is Freshness.UNSNAPSHOTTED


def _render_freshness(check: FreshnessCheck, outcome: FreshnessOutcome) -> str:
    """A failing freshness item's message — the whole answer, and what to do about it.

    The engine's own :meth:`~gebra.audit.models.FreshnessOutcome.summary` is the body, indented
    under this plugin's ``gebra · <target> · …`` header, so the words a pytest run shows and
    the words any other consumer shows are one text rather than two that can drift apart.

    The footer is per-state rather than fixed, because the fixed one was wrong on the empty
    store: "it reports that the content moved" describes a comparison that path never made.
    Both spellings say the same thing about what a freshness check is — a statement about the
    store, never a verdict about the workflow — which is the part that has to be there whatever
    the state.
    """
    body = "\n".join(f"  {line}" for line in outcome.summary().splitlines())
    footer = (
        "this is a check on the store, not a verdict about the workflow: it reports that the "
        "content moved and which counters move with it, never whether the change is safe "
        "(P-12 evolution-safety is deferred — SOW §8)."
        if not _freshness_state_is_unsnapshotted(outcome)
        else (
            "this is a check on the store, not a verdict about the workflow: nothing was "
            "compared, because the store holds nothing to compare against."
        )
    )
    return f"gebra · {check.target} · snapshot freshness\n{body}\n    {footer}"


def _run_freshness(item: pytest.Function, marker: pytest.Mark) -> bool:
    """Run one freshness item: build the target, resolve the store, compare, report."""
    check = _read_freshness_marker(marker, item.originalname, item.config.rootpath)
    target = _call_target(item)
    if target is None:
        raise GebraTargetError(
            f"@pytest.mark.{FRESHNESS_MARKER} function {item.originalname!r} returned None. "
            "The function body must return the workflow whose snapshot is being checked — a "
            "StateGraph, a compiled graph, an LCEL Runnable, or a gebra WorkflowIR."
        )
    outcome = check_freshness(target, store=check.store, sidecar=check.sidecar)
    if not outcome.fresh:
        pytest.fail(_render_freshness(check, outcome), pytrace=False)
    return True


@pytest.hookimpl(tryfirst=True)
def pytest_pyfunc_call(pyfuncitem: pytest.Function) -> bool | None:
    """Run one gebra item: the property verdict, or the freshness gate.

    Two surfaces, checked in cost order. The first is a dict lookup on the item's own
    parametrization, which is what a ``@pytest.mark.gebra`` item carries and what the
    overwhelming majority of items in any session do not; only when that misses is the
    ``@pytest.mark.gebra_freshness`` marker looked for, so an ordinary item pays one lookup and
    one ``get_closest_marker`` and nothing else. Returning ``None`` hands the item back to
    pytest's own runner.

    Taking over the call is what lets a marked function *return* its graph without tripping
    pytest's return-not-none warning: the default ``pytest_pyfunc_call`` — the implementation
    that warns — never runs for our items, on either surface.
    """
    check = _check_for(pyfuncitem)
    if check is None:
        freshness_marker = pyfuncitem.get_closest_marker(FRESHNESS_MARKER)
        if freshness_marker is None:
            return None
        # Imported here rather than at module scope for this module's own reason: the closure
        # of a `pytest11` entry point is `pytest` and the standard library (see the module
        # docstring). This branch already imports `gebra.audit` and `gebra.store` by way of
        # `check_freshness`, and both import `gebra.ir`, so naming the exception here costs
        # nothing — while at module scope it would cost every session that marks nothing at all.
        from gebra.ir import DynamicEdgeUnsupportedError

        try:
            return _run_freshness(pyfuncitem, freshness_marker)
        except GebraTargetError as error:
            pytest.fail(
                f"gebra · snapshot freshness\n"
                f"  the working definition could not be obtained, so nothing was compared: "
                f"{error}",
                pytrace=False,
            )
        # `StoreError` and the diff engine's duplicate-node-id refusal are both `ValueError`s,
        # the ir 1.1 decline is a `NotImplementedError` subclass, and all three mean the same
        # thing on this item: the check could not be made. Reporting any of them as "stale"
        # would ask a reader to re-snapshot their way out of a damaged store, an unstorable
        # document, or a construct this build has no semantics for yet — and none of the
        # three is a freshness answer. The 1.1 decline is caught by name because it is *not* a
        # `ValueError`: without this clause it escapes as the one thing this gate must never
        # print, a raw traceback through the plugin's own frames.
        except (DynamicEdgeUnsupportedError, ValueError) as error:
            pytest.fail(
                f"gebra · snapshot freshness\n  the freshness check could not be made: {error}",
                pytrace=False,
            )
    # No `__tracebackhide__` here on purpose. Both refusals below use `pytrace=False`, so a
    # gebra verdict already reports as its message and nothing else; hiding the frame as well
    # would also hide the traceback of an *unexpected* exception raised inside this hook,
    # which is the one case where a plugin frame is exactly what a reader needs.
    try:
        verification = _verification_for(pyfuncitem, check)
    except GebraTargetError as error:
        # REPORT-FORMAT-SPEC §2.4 stage `extraction`: the same class of event as the dispatch
        # error below, so it gets the same words. An item that failed because the IR could not
        # be obtained must not read as a verdict about the property it is named for.
        pytest.fail(
            f"gebra · {check.target} · {check.property}\n"
            f"  no verdict was reached — extraction: {error}\n"
            "    exit 2 is never a verification result (REPORT-FORMAT-SPEC §2.4).",
            pytrace=False,
        )
    _record_verification(
        pyfuncitem.config,
        _target_key(pyfuncitem.nodeid, check.property),
        verification,
        itemized=True,
    )
    outcome = item_outcome(verification, check.property)
    notes = _render_notes(outcome, verification)
    # Only on a passing item: `_render_failure` already carries them, and pytest prints a
    # failing item's report section too, so adding both would print each note twice. The
    # closing report is the surface that does not depend on `-rA`, and it speaks for this
    # target once rather than once per item.
    if notes and not outcome.failed:
        pyfuncitem.add_report_section("call", _REPORT_SECTION, "\n".join(notes))
    if outcome.failed:
        pytest.fail(_render_failure(outcome, verification), pytrace=False)
    return True


# ── The pytest surface: fixtures ─────────────────────────────────────────────────────────


@pytest.fixture
def gebra_check(request: pytest.FixtureRequest) -> GebraCheck:
    """This item's :class:`GebraCheck` — the target name and the property being checked.

    Only meaningful on an item ``@pytest.mark.gebra`` generated; requesting it anywhere else
    is a fixture error, because there is no check for it to be about.
    """
    param: object = getattr(request, "param", None)
    if not isinstance(param, GebraCheck):
        raise pytest.UsageError(
            f"the {CHECK_PARAM!r} fixture is only available on an item generated by "
            f"@pytest.mark.{MARKER}."
        )
    return param


@pytest.fixture
def gebra_workflow() -> object:
    """The workflow under verification — **override this in your ``conftest.py``**.

    The plugin ships the declaration so that ``gebra_graph`` and ``gebra_verification`` have
    something to depend on and so that a missing override is a message rather than a fixture
    lookup error. It has no default value: gebra cannot guess which of your graphs you meant.
    """
    raise pytest.UsageError(
        f"the {WORKFLOW_FIXTURE!r} fixture has no default. Define it in your conftest.py to "
        "declare the workflow gebra_graph and gebra_verification are about:\n\n"
        "    @pytest.fixture\n"
        f"    def {WORKFLOW_FIXTURE}():\n"
        "        return build_my_agent()\n"
    )


@pytest.fixture
def gebra_sidecar() -> str | None:
    """The explicit ``gebra.toml`` path for the fixture surface — override to pin one.

    The marker's ``sidecar=`` for the other surface. ``None`` leaves ANNOTATION-API-SPEC §2's
    rule-2 walk to start from the pytest process's working directory, which the same section
    asks reproducible/CI extraction to avoid: sidecar-filled annotations are inside the
    ``graph_version`` hash scope and they move P-04 and P-06 verdicts, so which ``gebra.toml``
    was in reach is a fact about the run. Whichever one was used is on
    ``gebra_verification.report.subject.sidecar``.
    """
    return None


@pytest.fixture
def gebra_graph(
    request: pytest.FixtureRequest, gebra_workflow: object, gebra_sidecar: str | None
) -> WorkflowIR:
    """The extracted :class:`~gebra.ir.WorkflowIR` of ``gebra_workflow`` — assert against it.

    Extraction runs per test rather than once per session, for the reason
    :func:`_verification_for` gives about caching, and because a session-scoped fixture here
    would force every user's ``gebra_workflow`` override to be session-scoped too. Hand it a
    ``WorkflowIR`` and no extraction — and no substrate import — happens at all.

    Any INTROSPECTION-SPEC §8 warning the extraction raised is recorded on this item and in
    the run's gebra summary rather than discarded: §8 makes warnings "never silently
    droppable", and this fixture returns only the IR, so dropping them here would be the
    silent drop in a surface that never mentions it.
    """
    resolution = resolve_ir(gebra_workflow, sidecar=gebra_sidecar)
    if resolution.notes:
        rendered = [f"  note: {note.render()}" for note in resolution.notes]
        _record_notes(request.config, request.node.nodeid, rendered)
        request.node.add_report_section("setup", _REPORT_SECTION, "\n".join(rendered))
    return resolution.ir


@pytest.fixture
def gebra_verification(
    request: pytest.FixtureRequest, gebra_workflow: object, gebra_sidecar: str | None
) -> TargetVerification:
    """``gebra_workflow`` verified — the whole run, for assertions of your own.

    A :class:`TargetVerification`, not a bare report, and named for what it is: ``.report`` is
    the :class:`~gebra.verify.RunReport` and ``.extraction_notes`` the warnings extraction
    raised on the way. ``.report.properties`` carries all thirteen catalog outcomes, so this
    is where the eight properties Phase-0 defers are visible as the structured
    :class:`~gebra.verify.NotImplementedMarker`\\ s they are; ``.report.gate`` is the §2.2
    exit code and counts.
    """
    verification = verify_target(
        gebra_workflow,
        name=WORKFLOW_FIXTURE,
        source=f"{request.node.nodeid}#{WORKFLOW_FIXTURE}",
        sidecar=gebra_sidecar,
        # The gate a suite asserts on must be the gate CI ran: `--gebra-strict` reaches this
        # surface too, so `.report.gate.exit_code` here and the marker items agree about the
        # same run. `--gebra-select`/`--gebra-skip` deliberately do not — they subset *items*,
        # and this fixture's contract is the whole run, all thirteen outcomes included.
        strict=gate_policy(request.config).strict,
    )
    # Keyed off the *target* rather than the item, on the same terms as the marker path, so
    # that a marked function which also requests this fixture contributes one block here
    # instead of one per generated item — and a suffix, so the two surfaces stay distinct:
    # they verify different objects and would otherwise collide on one key.
    check = _check_for(request.node) if isinstance(request.node, pytest.Function) else None
    base = (
        request.node.nodeid if check is None else _target_key(request.node.nodeid, check.property)
    )
    _record_verification(request.config, f"{base}#{WORKFLOW_FIXTURE}", verification, itemized=False)
    if verification.extraction_notes:
        rendered = [f"  note: {note.render()}" for note in verification.extraction_notes]
        request.node.add_report_section("setup", _REPORT_SECTION, "\n".join(rendered))
    return verification
