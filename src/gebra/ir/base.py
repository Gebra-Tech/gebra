"""The frozen pydantic base shared by every ``ir_version`` 1.0 model.

Normative authority: IR-SPEC §2.5, whose model stubs are the interface this package
implements, together with the memo-A6 conventions PC-1…PC-6 the spec adopts there:

* **PC-1 — one shared frozen base.** ``frozen=True``, so a validated IR is immutable and
  every model is value-compared by its fields. Hashability caveat (IR-SPEC §2.5 note 3):
  models carrying ``dict``-typed members (``args_schema``, ``path_map``, ``state``) are
  frozen but *not* hashable; only id-shaped models are used as set members or dict keys.
* **PC-2 — tuples, not lists,** for every repeated member; declared on the models
  themselves (:mod:`gebra.ir.models`).
* **PC-3 — ``extra="forbid"`` and ``strict=True``.** An unknown member is an error rather
  than silently-dropped content, and no value is coerced across types. One consequence is
  worth knowing before writing a payload by hand: under strict mode a JSON array validates
  into a ``tuple`` in JSON mode but not in Python mode, which is why IR-SPEC §2.5 note 4
  routes YAML payloads through ``model_validate_json`` over the JSON re-encoding.
* **PC-4 — canonical output serializes by alias** (``model_dump(by_alias=True)``); the one
  aliased field in 1.0 is ``from`` (IR-SPEC §2.5 note 2), so ``populate_by_name=True``
  keeps the Python-side name usable too.
* **PC-5 — schema lockstep.** ``WorkflowIR.model_json_schema()`` is meant to stay
  consistent with the ``gebra-ir`` ``$defs`` of the vendored fixture schema; the CI check
  that asserts it is its own task card.
* **PC-6 — ``model_construct()`` is banned.** It skips validation, and an IR that never
  passed validation would carry silent defects into every downstream consumer. The base
  overrides the classmethod so the ban is mechanical rather than a convention.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

__all__ = ["IRModel"]


class IRModel(BaseModel):
    """Normative base for every ``ir_version`` 1.0 model (IR-SPEC §2.5; A6 PC-1/PC-3)."""

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
            NotImplementedError: always. Build IR models through validation —
                ``model_validate``/``model_validate_json`` — or the constructor.
        """
        raise NotImplementedError(
            f"{cls.__name__}.model_construct() is banned for ir_version 1.0 models "
            "(IR-SPEC §2.5, memo A6 PC-6): it skips validation. Use "
            f"{cls.__name__}.model_validate(), .model_validate_json(), or the constructor."
        )
