"""The extraction surface — ``gebra.extract()``, its typed error, and its envelope.

Normative authority: INTROSPECTION-SPEC (how the IR is derived from LangGraph/LCEL objects)
and ANNOTATION-API-SPEC (how contracts attach to it). The whole public surface is re-exported
here::

    from gebra.extraction import extract, ExtractionError, ExtractionEnvelope

:func:`~gebra.extraction.dispatch.extract` is the entry point; it classifies the object
(:func:`~gebra.extraction.dispatch.classify` returns that decision on its own, for callers
that only want to know which rules apply), refuses at the boundary with
:class:`~gebra.extraction.errors.ExtractionError`, and returns an
:class:`~gebra.extraction.envelope.ExtractionEnvelope` — the core IR, its provenance, and
the structured warnings of :mod:`gebra.extraction.warnings`.

**It imports and inspects; it never invokes** (INTROSPECTION §1, decisions D-018/D-023). No
extraction path calls a node function, a router, a tool or ``Runnable.invoke``; none contacts
an LLM or opens a network connection; none calls ``compile()`` on a builder handed to it. The
tripwire fixtures that hold this to account live beside each path in ``tests/extraction/``
and ``tests/test_never_invokes.py``.

**What this build carries.** The entry point, the dispatch, the boundary errors, the envelope,
and all three family paths — §3 builder, §4 compiled, §5 LCEL fragment — each wired to its
family at the bottom of this module, which is the one place the family→path table is written.
Until a family's path is registered, ``extract()`` refuses that family rather than returning a
partial IR.

The §4 path is builder-primary (DEC-06): a compiled object's topology, state schema and
per-node declarations come from §3 on the ``.builder`` backreference, and the compiled level
adds the ``runtime`` block (interrupt gates and checkpointer presence), the provenance facts ir
1.0 has no slot for (discovered subgraphs, folded ``set_node_defaults``, the error-handler map)
and the §4.2 cross-check, whose disagreements are warned and never resolved. A Pregel object
with no backreference takes the §4.3 rule-4 downgrade, warned once.

The whole ANNOTATION-API-SPEC surface is wired into that path.
:mod:`gebra.extraction.contracts` walks §6's wrapper chain to the node's declared contract,
reads a LangChain tool's ``args_schema`` as the tool-carried tier, hands §4's engine the
innermost callable, and runs the §3 precedence chain over the four contributions — so a node's
``annotations`` is now the resolved contract, its conflicts and repairs ride the envelope as
``annotation-conflict``/``annotation-invalid``, and every heuristic slot is named by its
``contract-inferred``/``contract-defaulted`` record, which is what makes §5's grade lookup
answerable. The §2 sidecar is still resolved and validated exactly once per ``extract()``
call, at the entry point, and its entries are the chain's tier-3 contribution.

The §5 path stitches an LCEL ``Runnable`` handed straight to ``extract()`` into synthetic-token
node ids (``%seq[0]``, ``%map[docs]``) over the closed IR-SPEC §5.2 vocabulary, reading the
composition from attributes only — it never calls ``get_graph()``, so the run-dependent uuid
ids §5 rule 2 forbids are never constructed. A stitched lambda takes §5 rule 5's D-011 default
with its ``opaque-lambda`` record. Fragment discovery *inside* a ``StateGraph`` node is not
wired: §3 reads ``StateNodeSpec.runnable`` for contract attachment and for digests, not for
composition.

:mod:`gebra.extraction.digests` is the §7.4 rule set (ratified — DEC-15), wired into both
paths that have a bound object to read: a node whose own object is a prompt template carries
``prompt_digest``, one whose own object is a model carries ``config_digest``, and neither is
ever aggregated onto a parent. **Bodies never enter the IR** — the slots carry a
``"sha256:<hex>"`` fingerprint of a spec-fixed projection and nothing else — which is what lets
an edit to a prompt move ``graph_version`` the way an edit to an edge does, without the IR
becoming a copy of the prompt. A model inside ``model.bind(tools=…)`` is one of those carriers:
:mod:`gebra.extraction.stock` enumerates the stock langchain-core binding subclasses §7.4 (a) as
amended by DEC-21 admits by exact type, so the tool overlay reaches ``config_digest`` and a
tool-set edit moves ``graph_version`` too. Every other ``RunnableBinding`` subclass stays
declined and says so.
"""

