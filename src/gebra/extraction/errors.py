"""The typed extraction error — the object-boundary refusal of INTROSPECTION-SPEC §2.

The §2 error posture, in one sentence: extraction fails **hard at the object boundary and
softly inside it**. An object that is not one of the three families "MUST raise a typed
``ExtractionError`` naming the object type — never return a silent partial IR", while a
*supported* object containing constructs extraction cannot map "extracts with warnings
instead: partial honesty inside the IR, hard failure only at the object boundary". So
everything in this module is a boundary refusal; everything inside the boundary is an
:class:`~gebra.extraction.warnings.ExtractionWarning`, and the two are never traded for one
another.

**Why one class with a reason code**, rather than a hierarchy of exception types: the
refusals are one posture with several causes, and a caller that wants to branch does it on
:attr:`ExtractionError.reason` — a stable string — exactly as callers branch on
:class:`~gebra.ir.identity.NodeIdErrorReason` and
:class:`~gebra.ir.serialization.IRSerializationErrorReason`. It subclasses :class:`Exception`
rather than ``TypeError`` or ``ValueError`` on purpose: two of the reasons are about the
*type* handed in and two are about its *content*, so either builtin base would be wrong half
the time.

Nothing here imports langgraph, opens a socket, or executes anything (WA-07).
"""

from __future__ import annotations

from enum import Enum

from gebra.extraction.base import ObjectFamily, type_identity

__all__ = ["ExtractionError", "ExtractionErrorReason"]


class ExtractionErrorReason(str, Enum):
    """Why extraction refused an object at the boundary — a stable code to branch on.

    The first three are the §2 error posture; the next two are facts about this build rather
    than about the object; the last two are facts about the object that no build will carry.

    Attributes:
        UNSUPPORTED_OBJECT: The object is none of the three families — a raw dict, a
            non-``Runnable`` callable, a string (§2 "Error posture").
        NO_EXTRACTABLE_SURFACE: A Pregel-protocol object with neither a ``.builder``
            backreference nor a usable ``get_graph()`` — §2 dispatch's "no usable surface
            at all" branch. Listed by §2 under the same posture as
            :data:`UNSUPPORTED_OBJECT` and separated here because the fix is a different
            one.
        EMPTY_NODE_SET: The §2 degenerate-input rule's single boundary exception — "a
            builder with an empty ``.nodes`` dict has no extractable content and cannot
            satisfy the IR's ``nodes`` minItems 1 (IR-SPEC §2.1)". Every *other* degenerate
            shape extracts instead — with a warning where the wiring is genuinely undeclared,
            and warning-free where it is declared in a form ``entry``/``finish`` do not carry
            (DEC-18) — because well-formedness verdicts are P-01's and never ``extract()``'s.
        EXTRACTOR_NOT_REGISTERED: The object is a supported family and this build carries no
            extraction path for it yet. Not a §2 posture — a spec-supported object is never
            "unsupported" — but a refusal all the same, because the alternative is a partial
            IR and §2 forbids exactly that.
        CONSTRUCT_NOT_CARRIED: The object's family *is* carried, but it declares a construct
            whose ir 1.0 form this build cannot write — either because the rules that decide
            that form are a later card, or because the form itself is a pending ruling. The
            same reasoning as :data:`EXTRACTOR_NOT_REGISTERED`, one level in: a caller can do
            nothing about it either way, so the two share a message shape and differ only in
            what the message names.
        UNREPRESENTABLE_NODE_ID: A declared name has no node id under the IR-SPEC §5.1
            grammar — the substrate admits an empty node name, and no grammar admits ``""``.
            Unlike the two refusals above this is not about the build: no future version
            carries it, and the fix is to rename the node.
        LABEL_COLLISION: Two declared routing labels resolve to one ``path_map`` key —
            distinct source strings sharing one NFC normal form (IR-SPEC §6.3 puts labels
            in the NFC identifier role, so both authored spellings name the same key).
            Like :data:`UNREPRESENTABLE_NODE_ID` this is a fact about the object, never
            the build: no version can carry two identical ``dict[str, str]`` keys, a merge
            would silently drop a declared edge from ``graph_version`` (the partial IR §2
            forbids), and the fix is to rename one label (ruled — DEC-32: a collision is
            an error, never a merge).
    """

    UNSUPPORTED_OBJECT = "unsupported-object"
    NO_EXTRACTABLE_SURFACE = "no-extractable-surface"
    EMPTY_NODE_SET = "empty-node-set"
    EXTRACTOR_NOT_REGISTERED = "extractor-not-registered"
    CONSTRUCT_NOT_CARRIED = "construct-not-carried"
    UNREPRESENTABLE_NODE_ID = "unrepresentable-node-id"
    LABEL_COLLISION = "label-collision"


class ExtractionError(Exception):
    """Extraction refused an object at the boundary — never a silent partial IR (§2).

    Attributes:
        reason: The :class:`ExtractionErrorReason` code — match on this, not on the message.
        object_type: The refused object's type, as ``"<top-level package>:<qualname>"``.
            §2 requires the error to name the object type; this is that name, in the
            identity spelling of :func:`~gebra.extraction.base.type_identity`.
        family: The object family the refusal happened in, when classification got that far
            — set wherever classification reached a family (the builder-path refusals
            included), ``None`` for the two refusals that *are* a failure to classify.
    """

    def __init__(
        self,
        message: str,
        *,
        reason: ExtractionErrorReason,
        object_type: str,
        family: ObjectFamily | None = None,
    ) -> None:
        super().__init__(message)
        self.reason = reason
        self.object_type = object_type
        self.family = family

    @classmethod
    def for_object(
        cls,
        workflow: object,
        message: str,
        *,
        reason: ExtractionErrorReason,
        family: ObjectFamily | None = None,
    ) -> ExtractionError:
        """Build the error for ``workflow``, naming its type as §2 requires.

        The one construction path extraction uses, so the ``object_type`` spelling can never
        drift between call sites: it is always :func:`~gebra.extraction.base.type_identity`
        of the object handed to ``extract()``.
        """
        return cls(message, reason=reason, object_type=type_identity(workflow), family=family)
