"""The frozen pydantic base shared by every ``.gebra/`` store document model.

Normative authority: IR-SPEC §4.1 draws the line these models sit on the far side of. "The
**core IR** is everything specified in §2–§3: it is the hash scope of §6 … The **envelope**
is snapshot metadata wrapped *around* the core IR by ``gebra snapshot`` — outside the model,
outside the hash scope." §4.1 fixes the three envelope field names and gives their semantics
to brief D-11; PD-012 (ratified 2026-07-31) is where D-11's track spent that latitude, and
:mod:`gebra.store.models` is what PD-012 rules.

**Why this is a sibling of** :class:`~gebra.ir.base.IRModel` **rather than a subclass.**
``IRModel`` is documented as the base "shared by every ``ir_version`` 1.0 model", and the
envelope is explicitly *not* an ``ir_version`` 1.0 model — subclassing would put store
documents inside a version scope that governs the hash and the frozen §2 field set, so a
future ``ir_version`` bump would reach the store, and a store-layout change would look like
an IR change. The conventions are the same (A6 PC-1/PC-3/PC-4/PC-6); the version scope is
not. :class:`~gebra.verify.base.ReportModel` sits in the same relation for the same reason.

The store's own format version is :attr:`~gebra.store.models.StoreMeta.store_version`, which
is independent of ``ir_version`` on purpose: the layout can evolve without an IR-format bump,
and an IR-format bump does not restate the layout.

Nothing in this module imports langgraph, opens a socket, or executes anything (WA-07).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

__all__ = ["StoreModel"]


class StoreModel(BaseModel):
    """Normative base for every ``.gebra/`` store document model (PD-012; A6 PC-1/PC-3)."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        strict=True,
        populate_by_name=True,
    )

    @classmethod
    def model_construct(cls, _fields_set: set[str] | None = None, **values: Any) -> Any:
        """Refuse construction that skips validation (A6 PC-6).

        Raises:
            NotImplementedError: always. Build store documents through validation —
                ``model_validate`` / ``model_validate_json``, or
                :func:`~gebra.store.serialization.load_snapshot` /
                :func:`~gebra.store.serialization.load_meta` — or the constructor. All of
                them run the validators carrying the invariants the store relies on: a
                version label that is safe as a file name, a digest in the rendered §6.1
                step-8 form, and a ``current`` pointer that names a version the history
                actually holds.
        """
        raise NotImplementedError(
            f"{cls.__name__}.model_construct() is banned for the .gebra/ store models "
            "(PD-012, memo A6 PC-6): it skips validation, and with it the file-name "
            f"safety and history invariants. Use {cls.__name__}.model_validate(), "
            f".model_validate_json(), or the constructor."
        )
