"""IR models for ``ir_version`` 1.0/1.1 — normative authority IR-SPEC (frozen 2026-07-18,
DEC-09; the 1.1 edge kind ratified 2026-08-09, DEC-28).

The whole model surface is re-exported here::

    from gebra.ir import WorkflowIR

:class:`~gebra.ir.models.WorkflowIR` is the entry point; :data:`~gebra.ir.models.Edge` is
the kind-discriminated edge union; :class:`~gebra.ir.base.IRModel` is the frozen,
``extra="forbid"``, strict base every model shares.

The node-identity grammar of IR-SPEC §5 lives in :mod:`gebra.ir.identity` and is re-exported
alongside the models: :func:`~gebra.ir.identity.node_id_from_names` and
:func:`~gebra.ir.identity.synthetic_segment` build ids, :func:`~gebra.ir.identity.parse_node_id`
and :func:`~gebra.ir.identity.openinference_attributes` read them.

Canonical serialization and the content hash of IR-SPEC §6 live in :mod:`gebra.ir.canonical`:
:func:`~gebra.ir.canonical.canonical_bytes` emits the RFC 8785 canonical form,
:func:`~gebra.ir.canonical.graph_version` renders its SHA-256 digest as ``"sha256:<hex>"``,
and :func:`~gebra.ir.canonical.verify_graph_version` recomputes and string-compares. The two
halves the ``prompt_digest``/``config_digest`` pre-pass composes with — §3.6's foreign-object
pipeline (:func:`~gebra.ir.canonical.canonical_foreign_bytes`) and the §6.1 step-7/8 digest
renderer (:func:`~gebra.ir.canonical.render_digest`) — live in the same module, so the whole
package has one JCS emitter, one number formatter and one digest renderer.

The YAML and JSON *surface* — what a file on disk holds — is :mod:`gebra.ir.serialization`:
:func:`~gebra.ir.serialization.load_yaml` and :func:`~gebra.ir.serialization.load_json`
validate text into a model, :func:`~gebra.ir.serialization.dump_yaml` and
:func:`~gebra.ir.serialization.dump_json` write it back, and
:func:`~gebra.ir.serialization.read_ir` / :func:`~gebra.ir.serialization.write_ir` do the
same for a file, choosing the format by suffix. A model reloads equal to itself through
either format; those bytes are surface bytes and are never hashed.
"""

from gebra.ir.base import IRModel
from gebra.ir.canonical import (
    I_JSON_MAX_INT,
    I_JSON_MIN_INT,
    CanonicalizationError,
    CanonicalizationErrorReason,
    canonical_annotations_bytes,
    canonical_bytes,
    canonical_foreign_bytes,
    graph_version,
    render_digest,
    verify_graph_version,
)
from gebra.ir.identity import (
    OPENINFERENCE_ID,
    OPENINFERENCE_NAME,
    OPENINFERENCE_PARENT_ID,
    RESERVED_SEGMENTS,
    SEGMENT_SEPARATOR,
    SYNTHETIC_KINDS,
    NodeId,
    NodeIdError,
    NodeIdErrorReason,
    NodeIdStr,
    Segment,
    SegmentKind,
    escape_segment,
    is_valid_node_id,
    join_node_id,
    node_id_from_names,
    openinference_attributes,
    parse_node_id,
    split_node_id,
    synthetic_segment,
    unescape_segment,
    validate_node_id,
)
from gebra.ir.models import (
    IR_VERSION,
    IR_VERSION_DYNAMIC_EDGES,
    IR_VERSIONS,
    Annotations,
    Checkpointer,
    Compensation,
    ConditionalEdge,
    DeterministicSpec,
    DynamicEdge,
    DynamicEdgeUnsupportedError,
    Edge,
    IdempotentKey,
    Interrupts,
    IrVersion,
    Node,
    NormalEdge,
    RecursionLimit,
    RetryPolicy,
    Runtime,
    SendEdge,
    StateField,
    Variant,
    WorkflowIR,
    lowest_ir_version,
    refuse_dynamic_edges,
)
from gebra.ir.serialization import (
    JSON_SUFFIXES,
    YAML_SUFFIXES,
    IRSerializationError,
    IRSerializationErrorReason,
    dump_json,
    dump_yaml,
    load_json,
    load_yaml,
    read_ir,
    write_ir,
)

__all__ = [
    "IR_VERSION",
    "IR_VERSIONS",
    "IR_VERSION_DYNAMIC_EDGES",
    "I_JSON_MAX_INT",
    "I_JSON_MIN_INT",
    "JSON_SUFFIXES",
    "OPENINFERENCE_ID",
    "OPENINFERENCE_NAME",
    "OPENINFERENCE_PARENT_ID",
    "RESERVED_SEGMENTS",
    "SEGMENT_SEPARATOR",
    "SYNTHETIC_KINDS",
    "YAML_SUFFIXES",
    "Annotations",
    "CanonicalizationError",
    "CanonicalizationErrorReason",
    "Checkpointer",
    "Compensation",
    "ConditionalEdge",
    "DeterministicSpec",
    "DynamicEdge",
    "DynamicEdgeUnsupportedError",
    "Edge",
    "IRModel",
    "IRSerializationError",
    "IRSerializationErrorReason",
    "IdempotentKey",
    "Interrupts",
    "IrVersion",
    "Node",
    "NodeId",
    "NodeIdError",
    "NodeIdErrorReason",
    "NodeIdStr",
    "NormalEdge",
    "RecursionLimit",
    "RetryPolicy",
    "Runtime",
    "Segment",
    "SegmentKind",
    "SendEdge",
    "StateField",
    "Variant",
    "WorkflowIR",
    "canonical_annotations_bytes",
    "canonical_bytes",
    "canonical_foreign_bytes",
    "dump_json",
    "dump_yaml",
    "escape_segment",
    "graph_version",
    "is_valid_node_id",
    "join_node_id",
    "load_json",
    "load_yaml",
    "lowest_ir_version",
    "node_id_from_names",
    "openinference_attributes",
    "parse_node_id",
    "read_ir",
    "refuse_dynamic_edges",
    "render_digest",
    "split_node_id",
    "synthetic_segment",
    "unescape_segment",
    "validate_node_id",
    "verify_graph_version",
    "write_ir",
]