from gebra.extraction.base import ExtractionModel, ObjectFamily, type_identity
from gebra.extraction.builder import extract_builder
from gebra.extraction.compat import (
    CompatClass,
    GebraVersionWarning,
    SubstrateVersions,
    VersionCheck,
    check_version_once,
    classify_substrate,
    out_of_range_warning,
    read_installed_versions,
)
from gebra.extraction.compiled import extract_compiled
from gebra.extraction.contracts import (
    WRAPPER_MEMBERS,
    CarrierRule,
    Declarations,
    NodeContracts,
    resolve_node,
    state_schema_of,
    walk,
)
from gebra.extraction.digests import (
    UNREPRESENTABLE,
    NodeDigests,
    PromptGap,
    coerce,
    config_form,
    digests_for,
    prompt_form,
)
from gebra.extraction.dispatch import (
    Dispatch,
    Extractor,
    classify,
    extract,
    extractor_for,
    register_extractor,
    unregister_extractor,
)
from gebra.extraction.envelope import (
    CompiledSurfaces,
    CrossCheck,
    ExtractedFrom,
    ExtractionEnvelope,
    FoldedDefault,
    to_data,
    to_json,
)
from gebra.extraction.errors import ExtractionError, ExtractionErrorReason
from gebra.extraction.inference import FINDING_CODES, contract_warnings
from gebra.extraction.lcel import (
    FRAGMENT_CLASSES,
    FragmentKind,
    FragmentReading,
    extract_lcel_fragment,
    kind_of,
    stitch_fragment,
)
from gebra.extraction.sidecar import load_sidecar, sidecar_warnings, unknown_node_warnings
from gebra.extraction.state import (
    UNREPRESENTABLE_REDUCER,
    UNREPRESENTABLE_TYPE,
    StateReading,
    read_state,
)
from gebra.extraction.stock import (
    ADMITTED_BINDING_CLASSES,
    STOCK_BINDING_NAMES,
    STOCK_BINDING_SUBCLASSES,
    is_binding,
)
from gebra.extraction.warnings import (
    ANNOTATION_SLOTS,
    HEURISTIC_GRADE_CODES,
    WARNING_RULES,
    AnnotationSlot,
    ExtractionWarning,
    ExtractionWarningCode,
    SlotGrade,
    WarningRule,
    slot_grade,
    warning_rule,
)

__all__ = [
    "ADMITTED_BINDING_CLASSES",
    "ANNOTATION_SLOTS",
    "FINDING_CODES",
    "FRAGMENT_CLASSES",
    "HEURISTIC_GRADE_CODES",
    "STOCK_BINDING_NAMES",
    "STOCK_BINDING_SUBCLASSES",
    "UNREPRESENTABLE",
    "UNREPRESENTABLE_REDUCER",
    "UNREPRESENTABLE_TYPE",
    "WARNING_RULES",
    "WRAPPER_MEMBERS",
    "AnnotationSlot",
    "CarrierRule",
    "CompatClass",
    "CompiledSurfaces",
    "CrossCheck",
    "Declarations",
    "Dispatch",
    "ExtractedFrom",
    "ExtractionEnvelope",
    "ExtractionError",
    "ExtractionErrorReason",
    "ExtractionModel",
    "ExtractionWarning",
    "ExtractionWarningCode",
    "Extractor",
    "FoldedDefault",
    "FragmentKind",
    "FragmentReading",
    "GebraVersionWarning",
    "NodeContracts",
    "NodeDigests",
    "ObjectFamily",
    "PromptGap",
    "SlotGrade",
    "StateReading",
    "SubstrateVersions",
    "VersionCheck",
    "WarningRule",
    "check_version_once",
    "classify",
    "classify_substrate",
    "coerce",
    "config_form",
    "contract_warnings",
    "digests_for",
    "extract",
    "extract_builder",
    "extract_compiled",
    "extract_lcel_fragment",
    "extractor_for",
    "is_binding",
    "kind_of",
    "load_sidecar",
    "out_of_range_warning",
    "prompt_form",
    "read_installed_versions",
    "read_state",
    "register_extractor",
    "resolve_node",
    "sidecar_warnings",
    "slot_grade",
    "state_schema_of",
    "stitch_fragment",
    "to_data",
    "to_json",
    "type_identity",
    "unknown_node_warnings",
    "unregister_extractor",
    "walk",
    "warning_rule",
]

# The family→path table. Registration lives here rather than at the bottom of each path
# module so that importing a path is not what wires it: the wiring is one readable block,
# and a reviewer answering "which families does this build carry?" reads exactly these lines.
register_extractor(ObjectFamily.BUILDER, extract_builder)
register_extractor(ObjectFamily.COMPILED, extract_compiled)
register_extractor(ObjectFamily.LCEL, extract_lcel_fragment)
