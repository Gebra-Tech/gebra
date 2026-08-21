"""Shared foundations of the extraction surface: the model base, the family enum, identity.

Normative authority: INTROSPECTION-SPEC §2 (object-family dispatch) and IR-SPEC §4.1 (the
core-IR/envelope split).

:func:`~gebra.naming.type_identity` is re-exported here rather than defined here: the
annotation surface needs the same §7.4 spelling and cannot import this package (importing
:mod:`gebra.extraction` imports the substrate, and EX-11 makes the dependency run the other
way), so the definition lives in the dependency-free :mod:`gebra.naming`.

**Why the envelope has its own base.** :class:`ExtractionModel` repeats the A6 conventions
that :class:`gebra.ir.base.IRModel` and :class:`gebra.verify.base.ReportModel` carry —
``frozen``, ``extra="forbid"``, ``strict``, ``model_construct()`` refused — but it is
deliberately *not* a subclass of ``IRModel``. IR-SPEC §4.1 draws the line this package sits
on: the core IR is the hash scope, and the envelope is metadata wrapped around it, "outside
the model, outside the hash scope". Inheriting from the IR base would say the opposite of
what §6.4 requires, and the digest is computed from :attr:`ExtractionEnvelope.ir
<gebra.extraction.envelope.ExtractionEnvelope.ir>` alone — so no warning, no provenance
member, and no future envelope field can move a ``graph_version``.

Nothing here imports langgraph, opens a socket, or executes anything (WA-07).
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict

from gebra.naming import type_identity

__all__ = ["ExtractionModel", "ObjectFamily", "type_identity"]


class ObjectFamily(str, Enum):
    """The three object families ``gebra.extract()`` dispatches over (INTROSPECTION §2).

    The members are the *rule sets*, not the classes: :data:`COMPILED` is "§4 rules apply"
    — reached by a ``CompiledStateGraph`` and by any other Pregel-protocol object — and it
    covers both the builder-primary reading (§4.3 rule 1) and the builderless compiled-only
    downgrade (§4.3 rule 4), which :attr:`~gebra.extraction.dispatch.Dispatch.compiled_only`
    tells apart. :data:`BUILDER` is "§3 only, compiled-level surfaces recorded absent", and
    :data:`LCEL` is "§5 fragment extraction of the whole object".
    """

    COMPILED = "compiled"
    BUILDER = "builder"
    LCEL = "lcel"


class ExtractionModel(BaseModel):
    """Normative base for the provenance-envelope models (A6 PC-1/PC-3; IR-SPEC §4.1).

    Frozen and value-compared, ``extra="forbid"`` so an unknown member is an error rather
    than silently-dropped provenance, and ``strict=True`` so nothing is coerced across
    types. One consequence to know before writing a warning by hand: under strict mode a
    ``list`` is not a ``tuple`` in Python-mode validation, so repeated members are authored
    as tuples (A6 PC-2) — parsed JSON/YAML *data* validates through
    ``model_validate_json``, the ingestion path IR-SPEC §2.5 note 4 fixes for the IR models.

    Hashability follows the IR-SPEC §2.5 note-3 caveat rather than the envelope models of
    :mod:`gebra.verify.base`: :class:`~gebra.extraction.warnings.ExtractionWarning` carries
    a ``dict``-typed ``detail``, so it is frozen but not hashable.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    @classmethod
    def model_construct(cls, _fields_set: set[str] | None = None, **values: Any) -> Any:
        """Refuse construction that skips validation (A6 PC-6).

        Raises:
            NotImplementedError: always. Build envelope models through validation —
                ``model_validate``/``model_validate_json`` — or the constructor, both of
                which run the validators carrying the taxonomy's registry-shape rules.
        """
        raise NotImplementedError(
            f"{cls.__name__}.model_construct() is banned for the extraction envelope "
            "(A6 PC-6): it skips validation, and with it the INTROSPECTION-SPEC §8 / "
            f"ANNOTATION-API-SPEC §4 registry-shape rules. Use {cls.__name__}"
            ".model_validate(), .model_validate_json(), or the constructor."
        )
