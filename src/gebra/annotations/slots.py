"""The two closed vocabularies of ANNOTATION-API-SPEC §1, defined once.

§1 closes two sets, and both are load-bearing well beyond the decorator surface:

* **The nine annotatable slots.** "Exactly nine node-annotation slots (ledger §3) are
  settable through this spec's surfaces, and the decorator (§1) and sidecar (§2) share the
  set byte-for-byte". Everything else a node contract can carry is "extracted or computed,
  never annotated" — ``retry_policy`` is projected from the builder, ``prompt_digest`` /
  ``config_digest`` are extractor-computed, ``runtime.interrupts`` /
  ``runtime.checkpointer`` are compile-surface reads, and ``source`` / ``map`` belong to the
  parked data-isolation track (D-017).
* **The five effect tags.** The decision D-011 vocabulary
  ``{network, write, external, irreversible, billable}``; "an unknown tag is an error" on the
  decorator surface (§1) and a rejected tag with an ``annotation-invalid`` warning on the
  sidecar surface (§2).

They live here, in a module that imports nothing, because three lanes read them and the
import graph only runs one way: the decorators (§1, this package), the sidecar loader and
inference (§2/§4, this package), and the warning taxonomy of
:mod:`gebra.extraction.warnings`, whose ANNOTATION §5 grade lookup is quantified over
exactly this slot set. :mod:`gebra.extraction` imports the substrate, so it can be a
consumer of this package but never a supplier to it.

Slots are spelled with their **IR** names (ledger §3) rather than the decorator argument
names — ``reads``→``input``, ``writes``→``output``, ``effects``→``effect`` — because the
(node id, slot) pair of §5 is what validators run against the serialized IR.

:class:`SlotGrade` is here for the same one-definition reason. It is §5's declared-vs-heuristic
line, and both sides need it: :func:`gebra.extraction.warnings.slot_grade` *reads* a grade off
the envelope's warnings, while :mod:`gebra.annotations.inference` *produces* the two heuristic
grades §4 defines. A second enumeration in the annotation package would be one line of the
spec written twice.

Nothing here imports langgraph, opens a socket, or executes anything (WA-07).
"""

from __future__ import annotations

from enum import Enum
from typing import Final, Literal, TypeAlias

__all__ = ["ANNOTATION_SLOTS", "EFFECT_TAGS", "AnnotationSlot", "SlotGrade"]

#: The nine node-annotation slots ANNOTATION §1 calls "the closed annotatable-slot set".
AnnotationSlot: TypeAlias = Literal[
    "input",
    "output",
    "effect",
    "pure",
    "idempotent",
    "deterministic",
    "args_schema",
    "variant",
    "compensation",
]

#: :data:`AnnotationSlot`'s members, for iteration and membership tests. The order is the
#: order §1 writes them in, so a reader can check the set off against the spec line by line;
#: nothing downstream depends on it (canonical serialization sorts).
ANNOTATION_SLOTS: Final[tuple[AnnotationSlot, ...]] = (
    "input",
    "output",
    "effect",
    "pure",
    "idempotent",
    "deterministic",
    "args_schema",
    "variant",
    "compensation",
)

#: The closed decision D-011 effect vocabulary (ANNOTATION §1, §2). Adding a tag is a
#: decision, not a code change.
#:
#: It closes the *declaration surfaces* — the decorator (§1) and the sidecar (§2) — and not
#: the IR field: IR-SPEC §2.3 types ``effect`` as the D-011 vocabulary "plus declared
#: free-form tags", which is what keeps a 0.1-era fixture loadable, so
#: :class:`gebra.ir.models.Annotations` deliberately leaves it unconstrained. Propagating
#: this set into that model would be an IR-SPEC §2.3 defect, not a tidy-up.
EFFECT_TAGS: Final[frozenset[str]] = frozenset(
    {"network", "write", "external", "irreversible", "billable"}
)


class SlotGrade(str, Enum):
    """How a resolved contract slot came to hold its value (ANNOTATION §5).

    §5 draws one line — declared-grade or heuristic-grade — and §4 names the two heuristic
    origins separately, so the grade keeps them apart: a reader who only needs the §5 line
    asks :attr:`heuristic`, and one who needs to say *why* has it.
    """

    DECLARED = "declared"
    """No ``contract-inferred``/``contract-defaulted`` warning names the pair (§5)."""

    INFERRED = "inferred"
    """A ``contract-inferred`` warning names the pair — a §4 closed pattern licensed it."""

    DEFAULTED = "defaulted"
    """A ``contract-defaulted`` warning names the pair — the D-011 conservative default."""

    @property
    def heuristic(self) -> bool:
        """The §5 line: everything that is not declared-grade is heuristic-grade."""
        return self is not SlotGrade.DECLARED
