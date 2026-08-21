"""Property validators P-01..P-13 and the §0.3 result envelope every report is written in.

Normative authority: PROPERTY-CATALOG-SPEC (with TERMINATION-WITNESS-SPEC for P-02); the
shapes here are the ones ratified at review walkthrough #2 (2026-07-18, DEC-11). The wedge
five (P-01, P-02, P-04, P-06, P-08) come first.

The envelope is one set of models with two duties (A6 PC-6): the same classes validate a
fixture's ``expected:`` block and a validator's output, so a fixture cannot drift from the
result type and comparison is model equality, never raw-dict or string equality::

    from gebra.verify import PropertyReport, validate_report

    report = validate_report({"property": "graph-well-formed", **fixture["expected"]})
    report.result                      # "pass" | "fail"
    report.witness                     # present iff result == "pass"
    report.failure.property_condition  # a §0.4 registry member

The two registries are the emission and dispatch surfaces everything else is written
through::

    from gebra.verify import emit_failure, run_property

    failure = emit_failure("graph-well-formed", "node-unreachable-from-start", location)
    failure.severity            # "fatal" — read off §0.4, never restated by the validator
    run_property("retry-coherence", ir)   # a structured not-implemented marker, not a pass

The surface, by module: :mod:`gebra.verify.base` holds the frozen base, the scalar
vocabulary (:data:`~gebra.verify.base.Severity`, :data:`~gebra.verify.base.ClaimClass`,
:data:`~gebra.verify.base.PropertySlug`, the closed
:data:`~gebra.verify.base.ConditionId`), the START/END display-sentinel convention and the
PC-4 serialization profile; :mod:`gebra.verify.locations` holds the six structural anchors
and the wedge's concrete subtypes; :mod:`gebra.verify.witnesses` holds the five wedge
witness models; :mod:`gebra.verify.report` holds ``Failure``/``CoFailure``/``Advisory`` and
``PropertyReport``; :mod:`gebra.verify.conditions` holds the §0.4 condition-ID registry, the
tier rules and the emission constructors; :mod:`gebra.verify.registry` holds the thirteen-slug
property table, validator registration and dispatch; :mod:`gebra.verify.graph` holds the shared
pre-analysis the four topology-facing validators read their graph from — label expansion,
sentinel-augmented model construction, Tarjan SCC and the condensation utilities;
:mod:`gebra.verify.guards` holds P-02's form-(a) recognizer — the TERMINATION-WITNESS-SPEC
§3 guard grammar over declared ``condition`` strings (the L0 lexical gate and rules R0–R6),
kept separate from R1's Σ-side half, the §2.1 integer-compatibility test, which is asked as
its own call; it emits nothing, and its verdicts are not condition IDs;
:mod:`gebra.verify.properties` holds the
wedge validators themselves, each registering itself on import — all five: P-01
:func:`~gebra.verify.properties.graph_well_formed.check_graph_well_formed`, P-02
:func:`~gebra.verify.properties.termination_witness.check_termination_witness`, P-04
:func:`~gebra.verify.properties.dataflow_completeness.check_dataflow_completeness`, P-06
:func:`~gebra.verify.properties.effect_safety.check_effect_safety` and P-08
:func:`~gebra.verify.properties.determinism_replay.check_determinism_replay`.

One function here answers a **gate** question rather than producing a record:
:func:`~gebra.verify.properties.termination_witness.strict_promotions` selects the
WARNING-grade P-02 records a ``--gebra-strict`` policy promotes and attaches the condition ID
TERMINATION-WITNESS-SPEC §6.1's strict row reports them under. It returns promotions, never a
report: §0.2 and DEC-11 item 6 keep the record unchanged under promotion.

Above the per-property reports sits the run: :mod:`gebra.verify.run` holds
``docs/specs/REPORT-FORMAT-SPEC.md``'s run-level wrapper — the shape §0.3's scope boundary
hands that document — and :func:`~gebra.verify.run.verify`, which runs the wedge five over one
IR and derives the gate::

    from gebra.verify import RunPolicy, StrictPolicy, verify

    report = verify(ir)                    # all thirteen outcomes, in catalog order
    report.gate.exit_code                  # 0 pass · 1 fail · 2 no verdict reached
    report.gate.snapshot_eligible          # §2.5 — FATAL alone suppresses recording
    verify(ir, RunPolicy(strict=StrictPolicy(mode="all"))).gate.promotions

The split is the one §0.2 draws: a validator produces the **record** and never reads a flag;
the gate is where a strict policy changes an exit code, with every record left as it stands.

Nothing here imports langgraph, executes a workflow node, calls a model, or opens a network
connection (WA-07): a validator reads serialized IR and returns structured values.
"""

