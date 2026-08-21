"""``GebraContractError`` — the decoration-time refusal of ANNOTATION-API-SPEC §1.

§1 puts the annotation surface's *errors* in exactly one place: "Decoration-time consistency
rules (violations raise ``GebraContractError`` at import time — cheap, early, never at
extraction)". Everything else on the annotation surface degrades instead: the sidecar's
validation is warning-grade "because the sidecar is config and extraction stays total" (§2),
the cross-surface precedence conflicts are warnings (§3, DEC-07), and even a resolved contract
that violates a §1 invariant across surfaces is repaired-with-a-warning rather than raised
(§3). So this exception says something narrow and specific: **one author's own decorator
stack contradicts itself**, and "a single author's stack has no drift to excuse".

Where it is raised is part of the meaning. A decorator runs when the defining module is
imported, so a violation surfaces at ``import my_agent``, before any graph is built and long
before ``gebra.extract()`` — which is the whole point of §1 putting these four rules here
rather than in the resolved-contract pass.

**Why one class with a reason code**, rather than a hierarchy: the same reasoning
:mod:`gebra.extraction.errors` records for :class:`~gebra.extraction.errors.ExtractionError`.
The refusals are one posture with several causes, and a caller that wants to branch does it
on :attr:`GebraContractError.reason` — a stable string — exactly as callers branch on
:class:`~gebra.ir.identity.NodeIdErrorReason`. It subclasses :class:`Exception` rather than
``TypeError`` or ``ValueError`` because the causes are split between the two: a duplicate
slot is neither a wrong type nor a bad value.

Nothing here imports langgraph, opens a socket, or executes anything (WA-07).
"""

from __future__ import annotations

from enum import Enum

__all__ = ["ContractErrorReason", "GebraContractError"]


class ContractErrorReason(str, Enum):
    """Why decoration was refused — a stable code to branch on.

    The first four are the four §1 consistency rules, one code each, so that "each rule
    raises" is a checkable statement rather than a shared code with a variable message. The
    last three are refusals of a *shape* the surface does not have: a slot that is not one
    of the nine, a value that is not of the slot's kind, and a target that cannot carry the
    attribute at all.

    Attributes:
        DUPLICATE_SLOT: A slot was set twice across one decorator stack. §1: "Each slot is
            settable **at most once** across a decorator stack; a duplicate slot assignment
            is an error, not a merge — **regardless of value, identical duplicates
            included**." Deliberately stricter than §3's cross-surface rule, where identical
            values are not a conflict.
        PURE_EFFECT_EXCLUSIVE: ``pure=True`` and a non-empty ``effects`` were both declared
            (decision D-011). Checked over the whole stack, so declaring them through two
            different decorators is caught the same way as declaring both at once.
        UNKNOWN_EFFECT_TAG: An ``effects`` tag outside the closed D-011 vocabulary
            :data:`~gebra.annotations.slots.EFFECT_TAGS`. §1: "an unknown tag is an error".
        DETERMINISTIC_SEED_REQUIRED: The ``deterministic`` object form was used without
            ``seed``. §1 names the case outright: "``@gebra.deterministic(temperature=0.0)``
            without ``seed=`` raises at decoration time"; the frozen ledger §3 shape
            ``{seed: int, temperature?: number}`` owns the ruling.
        UNKNOWN_SLOT: A keyword that is not one of the nine annotatable slots — a typo, or
            one of the slots §1 puts out of annotation reach ("extracted or computed, never
            annotated").
        SLOT_VALUE_INVALID: A slot's value is not of that slot's kind — a bare string where
            a sequence of state keys is meant, a non-string effect tag, an ``args_schema``
            that is not a JSON object.
        ATTACHMENT_IMPOSSIBLE: The target cannot carry ``__gebra_contract__`` at all — a
            slotted or frozen object, a ``functools.partial``. §6 names this case and names
            its answer: "the **sidecar is the designated fallback**".
    """

    DUPLICATE_SLOT = "duplicate-slot"
    PURE_EFFECT_EXCLUSIVE = "pure-effect-exclusive"
    UNKNOWN_EFFECT_TAG = "unknown-effect-tag"
    DETERMINISTIC_SEED_REQUIRED = "deterministic-seed-required"
    UNKNOWN_SLOT = "unknown-slot"
    SLOT_VALUE_INVALID = "slot-value-invalid"
    ATTACHMENT_IMPOSSIBLE = "attachment-impossible"


class GebraContractError(Exception):
    """A decorator stack contradicts itself — raised at import time (§1).

    Attributes:
        reason: The :class:`ContractErrorReason` code — match on this, not on the message.
        slot: The annotation slot the refusal is about, as its IR name, or ``None`` for a
            refusal that is not about one slot (an unknown keyword, an unattachable target).
    """

    def __init__(
        self, message: str, *, reason: ContractErrorReason, slot: str | None = None
    ) -> None:
        super().__init__(message)
        self.reason = reason
        self.slot = slot
