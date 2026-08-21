"""Shallow inference as extraction sees it — ANNOTATION-API-SPEC §4.

:mod:`gebra.annotations.inference` owns the engine: the closed pattern table, the D-011
defaults, and the per-node findings that account for every slot it fills. This module is the
seam between that engine and an extraction, and it does the one thing the engine cannot —
turn a :class:`~gebra.annotations.inference.InferenceFinding` into a record of the single
warnings taxonomy (INTROSPECTION §8 / ANNOTATION §4), which lives in this package because
this package imports langgraph and the dependency between the annotation surface and the
extractor runs one way only.

The conversion adds exactly two things: the taxonomy code, which follows from §5's grade, and
the **node id**, which is an extraction concept — the engine reads a callable and has never
heard of the escaped path identity the node is filed under. Everything else the §4 registry
rows ask for is already on the finding, which is why the mapping below is four lines rather
than a second interpretation of the "what it carries" column.

**Which code, and the one substitution this module does not make.** §5's two heuristic grades
are the two codes: an inferred slot is ``contract-inferred`` and a defaulted one is
``contract-defaulted``. INTROSPECTION §8's ``contract-defaulted`` row adds that "for stitched
lambdas, ``opaque-lambda`` below is emitted instead and carries the default" — that record is
:mod:`gebra.extraction.lcel`'s to add, since it is the only caller that can know a node is a
*stitched* lambda. It adds rather than replaces, so what this module produces is unchanged
either way — which is the shape DEC-20 ratified when it amended §8's row from
"instead" to "in addition"; the reasoning is in that module.

**What resolves these into an IR.** §3's per-slot precedence chain decides what an inferred
value wins against, and :mod:`gebra.extraction.contracts` is where the two meet: it hands §4's
engine the innermost callable and turns what comes back into these records, so a warning naming
a node always names one whose ``annotations`` carry the slot it grades.

Nothing here executes anything (WA-07): it reads an inference and builds records.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from gebra.annotations.slots import SlotGrade
from gebra.extraction.warnings import ExtractionWarning, ExtractionWarningCode

if TYPE_CHECKING:
    from collections.abc import Mapping

    from gebra.annotations.inference import Inference

__all__ = ["FINDING_CODES", "contract_warnings"]

#: §5's two heuristic grades → the two §4 registry rows. The third grade, ``declared``, is the
#: *absence* of a record here, which is why :class:`~gebra.annotations.inference.InferenceFinding`
#: refuses to carry it and this table has two rows rather than three.
FINDING_CODES: Final[Mapping[SlotGrade, ExtractionWarningCode]] = {
    SlotGrade.INFERRED: ExtractionWarningCode.CONTRACT_INFERRED,
    SlotGrade.DEFAULTED: ExtractionWarningCode.CONTRACT_DEFAULTED,
}


def contract_warnings(node: str, inference: Inference) -> tuple[ExtractionWarning, ...]:
    """One §4 warning per finding, naming ``node`` — inferred first, defaulted second.

    Args:
        node: The node id in its escaped IR-SPEC §5 form. It is the first half of §5's
            (node id, slot) lookup key, so it is what makes the record actionable: "a slot on
            node *n* is declared-grade **iff** no ``contract-inferred``/``contract-defaulted``
            warning in the extraction envelope names the (node id, slot) pair".
        inference: What :func:`gebra.annotations.inference.infer` produced for that node.

    Returns:
        The records, in the engine's own order. Every slot the inference filled is named by
        exactly one of them, which is §4's "every inferred slot carries a ``contract-inferred``
        warning" and its D-011 counterpart, made checkable by
        :func:`gebra.extraction.warnings.slot_grade`.
    """
    return tuple(
        ExtractionWarning(
            code=FINDING_CODES[finding.grade],
            message=finding.message,
            node=node,
            slots=finding.slots,
            detail=dict(finding.detail),
        )
        for finding in inference.findings
    )