from gebra.verify.base import (
    END,
    START,
    ClaimClass,
    ConditionId,
    DisplayNodeRef,
    NodeId,
    PropertyId,
    PropertySlug,
    ReportModel,
    SetCompared,
    Severity,
    from_display,
    json_text,
    models_equivalent,
    set_compared_fields,
    to_data,
    to_display,
    to_json,
)
from gebra.verify.conditions import (
    CONDITION_IDS,
    CONDITION_REGISTRY,
    EMITTABLE_CONDITION_IDS,
    PROPOSED_CONDITION_IDS,
    RATIFIED_CONDITION_IDS,
    RESERVED_CONDITION_IDS,
    UNREGISTERED_CORPUS_STRINGS,
    AdvisoryCarriageError,
    ConditionEntry,
    ConditionOwnershipError,
    ConditionRegistryError,
    ConditionTier,
    NonEmittableConditionError,
    UnregisteredConditionError,
    condition,
    conditions_for,
    emit_advisory,
    emit_co_failure,
    emit_failure,
    emittable_condition,
    is_emittable,
    is_registered,
    property_for_condition,
)
from gebra.verify.graph import (
    END_VERTEX,
    SENTINEL_VERTICES,
    START_VERTEX,
    Components,
    EdgeKind,
    EdgeOrigin,
    ExpandedEdge,
    GraphModel,
    ReferenceRole,
    UnresolvedReference,
    build_graph_model,
    canonical_rotation,
    ledger_sort_key,
)
from gebra.verify.guards import (
    BOUND_DIRECTIONS,
    CMP_OPS,
    RESERVED_WORDS,
    BoundDirection,
    BoundedComparison,
    CounterQualification,
    GuardClassification,
    GuardGate,
    QualificationOutcome,
    RecognizedGuard,
    classify_guard,
    is_integer_compatible,
    qualify_counter_guard,
    recognize_bounded_comparison,
)
from gebra.verify.locations import (
    AnyLocation,
    CycleLocation,
    DataflowLocation,
    DeterminismNodeLocation,
    EdgeLocation,
    GuardEdgeLabels,
    Location,
    NodeLocation,
    P01EdgeLocation,
    P02CycleLocation,
    P02SccLocation,
    P06NodeLocation,
    PathLocation,
    SccLocation,
    StateKeyLocation,
)
from gebra.verify.properties.dataflow_completeness import check_dataflow_completeness
from gebra.verify.properties.determinism_replay import check_determinism_replay
from gebra.verify.properties.effect_safety import check_effect_safety
from gebra.verify.properties.graph_well_formed import check_graph_well_formed
from gebra.verify.properties.termination_witness import (
    StrictPromotion,
    check_termination_witness,
    strict_promotions,
)
from gebra.verify.registry import (
    NON_WEDGE_SLUGS,
    PROPERTY_REGISTRY,
    PROPERTY_SLUGS,
    WEDGE_SLUGS,
    NotImplementedMarker,
    NotImplementedStatus,
    PropertyArity,
    PropertyEntry,
    PropertyRegistryError,
    PropertyScope,
    Validator,
    is_implemented,
    not_implemented,
    property_entry,
    register_validator,
    run_property,
    unregister_validator,
    validator_for,
)
from gebra.verify.report import (
    Advisory,
    AnyFailure,
    CoFailure,
    Failure,
    P04Failure,
    PropertyReport,
    validate_failure,
    validate_location,
    validate_report,
    validate_witness,
)
from gebra.verify.run import (
    IN_PROCESS_SOURCE,
    PROMOTION_ORIGINS,
    REPORT_FORMAT,
    STRICT_ALL,
    STRICT_OFF,
    TOPOLOGY_SLUGS,
    GateOutcome,
    Promotion,
    PromotionOrigin,
    PropertyOutcome,
    RunPolicy,
    RunReport,
    RunReportModel,
    SeverityCounts,
    StrictPolicy,
    Subject,
    SubjectRef,
    Tool,
    ToolError,
    anchor_location,
    verify,
)
from gebra.verify.witnesses import (
    CounterGuardSource,
    CycleCensus,
    DataflowCoverage,
    DataflowWitness,
    DeterminismClaim,
    DeterminismWitness,
    DischargeScope,
    EffectSafetyWitness,
    GuardEdgeRef,
    P06EffectRecord,
    RecursionLimitDecl,
    RecursionLimitSource,
    Region,
    TerminationWitness,
    VariantDecl,
    VariantSource,
    WellFormednessWitness,
    Witness,
    WitnessElement,
    WitnessInventoryEntry,
    WitnessNote,
    WitnessNoteKind,
    WitnessSource,
)

