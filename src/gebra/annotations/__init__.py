"""The contract-declaration surface — ANNOTATION-API-SPEC.

How an author tells gebra what a node does. The spec gives the surface four parts, and this
package is where they land::

    from gebra import contract, pure, effect, idempotent, deterministic, variant, compensation

* **§1 — decorators.** ``@gebra.contract`` and its six shorthands attach a
  :class:`~gebra.annotations.contract.NodeContract` under ``__gebra_contract__`` and return
  the decorated callable unchanged. Four consistency rules raise
  :class:`~gebra.annotations.errors.GebraContractError` at import time.
* **§2 — the ``gebra.toml`` sidecar.** :mod:`gebra.annotations.sidecar` finds the file (an
  explicit ``gebra.extract(workflow, sidecar=…)`` argument, else the nearest ``gebra.toml``
  walking from the CWD to the repository root), parses it, and validates it — all of it
  warning-grade, because "the sidecar is config and extraction stays total".
* **§4 — shallow inference.** :mod:`gebra.annotations.inference` reads a node callable's own
  AST and applies the closed DEC-08 pattern table — ``input`` and ``output`` only — falling
  to the decision D-011 conservative defaults with a finding that says why. It never yields
  ``idempotent``, ``deterministic``, ``variant``, ``compensation`` or ``args_schema``, and it
  evaluates nothing.
* **§3 — the per-slot precedence chain.** :mod:`gebra.annotations.resolve` runs the strict
  Decorator > Tool-carried > Sidecar > Inference order per slot, reports a lower tier that
  disagrees with an ``annotation-conflict`` (identical values, decided by byte-equality of
  their ledger §6 canonicalizations, are not a disagreement), and validates the *resolved*
  contract against the §1 invariants — all of it warning-grade, because extraction stays
  total. Which live object supplies each tier is the extractor's question, and
  :mod:`gebra.extraction.contracts` answers it.

**This package never imports the substrate,** and the direction is deliberate rather than
incidental: :mod:`gebra.extraction` imports langgraph to dispatch on its classes, and the
resolution step makes it a consumer of this package. Keeping the dependency one-way is
what lets ``import gebra`` — and a module that only decorates its node functions — stay free
of both the substrate and the extractor.

Nothing here imports langgraph, opens a socket, or executes anything (WA-07).
"""

from gebra.annotations.contract import (
    CONTRACT_ATTRIBUTE,
    SLOT_KEYWORDS,
    NodeContract,
    compensation,
    contract,
    deterministic,
    effect,
    idempotent,
    pure,
    read_contract,
    variant,
)
from gebra.annotations.errors import ContractErrorReason, GebraContractError
from gebra.annotations.inference import (
    DEFAULT_EFFECT,
    INFERENCE_SLOTS,
    NEVER_INFERRED,
    Blocker,
    DefaultRule,
    Inference,
    InferenceFinding,
    InferredKey,
    NodeSource,
    Pattern,
    SourceCache,
    SourceRule,
    StateSchema,
    infer,
    infer_node,
    read_node_source,
)
from gebra.annotations.resolve import (
    IDENTIFIER_SLOTS,
    PRECEDENCE,
    TIER_SLOTS,
    Contribution,
    IssueKind,
    Resolution,
    ResolutionIssue,
    ResolutionRule,
    Surface,
    carriable,
    resolve,
    slot_bytes,
    slot_data,
)
from gebra.annotations.sidecar import (
    SIDECAR_FILENAME,
    SIDECAR_SCHEMA,
    SidecarIssue,
    SidecarReading,
    SidecarRule,
    SidecarSource,
    discover_sidecar,
    read_sidecar,
    repository_root,
)
from gebra.annotations.slots import ANNOTATION_SLOTS, EFFECT_TAGS, AnnotationSlot, SlotGrade

__all__ = [
    "ANNOTATION_SLOTS",
    "CONTRACT_ATTRIBUTE",
    "DEFAULT_EFFECT",
    "EFFECT_TAGS",
    "IDENTIFIER_SLOTS",
    "INFERENCE_SLOTS",
    "NEVER_INFERRED",
    "PRECEDENCE",
    "SIDECAR_FILENAME",
    "SIDECAR_SCHEMA",
    "SLOT_KEYWORDS",
    "TIER_SLOTS",
    "AnnotationSlot",
    "Blocker",
    "ContractErrorReason",
    "Contribution",
    "DefaultRule",
    "GebraContractError",
    "Inference",
    "InferenceFinding",
    "InferredKey",
    "IssueKind",
    "NodeContract",
    "NodeSource",
    "Pattern",
    "Resolution",
    "ResolutionIssue",
    "ResolutionRule",
    "SidecarIssue",
    "SidecarReading",
    "SidecarRule",
    "SidecarSource",
    "SlotGrade",
    "SourceCache",
    "SourceRule",
    "StateSchema",
    "Surface",
    "carriable",
    "compensation",
    "contract",
    "deterministic",
    "discover_sidecar",
    "effect",
    "idempotent",
    "infer",
    "infer_node",
    "pure",
    "read_contract",
    "read_node_source",
    "read_sidecar",
    "repository_root",
    "resolve",
    "slot_bytes",
    "slot_data",
    "variant",
]