__all__ = [
    "BOUND_DIRECTIONS",
    "CMP_OPS",
    "CONDITION_IDS",
    "CONDITION_REGISTRY",
    "EMITTABLE_CONDITION_IDS",
    "END",
    "END_VERTEX",
    "IN_PROCESS_SOURCE",
    "NON_WEDGE_SLUGS",
    "PROMOTION_ORIGINS",
    "PROPERTY_REGISTRY",
    "PROPERTY_SLUGS",
    "PROPOSED_CONDITION_IDS",
    "RATIFIED_CONDITION_IDS",
    "REPORT_FORMAT",
    "RESERVED_CONDITION_IDS",
    "RESERVED_WORDS",
    "SENTINEL_VERTICES",
    "START",
    "START_VERTEX",
    "STRICT_ALL",
    "STRICT_OFF",
    "TOPOLOGY_SLUGS",
    "UNREGISTERED_CORPUS_STRINGS",
    "WEDGE_SLUGS",
    "Advisory",
    "AdvisoryCarriageError",
    "AnyFailure",
    "AnyLocation",
    "BoundDirection",
    "BoundedComparison",
    "ClaimClass",
    "CoFailure",
    "Components",
    "ConditionEntry",
    "ConditionId",
    "ConditionOwnershipError",
    "ConditionRegistryError",
    "ConditionTier",
    "CounterGuardSource",
    "CounterQualification",
    "CycleCensus",
    "CycleLocation",
    "DataflowCoverage",
    "DataflowLocation",
    "DataflowWitness",
    "DeterminismClaim",
    "DeterminismNodeLocation",
    "DeterminismWitness",
    "DischargeScope",
    "DisplayNodeRef",
    "EdgeKind",
    "EdgeLocation",
    "EdgeOrigin",
    "EffectSafetyWitness",
    "ExpandedEdge",
    "Failure",
    "GateOutcome",
    "GraphModel",
    "GuardClassification",
    "GuardEdgeLabels",
    "GuardEdgeRef",
    "GuardGate",
    "Location",
    "NodeId",
    "NodeLocation",
    "NonEmittableConditionError",
    "NotImplementedMarker",
    "NotImplementedStatus",
    "P01EdgeLocation",
    "P02CycleLocation",
    "P02SccLocation",
    "P04Failure",
    "P06EffectRecord",
    "P06NodeLocation",
    "PathLocation",
    "Promotion",
    "PromotionOrigin",
    "PropertyArity",
    "PropertyEntry",
    "PropertyId",
    "PropertyOutcome",
    "PropertyRegistryError",
    "PropertyReport",
    "PropertyScope",
    "PropertySlug",
    "QualificationOutcome",
    "RecognizedGuard",
    "RecursionLimitDecl",
    "RecursionLimitSource",
    "ReferenceRole",
    "Region",
    "ReportModel",
    "RunPolicy",
    "RunReport",
    "RunReportModel",
    "SccLocation",
    "SetCompared",
    "Severity",
    "SeverityCounts",
    "StateKeyLocation",
    "StrictPolicy",
    "StrictPromotion",
    "Subject",
    "SubjectRef",
    "TerminationWitness",
    "Tool",
    "ToolError",
    "UnregisteredConditionError",
    "UnresolvedReference",
    "Validator",
    "VariantDecl",
    "VariantSource",
    "WellFormednessWitness",
    "Witness",
    "WitnessElement",
    "WitnessInventoryEntry",
    "WitnessNote",
    "WitnessNoteKind",
    "WitnessSource",
    "anchor_location",
    "build_graph_model",
    "canonical_rotation",
    "check_dataflow_completeness",
    "check_determinism_replay",
    "check_effect_safety",
    "check_graph_well_formed",
    "check_termination_witness",
    "classify_guard",
    "condition",
    "conditions_for",
    "emit_advisory",
    "emit_co_failure",
    "emit_failure",
    "emittable_condition",
    "from_display",
    "is_emittable",
    "is_implemented",
    "is_integer_compatible",
    "is_registered",
    "json_text",
    "ledger_sort_key",
    "models_equivalent",
    "not_implemented",
    "property_entry",
    "property_for_condition",
    "qualify_counter_guard",
    "recognize_bounded_comparison",
    "register_validator",
    "run_property",
    "set_compared_fields",
    "strict_promotions",
    "to_data",
    "to_display",
    "to_json",
    "unregister_validator",
    "validate_failure",
    "validate_location",
    "validate_report",
    "validate_witness",
    "validator_for",
    "verify",
]
